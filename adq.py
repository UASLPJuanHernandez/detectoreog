"""
EOG Adquisición - Interfaz de captura de señales para ojo biónico
Requiere: pyserial  →  pip install pyserial
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import serial
import serial.tools.list_ports
import threading
import csv
import time
import os
from datetime import datetime
from collections import deque
import numpy as np
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# ─────────────────────────────────────────────
#  CONFIGURACIÓN
# ─────────────────────────────────────────────
CLASES        = ["reposo", "izquierda", "derecha", "arriba", "abajo", "parpadeo"]
FLECHAS       = {"reposo": "●", "izquierda": "←", "derecha": "→",
                 "arriba": "↑", "abajo": "↓", "parpadeo": "👁"}
COLORES_CLASE = {"reposo": "#4A9EFF", "izquierda": "#FF6B6B",
                 "derecha": "#FFD93D", "arriba": "#6BCB77", "abajo": "#C77DFF",
                 "parpadeo": "#FF9F43"}

TIEMPO_LINEA_BASE  = 0.3   # seg — mira al centro antes
TIEMPO_MOVIMIENTO  = 1.5   # seg — duración de captura
TIEMPO_DESCANSO    = 1.2   # seg — entre muestras
BLOQUE_DESCANSO    = 25    # muestras antes de pausa larga
PAUSA_LARGA        = 60.0  # seg — pausa entre bloques

BAUD_RATE = 115200
FS        = 200            # Hz esperados del Arduino

# ─────────────────────────────────────────────
#  PALETA
# ─────────────────────────────────────────────
BG       = "#0D0F14"
BG2      = "#151820"
BG3      = "#1E2230"
ACCENT   = "#00E5FF"
ACCENT2  = "#FF6B6B"
TEXT     = "#E8EAF0"
TEXT_DIM = "#6B7280"
SUCCESS  = "#6BCB77"
WARNING  = "#FFD93D"


# ═══════════════════════════════════════════════════════════
class EOGApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("EOG Adquisición — Ojo Biónico")
        self.geometry("960x720")
        self.minsize(860, 640)
        self.configure(bg=BG)
        self.resizable(True, True)

        # Estado
        self.ser            = None
        self.grabando       = False
        self.cancelar_flag  = False
        self.csv_writer     = None
        self.csv_file       = None
        self.muestras_totales    = {c: 0 for c in CLASES}
        self.muestras_objetivo   = 150
        self.clase_actual   = None
        self.buffer_señal   = deque([0.0] * 300, maxlen=300)   # para mini-gráfica
        self.capturando     = False
        self.captura_n      = 0
        self.captura_clase  = None

        self._build_ui()
        self._refresh_ports()
        self._tick_grafica()

    # ──────────────────────────────────────────
    #  CONSTRUCCIÓN UI
    # ──────────────────────────────────────────
    def _build_ui(self):
        self._build_header()
        content = tk.Frame(self, bg=BG)
        content.pack(fill="both", expand=True, padx=18, pady=(0, 14))
        content.columnconfigure(0, weight=2)
        content.columnconfigure(1, weight=3)
        content.rowconfigure(0, weight=1)

        self._build_panel_izq(content)
        self._build_panel_der(content)
        self._build_statusbar()

    def _build_header(self):
        h = tk.Frame(self, bg=BG2, height=56)
        h.pack(fill="x")
        h.pack_propagate(False)
        tk.Label(h, text="◉  EOG ADQUISICIÓN", font=("Courier New", 15, "bold"),
                 bg=BG2, fg=ACCENT).pack(side="left", padx=20, pady=12)
        tk.Label(h, text="Ojo Biónico  •  Clasificador de movimientos",
                 font=("Courier New", 9), bg=BG2, fg=TEXT_DIM).pack(side="left", pady=16)

    def _build_panel_izq(self, parent):
        frame = tk.Frame(parent, bg=BG)
        frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=10)

        # — Conexión Serial —
        sec = self._section(frame, "CONEXIÓN SERIAL")
        row = tk.Frame(sec, bg=BG2)
        row.pack(fill="x", pady=4)
        self.port_var = tk.StringVar()
        self.port_cb = ttk.Combobox(row, textvariable=self.port_var,
                                    width=14, state="readonly")
        self.port_cb.pack(side="left", padx=(0, 6))
        self._btn(row, "⟳", self._refresh_ports, w=3).pack(side="left", padx=(0,6))
        self.btn_conectar = self._btn(row, "Conectar", self._toggle_conexion)
        self.btn_conectar.pack(side="left")
        self.lbl_conexion = tk.Label(sec, text="● Sin conexión",
                                     font=("Courier New", 9), bg=BG2, fg=ACCENT2)
        self.lbl_conexion.pack(anchor="w", pady=(2, 6))

        # — Archivo de salida —
        sec2 = self._section(frame, "ARCHIVO CSV")
        frow = tk.Frame(sec2, bg=BG2)
        frow.pack(fill="x", pady=4)
        self.archivo_var = tk.StringVar(value="datos_eog.csv")
        tk.Entry(frow, textvariable=self.archivo_var,
                 bg=BG3, fg=TEXT, insertbackground=ACCENT,
                 relief="flat", font=("Courier New", 9), width=18).pack(side="left", padx=(0,6))
        self._btn(frow, "…", self._elegir_archivo, w=3).pack(side="left")

        # — Configuración —
        sec3 = self._section(frame, "CONFIGURACIÓN")
        grid = tk.Frame(sec3, bg=BG2)
        grid.pack(fill="x")
        tk.Label(grid, text="Muestras por clase:", font=("Courier New", 9),
                 bg=BG2, fg=TEXT_DIM).grid(row=0, column=0, sticky="w", pady=2)
        self.spin_muestras = tk.Spinbox(grid, from_=30, to=500, increment=10,
                                        width=6, bg=BG3, fg=TEXT, relief="flat",
                                        buttonbackground=BG3,
                                        font=("Courier New", 10))
        self.spin_muestras.delete(0, "end")
        self.spin_muestras.insert(0, "150")
        self.spin_muestras.grid(row=0, column=1, padx=6, pady=2)

        tk.Label(grid, text="Solo clases:", font=("Courier New", 9),
                 bg=BG2, fg=TEXT_DIM).grid(row=1, column=0, sticky="w", pady=4)
        self.clase_vars = {}
        cf = tk.Frame(grid, bg=BG2)
        cf.grid(row=1, column=1, columnspan=2, sticky="w")
        for c in CLASES:
            v = tk.BooleanVar(value=True)
            self.clase_vars[c] = v
            tk.Checkbutton(cf, text=FLECHAS[c], variable=v,
                           bg=BG2, fg=COLORES_CLASE[c], selectcolor=BG3,
                           activebackground=BG2, relief="flat",
                           font=("Courier New", 13)).pack(side="left")

        # — Progreso por clase —
        sec4 = self._section(frame, "PROGRESO")
        self.barras = {}
        self.lbl_conteo = {}
        for c in CLASES:
            row2 = tk.Frame(sec4, bg=BG2)
            row2.pack(fill="x", pady=2)
            tk.Label(row2, text=f"{FLECHAS[c]} {c:<10}",
                     font=("Courier New", 9), bg=BG2,
                     fg=COLORES_CLASE[c], width=14, anchor="w").pack(side="left")
            canvas = tk.Canvas(row2, height=14, bg=BG3,
                                highlightthickness=0, width=130)
            canvas.pack(side="left", padx=4)
            self.barras[c] = canvas
            lbl = tk.Label(row2, text="0/150", font=("Courier New", 8),
                           bg=BG2, fg=TEXT_DIM, width=7)
            lbl.pack(side="left")
            self.lbl_conteo[c] = lbl

        # — Botones principales —
        bf = tk.Frame(frame, bg=BG)
        bf.pack(fill="x", pady=(14, 0))
        self.btn_iniciar = self._btn(bf, "▶  INICIAR ADQUISICIÓN",
                                     self._iniciar, accent=True, h=40)
        self.btn_iniciar.pack(fill="x", pady=(0, 6))
        self.btn_cancelar = self._btn(bf, "■  DETENER",
                                      self._cancelar, color=ACCENT2, h=32)
        self.btn_cancelar.pack(fill="x")
        self.btn_cancelar.config(state="disabled")

    def _build_panel_der(self, parent):
        frame = tk.Frame(parent, bg=BG)
        frame.grid(row=0, column=1, sticky="nsew", pady=10)
        frame.rowconfigure(1, weight=0)
        frame.rowconfigure(2, weight=1)
        frame.columnconfigure(0, weight=1)

        # — Instrucción visual grande —
        sec = tk.Frame(frame, bg=BG2, relief="flat", bd=0)
        sec.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.lbl_instruccion = tk.Label(sec,
            text="Configura y presiona\nINICIAR", font=("Courier New", 13, "bold"),
            bg=BG2, fg=TEXT_DIM, pady=18)
        self.lbl_instruccion.pack()

        # Flecha grande
        self.lbl_flecha = tk.Label(sec, text="", font=("Courier New", 72, "bold"),
                                   bg=BG2, fg=ACCENT, pady=10)
        self.lbl_flecha.pack()

        # Clase actual
        self.lbl_clase = tk.Label(sec, text="",
                                  font=("Courier New", 16, "bold"),
                                  bg=BG2, fg=TEXT, pady=4)
        self.lbl_clase.pack(pady=(0, 10))

        # — Temporizador / barra de progreso de muestra —
        tf = tk.Frame(frame, bg=BG2)
        tf.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self.lbl_fase = tk.Label(tf, text="", font=("Courier New", 10),
                                 bg=BG2, fg=TEXT_DIM)
        self.lbl_fase.pack(pady=(8, 4))
        self.progress_var = tk.DoubleVar()
        style = ttk.Style()
        style.theme_use("default")
        style.configure("EOG.Horizontal.TProgressbar",
                        troughcolor=BG3, background=ACCENT,
                        thickness=10, borderwidth=0)
        self.pb = ttk.Progressbar(tf, variable=self.progress_var,
                                  maximum=100, length=400,
                                  style="EOG.Horizontal.TProgressbar")
        self.pb.pack(padx=20, pady=(0, 8))

        # — Mini osciloscopio —
        sec2 = tk.Frame(frame, bg=BG2)
        sec2.grid(row=2, column=0, sticky="nsew", pady=(0, 8))
        tk.Label(sec2, text="SEÑAL EN TIEMPO REAL", font=("Courier New", 8, "bold"),
                 bg=BG2, fg=ACCENT).pack(anchor="w", padx=10, pady=(8, 4))
        self.fig, self.ax = plt.subplots(figsize=(7.5, 4), facecolor=BG2)
        self.ax.set_facecolor(BG3)
        for sp in self.ax.spines.values():
            sp.set_edgecolor(TEXT_DIM)
        self.ax.tick_params(colors=TEXT_DIM, labelsize=8)
        self.ax.set_ylabel("amplitud (H)", color=TEXT_DIM, fontsize=9)
        self.ax.set_xlabel("muestras recientes", color=TEXT_DIM, fontsize=9)
        self.ax.axhline(0, color=TEXT_DIM, linewidth=0.5, linestyle="--")
        self.ax.set_xlim(0, 300)
        self.line_señal, = self.ax.plot(
            np.arange(300), list(self.buffer_señal), color=ACCENT, linewidth=0.9)
        self.fig.tight_layout(pad=1.2)
        self.canvas_mpl = FigureCanvasTkAgg(self.fig, master=sec2)
        self.canvas_mpl.get_tk_widget().pack(fill="both", expand=True)

        # — Log —
        sec3 = tk.Frame(frame, bg=BG2, pady=8, padx=10)
        sec3.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        tk.Label(sec3, text="LOG", font=("Courier New", 8, "bold"),
                 bg=BG2, fg=ACCENT).pack(anchor="w", pady=(0, 4))
        self.txt_log = tk.Text(sec3, height=7, bg=BG3, fg=TEXT_DIM,
                               font=("Courier New", 8), relief="flat",
                               state="disabled", wrap="word")
        self.txt_log.pack(fill="both", expand=True, padx=4, pady=4)
        sb = ttk.Scrollbar(sec3, command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=sb.set)

    def _build_statusbar(self):
        sb = tk.Frame(self, bg=BG2, height=24)
        sb.pack(fill="x", side="bottom")
        sb.pack_propagate(False)
        self.lbl_status = tk.Label(sb, text="Listo", font=("Courier New", 8),
                                   bg=BG2, fg=TEXT_DIM)
        self.lbl_status.pack(side="left", padx=12)
        self.lbl_total = tk.Label(sb, text="Total: 0 muestras",
                                  font=("Courier New", 8), bg=BG2, fg=TEXT_DIM)
        self.lbl_total.pack(side="right", padx=12)

    # ──────────────────────────────────────────
    #  HELPERS UI
    # ──────────────────────────────────────────
    def _section(self, parent, titulo):
        outer = tk.Frame(parent, bg=BG2, pady=8, padx=10)
        outer.pack(fill="x", pady=(0, 8))
        tk.Label(outer, text=titulo, font=("Courier New", 8, "bold"),
                 bg=BG2, fg=ACCENT).pack(anchor="w", pady=(0, 4))
        return outer

    def _btn(self, parent, txt, cmd, accent=False, color=None, w=None, h=None):
        c = color or (ACCENT if accent else BG3)
        fg = BG if accent else TEXT
        kw = dict(text=txt, command=cmd, bg=c, fg=fg, relief="flat",
                  font=("Courier New", 9, "bold"), cursor="hand2",
                  activebackground=ACCENT, activeforeground=BG,
                  padx=8, pady=4)
        if w: kw["width"] = w
        if h: kw["height"] = h
        return tk.Button(parent, **kw)

    def _log(self, msg, color=None):
        self.txt_log.config(state="normal")
        tag = f"tag_{int(time.time()*1000)}"
        self.txt_log.insert("end", f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n", tag)
        if color:
            self.txt_log.tag_config(tag, foreground=color)
        self.txt_log.see("end")
        self.txt_log.config(state="disabled")

    def _set_status(self, txt):
        self.lbl_status.config(text=txt)

    def _update_barra(self, clase, n, total):
        canvas = self.barras[clase]
        w = canvas.winfo_width() or 130
        canvas.delete("all")
        frac = min(n / total, 1.0)
        if frac > 0:
            canvas.create_rectangle(0, 0, int(w * frac), 14,
                                    fill=COLORES_CLASE[clase], outline="")
        self.lbl_conteo[clase].config(text=f"{n}/{total}")
        total_all = sum(self.muestras_totales.values())
        self.lbl_total.config(text=f"Total: {total_all} muestras")

    def _mostrar_instruccion(self, texto, flecha="", clase="", color=ACCENT):
        self.lbl_instruccion.config(text=texto, fg=TEXT)
        self.lbl_flecha.config(text=flecha, fg=color)
        self.lbl_clase.config(text=clase, fg=color)

    def _set_fase(self, txt, pct=0):
        self.lbl_fase.config(text=txt)
        self.progress_var.set(pct)

    # ──────────────────────────────────────────
    #  SERIAL
    # ──────────────────────────────────────────
    def _refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_cb["values"] = ports
        if ports:
            self.port_cb.current(0)

    def _toggle_conexion(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            self.ser = None
            self.lbl_conexion.config(text="● Sin conexión", fg=ACCENT2)
            self.btn_conectar.config(text="Conectar")
            self._log("Puerto cerrado.", color=TEXT_DIM)
        else:
            port = self.port_var.get()
            if not port:
                messagebox.showwarning("Puerto", "Selecciona un puerto serial.")
                return
            try:
                self.ser = serial.Serial(port, BAUD_RATE, timeout=1)
                time.sleep(2)
                self.ser.reset_input_buffer()
                self.lbl_conexion.config(text=f"● Conectado: {port}", fg=SUCCESS)
                self.btn_conectar.config(text="Desconectar")
                self._log(f"Conectado a {port} @ {BAUD_RATE}", color=SUCCESS)
                threading.Thread(target=self._leer_serial_continuo,
                                 daemon=True).start()
            except Exception as e:
                messagebox.showerror("Error Serial", str(e))

    def _leer_serial_continuo(self):
        """Hilo único de lectura serial — alimenta osciloscopio y CSV."""
        while self.ser and self.ser.is_open:
            try:
                linea = self.ser.readline().decode(errors="ignore").strip()
                partes = linea.split(",")
                if len(partes) == 2:
                    h = float(partes[0].strip())
                    v = float(partes[1].strip())
                    if abs(h - v) < 50:
                        self.buffer_señal.append(h)
                        if self.capturando and self.csv_writer:
                            ts = int(time.time() * 1000)
                            self.csv_writer.writerow([ts, h, v, self.captura_clase])
                            self.captura_n += 1
            except (ValueError, IndexError):
                pass
            except:
                pass

    def _tick_grafica(self):
        datos = list(self.buffer_señal)
        self.line_señal.set_ydata(datos)
        yabs = max(float(np.abs(datos).max()), 20) * 1.2
        self.ax.set_ylim(-yabs, yabs)
        self.canvas_mpl.draw()
        self.after(80, self._tick_grafica)

    # ──────────────────────────────────────────
    #  ADQUISICIÓN
    # ──────────────────────────────────────────
    def _iniciar(self):
        # Validar
        clases_sel = [c for c in CLASES if self.clase_vars[c].get()]
        if not clases_sel:
            messagebox.showwarning("Clases", "Selecciona al menos una clase.")
            return
        if not (self.ser and self.ser.is_open):
            if not messagebox.askyesno("Sin conexión",
                "No hay Arduino conectado.\n¿Continuar en modo simulación (sin guardar)?"):
                return
            self.modo_sim = True
        else:
            self.modo_sim = False

        try:
            self.muestras_objetivo = int(self.spin_muestras.get())
        except:
            self.muestras_objetivo = 150

        # Abrir CSV
        if not self.modo_sim:
            ruta = self.archivo_var.get()
            append = os.path.exists(ruta)
            self.csv_file = open(ruta, "a" if append else "w", newline="")
            self.csv_writer = csv.writer(self.csv_file)
            if not append:
                self.csv_writer.writerow(["timestamp_ms", "H", "V", "etiqueta"])
            self._log(f"CSV {'abierto (append)' if append else 'creado'}: {ruta}", color=SUCCESS)

        self.cancelar_flag = False
        self.grabando = True
        self.btn_iniciar.config(state="disabled")
        self.btn_cancelar.config(state="normal")

        hilo = threading.Thread(target=self._protocolo_adquisicion,
                                args=(clases_sel,), daemon=True)
        hilo.start()

    def _cancelar(self):
        self.cancelar_flag = True
        self._log("⚠ Adquisición cancelada por el usuario.", color=WARNING)

    def _protocolo_adquisicion(self, clases):
        try:
            for clase in clases:
                if self.cancelar_flag:
                    break
                pendientes = self.muestras_objetivo - self.muestras_totales[clase]
                if pendientes <= 0:
                    self._log(f"'{clase}' ya completa, saltando.", color=TEXT_DIM)
                    continue

                self._log(f"\n▶ Iniciando clase: {clase.upper()} ({pendientes} muestras)", color=COLORES_CLASE[clase])
                self.after(0, self._mostrar_instruccion,
                           f"Prepárate para:\n{clase.upper()}",
                           FLECHAS[clase], clase, COLORES_CLASE[clase])
                time.sleep(2.0)

                for i in range(pendientes):
                    if self.cancelar_flag:
                        break

                    n_total = self.muestras_totales[clase]

                    # Pausa de bloque
                    if i > 0 and i % BLOQUE_DESCANSO == 0:
                        self.after(0, self._mostrar_instruccion,
                                   "😌  DESCANSO\nCierra los ojos un momento", "—",
                                   f"Bloque {i//BLOQUE_DESCANSO} completado", TEXT_DIM)
                        self.after(0, self._set_fase, f"Pausa {PAUSA_LARGA:.0f}s...", 0)
                        self._log(f"  Pausa entre bloques ({PAUSA_LARGA}s)")
                        self._sleep_cancelable(PAUSA_LARGA)
                        if self.cancelar_flag:
                            break

                    # Fase 1: Mira al centro
                    self.after(0, self._mostrar_instruccion,
                               "👁  Mira al CENTRO", "●",
                               f"Muestra {i+1}/{pendientes}  —  {clase}", ACCENT)
                    self.after(0, self._set_fase, "Línea base...", 10)
                    self._sleep_cancelable(TIEMPO_LINEA_BASE)
                    if self.cancelar_flag:
                        break

                    # Fase 2: ¡Mueve!
                    color_c = COLORES_CLASE[clase]
                    self.after(0, self._mostrar_instruccion,
                               "¡MUEVE LOS OJOS!", FLECHAS[clase], clase, color_c)
                    self.after(0, self._set_fase, "⬤  Capturando...", 50)

                    muestras_capturadas = self._capturar_muestra(clase, TIEMPO_MOVIMIENTO)

                    if not self.cancelar_flag:
                        self.muestras_totales[clase] += 1
                        self.after(0, self._update_barra, clase,
                                   self.muestras_totales[clase], self.muestras_objetivo)
                        self._log(f"  ✓ {clase} #{self.muestras_totales[clase]}  ({muestras_capturadas} puntos)")

                    # Fase 3: Regresa al centro
                    self.after(0, self._mostrar_instruccion,
                               "👁  Regresa al CENTRO", "●", "", ACCENT)
                    self.after(0, self._set_fase, "Regresando...", 85)
                    self._sleep_cancelable(0.2)

                    # Fase 4: Descanso
                    self.after(0, self._set_fase,
                               f"Descansando... ({TIEMPO_DESCANSO}s)", 95)
                    self._sleep_cancelable(TIEMPO_DESCANSO)
                    self.after(0, self._set_fase, "", 0)

                self._log(f"  ✅ Clase '{clase}' completada.", color=SUCCESS)

        finally:
            self._finalizar()

    def _capturar_muestra(self, clase, duracion):
        """Activa la grabación al CSV durante 'duracion' segundos.
        La lectura serial la hace _leer_serial_continuo (único lector)."""
        self.captura_clase = clase
        self.captura_n     = 0
        self.capturando    = True
        self._sleep_cancelable(duracion)
        self.capturando    = False
        if self.csv_file:
            self.csv_file.flush()
        return self.captura_n

    def _sleep_cancelable(self, seg):
        fin = time.time() + seg
        while time.time() < fin:
            if self.cancelar_flag:
                return
            time.sleep(0.05)

    def _finalizar(self):
        self.grabando = False
        if self.csv_file:
            self.csv_file.close()
            self.csv_file = None
            self.csv_writer = None

        total = sum(self.muestras_totales.values())
        self.after(0, self._mostrar_instruccion,
                   "✅  Adquisición finalizada" if not self.cancelar_flag
                   else "⚠  Adquisición detenida",
                   "", f"{total} muestras guardadas", SUCCESS)
        self.after(0, self._set_fase, "", 0)
        self.after(0, self.btn_iniciar.config, {"state": "normal"})
        self.after(0, self.btn_cancelar.config, {"state": "disabled"})
        self.after(0, self._set_status, f"Listo — {total} muestras totales")

        if not self.cancelar_flag:
            self.after(0, self._log,
                       f"\n🎉 ¡Listo! Total: {total} muestras en {self.archivo_var.get()}",
                       SUCCESS)
            self.after(100, lambda: messagebox.showinfo(
                "Completado",
                f"Adquisición finalizada.\n{total} muestras guardadas en:\n{self.archivo_var.get()}"
            ))

    # ──────────────────────────────────────────
    #  ARCHIVO
    # ──────────────────────────────────────────
    def _elegir_archivo(self):
        ruta = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("Todos", "*.*")],
            initialfile="datos_eog.csv"
        )
        if ruta:
            self.archivo_var.set(ruta)

    def on_close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
        self.destroy()


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    app = EOGApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
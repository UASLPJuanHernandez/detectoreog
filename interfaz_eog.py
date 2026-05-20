"""
Interfaz en tiempo real EOG — muestra señal y clasifica dirección.
Requiere: modelo_eog.pkl  y  encoder_eog.pkl  (correr entrenar_eog.py primero)
Uso: python3 interfaz_eog.py
"""

import os, sys, time, threading, queue, signal
import numpy as np
from scipy import stats
import joblib
import serial
import serial.tools.list_ports
import tkinter as tk
from tkinter import ttk
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from collections import deque

BASE = os.path.dirname(os.path.abspath(__file__))

# ── Cargar modelo ─────────────────────────────────────────────────
try:
    modelo  = joblib.load(os.path.join(BASE, "modelo_eog.pkl"))
    encoder = joblib.load(os.path.join(BASE, "encoder_eog.pkl"))
except FileNotFoundError:
    print("ERROR: No se encontró modelo_eog.pkl — corre entrenar_eog.py primero.")
    sys.exit(1)

# ── Parámetros ────────────────────────────────────────────────────
BAUD_RATE   = 115200
BUFFER_GRAF = 400   # puntos visibles en la gráfica
VENTANA_CLS = 80    # puntos por clasificación (igual que entrenamiento)
PASO_CLS    = 15    # clasificar cada N puntos nuevos
VOTOS       = 5     # cuántas clasificaciones consecutivas para confirmar
VOTOS_OK    = 3     # cuántas deben coincidir (de VOTOS) para disparar
COOLDOWN    = 2.0   # segundos mínimos entre comandos
CONF_MINIMA = 0.50  # confianza mínima por voto individual
# Tras detectar una dirección, bloquear la opuesta extra tiempo (evita ojo volviendo al centro)
OPUESTAS    = {"izquierda": "derecha", "derecha": "izquierda", "arriba": None}

FLECHAS = {"izquierda": "←", "derecha": "→", "reposo": "●", "arriba": "↑"}
COLORES = {
    "izquierda": "#FF6B6B",
    "derecha":   "#FFD93D",
    "reposo":    "#4A9EFF",
    "arriba":    "#6BCB77",
    "–":         "#6B7280",
}
COMANDOS = {"izquierda": b'L', "derecha": b'R', "reposo": b'C', "arriba": b'U'}

BG      = "#0D0F14"
BG2     = "#151820"
ACCENT  = "#00E5FF"
TEXT    = "#E8EAF0"
DIM     = "#6B7280"
SUCCESS = "#6BCB77"
ERROR   = "#FF6B6B"

# ── Features (idéntico al entrenamiento) ──────────────────────────
def extraer_features(seg):
    seg = np.array(seg, dtype=float)
    seg = seg - seg.mean()
    rango  = seg.max() - seg.min()
    seg_n  = seg / rango if rango > 0 else seg
    fft    = np.abs(np.fft.rfft(seg_n))
    n      = len(fft)
    e_baja = fft[:max(1, n//8)].mean()
    e_alta = fft[max(1, n//8):].mean()
    primera = seg[:25].mean()
    ultima  = seg[-25:].mean()
    dir_pico      = seg.max() / rango if rango > 0 else 0.5
    deriv         = np.diff(seg_n)
    vel_max       = np.abs(deriv).max()
    deriv_std     = deriv.std()
    mid           = len(seg_n) // 2
    asimetria     = seg_n[:mid].std() / (seg_n[mid:].std() + 1e-6)
    pico_idx      = np.argmax(np.abs(seg_n))
    pos_pico_abs  = pico_idx / len(seg_n)
    media_segunda = seg_n[mid:].mean()

    pend_subida = seg_n[pico_idx] / pico_idx if pico_idx > 0 else 0.0
    resto = len(seg_n) - pico_idx
    pend_bajada = (seg_n[-1] - seg_n[pico_idx]) / resto if resto > 1 else 0.0
    sostenida     = (np.abs(seg_n) > 0.3).mean()
    kurt          = stats.kurtosis(seg_n)
    return [[
        seg.max(), seg.min(), rango, seg.std(),
        seg.argmax() / len(seg), seg.argmin() / len(seg),
        np.sum(seg**2) / len(seg),
        np.sum(np.diff(np.sign(seg)) != 0),
        np.percentile(seg, 25), np.percentile(seg, 75), np.median(seg),
        e_baja, e_alta,
        primera, ultima, primera - ultima,
        vel_max, deriv_std, asimetria, pos_pico_abs,
        dir_pico, media_segunda,
        sostenida, kurt,
        pend_subida, pend_bajada,
    ]]

# ══════════════════════════════════════════════════════════════════
class AppEOG:
    def __init__(self, root):
        self.root    = root
        self.root.title("EOG — Detección en tiempo real")
        self.root.configure(bg=BG)
        self.root.geometry("1100x700")

        self.ser        = None
        self.leyendo    = False
        self.activo     = True
        # Cola thread-safe: el hilo escribe, el main-loop lee
        self.q          = queue.Queue()

        self.buf_graf     = deque([0.0] * BUFFER_GRAF, maxlen=BUFFER_GRAF)
        self.buf_cls      = deque(maxlen=VENTANA_CLS)
        self.votos        = deque(maxlen=VOTOS)
        self.n_nuevos     = 0
        self.ultimo_cmd   = 0.0
        self._estado_inst = None
        self.prediccion   = "–"
        self.confianza    = 0.0
        self.conteo       = {"izquierda": 0, "derecha": 0, "reposo": 0, "arriba": 0}
        # Histéresis: bloquea la dirección opuesta para ignorar el ojo volviendo al centro
        self._bloqueada   = None   # dirección bloqueada temporalmente
        self._bloqueo_fin = 0.0   # timestamp hasta cuando está bloqueada

        self._after_id  = None
        self._construir_ui()
        self._iniciar_grafica()
        self._tick()   # arranca el loop principal en el hilo de tkinter

    # ── Loop principal (hilo tkinter) ─────────────────────────────
    def _tick(self):
        """Drena la cola y actualiza gráfica + UI. Corre solo en el hilo main."""
        if not self.activo:
            return
        try:
            # Procesar todos los mensajes pendientes
            try:
                while True:
                    msg = self.q.get_nowait()
                    self._procesar_mensaje(msg)
            except queue.Empty:
                pass

            # Redibujar gráfica
            datos = list(self.buf_graf)
            self.line_graf.set_ydata(datos)
            yabs = max(np.abs(datos).max(), 20) * 1.2
            self.ax.set_ylim(-yabs, yabs)
            self.canvas.draw()

            self._after_id = self.root.after(80, self._tick)   # ~12 fps
        except tk.TclError:
            pass  # ventana ya destruida

    def _procesar_mensaje(self, msg):
        tipo = msg[0]

        if tipo == "dato":
            # msg = ("dato", valor_float)
            # ya acumulado en el hilo; solo actualizamos la UI si hay predicción nueva
            pass

        elif tipo == "pred":
            # msg = ("pred", direccion, confianza, enviar_arduino)
            _, direccion, confianza, enviar = msg
            self.prediccion = direccion
            self.confianza  = confianza
            color  = COLORES.get(direccion, COLORES["–"])
            flecha = FLECHAS.get(direccion, "–")

            self.lbl_flecha.config(text=flecha, fg=color)
            self.lbl_dir.config(
                text=direccion.upper() if direccion != "–" else "–", fg=color)
            self.lbl_conf.config(text=f"confianza: {confianza:.0%}")
            for clase, lbl in self.lbl_conteo.items():
                lbl.config(text=str(self.conteo.get(clase, 0)))

            if enviar:
                self.lbl_arduino.config(
                    text=f"Enviado: {COMANDOS[direccion].decode()} ({direccion})",
                    fg=SUCCESS)

        elif tipo == "pred_raw":
            # Muestra predicción cruda aunque no supere umbral
            _, direccion, confianza = msg
            color  = COLORES.get(direccion, COLORES["–"])
            flecha = FLECHAS.get(direccion, "–")
            self.lbl_flecha.config(text=flecha, fg=color)
            self.lbl_dir.config(text=direccion.upper(), fg=color)
            ok = "✓" if confianza >= CONF_MINIMA else "✗ baja"
            self.lbl_conf.config(text=f"confianza: {confianza:.0%} {ok}")
            for clase, lbl in self.lbl_conteo.items():
                lbl.config(text=str(self.conteo.get(clase, 0)))

        elif tipo == "instruccion":
            _, texto, color = msg
            self.lbl_instruccion.config(text=texto, fg=color)

        elif tipo == "ultimo":
            _, texto, color = msg
            self.lbl_ultimo.config(text=texto, fg=color)

        elif tipo == "log":
            self.lbl_log.config(text=msg[1])

        elif tipo == "estado":
            _, texto, color = msg
            self.lbl_estado.config(text=texto, fg=color)

        elif tipo == "btn":
            self.btn_conectar.config(text=msg[1])

    # ── UI ────────────────────────────────────────────────────────
    def _construir_ui(self):
        top = tk.Frame(self.root, bg=BG, pady=6)
        top.pack(fill="x", padx=10)

        tk.Label(top, text="Puerto:", bg=BG, fg=DIM,
                 font=("Helvetica", 11)).pack(side="left")
        self.combo_port = ttk.Combobox(top, width=22, state="readonly")
        self.combo_port["values"] = self._listar_puertos()
        if self.combo_port["values"]:
            self.combo_port.current(0)
        self.combo_port.pack(side="left", padx=(4, 10))

        self.btn_conectar = tk.Button(
            top, text="Conectar", command=self._conectar,
            bg="#1E2230", fg=TEXT, relief="flat",
            padx=14, pady=4, font=("Helvetica", 11))
        self.btn_conectar.pack(side="left", padx=4)

        self.lbl_estado = tk.Label(
            top, text="● Desconectado", bg=BG, fg=ERROR,
            font=("Helvetica", 11))
        self.lbl_estado.pack(side="left", padx=12)

        tk.Button(top, text="Actualizar puertos", command=self._refresh_ports,
                  bg="#1E2230", fg=DIM, relief="flat", padx=8, pady=4,
                  font=("Helvetica", 10)).pack(side="right")

        centro = tk.Frame(self.root, bg=BG)
        centro.pack(fill="both", expand=True, padx=10, pady=4)

        col_graf = tk.Frame(centro, bg=BG)
        col_graf.pack(side="left", fill="both", expand=True)

        self.fig_frame = col_graf

        col_res = tk.Frame(centro, bg=BG2, width=260)
        col_res.pack(side="right", fill="y", padx=(10, 0))
        col_res.pack_propagate(False)

        tk.Label(col_res, text="DIRECCIÓN", bg=BG2, fg=DIM,
                 font=("Helvetica", 12, "bold")).pack(pady=(24, 4))

        self.lbl_flecha = tk.Label(col_res, text="–", bg=BG2,
                                    fg=COLORES["–"], font=("Helvetica", 90, "bold"))
        self.lbl_flecha.pack()

        self.lbl_dir = tk.Label(col_res, text="–", bg=BG2,
                                 fg=TEXT, font=("Helvetica", 18, "bold"))
        self.lbl_dir.pack(pady=(0, 6))

        self.lbl_conf = tk.Label(col_res, text="confianza: –", bg=BG2,
                                  fg=DIM, font=("Helvetica", 11))
        self.lbl_conf.pack()

        tk.Frame(col_res, bg=DIM, height=1).pack(fill="x", padx=20, pady=16)

        tk.Label(col_res, text="Detecciones", bg=BG2, fg=DIM,
                 font=("Helvetica", 11, "bold")).pack()
        self.lbl_conteo = {}
        for clase in ("izquierda", "derecha", "arriba", "reposo"):
            f = tk.Frame(col_res, bg=BG2)
            f.pack(fill="x", padx=20, pady=2)
            tk.Label(f, text=f"{FLECHAS[clase]} {clase}", bg=BG2,
                     fg=COLORES[clase], font=("Helvetica", 11)).pack(side="left")
            lbl = tk.Label(f, text="0", bg=BG2, fg=TEXT,
                           font=("Helvetica", 11, "bold"))
            lbl.pack(side="right")
            self.lbl_conteo[clase] = lbl

        tk.Frame(col_res, bg=DIM, height=1).pack(fill="x", padx=20, pady=16)

        tk.Label(col_res, text="Arduino", bg=BG2, fg=DIM,
                 font=("Helvetica", 11, "bold")).pack()
        self.lbl_arduino = tk.Label(col_res, text="Sin enviar", bg=BG2,
                                     fg=DIM, font=("Helvetica", 10))
        self.lbl_arduino.pack(pady=2)

        bot = tk.Frame(self.root, bg="#0A0C10", pady=4)
        bot.pack(fill="x", side="bottom")
        self.lbl_log = tk.Label(bot, text="Listo.", bg="#0A0C10",
                                 fg=DIM, font=("Helvetica", 9), anchor="w")
        self.lbl_log.pack(fill="x", padx=10)

        # ── Instrucción flotante centrada sobre todo ───────────────
        self.lbl_instruccion = tk.Label(
            self.root, text="Conecta el Arduino para comenzar",
            bg="#0D0F14", fg=DIM,
            font=("Helvetica", 26, "bold"),
            wraplength=700, justify="center",
            padx=20, pady=12)
        self.lbl_instruccion.place(relx=0.42, rely=0.45, anchor="center")

        # ── Último movimiento detectado (debajo del anterior) ──────
        self.lbl_ultimo = tk.Label(
            self.root, text="",
            bg="#0D0F14", fg=DIM,
            font=("Helvetica", 16),
            wraplength=700, justify="center",
            padx=20, pady=6)
        self.lbl_ultimo.place(relx=0.42, rely=0.58, anchor="center")

    # ── Gráfica ────────────────────────────────────────────────────
    def _iniciar_grafica(self):
        self.fig, self.ax = plt.subplots(figsize=(7.5, 4), facecolor=BG)
        self.ax.set_facecolor(BG2)
        for sp in self.ax.spines.values(): sp.set_edgecolor(DIM)
        self.ax.tick_params(colors=DIM, labelsize=8)
        self.ax.set_ylabel("amplitud (H)", color=DIM, fontsize=9)
        self.ax.set_xlabel("muestras recientes", color=DIM, fontsize=9)
        self.ax.axhline(0, color=DIM, linewidth=0.5, linestyle="--")
        self.ax.set_xlim(0, BUFFER_GRAF)
        self.line_graf, = self.ax.plot(
            np.arange(BUFFER_GRAF), list(self.buf_graf),
            color=ACCENT, linewidth=0.9)
        self.fig.tight_layout(pad=1.2)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.fig_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    # ── Serial ────────────────────────────────────────────────────
    def _listar_puertos(self):
        return [p.device for p in serial.tools.list_ports.comports()] or ["(ninguno)"]

    def _refresh_ports(self):
        self.combo_port["values"] = self._listar_puertos()
        if self.combo_port["values"]:
            self.combo_port.current(0)

    def _conectar(self):
        if self.leyendo:
            self._desconectar()
            return
        port = self.combo_port.get()
        if port == "(ninguno)":
            return
        try:
            self.ser = serial.Serial(port, BAUD_RATE, timeout=1)
            time.sleep(1.5)
            self.ser.reset_input_buffer()
            self.leyendo = True
            self.btn_conectar.config(text="Desconectar")
            self.lbl_estado.config(text=f"● Conectado — {port}", fg=SUCCESS)
            self.q.put(("log", f"Conectado a {port} @ {BAUD_RATE}"))
            self.q.put(("instruccion", "Mira al centro — calibrando señal...", DIM))
            threading.Thread(target=self._hilo_lectura, daemon=True).start()
        except Exception as e:
            self.lbl_estado.config(text="● Error al conectar", fg=ERROR)
            self.q.put(("log", f"Error: {e}"))

    def _desconectar(self):
        self.leyendo = False
        if self.ser:
            self.ser.close()
            self.ser = None
        self.btn_conectar.config(text="Conectar")
        self.lbl_estado.config(text="● Desconectado", fg=ERROR)
        self.q.put(("log", "Desconectado."))

    def _instruccion(self, key, texto, color):
        """Solo encola si el estado cambió, para que el mensaje no parpadee."""
        if self._estado_inst != key:
            self._estado_inst = key
            self.q.put(("instruccion", texto, color))

    # ── Hilo de lectura ───────────────────────────────────────────
    def _hilo_lectura(self):
        self._instruccion("listo", "Mueve el ojo cuando quieras   →  ←  ●", SUCCESS)
        while self.leyendo and self.ser:
            try:
                linea = self.ser.readline().decode(errors="ignore").strip()
                if not linea:
                    continue
                valor = float(linea.split(",")[0])
            except (ValueError, serial.SerialException):
                continue

            self.buf_graf.append(valor)
            self.buf_cls.append(valor)
            self.n_nuevos += 1

            # Clasificar cada PASO_CLS puntos nuevos y cuando el buffer esté lleno
            if self.n_nuevos >= PASO_CLS and len(self.buf_cls) == VENTANA_CLS:
                self.n_nuevos = 0
                self._votar()

    def _votar(self):
        """Clasifica la ventana actual y acumula votos. Dispara si hay consenso."""
        try:
            feats     = extraer_features(list(self.buf_cls))
            pred_idx  = modelo.predict(feats)[0]
            proba     = modelo.predict_proba(feats)[0]
            confianza = proba.max()
            direccion = str(encoder.inverse_transform([pred_idx])[0])
        except Exception as e:
            self.q.put(("log", f"ERROR: {e}"))
            return

        # Ignorar dirección bloqueada por histéresis (ojo volviendo al centro)
        ahora = time.time()
        if self._bloqueada and ahora < self._bloqueo_fin and direccion == self._bloqueada:
            direccion = "reposo"
        elif ahora >= self._bloqueo_fin:
            self._bloqueada = None

        # Solo contar votos con suficiente confianza
        voto = direccion if confianza >= CONF_MINIMA else "reposo"
        self.votos.append(voto)

        # Actualizar indicador de votación en log
        bloq = f" [bloq:{self._bloqueada}]" if self._bloqueada else ""
        resumen = f"votos: {list(self.votos)}  conf={confianza:.0%}{bloq}"
        self.q.put(("log", resumen))

        # Comprobar consenso (solo para izq/der/arriba)
        if (len(self.votos) == VOTOS and
                ahora - self.ultimo_cmd > COOLDOWN):
            for clase in ("izquierda", "derecha", "arriba"):
                if self.votos.count(clase) >= VOTOS_OK:
                    self._disparar(clase, confianza)
                    self.votos.clear()
                    break

    def _disparar(self, direccion, confianza):
        self.ultimo_cmd = time.time()
        self.conteo[direccion] = self.conteo.get(direccion, 0) + 1
        color = COLORES.get(direccion, COLORES["–"])

        # Bloquear dirección opuesta durante COOLDOWN extra (ignora ojo volviendo al centro)
        opuesta = OPUESTAS.get(direccion)
        if opuesta:
            self._bloqueada   = opuesta
            self._bloqueo_fin = time.time() + COOLDOWN + 0.8

        self.q.put(("pred_raw", direccion, confianza))
        self.q.put(("ultimo",
            f"Último detectado:  {FLECHAS.get(direccion,'–')} {direccion.upper()}  {confianza:.0%} ✓",
            color))
        self._estado_inst = None
        self._instruccion("cooldown", "● Regresa al centro y espera...", DIM)

        enviar = False
        if self.ser and self.leyendo and direccion in COMANDOS:
            try:
                self.ser.write(COMANDOS[direccion])
                enviar = True
            except Exception:
                pass
        self.q.put(("pred", direccion, confianza, enviar))

        # Tras cooldown, volver a "listo"
        def volver_listo():
            time.sleep(COOLDOWN)
            if self.leyendo:
                self._estado_inst = None
                self._instruccion("listo",
                    "Mueve el ojo cuando quieras   →  ←  ●", SUCCESS)
        threading.Thread(target=volver_listo, daemon=True).start()

    # ── Cierre limpio ─────────────────────────────────────────────
    def cerrar(self):
        self.activo  = False
        self.leyendo = False
        if self._after_id is not None:
            try:
                self.root.after_cancel(self._after_id)
            except tk.TclError:
                pass
        if self.ser:
            self.ser.close()
        try:
            self.root.destroy()
        except tk.TclError:
            pass


# ── Main ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    app  = AppEOG(root)
    root.protocol("WM_DELETE_WINDOW", app.cerrar)
    # Route Ctrl+C through tkinter's event loop so it never interrupts mid-draw
    signal.signal(signal.SIGINT, lambda *_: root.after(0, app.cerrar))
    root.mainloop()

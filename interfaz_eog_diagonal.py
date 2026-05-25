"""
Interfaz EOG con fusión diagonal (lateral → vertical).
Basada en interfaz_eog.py — mismos parámetros y lógica de clasificación.
Diagonales: izquierda/derecha abren ventana de fusión; si llega arriba/abajo
dentro de FUSION_WINDOW segundos se emite la diagonal. arriba/abajo solos emiten directo.
Requiere: modelo_eog.pkl  y  encoder_eog.pkl
Uso: python3 interfaz_eog_diagonal.py
"""

import os, sys, time, threading, queue, signal
import tkinter as tk
from tkinter import ttk
from collections import deque

BASE = os.path.dirname(os.path.abspath(__file__))

# ── Splash ────────────────────────────────────────────────────────
class _Cargador:
    def __init__(self):
        self.win = tk.Tk()
        self.win.title("EOG")
        self.win.geometry("360x100")
        self.win.configure(bg="#0D0F14")
        self.win.resizable(False, False)
        self.win.eval("tk::PlaceWindow . center")
        tk.Label(self.win, text="EOG — Detección en tiempo real",
                 bg="#0D0F14", fg="#00E5FF",
                 font=("Courier New", 12, "bold")).pack(pady=(16, 6))
        self.lbl = tk.Label(self.win, text="Importando librerías...",
                            bg="#0D0F14", fg="#6B7280",
                            font=("Courier New", 9))
        self.lbl.pack()
        self._q      = queue.Queue()
        self.modelo  = None
        self.encoder = None
        threading.Thread(target=self._cargar, daemon=True).start()
        self.win.after(100, self._poll)
        self.win.mainloop()

    def _cargar(self):
        try:
            import pickle
            import numpy, scipy.stats, serial, serial.tools.list_ports
            import matplotlib; matplotlib.use("TkAgg")
            import matplotlib.pyplot, matplotlib.backends.backend_tkagg
            self._q.put(("status", "Cargando modelo de clasificación..."))
            with open(os.path.join(BASE, "modelo_eog.pkl"), "rb") as f:
                m = pickle.load(f)
            with open(os.path.join(BASE, "encoder_eog.pkl"), "rb") as f:
                e = pickle.load(f)
            self._q.put(("ok", m, e))
        except FileNotFoundError:
            self._q.put(("error", "No se encontró modelo_eog.pkl — corre entrenar_eog.py"))
        except Exception as ex:
            self._q.put(("error", str(ex)))

    def _poll(self):
        try:
            while True:
                msg = self._q.get_nowait()
                if msg[0] == "status":
                    self.lbl.config(text=msg[1])
                elif msg[0] == "ok":
                    self.modelo  = msg[1]
                    self.encoder = msg[2]
                    self.win.destroy()
                    return
                elif msg[0] == "error":
                    self.lbl.config(text=msg[1], fg="#FF6B6B")
                    tk.Button(self.win, text="Salir", command=sys.exit,
                              bg="#FF6B6B", fg="white", relief="flat",
                              font=("Courier New", 9)).pack(pady=6)
                    return
        except queue.Empty:
            pass
        self.win.after(100, self._poll)

# ── Parámetros (idénticos a interfaz_eog.py) ─────────────────────
BAUD_RATE   = 115200
BUFFER_GRAF = 400
VENTANA_CLS = 80
PASO_CLS    = 15
VOTOS       = 5
VOTOS_OK    = 3
COOLDOWN    = 2.0
CONF_MINIMA = 0.50
OPUESTAS    = {"izquierda": "derecha", "derecha": "izquierda",
               "arriba": "abajo", "abajo": "arriba"}

ONSET_FACTOR   = 4.0
ONSET_MIN      = 500
BASE_VENTANA   = 200
POST_ONSET     = 200
ONSET_CONSEC   = 2

# ── Fusión diagonal ───────────────────────────────────────────────
# Cuando se detecta "arriba", se espera FUSION_WINDOW segundos por un
# lateral. Si llega, se emite la diagonal; si no, se emite "arriba".
FUSION_WINDOW = 2.5   # segundos para esperar el segundo movimiento (vertical)
FUSION_DELAY  = 0.30  # segundos antes de votar (señal de retorno asentándose)

# Solo lateral-primero: izquierda/derecha abren ventana, arriba/abajo emiten directo
_DIAGONALES = {
    ("izquierda", "arriba"): "arriba-izquierda",
    ("izquierda", "abajo"):  "abajo-izquierda",
    ("derecha",   "arriba"): "arriba-derecha",
    ("derecha",   "abajo"):  "abajo-derecha",
}

# ── Colores / flechas / comandos ──────────────────────────────────
FLECHAS = {
    "izquierda":        "←",
    "derecha":          "→",
    "reposo":           "●",
    "arriba":           "↑",
    "abajo":            "↓",
    "arriba-derecha":   "↗",
    "arriba-izquierda": "↖",
    "abajo-derecha":    "↘",
    "abajo-izquierda":  "↙",
    "–":                "–",
}
COLORES = {
    "izquierda":        "#FF6B6B",
    "derecha":          "#FFD93D",
    "reposo":           "#4A9EFF",
    "arriba":           "#6BCB77",
    "abajo":            "#FF922B",
    "arriba-derecha":   "#C8F560",
    "arriba-izquierda": "#FF9898",
    "abajo-derecha":    "#FFB347",
    "abajo-izquierda":  "#FF7B55",
    "–":                "#6B7280",
}
COMANDOS = {
    "izquierda":        b'L',
    "derecha":          b'R',
    "reposo":           b'C',
    "arriba":           b'U',
    "abajo":            b'D',
    "arriba-derecha":   b'E',
    "arriba-izquierda": b'Q',
    "abajo-derecha":    b'X',
    "abajo-izquierda":  b'Z',
}

_CLASES_UI = ("izquierda", "derecha", "arriba", "abajo",
              "arriba-derecha", "arriba-izquierda",
              "abajo-derecha", "abajo-izquierda", "reposo")

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
    n_ext        = max(1, len(seg_n) // 8)
    inicio_n     = seg_n[:n_ext].mean()
    fin_n        = seg_n[-n_ext:].mean()
    tendencia_n  = fin_n - inicio_n
    cuarto       = max(1, len(deriv) // 4)
    deriv_inicio = deriv[:cuarto].mean()
    deriv_final  = deriv[-cuarto:].mean()
    n_q          = max(1, len(seg_n) // 4)
    q2_n         = seg_n[n_q:2*n_q].mean()
    rango_q1_n   = seg_n[:n_q].max() - seg_n[:n_q].min()
    fin_n_feat   = fin_n
    inicio_n_feat = inicio_n
    amp_abs        = np.abs(seg).max()
    amp_media      = np.mean(np.abs(seg))
    amp_sobre_3000 = float(amp_abs > 3000)
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
        tendencia_n, deriv_inicio, deriv_final,
        q2_n, rango_q1_n,
        fin_n_feat, inicio_n_feat,
        amp_abs, amp_media, amp_sobre_3000,
    ]]

# ══════════════════════════════════════════════════════════════════
class AppEOG:
    def __init__(self, root):
        self.root    = root
        self.root.title("EOG — Detección en tiempo real  [DIAGONAL]")
        self.root.configure(bg=BG)
        self.root.geometry("1100x700")

        self.ser        = None
        self.leyendo    = False
        self.activo     = True
        self.q          = queue.Queue()

        self.buf_graf     = deque([0.0] * BUFFER_GRAF, maxlen=BUFFER_GRAF)
        self.buf_cls      = deque(maxlen=VENTANA_CLS)
        self.votos        = deque(maxlen=VOTOS)
        self.n_nuevos     = 0
        self.ultimo_cmd   = 0.0

        self.base_buf        = deque(maxlen=BASE_VENTANA)
        self.base_activa     = True
        self.post_onset_cnt  = 0
        self.consec_sobre    = 0
        self._estado_inst    = None
        self.prediccion      = "–"
        self.confianza       = 0.0
        self.conteo          = {c: 0 for c in _CLASES_UI}
        self._bloqueada      = None
        self._bloqueo_fin    = 0.0

        # Estado de fusión diagonal
        self._fusion_pending = False
        self._fusion_primera = None
        self._fusion_conf    = 0.0
        self._fusion_fin     = 0.0
        self._fusion_t0      = 0.0
        self._fusion_timer   = None

        self._after_id  = None
        self._construir_ui()
        self._iniciar_grafica()
        self._tick()

    # ── Loop principal ────────────────────────────────────────────
    def _tick(self):
        if not self.activo:
            return
        try:
            try:
                while True:
                    msg = self.q.get_nowait()
                    self._procesar_mensaje(msg)
            except queue.Empty:
                pass
            datos = list(self.buf_graf)
            self.line_graf.set_ydata(datos)
            yabs = max(np.abs(datos).max(), 20) * 1.2
            self.ax.set_ylim(-yabs, yabs)
            self.canvas.draw()
            self._after_id = self.root.after(80, self._tick)
        except tk.TclError:
            pass

    def _procesar_mensaje(self, msg):
        tipo = msg[0]
        if tipo == "dato":
            pass
        elif tipo == "pred":
            _, direccion, confianza, enviar = msg
            self.prediccion = direccion
            self.confianza  = confianza
            color  = COLORES.get(direccion, COLORES["–"])
            flecha = FLECHAS.get(direccion, "–")
            self.lbl_flecha.config(text=flecha, fg=color)
            self.lbl_dir.config(text=direccion.upper() if direccion != "–" else "–", fg=color)
            self.lbl_conf.config(text=f"confianza: {confianza:.0%}")
            for clase, lbl in self.lbl_conteo.items():
                lbl.config(text=str(self.conteo.get(clase, 0)))
            if enviar:
                self.lbl_arduino.config(
                    text=f"Enviado: {COMANDOS[direccion].decode()} ({direccion})",
                    fg=SUCCESS)
        elif tipo == "pred_raw":
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
                                    fg=COLORES["–"], font=("Helvetica", 80, "bold"))
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
        for clase in _CLASES_UI:
            f = tk.Frame(col_res, bg=BG2)
            f.pack(fill="x", padx=20, pady=2)
            tk.Label(f, text=f"{FLECHAS[clase]} {clase}", bg=BG2,
                     fg=COLORES[clase], font=("Helvetica", 10)).pack(side="left")
            lbl = tk.Label(f, text="0", bg=BG2, fg=TEXT,
                           font=("Helvetica", 10, "bold"))
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

        self.lbl_instruccion = tk.Label(
            self.root, text="Conecta el Arduino para comenzar",
            bg="#0D0F14", fg=DIM,
            font=("Helvetica", 26, "bold"),
            wraplength=700, justify="center",
            padx=20, pady=12)
        self.lbl_instruccion.place(relx=0.42, rely=0.45, anchor="center")
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
        if self._estado_inst != key:
            self._estado_inst = key
            self.q.put(("instruccion", texto, color))

    # ── Hilo de lectura — IDÉNTICO a interfaz_eog.py ─────────────
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

            if self.base_activa:
                self.base_buf.append(valor)
                if len(self.base_buf) >= 50:
                    base_mean = np.mean(list(self.base_buf))
                    base_std  = max(np.std(list(self.base_buf)), 20)
                    umbral    = max(ONSET_MIN, ONSET_FACTOR * base_std)
                    if abs(valor - base_mean) > umbral:
                        self.consec_sobre += 1
                        if self.consec_sobre >= ONSET_CONSEC:
                            self.base_activa    = False
                            self.post_onset_cnt = 0
                            self.consec_sobre   = 0
                            self.buf_cls.clear()
                            self.n_nuevos = 0
                            self.votos.clear()
                    else:
                        self.consec_sobre = 0
            else:
                self.post_onset_cnt += 1
                if self.post_onset_cnt >= POST_ONSET:
                    self.base_activa    = True
                    self.post_onset_cnt = 0

            self.buf_cls.append(valor)
            self.n_nuevos += 1

            if self.n_nuevos >= PASO_CLS and len(self.buf_cls) == VENTANA_CLS:
                self.n_nuevos = 0
                self._votar()

    # ── Votación ─────────────────────────────────────────────────
    def _votar(self):
        if self._fusion_pending:
            if time.time() - self._fusion_t0 < FUSION_DELAY:
                return
            self._votar_segunda_fusion()
            return

        # Clasificación ML normal — IDÉNTICA a interfaz_eog.py
        try:
            feats     = extraer_features(list(self.buf_cls))
            pred_idx  = modelo.predict(feats)[0]
            proba     = modelo.predict_proba(feats)[0]
            confianza = proba.max()
            direccion = str(encoder.inverse_transform([pred_idx])[0])
        except Exception as e:
            self.q.put(("log", f"ERROR: {e}"))
            return

        seg_raw    = np.array(list(self.buf_cls), dtype=float)
        amp_abs_rt = float(np.abs(seg_raw - seg_raw.mean()).max())
        if direccion == "arriba" and amp_abs_rt < 1500:
            proba_tmp        = proba.copy()
            proba_tmp[pred_idx] = 0
            pred_idx  = int(proba_tmp.argmax())
            confianza = float(proba_tmp.max())
            direccion = str(encoder.inverse_transform([pred_idx])[0])

        ahora = time.time()
        if self._bloqueada and ahora < self._bloqueo_fin and direccion == self._bloqueada:
            direccion = "reposo"
        elif ahora >= self._bloqueo_fin:
            self._bloqueada = None

        voto = direccion if confianza >= CONF_MINIMA else "reposo"

        opuesta_voto = OPUESTAS.get(voto)
        if opuesta_voto and self.votos.count(opuesta_voto) > 0:
            voto = "reposo"

        HORIZONTALES = ("izquierda", "derecha")
        if voto == "abajo" and any(v in HORIZONTALES for v in self.votos):
            voto = "reposo"
        if voto == "arriba" and any(v in HORIZONTALES for v in self.votos):
            voto = "reposo"

        self.votos.append(voto)

        bloq = f" [bloq:{self._bloqueada}]" if self._bloqueada else ""
        resumen = f"votos: {list(self.votos)}  conf={confianza:.0%}  amp={amp_abs_rt:.0f}{bloq}"
        self.q.put(("log", resumen))

        if (len(self.votos) == VOTOS and ahora - self.ultimo_cmd > COOLDOWN):
            for clase in ("izquierda", "derecha", "arriba", "abajo"):
                if self.votos.count(clase) >= VOTOS_OK:
                    self._disparar(clase, confianza)
                    self.votos.clear()
                    break

    def _votar_segunda_fusion(self):
        """Segundo movimiento post-horizontal/abajo: usa ML pero solo acepta dirección ortogonal."""
        if len(self.buf_cls) < VENTANA_CLS:
            return
        try:
            feats     = extraer_features(list(self.buf_cls))
            pred_idx  = modelo.predict(feats)[0]
            proba     = modelo.predict_proba(feats)[0]
            confianza = proba.max()
            direccion = str(encoder.inverse_transform([pred_idx])[0])
        except Exception as e:
            self.q.put(("log", f"ERROR fusión2: {e}"))
            return

        primera = self._fusion_primera
        validas = ("arriba", "abajo")

        voto = direccion if (confianza >= CONF_MINIMA and direccion in validas) else "reposo"
        self.votos.append(voto)
        ahora = time.time()
        self.q.put(("log", f"fusión2 votos: {list(self.votos)}  conf={confianza:.0%}"))

        if (len(self.votos) == VOTOS and ahora - self.ultimo_cmd > COOLDOWN):
            for clase in validas:
                if self.votos.count(clase) >= VOTOS_OK:
                    self._disparar(clase, confianza)
                    self.votos.clear()
                    break

    # ── Fusión y envío ────────────────────────────────────────────
    def _disparar(self, direccion, confianza):
        """Detectó un movimiento. Si hay ventana abierta, intenta combinar."""
        ahora = time.time()

        if self._fusion_pending and ahora < self._fusion_fin:
            diagonal = _DIAGONALES.get((self._fusion_primera, direccion))
            if diagonal:
                if self._fusion_timer:
                    self._fusion_timer.cancel()
                    self._fusion_timer = None
                self._fusion_pending = False
                self._enviar(diagonal, max(confianza, self._fusion_conf))
            # Si no hay combinación válida (mismo eje), ignorar
            return

        # Solo lateral abre ventana de fusión; arriba/abajo emiten directo
        if direccion not in ("izquierda", "derecha"):
            self._enviar(direccion, confianza)
            return

        self._fusion_pending = True
        self._fusion_primera = direccion
        self._fusion_conf    = confianza
        self._fusion_fin     = ahora + FUSION_WINDOW
        self._fusion_t0      = ahora

        self.buf_cls.clear()
        self.base_buf.clear()
        self.n_nuevos       = 0
        self.votos.clear()
        self.base_activa    = True
        self.post_onset_cnt = 0
        self.consec_sobre   = 0

        hint = f"{FLECHAS[direccion]}  ¿diagonal?  Mira ↑ o ↓ ahora..."
        self._estado_inst = None
        self._instruccion(f"fusion_{direccion}", hint, COLORES.get(direccion, DIM))
        self.q.put(("log", f"Ventana fusión: {direccion} — {FUSION_WINDOW}s"))

        if self._fusion_timer:
            self._fusion_timer.cancel()
        self._fusion_timer = threading.Timer(
            FUSION_WINDOW, self._fusion_fallback, args=[direccion, confianza])
        self._fusion_timer.daemon = True
        self._fusion_timer.start()

    def _fusion_fallback(self, direccion, confianza):
        """Timer expiró sin segundo movimiento — emitir el simple."""
        if self._fusion_pending and self._fusion_primera == direccion:
            self._fusion_pending = False
            self._fusion_timer   = None
            self._enviar(direccion, confianza)

    def _enviar(self, direccion, confianza):
        """Emite el comando al Arduino y actualiza la UI."""
        self.ultimo_cmd = time.time()
        self.conteo[direccion] = self.conteo.get(direccion, 0) + 1
        color = COLORES.get(direccion, COLORES["–"])

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

        def volver_listo():
            time.sleep(COOLDOWN)
            if self.leyendo:
                if self.ser:
                    try:
                        self.ser.write(b'C')
                    except Exception:
                        pass
                self._estado_inst = None
                self._instruccion("listo", "Mueve el ojo cuando quieras   →  ←  ●", SUCCESS)
        threading.Thread(target=volver_listo, daemon=True).start()

    # ── Cierre limpio ─────────────────────────────────────────────
    def cerrar(self):
        self.activo  = False
        self.leyendo = False
        if self._fusion_timer:
            self._fusion_timer.cancel()
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
    _cargador = _Cargador()
    modelo    = _cargador.modelo
    encoder   = _cargador.encoder
    if modelo is None:
        sys.exit(1)

    import numpy as np
    from scipy import stats
    import pickle
    import serial
    import serial.tools.list_ports
    import matplotlib
    matplotlib.use("TkAgg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

    root = tk.Tk()
    app  = AppEOG(root)
    root.protocol("WM_DELETE_WINDOW", app.cerrar)
    signal.signal(signal.SIGINT, lambda *_: root.after(0, app.cerrar))
    root.mainloop()

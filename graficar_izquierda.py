"""
Grafica las muestras de izquierda con slider para navegar.
Uso: python3 graficar_izquierda.py [archivo.csv]
"""

import sys
import os
import csv
import glob
import matplotlib.pyplot as plt
import matplotlib.widgets as widgets
import numpy as np

# ── Buscar archivo ─────────────────────────────────────────────────
if len(sys.argv) > 1:
    archivo = sys.argv[1]
else:
    csvs = sorted(glob.glob(os.path.join(os.path.dirname(__file__), "*.csv")),
                  key=os.path.getmtime, reverse=True)
    if not csvs:
        print("No se encontró ningún CSV.")
        sys.exit(1)
    archivo = csvs[0]
    print(f"Usando: {archivo}")

# ── Leer datos ─────────────────────────────────────────────────────
timestamps, señal = [], []
with open(archivo, newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row["etiqueta"].strip() == "izquierda":
            try:
                timestamps.append(int(row["timestamp_ms"]))
                señal.append(float(row["H"]))
            except ValueError:
                pass

if not señal:
    print("No hay filas con etiqueta 'izquierda'.")
    sys.exit(1)

señal  = np.array(señal)
n_pts  = len(señal)
t_rel  = np.array(timestamps) - timestamps[0]

# ── Detectar muestras (gap > 500ms) ───────────────────────────────
gaps       = np.where(np.diff(t_rel) > 500)[0] + 1
bordes     = np.concatenate([[0], gaps, [n_pts]])
muestras   = [señal[bordes[i]:bordes[i+1]] for i in range(len(bordes)-1)]
n_muestras = len(muestras)
print(f"Muestras: {n_muestras}  |  Puntos: {n_pts}")

# ── Paleta ────────────────────────────────────────────────────────
BG     = "#0D0F14"
BG2    = "#151820"
ACCENT = "#00E5FF"
SEP    = "#FF6B6B"
TEXT   = "#E8EAF0"
DIM    = "#6B7280"

y_abs = np.abs(señal).max()
y_lim = max(y_abs * 1.15, 20)

# ══════════════════════════════════════════════════════════════════
# FIGURA 1 — Vista continua con slider
# ══════════════════════════════════════════════════════════════════
ventana = min(500, n_pts)
fig1, ax1 = plt.subplots(figsize=(14, 5), facecolor=BG)
fig1.subplots_adjust(bottom=0.18)
fig1.suptitle(f"Izquierda — {os.path.basename(archivo)}  ({n_muestras} muestras, {n_pts} pts)",
              color=TEXT, fontsize=11, fontweight="bold")
ax1.set_facecolor(BG2)
for sp in ax1.spines.values(): sp.set_edgecolor(DIM)
ax1.tick_params(colors=DIM)
ax1.set_ylabel("amplitud", color=DIM, fontsize=9)
ax1.set_xlabel("punto", color=DIM, fontsize=9)
ax1.axhline(0, color=DIM, linewidth=0.5, linestyle="--")
ax1.set_ylim(-y_lim, y_lim)

x_all = np.arange(n_pts)
line1, = ax1.plot(x_all[:ventana], señal[:ventana], color=ACCENT, linewidth=0.8)

sep_lines = []
for g in gaps:
    sl = ax1.axvline(g, color=SEP, linewidth=0.6, alpha=0.5)
    sep_lines.append((g, sl))
    sl.set_visible(g < ventana)

ax1.set_xlim(0, ventana)

ax_sl = fig1.add_axes([0.1, 0.05, 0.8, 0.04], facecolor=BG2)
slider = widgets.Slider(ax_sl, "", 0, max(n_pts - ventana, 1),
                        valinit=0, valstep=1, color=ACCENT)
slider.label.set_color(DIM)
slider.valtext.set_color(DIM)
ax_sl.text(0.5, 1.5, "◀  desliza para navegar  ▶",
           transform=ax_sl.transAxes, ha="center", color=DIM, fontsize=8)

def update_slider(val):
    ini, fin = int(slider.val), int(slider.val) + ventana
    line1.set_xdata(x_all[ini:fin])
    line1.set_ydata(señal[ini:fin])
    ax1.set_xlim(ini, fin)
    for g, sl in sep_lines:
        sl.set_visible(ini <= g <= fin)
    fig1.canvas.draw_idle()

slider.on_changed(update_slider)

plt.figure(fig1.number)
plt.savefig(os.path.join(os.path.dirname(archivo),
            f"izquierda_{os.path.splitext(os.path.basename(archivo))[0]}.png"),
            dpi=150, bbox_inches="tight", facecolor=BG)
print("Imagen guardada.")

# ══════════════════════════════════════════════════════════════════
# FIGURA 2 — Una muestra a la vez, pantalla completa
# ══════════════════════════════════════════════════════════════════
idx = [0]  # índice mutable

fig2, ax2 = plt.subplots(figsize=(14, 7), facecolor=BG)
fig2.subplots_adjust(bottom=0.15, left=0.08, right=0.92)
fig2.canvas.manager.set_window_title("Muestras individuales")

ax2.set_facecolor(BG2)
for sp in ax2.spines.values(): sp.set_edgecolor(DIM)
ax2.tick_params(colors=DIM, labelsize=10)
ax2.set_ylabel("amplitud", color=DIM, fontsize=11)
ax2.set_xlabel("punto", color=DIM, fontsize=11)
ax2.axhline(0, color=DIM, linewidth=0.7, linestyle="--")
ax2.set_ylim(-y_lim, y_lim)

seg0 = muestras[0]
line2, = ax2.plot(np.arange(len(seg0)), seg0, color=ACCENT, linewidth=1.5)
titulo2 = fig2.suptitle("", color=TEXT, fontsize=14, fontweight="bold")

def dibujar_muestra(i):
    seg = muestras[i]
    x_seg = np.arange(len(seg))
    line2.set_xdata(x_seg)
    line2.set_ydata(seg)
    ax2.set_xlim(0, max(len(seg) - 1, 1))
    titulo2.set_text(f"Izquierda — muestra {i+1} / {n_muestras}   ({len(seg)} pts)")
    fig2.canvas.draw_idle()

dibujar_muestra(0)

# Botones ◀ ▶
ax_prev = fig2.add_axes([0.35, 0.03, 0.12, 0.06], facecolor=BG2)
ax_next = fig2.add_axes([0.53, 0.03, 0.12, 0.06], facecolor=BG2)

btn_prev = widgets.Button(ax_prev, "◀  Anterior", color=BG2, hovercolor="#1E2230")
btn_next = widgets.Button(ax_next, "Siguiente  ▶", color=BG2, hovercolor="#1E2230")
btn_prev.label.set_color(TEXT)
btn_next.label.set_color(TEXT)

def prev_muestra(event):
    idx[0] = (idx[0] - 1) % n_muestras
    dibujar_muestra(idx[0])

def next_muestra(event):
    idx[0] = (idx[0] + 1) % n_muestras
    dibujar_muestra(idx[0])

btn_prev.on_clicked(prev_muestra)
btn_next.on_clicked(next_muestra)

# Teclas ← →
def on_key(event):
    if event.key == "right":
        next_muestra(None)
    elif event.key == "left":
        prev_muestra(None)

fig2.canvas.mpl_connect("key_press_event", on_key)

try:
    fig2.canvas.manager.window.showMaximized()
except Exception:
    pass

plt.show()

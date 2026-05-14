"""
Grafica las muestras de reposo con slider para navegar.
Uso: python3 graficar_reposo.py [archivo.csv]
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
        if row["etiqueta"].strip() == "reposo":
            try:
                timestamps.append(int(row["timestamp_ms"]))
                señal.append(float(row["H"]))
            except ValueError:
                pass

if not señal:
    print("No hay filas con etiqueta 'reposo'.")
    sys.exit(1)

señal = np.array(señal)
n_pts = len(señal)

# ── Detectar límites de muestras ──────────────────────────────────
t_rel = np.array(timestamps) - timestamps[0]
gaps  = np.where(np.diff(t_rel) > 500)[0] + 1
n_muestras = len(gaps) + 1
print(f"Muestras: {n_muestras}  |  Puntos: {n_pts}")

# ── Paleta ────────────────────────────────────────────────────────
BG     = "#0D0F14"
BG2    = "#151820"
ACCENT = "#00E5FF"
SEP    = "#FF6B6B"
TEXT   = "#E8EAF0"
DIM    = "#6B7280"

# ── Ventana visible (puntos) ──────────────────────────────────────
ventana = min(500, n_pts)

# ── Figura ────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(14, 5), facecolor=BG)
fig.subplots_adjust(bottom=0.18)
fig.suptitle(f"Reposo — {os.path.basename(archivo)}  ({n_muestras} muestras, {n_pts} pts)",
             color=TEXT, fontsize=11, fontweight="bold")

ax.set_facecolor(BG2)
for spine in ax.spines.values():
    spine.set_edgecolor(DIM)
ax.tick_params(colors=DIM)
ax.set_ylabel("amplitud", color=DIM, fontsize=9)
ax.set_xlabel("punto", color=DIM, fontsize=9)

# Señal y líneas separadoras
x = np.arange(n_pts)
line, = ax.plot(x[:ventana], señal[:ventana], color=ACCENT, linewidth=0.8)
ax.axhline(0, color=DIM, linewidth=0.5, linestyle="--")

sep_lines = []
for g in gaps:
    if g < ventana:
        sl = ax.axvline(g, color=SEP, linewidth=0.6, alpha=0.5)
        sep_lines.append((g, sl))

y_abs = np.abs(señal).max()
y_lim = max(y_abs * 1.15, 20)
ax.set_ylim(-y_lim, y_lim)
ax.set_xlim(0, ventana)

# ── Slider ────────────────────────────────────────────────────────
ax_slider = fig.add_axes([0.1, 0.05, 0.8, 0.04], facecolor=BG2)
slider = widgets.Slider(ax_slider, "", 0, max(n_pts - ventana, 1),
                        valinit=0, valstep=1, color=ACCENT)
slider.label.set_color(DIM)
slider.valtext.set_color(DIM)
ax_slider.text(0.5, 1.5, "◀  desliza para navegar  ▶",
               transform=ax_slider.transAxes,
               ha="center", color=DIM, fontsize=8)

def update(val):
    ini = int(slider.val)
    fin = ini + ventana
    line.set_xdata(x[ini:fin])
    line.set_ydata(señal[ini:fin])
    ax.set_xlim(ini, fin)
    # actualizar separadores
    for g, sl in sep_lines:
        sl.set_visible(ini <= g <= fin)
    fig.canvas.draw_idle()

slider.on_changed(update)

plt.savefig(os.path.join(os.path.dirname(archivo),
            f"reposo_{os.path.splitext(os.path.basename(archivo))[0]}.png"),
            dpi=150, bbox_inches="tight", facecolor=BG)
print("Imagen guardada.")
plt.show()

"""
Entrena el clasificador EOG con los CSV de cada dirección.
Uso: python3 entrenar_eog.py
Genera: modelo_eog.pkl  y  encoder_eog.pkl
"""

import os, csv, pickle
import numpy as np
from scipy import stats
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import classification_report, confusion_matrix

BASE = os.path.dirname(os.path.abspath(__file__))

ARCHIVOS = {
    "izquierda": os.path.join(BASE, "IZQUIERDA.csv"),
    "derecha":   os.path.join(BASE, "DERECHA.csv"),
    "reposo":    os.path.join(BASE, "REPOSO.csv"),
    "arriba":    os.path.join(BASE, "ARRIBA.csv"),
    "abajo":     os.path.join(BASE, "ABAJO.csv"),
    "parpadeo":  os.path.join(BASE, "PARPADEO.csv"),
}

VENTANA = 80   # puntos por ventana (mismo que tiempo real)
PASO    = 15   # paso del sliding window

# Escalas por clase — arriba no baja de 0.7 para mantener separación de amplitud con parpadeo
ESCALAS = {
    "izquierda": [0.7, 0.85, 1.0],
    "derecha":   [0.7, 0.85, 1.0],
    "arriba":    [0.7, 0.85, 1.0],
    "abajo":     [0.7, 0.85, 1.0],
    "reposo":    [1.0],
    "parpadeo":  [1.0],
}

# ── Cargar y segmentar por gaps > 500 ms ──────────────────────────
def cargar_adquisiciones(etiqueta, archivo):
    timestamps, señal = [], []
    with open(archivo, newline="") as f:
        for row in csv.DictReader(f):
            try:
                timestamps.append(int(row["timestamp_ms"]))
                señal.append(float(row["H"]))
            except ValueError:
                pass
    if not señal:
        return []
    t = np.array(timestamps)
    s = np.array(señal)
    gaps = np.where(np.diff(t) > 500)[0] + 1
    bordes = np.concatenate([[0], gaps, [len(s)]])
    return [(etiqueta, s[bordes[i]:bordes[i+1]])
            for i in range(len(bordes)-1) if bordes[i+1]-bordes[i] >= VENTANA]

# ── Características por ventana ───────────────────────────────────
def extraer_features(seg):
    seg = np.array(seg, dtype=float)
    seg = seg - seg.mean()          # eliminar offset DC

    rango  = seg.max() - seg.min()
    seg_n  = seg / rango if rango > 0 else seg
    fft    = np.abs(np.fft.rfft(seg_n))
    n      = len(fft)
    e_baja = fft[:max(1, n//8)].mean()
    e_alta = fft[max(1, n//8):].mean()

    primera = seg[:25].mean()
    ultima  = seg[-25:].mean()

    # Dirección del pico: >0.5 = deflexión positiva, <0.5 = negativa
    dir_pico = seg.max() / rango if rango > 0 else 0.5

    # Features de forma
    deriv        = np.diff(seg_n)
    vel_max      = np.abs(deriv).max()
    deriv_std    = deriv.std()
    mid          = len(seg_n) // 2
    asimetria    = seg_n[:mid].std() / (seg_n[mid:].std() + 1e-6)
    pico_idx     = np.argmax(np.abs(seg_n))
    pos_pico_abs = pico_idx / len(seg_n)
    media_segunda = seg_n[mid:].mean()

    pend_subida = seg_n[pico_idx] / pico_idx if pico_idx > 0 else 0.0
    resto = len(seg_n) - pico_idx
    pend_bajada = (seg_n[-1] - seg_n[pico_idx]) / resto if resto > 1 else 0.0

    # "Sostenida": fracción del tiempo que la señal está por encima del 30% del pico
    sostenida = (np.abs(seg_n) > 0.3).mean()

    # Kurtosis: pico agudo = alta, señal sostenida = baja
    kurt = stats.kurtosis(seg_n)

    # ── Dirección de tendencia normalizada ────────────────────────
    n_ext = max(1, len(seg_n) // 8)        # ~12 % de la ventana (≈10 muestras en VENTANA=80)
    inicio_n    = seg_n[:n_ext].mean()
    fin_n       = seg_n[-n_ext:].mean()
    tendencia_n = fin_n - inicio_n          # >0 = señal sube; <0 = señal baja

    # Pendiente media por cuartos
    cuarto = max(1, len(deriv) // 4)
    deriv_inicio = deriv[:cuarto].mean()
    deriv_final  = deriv[-cuarto:].mean()

    # ── Features cuartos normalizados ────────────────────────────
    n_q = max(1, len(seg_n) // 4)
    q2_n       = seg_n[n_q:2*n_q].mean()
    rango_q1_n = seg_n[:n_q].max() - seg_n[:n_q].min()

    # Nivel final e inicial normalizados (explícitos, sin la resta de tendencia_n)
    # fin_n distingue abajo (muy negativo al final) de arriba/izquierda (positivo)
    # inicio_n distingue arriba/izquierda (negativo) de derecha/abajo (positivo)
    fin_n_feat   = fin_n     # ya calculado arriba
    inicio_n_feat = inicio_n  # ya calculado arriba

    # Amplitud absoluta — discrimina arriba (>>9000) del resto (<2000)
    amp_abs        = np.abs(seg).max()          # pico absoluto
    amp_media      = np.mean(np.abs(seg))       # amplitud media sostenida
    amp_sobre_3000 = float(amp_abs > 3000)      # 1.0 solo si es arriba-nivel

    return [
        seg.max(),
        seg.min(),
        rango,
        seg.std(),
        seg.argmax() / len(seg),
        seg.argmin() / len(seg),
        np.sum(seg**2) / len(seg),
        np.sum(np.diff(np.sign(seg)) != 0),
        np.percentile(seg, 25),
        np.percentile(seg, 75),
        np.median(seg),
        e_baja,
        e_alta,
        primera,
        ultima,
        primera - ultima,
        vel_max,
        deriv_std,
        asimetria,
        pos_pico_abs,
        dir_pico,
        media_segunda,
        sostenida,
        kurt,
        pend_subida,
        pend_bajada,
        tendencia_n,
        deriv_inicio,
        deriv_final,
        q2_n,
        rango_q1_n,
        fin_n_feat,
        inicio_n_feat,
        amp_abs,
        amp_media,
        amp_sobre_3000,
    ]

FEATURE_NAMES = [
    "max", "min", "rango", "std",
    "pos_pico_pos", "pos_pico_neg", "energia", "cruces_cero",
    "p25", "p75", "mediana", "e_baja", "e_alta",
    "primera", "ultima", "cambio",
    "vel_max", "deriv_std", "asimetria", "pos_pico_abs",
    "dir_pico", "media_segunda",
    "sostenida", "kurtosis",
    "pend_subida", "pend_bajada",
    "tendencia_n", "deriv_inicio", "deriv_final",
    "q2_n", "rango_q1_n",
    "fin_n", "inicio_n",
    "amp_abs", "amp_media", "amp_sobre_3000",
]

# ── Construir dataset con sliding windows ─────────────────────────
print("Cargando datos y generando ventanas...")
X_rows, y_rows = [], []

for etiqueta, archivo in ARCHIVOS.items():
    if not os.path.exists(archivo):
        print(f"  {etiqueta}: archivo no encontrado, se omite")
        continue
    adqs = cargar_adquisiciones(etiqueta, archivo)
    n_ventanas = 0
    for (lab, seg) in adqs:
        n = len(seg)
        # Reposo/parpadeo: segmento completo.
        # Arriba: garantiza al menos 2 ventanas de onset incluso para segmentos cortos
        #   usando max(VENTANA+PASO+1, n//2). Evita fases medias/retorno que se
        #   solapan con izquierda y abajo (el n-40 causaba falsas predicciones).
        # Otros movimientos: primera mitad (fase de onset).
        if lab in ("reposo", "parpadeo"):
            limite = n
        elif lab == "arriba":
            limite = min(n, max(VENTANA + PASO + 1, n // 2))
        else:
            limite = n // 2

        escalas    = ESCALAS.get(lab, [1.0])
        media_base = seg.mean()

        for escala in escalas:
            # Escalar amplitud alrededor de la media para simular movimientos débiles
            seg_aug = media_base + (seg - media_base) * escala
            for inicio in range(0, limite - VENTANA + 1, PASO):
                ventana = seg_aug[inicio:inicio + VENTANA]
                X_rows.append(extraer_features(ventana))
                y_rows.append(str(lab))
                n_ventanas += 1

    print(f"  {etiqueta}: {len(adqs)} adqs → {n_ventanas} ventanas (con augmentación)")

X  = np.array(X_rows)
le = LabelEncoder()
y  = le.fit_transform(y_rows)
print(f"\nTotal ventanas: {len(y)}  |  Clases: {list(le.classes_)}\n")

# ── Validación cruzada ────────────────────────────────────────────
modelo_cv = RandomForestClassifier(n_estimators=300, min_samples_leaf=2,
                                    class_weight="balanced",
                                    random_state=42, n_jobs=-1)
cv     = StratifiedKFold(n_splits=10, shuffle=True, random_state=42)
scores = cross_val_score(modelo_cv, X, y, cv=cv, scoring="accuracy")
print(f"Validación cruzada (10-fold):")
print(f"  Accuracy media : {scores.mean()*100:.1f}%")
print(f"  Desviación std : {scores.std()*100:.1f}%\n")

# ── Entrenar modelo final ─────────────────────────────────────────
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.15, stratify=y, random_state=42)

modelo = RandomForestClassifier(n_estimators=300, min_samples_leaf=2,
                                 class_weight="balanced",
                                 random_state=42, n_jobs=-1)
modelo.fit(X_train, y_train)

print("── Reporte en conjunto de prueba (15%) ───────────────────")
print(classification_report(y_test, modelo.predict(X_test),
                              target_names=le.classes_))

print("── Matriz de confusión ───────────────────────────────────")
cm = confusion_matrix(y_test, modelo.predict(X_test))
print(f"{'':12}", "  ".join(f"{c:>9}" for c in le.classes_))
for i, fila in enumerate(cm):
    print(f"{le.classes_[i]:12}", "  ".join(f"{v:>9}" for v in fila))

print("\n── Importancia de características ───────────────────────")
for nombre, imp in sorted(zip(FEATURE_NAMES, modelo.feature_importances_),
                           key=lambda x: -x[1]):
    print(f"  {nombre:16} {imp:.3f}  {'█' * int(imp * 40)}")

with open(os.path.join(BASE, "modelo_eog.pkl"), "wb") as f:
    pickle.dump(modelo, f, protocol=pickle.HIGHEST_PROTOCOL)
with open(os.path.join(BASE, "encoder_eog.pkl"), "wb") as f:
    pickle.dump(le, f, protocol=pickle.HIGHEST_PROTOCOL)
print(f"\nModelo guardado: modelo_eog.pkl  |  encoder_eog.pkl")

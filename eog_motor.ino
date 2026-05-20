// ═══════════════════════════════════════════════════════════════
//  EOG + Control de Motor — un solo sketch
//  - Envía señal EOG por Serial a Python para clasificación
//  - Recibe comandos de Python (L/R/U/D/C) y mueve el motor
// ═══════════════════════════════════════════════════════════════

// ── Pines EOG ─────────────────────────────────────────────────
const int EOG_PIN = A0;

// ── Pines motor (ajusta según tu driver) ──────────────────────
#define PIN_IZQ    8
#define PIN_DER    9
#define PIN_ARRIBA 10
#define PIN_ABAJO  11
#define PIN_ENABLE 6    // PWM velocidad

const int VELOCIDAD = 180;

// ── Variables EOG ─────────────────────────────────────────────
float baseline = 0;
float filtrado  = 0;

// ── Flags de dirección ────────────────────────────────────────
bool moverIzquierda = 0;
bool moverDerecha   = 0;
bool moverArriba    = 0;
bool moverAbajo     = 0;

// ─────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);

  // Calibrar baseline EOG
  long suma = 0;
  for (int i = 0; i < 500; i++) {
    suma += analogRead(EOG_PIN);
    delay(5);
  }
  baseline = suma / 500.0;

  // Pines motor
  pinMode(PIN_IZQ,    OUTPUT);
  pinMode(PIN_DER,    OUTPUT);
  pinMode(PIN_ARRIBA, OUTPUT);
  pinMode(PIN_ABAJO,  OUTPUT);
  pinMode(PIN_ENABLE, OUTPUT);
  detener();
}

// ─────────────────────────────────────────────────────────────
void loop() {
  // 1) Leer y enviar señal EOG a Python
  int raw           = analogRead(EOG_PIN);
  float signal      = raw - baseline;
  filtrado          = 0.9 * filtrado + 0.1 * signal;
  float amplificada = filtrado * 20;

  Serial.print(amplificada);
  Serial.print(",");
  Serial.println(amplificada);

  // 2) Leer comando de Python si llegó uno
  if (Serial.available()) {
    char cmd = Serial.read();
    resetFlags();
    if      (cmd == 'L') moverIzquierda = 1;
    else if (cmd == 'R') moverDerecha   = 1;
    else if (cmd == 'U') moverArriba    = 1;
    else if (cmd == 'D') moverAbajo     = 1;
    // 'C' deja todo en 0 → detener
  }

  // 3) Aplicar flags al motor
  if      (moverIzquierda) girarIzquierda();
  else if (moverDerecha)   girarDerecha();
  else if (moverArriba)    subirArriba();
  else if (moverAbajo)     bajarAbajo();
  else                     detener();

  delay(5); // ~200 Hz
}

// ── Acciones de motor ─────────────────────────────────────────
void girarIzquierda() {
  analogWrite(PIN_ENABLE, VELOCIDAD);
  digitalWrite(PIN_IZQ,    HIGH);
  digitalWrite(PIN_DER,    LOW);
  digitalWrite(PIN_ARRIBA, LOW);
  digitalWrite(PIN_ABAJO,  LOW);
}

void girarDerecha() {
  analogWrite(PIN_ENABLE, VELOCIDAD);
  digitalWrite(PIN_IZQ,    LOW);
  digitalWrite(PIN_DER,    HIGH);
  digitalWrite(PIN_ARRIBA, LOW);
  digitalWrite(PIN_ABAJO,  LOW);
}

void subirArriba() {
  analogWrite(PIN_ENABLE, VELOCIDAD);
  digitalWrite(PIN_IZQ,    LOW);
  digitalWrite(PIN_DER,    LOW);
  digitalWrite(PIN_ARRIBA, HIGH);
  digitalWrite(PIN_ABAJO,  LOW);
}

void bajarAbajo() {
  analogWrite(PIN_ENABLE, VELOCIDAD);
  digitalWrite(PIN_IZQ,    LOW);
  digitalWrite(PIN_DER,    LOW);
  digitalWrite(PIN_ARRIBA, LOW);
  digitalWrite(PIN_ABAJO,  HIGH);
}

void detener() {
  analogWrite(PIN_ENABLE, 0);
  digitalWrite(PIN_IZQ,    LOW);
  digitalWrite(PIN_DER,    LOW);
  digitalWrite(PIN_ARRIBA, LOW);
  digitalWrite(PIN_ABAJO,  LOW);
}

void resetFlags() {
  moverIzquierda = 0;
  moverDerecha   = 0;
  moverArriba    = 0;
  moverAbajo     = 0;
}

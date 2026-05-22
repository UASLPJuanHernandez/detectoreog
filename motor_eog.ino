// ── Pines motor (ajusta según tu driver) ──────────────────────────
#define PIN_IZQ   8
#define PIN_DER   9
#define PIN_ARRIBA  10
#define PIN_ABAJO   11
#define PIN_ENABLE  6   // PWM para velocidad (si tu driver lo soporta)

// ── Velocidad (0-255) ─────────────────────────────────────────────
const int VELOCIDAD = 180;

// ── Flags de dirección — pon 1 para activar, 0 para detener ───────
// Cuando el EOG esté listo, estas variables las escribirá la lógica
// de clasificación por Serial en lugar de definirlas aquí a mano.
bool moverIzquierda = 0;
bool moverDerecha   = 0;
bool moverArriba    = 0;
bool moverAbajo     = 0;

// ─────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);

  pinMode(PIN_IZQ,    OUTPUT);
  pinMode(PIN_DER,    OUTPUT);
  pinMode(PIN_ARRIBA, OUTPUT);
  pinMode(PIN_ABAJO,  OUTPUT);
  pinMode(PIN_ENABLE, OUTPUT);

  detener();
  Serial.println("Motor listo. Esperando comandos...");
}

// ─────────────────────────────────────────────────────────────────
void loop() {
  // Leer comandos desde Serial (enviados por interfaz_eog.py)
  // L = izquierda | R = derecha | U = arriba | D = abajo | C = centro
  if (Serial.available()) {
    char cmd = Serial.read();
    resetFlags();
    if      (cmd == 'L') moverIzquierda = 1;
    else if (cmd == 'R') moverDerecha   = 1;
    else if (cmd == 'U') moverArriba    = 1;
    else if (cmd == 'D') moverAbajo     = 1;
    // 'C' deja todo en 0 → detener
  }

  // Aplicar flags al motor
  if      (moverIzquierda) girarIzquierda();
  else if (moverDerecha)   girarDerecha();
  else if (moverArriba)    subirArriba();
  else if (moverAbajo)     bajarAbajo();
  else                     detener();
}

// ── Acciones de motor ─────────────────────────────────────────────
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

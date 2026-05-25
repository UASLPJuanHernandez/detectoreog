// ═══════════════════════════════════════════════════════════════
//  EOG + Control de Motor — con soporte de diagonales
//  Comandos recibidos de Python:
//    L = izquierda      R = derecha
//    U = arriba         D = abajo
//    Q = arriba-izq ↖   E = arriba-der ↗
//    Z = abajo-izq  ↙   X = abajo-der  ↘
//    C = centro (detener)
// ═══════════════════════════════════════════════════════════════

// ── Pines EOG ─────────────────────────────────────────────────
const int EOG_PIN = A0;

// ── Pines motor ───────────────────────────────────────────────
#define PIN_IZQ    8
#define PIN_DER    9
#define PIN_ARRIBA 10
#define PIN_ABAJO  11
#define PIN_ENABLE 6

const int VELOCIDAD = 180;

// ── Variables EOG ─────────────────────────────────────────────
float baseline = 0;
float filtrado  = 0;

// ── Flags de dirección ────────────────────────────────────────
bool moverIzquierda = false;
bool moverDerecha   = false;
bool moverArriba    = false;
bool moverAbajo     = false;

// ─────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);

  long suma = 0;
  for (int i = 0; i < 500; i++) {
    suma += analogRead(EOG_PIN);
    delay(5);
  }
  baseline = suma / 500.0;

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
  int raw      = analogRead(EOG_PIN);
  float signal = raw - baseline;
  filtrado     = 0.9 * filtrado + 0.1 * signal;
  float amp    = filtrado * 20;

  Serial.print(amp);
  Serial.print(",");
  Serial.println(amp);

  // 2) Leer comando de Python
  if (Serial.available()) {
    char cmd = Serial.read();
    resetFlags();
    if      (cmd == 'L') { moverIzquierda = true; }
    else if (cmd == 'R') { moverDerecha   = true; }
    else if (cmd == 'U') { moverArriba    = true; }
    else if (cmd == 'D') { moverAbajo     = true; }
    else if (cmd == 'Q') { moverIzquierda = true; moverArriba = true; }  // ↖
    else if (cmd == 'E') { moverDerecha   = true; moverArriba = true; }  // ↗
    else if (cmd == 'Z') { moverIzquierda = true; moverAbajo  = true; }  // ↙
    else if (cmd == 'X') { moverDerecha   = true; moverAbajo  = true; }  // ↘
    // 'C' deja todos en false → detener
  }

  // 3) Aplicar al motor — diagonales primero
  if      (moverIzquierda && moverArriba) diagonalArribaIzquierda();
  else if (moverDerecha   && moverArriba) diagonalArribaDerecha();
  else if (moverIzquierda && moverAbajo)  diagonalAbajoIzquierda();
  else if (moverDerecha   && moverAbajo)  diagonalAbajoDerecha();
  else if (moverIzquierda)               girarIzquierda();
  else if (moverDerecha)                 girarDerecha();
  else if (moverArriba)                  subirArriba();
  else if (moverAbajo)                   bajarAbajo();
  else                                   detener();

  delay(5); // ~200 Hz
}

// ── Movimientos simples ───────────────────────────────────────
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

// ── Movimientos diagonales ────────────────────────────────────
void diagonalArribaDerecha() {   // ↗  E
  analogWrite(PIN_ENABLE, VELOCIDAD);
  digitalWrite(PIN_IZQ,    LOW);
  digitalWrite(PIN_DER,    HIGH);
  digitalWrite(PIN_ARRIBA, HIGH);
  digitalWrite(PIN_ABAJO,  LOW);
}

void diagonalArribaIzquierda() { // ↖  Q
  analogWrite(PIN_ENABLE, VELOCIDAD);
  digitalWrite(PIN_IZQ,    HIGH);
  digitalWrite(PIN_DER,    LOW);
  digitalWrite(PIN_ARRIBA, HIGH);
  digitalWrite(PIN_ABAJO,  LOW);
}

void diagonalAbajoDerecha() {    // ↘  X
  analogWrite(PIN_ENABLE, VELOCIDAD);
  digitalWrite(PIN_IZQ,    LOW);
  digitalWrite(PIN_DER,    HIGH);
  digitalWrite(PIN_ARRIBA, LOW);
  digitalWrite(PIN_ABAJO,  HIGH);
}

void diagonalAbajoIzquierda() {  // ↙  Z
  analogWrite(PIN_ENABLE, VELOCIDAD);
  digitalWrite(PIN_IZQ,    HIGH);
  digitalWrite(PIN_DER,    LOW);
  digitalWrite(PIN_ARRIBA, LOW);
  digitalWrite(PIN_ABAJO,  HIGH);
}

// ─────────────────────────────────────────────────────────────
void detener() {
  analogWrite(PIN_ENABLE, 0);
  digitalWrite(PIN_IZQ,    LOW);
  digitalWrite(PIN_DER,    LOW);
  digitalWrite(PIN_ARRIBA, LOW);
  digitalWrite(PIN_ABAJO,  LOW);
}

void resetFlags() {
  moverIzquierda = false;
  moverDerecha   = false;
  moverArriba    = false;
  moverAbajo     = false;
}

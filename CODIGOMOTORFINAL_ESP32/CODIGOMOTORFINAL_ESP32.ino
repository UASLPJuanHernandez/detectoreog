// ═══════════════════════════════════════════════════════════════
//  EOG + Control de Motor — ESP32
//  - Envía señal EOG por Serial a Python para clasificación
//  - Recibe comandos de Python (L/R/U/D/C) y mueve el motor con PID
// ═══════════════════════════════════════════════════════════════

#include <Encoder.h>

// ── Pines EOG ─────────────────────────────────────────────────
// GPIO36 (VP) es input-only → ideal para señal analógica sensible
const int EOG_PIN = 36;

// ── Pines motor ───────────────────────────────────────────────
const int CtrlVel = 16;
const int CtrlA   = 17;
const int CtrlB   = 18;

// ── LEDC (PWM del ESP32) ──────────────────────────────────────
const int PWM_CH   = 0;
const int PWM_FREQ = 5000;
const int PWM_BITS = 8;     // resolución 8 bits → 0-255

// ── Encoder ───────────────────────────────────────────────────
// Cualquier GPIO soporta interrupciones en ESP32
Encoder Enc1(19, 21);

// ── Variables EOG ─────────────────────────────────────────────
float baseline  = 0;
float filtrado  = 0;

// ── PID ───────────────────────────────────────────────────────
float referencia     = 0.0;
float error          = 0.0;
float integral       = 0.0;
float derivada       = 0.0;
float senal_control  = 0.0;
float pos            = 0.0;
float pos_anterior   = 0.0;
float vel            = 0.0;

// ── Ganancias PID ─────────────────────────────────────────────
float Kp = 2.0;
float Ki = 1.0;
float Kd = 0.05;

// ── Tiempo de muestreo del PID ────────────────────────────────
// Timer dispara cada 1 ms → Ts = 0.001 s
const float Ts = 0.001;

// ── Parámetros mecánicos ──────────────────────────────────────
const float PPR            = 1412.0;
const int   PWM_MIN        = 130;
const float ZONA_MUERTA    = 1.0;
const float LIMITE_INTEGRAL = 100.0;

// ── Posiciones ────────────────────────────────────────────────
const float POS_CENTRO    =  0.0;
const float POS_DERECHA   =  60.0;
const float POS_IZQUIERDA = -60.0;
// const float POS_ARRIBA =  60.0;   // descomentar al agregar eje vertical
// const float POS_ABAJO  = -60.0;

// ── Timer ISR ─────────────────────────────────────────────────
// El ISR solo levanta una bandera; el cálculo float ocurre en el loop
// (el ESP32 no guarda contexto FPU en ISR de hardware por defecto)
hw_timer_t*       timer    = NULL;
volatile bool     pidFlag  = false;
portMUX_TYPE      mux      = portMUX_INITIALIZER_UNLOCKED;

void IRAM_ATTR onTimer() {
  portENTER_CRITICAL_ISR(&mux);
  pidFlag = true;
  portEXIT_CRITICAL_ISR(&mux);
}

// ── Timing EOG (sin delay bloqueante) ─────────────────────────
unsigned long ultimoEog = 0;

// ─────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);

  // Motor
  pinMode(CtrlA, OUTPUT);
  pinMode(CtrlB, OUTPUT);
  ledcSetup(PWM_CH, PWM_FREQ, PWM_BITS);
  ledcAttachPin(CtrlVel, PWM_CH);
  ledcWrite(PWM_CH, 0);
  digitalWrite(CtrlA, HIGH);
  digitalWrite(CtrlB, HIGH);

  // Calibrar baseline EOG (~2.5 s quieto mirando al frente)
  long suma = 0;
  for (int i = 0; i < 500; i++) {
    suma += analogRead(EOG_PIN);
    delay(5);
  }
  baseline = suma / 500.0;

  // Cero del encoder
  Enc1.write(0);

  // Timer 1 ms para PID (prescaler 80 → clock 1 MHz; alarma cada 1000 µs)
  timer = timerBegin(0, 80, true);
  timerAttachInterrupt(timer, &onTimer, true);
  timerAlarmWrite(timer, 1000, true);
  timerAlarmEnable(timer);
}

// ─────────────────────────────────────────────────────────────
void loop() {
  // 1) PID — corre cada vez que el timer (1 kHz) levanta la bandera
  bool correrPid = false;
  portENTER_CRITICAL(&mux);
  if (pidFlag) { pidFlag = false; correrPid = true; }
  portEXIT_CRITICAL(&mux);
  if (correrPid) pidControl();

  // 2) EOG + Serial TX — ~200 Hz (cada 5 ms, sin delay bloqueante)
  unsigned long ahora = millis();
  if (ahora - ultimoEog >= 5) {
    ultimoEog = ahora;

    int raw = analogRead(EOG_PIN);
    // ESP32 ADC es 12 bits (0-4095); dividir por 4 para mantener
    // la misma escala que el Arduino Uno (10 bits) que usó el entrenamiento
    float signal      = (raw - baseline) / 4.0;
    filtrado          = 0.9 * filtrado + 0.1 * signal;
    float amplificada = filtrado * 20.0;

    Serial.print(amplificada);
    Serial.print(",");
    Serial.println(amplificada);
  }

  // 3) Recibir comando de Python
  if (Serial.available() > 0) {
    char cmd = Serial.read();
    if      (cmd == 'R') { referencia = POS_DERECHA;    integral = 0; }
    else if (cmd == 'L') { referencia = POS_IZQUIERDA;  integral = 0; }
    else if (cmd == 'C') { referencia = POS_CENTRO;     integral = 0; }
    // else if (cmd == 'U') { referencia = POS_ARRIBA;  integral = 0; }
    // else if (cmd == 'D') { referencia = POS_ABAJO;   integral = 0; }
  }
}

// ── Control PID ───────────────────────────────────────────────
void pidControl() {
  pos = Enc1.read() * (360.0 / PPR);

  vel          = (pos - pos_anterior) / Ts;
  pos_anterior = pos;
  error        = referencia - pos;

  // Zona muerta → freno activo
  if (abs(error) < ZONA_MUERTA) {
    ledcWrite(PWM_CH, 0);
    digitalWrite(CtrlA, HIGH);
    digitalWrite(CtrlB, HIGH);
    integral      = 0;
    senal_control = 0;
    return;
  }

  // Integral con anti-windup
  integral += error * Ts;
  if (integral >  LIMITE_INTEGRAL) integral =  LIMITE_INTEGRAL;
  if (integral < -LIMITE_INTEGRAL) integral = -LIMITE_INTEGRAL;

  // Derivada sobre velocidad (evita derivative kick)
  derivada = -vel;

  senal_control = Kp*error + Ki*integral + Kd*derivada;

  if (senal_control >  255) senal_control =  255;
  if (senal_control < -255) senal_control = -255;

  int PWMv = abs((int)senal_control);
  if (PWMv > 0 && PWMv < PWM_MIN) PWMv = PWM_MIN;

  if (senal_control > 0) {
    digitalWrite(CtrlA, LOW);
    digitalWrite(CtrlB, HIGH);
  } else if (senal_control < 0) {
    digitalWrite(CtrlA, HIGH);
    digitalWrite(CtrlB, LOW);
  } else {
    ledcWrite(PWM_CH, 0);
    digitalWrite(CtrlA, HIGH);
    digitalWrite(CtrlB, HIGH);
    return;
  }

  ledcWrite(PWM_CH, PWMv);
}

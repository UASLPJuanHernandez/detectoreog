#include <TimerOne.h>
#include <Encoder.h>

// ================= EOG =================
const int EOG_PIN = A0;
float baseline = 0;
float filtrado  = 0;

// ================= MOTOR EJE H (horizontal) =================
int CtrlVel = 6;
int CtrlA   = 4;
int CtrlB   = 5;

// ================= ENCODER EJE H =================
Encoder Enc1(2, 3);
float pos_h          = 0.0;
float pos_h_anterior = 0.0;
float vel_h          = 0.0;

// ================= PID EJE H =================
float ref_h          = 0.0;
float error_h        = 0.0;
float integral_h     = 0.0;
float derivada_h     = 0.0;
float senal_ctrl_h   = 0.0;

float Kp = 2.0;
float Ki = 1.0;
float Kd = 0.05;

// ================= TIEMPO =================
float Ts     = 0.001;
float tiempo = 0.0;

// ================= PARAMETROS =================
const float PPR = 1412.0;

// ================= POSICIONES EJE H =================
const float POS_CENTRO    =   0.0;
const float POS_DERECHA   =  60.0;
const float POS_IZQUIERDA = -60.0;
const float POS_DIAG_H    =  42.0;   // componente H de cualquier diagonal (~60° * cos45°)

// ================= POSICIONES EJE V (a futuro) =================
// Descomentar cuando se conecte el segundo motor + encoder.
// const float POS_ARRIBA  =  60.0;
// const float POS_ABAJO   = -60.0;
// const float POS_DIAG_V  =  42.0;

// ================= EXTRAS =================
const int   PWM_MIN         = 130;
int         PWM_Apl         = 0;
const float ZONA_MUERTA     = 1.0;
const float LIMITE_INTEGRAL = 100.0;

String estado = "CENTRO";

// ── Comandos recibidos de Python ─────────────────────────────────
// Simples:    L  R  U  D  C
// Diagonales: Q(↖)  E(↗)  Z(↙)  X(↘)

void setup()
{
  pinMode(CtrlVel, OUTPUT);
  pinMode(CtrlA,   OUTPUT);
  pinMode(CtrlB,   OUTPUT);

  Serial.begin(115200);

  long suma = 0;
  for (int i = 0; i < 500; i++) {
    suma += analogRead(EOG_PIN);
    delay(5);
  }
  baseline = suma / 500.0;

  Enc1.write(0);

  Timer1.attachInterrupt(timerIsr);
  Timer1.initialize(1000);   // 1 ms
}

void loop()
{
  // 1) Leer EOG y enviar a Python
  int   raw         = analogRead(EOG_PIN);
  float signal      = raw - baseline;
  filtrado          = 0.9 * filtrado + 0.1 * signal;
  float amplificada = filtrado * 20;

  Serial.print(amplificada);
  Serial.print(",");
  Serial.println(amplificada);

  // 2) Recibir comando de Python
  if (Serial.available() > 0)
  {
    char cmd = Serial.read();
    integral_h = 0;   // reset integral en cada nuevo comando

    // ── Movimientos simples ──────────────────────────────────────
    if (cmd == 'R') {
      ref_h  = POS_DERECHA;
      estado = "DERECHA";
      // ref_v = POS_CENTRO;   // (cuando haya eje V)
    }
    else if (cmd == 'L') {
      ref_h  = POS_IZQUIERDA;
      estado = "IZQUIERDA";
      // ref_v = POS_CENTRO;
    }
    else if (cmd == 'C') {
      ref_h  = POS_CENTRO;
      estado = "CENTRO";
      // ref_v = POS_CENTRO;
    }
    // ── Eje vertical: activar cuando se conecte el segundo motor ─
    // else if (cmd == 'U') {
    //   ref_h  = POS_CENTRO;
    //   ref_v  = POS_ARRIBA;
    //   estado = "ARRIBA";
    // }
    // else if (cmd == 'D') {
    //   ref_h  = POS_CENTRO;
    //   ref_v  = POS_ABAJO;
    //   estado = "ABAJO";
    // }

    // ── Diagonales ───────────────────────────────────────────────
    // Componente H activa ahora. Componente V se activa al agregar eje V.
    else if (cmd == 'E') {           // ↗ arriba-derecha
      ref_h  = POS_DIAG_H;
      estado = "ARRIBA-DER";
      // ref_v = POS_DIAG_V;
    }
    else if (cmd == 'Q') {           // ↖ arriba-izquierda
      ref_h  = -POS_DIAG_H;
      estado = "ARRIBA-IZQ";
      // ref_v = POS_DIAG_V;
    }
    else if (cmd == 'X') {           // ↘ abajo-derecha
      ref_h  = POS_DIAG_H;
      estado = "ABAJO-DER";
      // ref_v = -POS_DIAG_V;
    }
    else if (cmd == 'Z') {           // ↙ abajo-izquierda
      ref_h  = -POS_DIAG_H;
      estado = "ABAJO-IZQ";
      // ref_v = -POS_DIAG_V;
    }
  }

  delay(5);   // ~200 Hz
}

// ── ISR PID eje H (1 kHz) ────────────────────────────────────────
void timerIsr()
{
  tiempo += Ts;

  // Leer encoder
  pos_h = Enc1.read() * (360.0 / PPR);

  // Velocidad
  vel_h       = (pos_h - pos_h_anterior) / Ts;
  pos_h_anterior = pos_h;

  // Error
  error_h = ref_h - pos_h;

  // Zona muerta
  if (abs(error_h) < ZONA_MUERTA)
  {
    analogWrite(CtrlVel, 0);
    digitalWrite(CtrlA, HIGH);
    digitalWrite(CtrlB, HIGH);
    integral_h    = 0;
    senal_ctrl_h  = 0;
    PWM_Apl       = 0;
    return;
  }

  // Integral con anti-windup
  integral_h += error_h * Ts;
  if (integral_h >  LIMITE_INTEGRAL) integral_h =  LIMITE_INTEGRAL;
  if (integral_h < -LIMITE_INTEGRAL) integral_h = -LIMITE_INTEGRAL;

  // Derivada sobre velocidad (evita derivative kick)
  derivada_h = -vel_h;

  // PID
  senal_ctrl_h = Kp * error_h + Ki * integral_h + Kd * derivada_h;

  // Saturación
  if (senal_ctrl_h >  255) senal_ctrl_h =  255;
  if (senal_ctrl_h < -255) senal_ctrl_h = -255;

  // Aplicar al motor
  int PWMv = abs(senal_ctrl_h);
  if (PWMv > 0 && PWMv < PWM_MIN) PWMv = PWM_MIN;

  if (senal_ctrl_h > 0)
  {
    digitalWrite(CtrlA, LOW);
    digitalWrite(CtrlB, HIGH);
    PWM_Apl = PWMv;
  }
  else if (senal_ctrl_h < 0)
  {
    digitalWrite(CtrlA, HIGH);
    digitalWrite(CtrlB, LOW);
    PWM_Apl = -PWMv;
  }
  else
  {
    digitalWrite(CtrlA, HIGH);
    digitalWrite(CtrlB, HIGH);
    PWMv    = 0;
    PWM_Apl = 0;
  }

  analogWrite(CtrlVel, PWMv);
}

#include <TimerOne.h>
#include <Encoder.h>

// ================= EOG =================
const int EOG_PIN = A0;
float baseline = 0;
float filtrado  = 0;

// ================= MOTOR =================
int CtrlVel = 6;
int CtrlA = 4;
int CtrlB = 5;

// ================= ENCODER =================
Encoder Enc1(2,3);
float pos = 0.0;
float pos_anterior = 0.0;
float vel = 0.0;

// ================= PID =================
float referencia = 0.0;
float error = 0.0;
float integral = 0.0;
float derivada = 0.0;
float senal_control = 0.0;

// ================= GANANCIAS =================
float Kp = 2.0;
float Ki = 1.0;
float Kd = 0.05;

// ================= TIEMPO =================
float Ts = 0.001;
float tiempo = 0.0;

// ================= PARAMETROS =================
const float PPR = 1412.0;

// ================= POSICIONES HORIZONTALES =================
const float POS_CENTRO    =  0.0;
const float POS_DERECHA   =  60.0;
const float POS_IZQUIERDA = -60.0;

// ================= POSICIONES VERTICALES (a futuro) =================
// const float POS_ARRIBA =  60.0;   // ajustar según rango del eje vertical
// const float POS_ABAJO  = -60.0;

// ================= EXTRAS =================
const int PWM_MIN = 130;
int PWM_Apl = 0;

const float ZONA_MUERTA = 1.0;
const float LIMITE_INTEGRAL = 100.0;

String estado = "CENTRO";

void setup()
{
  pinMode(CtrlVel, OUTPUT);
  pinMode(CtrlA, OUTPUT);
  pinMode(CtrlB, OUTPUT);

  Serial.begin(115200);

  // Calibrar baseline EOG (~2.5 s antes de arrancar)
  long suma = 0;
  for (int i = 0; i < 500; i++) {
    suma += analogRead(EOG_PIN);
    delay(5);
  }
  baseline = suma / 500.0;

  // Definir cero del encoder al encender
  Enc1.write(0);

  Timer1.attachInterrupt(timerIsr);
  Timer1.initialize(1000);   // 1 ms → ISR del PID
}

void loop()
{
  // 1) Leer EOG, filtrar y enviar a Python en formato "valor,valor\n"
  int raw           = analogRead(EOG_PIN);
  float signal      = raw - baseline;
  filtrado          = 0.9 * filtrado + 0.1 * signal;
  float amplificada = filtrado * 20;

  Serial.print(amplificada);
  Serial.print(",");
  Serial.println(amplificada);

  // 2) Recibir comando de Python y actualizar referencia del PID
  if (Serial.available() > 0)
  {
    char cmd = Serial.read();

    if (cmd == 'R') {
      referencia = POS_DERECHA;
      integral   = 0;
      estado     = "DERECHA";
    }
    else if (cmd == 'L') {
      referencia = POS_IZQUIERDA;
      integral   = 0;
      estado     = "IZQUIERDA";
    }
    else if (cmd == 'C') {
      referencia = POS_CENTRO;
      integral   = 0;
      estado     = "CENTRO";
    }
    // ── Eje vertical: descomentar cuando se agregue el hardware ──────────
    // else if (cmd == 'U') {
    //   referencia = POS_ARRIBA;   // apuntar al encoder/driver del eje vertical
    //   integral   = 0;
    //   estado     = "ARRIBA";
    // }
    // else if (cmd == 'D') {
    //   referencia = POS_ABAJO;
    //   integral   = 0;
    //   estado     = "ABAJO";
    // }
  }

  delay(5);   // ~200 Hz — mismo ritmo que el clasificador Python
}

void timerIsr()
{
  tiempo += Ts;

  // ===== Leer encoder =====
  pos = Enc1.read() * (360.0 / PPR);

  // ===== Calcular velocidad =====
  vel = (pos - pos_anterior) / Ts;
  pos_anterior = pos;

  // ===== Error =====
  error = referencia - pos;

  // ===== Zona muerta =====
  if (abs(error) < ZONA_MUERTA)
  {
    analogWrite(CtrlVel, 0);
    digitalWrite(CtrlA, HIGH);
    digitalWrite(CtrlB, HIGH);
    integral      = 0;
    senal_control = 0;
    PWM_Apl       = 0;
    return;
  }

  // ===== Integral con anti-windup =====
  integral += error * Ts;
  if (integral >  LIMITE_INTEGRAL) integral =  LIMITE_INTEGRAL;
  if (integral < -LIMITE_INTEGRAL) integral = -LIMITE_INTEGRAL;

  // ===== Derivada (sobre velocidad — evita derivative kick) =====
  derivada = -vel;

  // ===== PID =====
  senal_control = Kp*error + Ki*integral + Kd*derivada;

  // ===== Saturación =====
  if (senal_control >  255) senal_control =  255;
  if (senal_control < -255) senal_control = -255;

  // ===== Aplicar al motor =====
  int PWMv = abs(senal_control);
  if (PWMv > 0 && PWMv < PWM_MIN) PWMv = PWM_MIN;

  if (senal_control > 0)
  {
    digitalWrite(CtrlA, LOW);
    digitalWrite(CtrlB, HIGH);
    PWM_Apl = PWMv;
  }
  else if (senal_control < 0)
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

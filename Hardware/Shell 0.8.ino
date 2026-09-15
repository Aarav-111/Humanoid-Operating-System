// Shell 0.8 - Arduino Uno / CNC Shield V3
// IR: Y+ (D10).
// Normally-open limit switch: Z+ (D11) to GND; pressed = LOW.
// X/Y/Z: 1/16 microstepping. A: full step.
//
// HX: move in HD direction, pause while limit is pressed,
//     resume when released. Received HU or S cancels HX.
// HD: stop at IR detection OR limit press.
// HU: cancel HX, then move in the opposite direction.
// U/D/L/R and UQ/DQ/LQ/RQ: existing X/Y motion.
// I: IR diagnostic.
// J: limit reading and HX state.
// G0...G90: existing gripper movement.
// S: cancel HX and stop motion.

#include <Arduino.h>

const uint8_t X_STEP_PIN = 2;
const uint8_t X_DIR_PIN  = 5;
const uint8_t Y_STEP_PIN = 3;
const uint8_t Y_DIR_PIN  = 6;
const uint8_t Z_STEP_PIN = 4;
const uint8_t Z_DIR_PIN  = 7;
const uint8_t ENABLE_PIN = 8;

#define A_STEP_PIN 12
#define A_DIR_PIN  13

const uint8_t IR_SENSOR_PIN = 10;
const uint8_t Z_LIMIT_PIN = 11;

const uint8_t IR_DETECTED_LEVEL = LOW;
const uint8_t LIMIT_SWITCH_PRESSED_LEVEL = LOW;

static_assert(IR_SENSOR_PIN != Z_LIMIT_PIN,
              "IR and limit switch must use separate Arduino inputs.");

const unsigned long SERIAL_BAUD = 115200;

const uint16_t MOTOR_FULL_STEPS_PER_REV = 200;
const uint8_t MICROSTEP = 16;
const uint8_t A_MICROSTEP = 1;

const unsigned long STEP_HALF_PERIOD_US = 167;
const unsigned long SLOW_STEP_HALF_PERIOD_US =
  STEP_HALF_PERIOD_US * 3;

const unsigned long Z_CRUISE_STEP_HALF_PERIOD_US = 167UL;
const unsigned long Z_START_STEP_HALF_PERIOD_US = 1000UL;
const unsigned long Z_ACCEL_MICROSTEPS = 800UL;

const unsigned long A_START_STEP_DELAY_US = 12000UL;
const unsigned long A_CRUISE_STEP_DELAY_US = 3000UL;
const unsigned long A_ACCEL_STEPS = 12UL;

const bool INVERT_X_DIRECTION = false;
const bool INVERT_Y_DIRECTION = false;
const bool INVERT_Z_DIRECTION = false;
const bool INVERT_A_DIRECTION = false;

const unsigned long COMMAND_WAIT_US = 5000;
const unsigned long G_COMMAND_WAIT_US = 20000;

bool running = false;
bool hdActive = false;
bool irStopLatched = false;

uint8_t activeStepPin = X_STEP_PIN;
uint8_t activeDirPin = X_DIR_PIN;

unsigned long activeStepHalfPeriodUs = STEP_HALF_PERIOD_US;
unsigned long lastStepMicros = 0;
unsigned long zAccelerationMicrosteps = 0;

const long A_STEPS_PER_REV =
  (long)MOTOR_FULL_STEPS_PER_REV * A_MICROSTEP;

long currentASteps = 0;

// -----------------------------------------------------------------------------
// SEPARATE HX PAUSE / RESUME MODULE
// -----------------------------------------------------------------------------

class HXPauseResumeModule {
public:
  void cancel(char reason = 0) {
    pausePulses();
    enabled_ = false;
    cancelReason_ = reason;
    hdOverride_ = false;
    gripperBusy_ = false;
    contactReported_ = false;
  }

  void begin(uint8_t direction) {
    cancel();

    direction_ = direction;
    enabled_ = true;

    digitalWrite(Z_STEP_PIN, LOW);
    digitalWrite(Z_DIR_PIN, direction_);

    if (!checkLimit()) {
      startSegment((uint32_t)micros());
    }
  }

  void planarCommand() {
    // Preserve HX across X/Y commands.
    // Never re-arm HX after received HU or S.
    if (enabled_) hdOverride_ = false;
  }

  void explicitHDCommand() {
    // Preserve the existing explicit HD sensor-stop behavior.
    pausePulses();
    if (enabled_) hdOverride_ = true;
  }

  void gripperCommand() {
    pausePulses();
    gripperBusy_ = true;
  }

  void gripperFinished() {
    gripperBusy_ = false;
  }

  bool checkLimit() {
    if (!enabled_ || hdOverride_ || gripperBusy_) return false;

    if (digitalRead(Z_LIMIT_PIN) != LIMIT_SWITCH_PRESSED_LEVEL) {
      return false;
    }

    // Pressed: stop pulses immediately, but KEEP enabled_ true.
    pausePulses();
    digitalWrite(Z_STEP_PIN, LOW);

    if (!contactReported_) {
      contactReported_ = true;

      // Outgoing notification only. This does NOT cancel HX.
      Serial.println("S");
    }

    return true;
  }

  void service(bool primaryZBusy, bool stopPrefixQueued) {
    if (!enabled_ || hdOverride_ || gripperBusy_) return;

    if (primaryZBusy) {
      pausePulses();
      return;
    }

    if (checkLimit()) return;

    // Give a queued S or H command priority.
    // Ordinary serial traffic does not block HX.
    if (stopPrefixQueued) {
      pausePulses();
      return;
    }

    const uint32_t now = (uint32_t)micros();

    // Released and still armed: restart directly.
    // No release latch and no 20 ms release timer.
    if (!moving_) {
      startSegment(now);
      return;
    }

    if ((uint32_t)(now - lastStepAt_) < halfPeriodUs_) {
      return;
    }

    // Check again immediately before generating a pulse edge.
    if (checkLimit()) return;

    stepHigh_ = !stepHigh_;
    digitalWrite(Z_STEP_PIN, stepHigh_ ? HIGH : LOW);
    lastStepAt_ = now;

    // Preserve the existing Z acceleration.
    if (!stepHigh_ && accelerationSteps_ < Z_ACCEL_MICROSTEPS) {
      ++accelerationSteps_;

      const uint32_t reduction =
        ((Z_START_STEP_HALF_PERIOD_US - Z_CRUISE_STEP_HALF_PERIOD_US) *
         accelerationSteps_) / Z_ACCEL_MICROSTEPS;

      halfPeriodUs_ = Z_START_STEP_HALF_PERIOD_US - reduction;
    }
  }

  bool isEnabled() const { return enabled_; }
  bool isMoving() const { return moving_; }
  bool isHDOverride() const { return hdOverride_; }

  void printStatus() const {
    if (!enabled_) {
      if (cancelReason_ == 's') {
        Serial.println(F("HX:CANCELLED_BY_S"));
      } else if (cancelReason_ == 'u') {
        Serial.println(F("HX:CANCELLED_BY_HU"));
      } else {
        Serial.println(F("HX:OFF_SEND_HX"));
      }
    } else if (hdOverride_) {
      Serial.println(F("HX:PAUSED_FOR_HD"));
    } else if (gripperBusy_) {
      Serial.println(F("HX:PAUSED_FOR_GRIPPER"));
    } else if (digitalRead(Z_LIMIT_PIN) == LIMIT_SWITCH_PRESSED_LEVEL) {
      Serial.println(F("HX:ARMED_LIMIT_PRESSED"));
    } else {
      Serial.println(F("HX:ARMED_LIMIT_RELEASED"));
    }
  }

private:
  bool enabled_ = false;
  bool moving_ = false;
  bool stepHigh_ = false;
  bool hdOverride_ = false;
  bool gripperBusy_ = false;
  char cancelReason_ = 0;
  bool contactReported_ = false;

  uint8_t direction_ = LOW;
  uint32_t lastStepAt_ = 0;
  uint32_t halfPeriodUs_ = Z_START_STEP_HALF_PERIOD_US;
  uint32_t accelerationSteps_ = 0;

  void pausePulses() {
    // Do not interfere when HU/HD owns Z.
    if (moving_) digitalWrite(Z_STEP_PIN, LOW);

    moving_ = false;
    stepHigh_ = false;
  }

  void startSegment(uint32_t now) {
    digitalWrite(Z_STEP_PIN, LOW);
    digitalWrite(Z_DIR_PIN, direction_);

    stepHigh_ = false;
    moving_ = true;
    halfPeriodUs_ = Z_START_STEP_HALF_PERIOD_US;
    accelerationSteps_ = 0;
    lastStepAt_ = now;
  }
};

HXPauseResumeModule hxHold;

// -----------------------------------------------------------------------------
// EXISTING MOTION AND SENSOR LOGIC
// -----------------------------------------------------------------------------

void stopAll() {
  running = false;
  hdActive = false;

  digitalWrite(X_STEP_PIN, LOW);
  digitalWrite(Y_STEP_PIN, LOW);
  digitalWrite(Z_STEP_PIN, LOW);
}

bool isIRDetected() {
  return digitalRead(IR_SENSOR_PIN) == IR_DETECTED_LEVEL;
}

bool isLimitSwitchPressed() {
  return digitalRead(Z_LIMIT_PIN) == LIMIT_SWITCH_PRESSED_LEVEL;
}

void stopForIR() {
  stopAll();

  if (!irStopLatched) {
    Serial.println("S");
  }

  irStopLatched = true;
}

bool serviceSafetyStops() {
  if (running && hdActive) {
    if (isIRDetected()) {
      stopForIR();
      return true;
    }

    if (isLimitSwitchPressed()) {
      stopAll();
      Serial.println("S");
      return true;
    }
  }

  return false;
}

void startMotion(char cmd, bool slow) {
  hxHold.planarCommand();
  hdActive = false;

  bool dirLevel;

  switch (cmd) {
    case 'u':
      activeStepPin = Y_STEP_PIN;
      activeDirPin = Y_DIR_PIN;
      dirLevel = LOW;
      if (INVERT_Y_DIRECTION) dirLevel = !dirLevel;
      digitalWrite(activeDirPin, dirLevel);
      break;

    case 'd':
      activeStepPin = Y_STEP_PIN;
      activeDirPin = Y_DIR_PIN;
      dirLevel = HIGH;
      if (INVERT_Y_DIRECTION) dirLevel = !dirLevel;
      digitalWrite(activeDirPin, dirLevel);
      break;

    case 'r':
      activeStepPin = X_STEP_PIN;
      activeDirPin = X_DIR_PIN;
      dirLevel = LOW;
      if (INVERT_X_DIRECTION) dirLevel = !dirLevel;
      digitalWrite(activeDirPin, dirLevel);
      break;

    case 'l':
      activeStepPin = X_STEP_PIN;
      activeDirPin = X_DIR_PIN;
      dirLevel = HIGH;
      if (INVERT_X_DIRECTION) dirLevel = !dirLevel;
      digitalWrite(activeDirPin, dirLevel);
      break;

    default:
      return;
  }

  activeStepHalfPeriodUs =
    slow ? SLOW_STEP_HALF_PERIOD_US : STEP_HALF_PERIOD_US;

  running = true;
  lastStepMicros = micros();
  digitalWrite(activeStepPin, HIGH);
}

void startZMotion(char cmd) {
  bool dirLevel;

  if (cmd == 'x') {
    stopAll();

    // HX and HD use the same direction.
    dirLevel = LOW;
    if (INVERT_Z_DIRECTION) dirLevel = !dirLevel;

    hxHold.begin(dirLevel);
    return;
  }

  if (cmd == 'u') {
    hxHold.cancel('u');
    dirLevel = HIGH;
    hdActive = false;
  } else if (cmd == 'd') {
    hxHold.explicitHDCommand();

    if (isLimitSwitchPressed()) {
      stopAll();
      Serial.println("S");
      return;
    }

    if (isIRDetected() || irStopLatched) {
      stopForIR();
      return;
    }

    dirLevel = LOW;
    hdActive = true;
  } else {
    return;
  }

  if (INVERT_Z_DIRECTION) dirLevel = !dirLevel;

  activeStepPin = Z_STEP_PIN;
  activeDirPin = Z_DIR_PIN;
  activeStepHalfPeriodUs = Z_START_STEP_HALF_PERIOD_US;
  zAccelerationMicrosteps = 0;

  digitalWrite(Z_STEP_PIN, LOW);
  digitalWrite(activeDirPin, dirLevel);
  delayMicroseconds(5);

  running = true;
  lastStepMicros = micros();
}

void moveAToAngle(uint8_t angle) {
  if (angle > 90) {
    Serial.println("ERR:G_RANGE");
    return;
  }

  long targetSteps =
    ((long)angle * A_STEPS_PER_REV + 180L) / 360L;

  long deltaSteps = targetSteps - currentASteps;

  if (deltaSteps == 0) return;

  bool dirLevel;
  long stepChange;

  if (deltaSteps > 0) {
    dirLevel = HIGH;
    stepChange = 1;
  } else {
    dirLevel = LOW;
    stepChange = -1;
  }

  if (INVERT_A_DIRECTION) dirLevel = !dirLevel;

  digitalWrite(A_DIR_PIN, dirLevel);
  delayMicroseconds(100);

  unsigned long stepsToMove =
    (deltaSteps > 0)
      ? (unsigned long)deltaSteps
      : (unsigned long)(-deltaSteps);

  unsigned long rampSteps = A_ACCEL_STEPS;

  if (rampSteps * 2UL > stepsToMove) {
    rampSteps = stepsToMove / 2UL;
  }

  for (unsigned long i = 0; i < stepsToMove; i++) {
    unsigned long stepDelayUs = A_CRUISE_STEP_DELAY_US;

    if (rampSteps > 0) {
      unsigned long fromStart = i;
      unsigned long fromEnd = stepsToMove - 1UL - i;
      unsigned long edgeDistance =
        (fromStart < fromEnd) ? fromStart : fromEnd;

      if (edgeDistance < rampSteps) {
        unsigned long delayRange =
          A_START_STEP_DELAY_US - A_CRUISE_STEP_DELAY_US;

        stepDelayUs =
          A_START_STEP_DELAY_US -
          (delayRange * edgeDistance) / rampSteps;
      }
    } else {
      stepDelayUs = A_START_STEP_DELAY_US;
    }

    digitalWrite(A_STEP_PIN, HIGH);
    delayMicroseconds(stepDelayUs);

    digitalWrite(A_STEP_PIN, LOW);
    delayMicroseconds(stepDelayUs);

    currentASteps += stepChange;

    if (Serial.available() > 0) {
      char next = (char)Serial.peek();

      if (next == 's' || next == 'S') {
        hxHold.cancel('s');
        stopAll();
        Serial.read();
        digitalWrite(A_STEP_PIN, LOW);
        return;
      }
    }
  }
}

void processGCommand() {
  int angle = 0;
  bool gotDigit = false;
  unsigned long waitStart = micros();

  while ((unsigned long)(micros() - waitStart) < G_COMMAND_WAIT_US) {
    if (Serial.available() > 0) {
      char next = (char)Serial.peek();

      if (next >= '0' && next <= '9') {
        Serial.read();
        gotDigit = true;
        angle = angle * 10 + (next - '0');
        waitStart = micros();
        continue;
      }

      if (next == '\r' || next == '\n' ||
          next == ' ' || next == '\t') {
        Serial.read();
        if (gotDigit) break;
        continue;
      }

      break;
    }
  }

  if (!gotDigit) {
    Serial.println("ERR:G");
    return;
  }

  if (angle < 0 || angle > 90) {
    Serial.println("ERR:G_RANGE");
    return;
  }

  moveAToAngle((uint8_t)angle);
}

void processCommand(char cmd) {
  if (cmd >= 'A' && cmd <= 'Z') {
    cmd = cmd - 'A' + 'a';
  }

  if (cmd == 's') {
    hxHold.cancel('s');
    stopAll();
    return;
  }

  if (cmd == 'g') {
    hxHold.gripperCommand();
    processGCommand();
    hxHold.gripperFinished();
    return;
  }

  if (cmd == 'i') {
    Serial.println(isIRDetected() ? "IR:DETECTED" : "IR:CLEAR");
    return;
  }

  if (cmd == 'j') {
    Serial.println(
      isLimitSwitchPressed() ? "LIMIT:PRESSED" : "LIMIT:RELEASED"
    );
    hxHold.printStatus();
    return;
  }

  if (cmd == 'h') {
    unsigned long waitStart = micros();

    while ((unsigned long)(micros() - waitStart) < COMMAND_WAIT_US) {
      if (Serial.available() > 0) {
        char next = (char)Serial.peek();

        if (next >= 'A' && next <= 'Z') {
          next = next - 'A' + 'a';
        }

        if (next == 'u' || next == 'd' || next == 'x') {
          Serial.read();
          startZMotion(next);
        }

        // Leave unrelated commands queued.
        break;
      }
    }

    return;
  }

  if (cmd != 'u' && cmd != 'd' && cmd != 'r' && cmd != 'l') {
    return;
  }

  bool slow = false;
  unsigned long waitStart = micros();

  while ((unsigned long)(micros() - waitStart) < COMMAND_WAIT_US) {
    if (Serial.available() > 0) {
      char next = (char)Serial.peek();

      if (next >= 'A' && next <= 'Z') {
        next = next - 'A' + 'a';
      }

      if (next == 'q') {
        Serial.read();
        slow = true;
      }

      break;
    }
  }

  startMotion(cmd, slow);
}

void setup() {
  pinMode(X_STEP_PIN, OUTPUT);
  pinMode(X_DIR_PIN, OUTPUT);
  pinMode(Y_STEP_PIN, OUTPUT);
  pinMode(Y_DIR_PIN, OUTPUT);
  pinMode(Z_STEP_PIN, OUTPUT);
  pinMode(Z_DIR_PIN, OUTPUT);

  pinMode(A_STEP_PIN, OUTPUT);
  pinMode(A_DIR_PIN, OUTPUT);

  pinMode(ENABLE_PIN, OUTPUT);
  pinMode(IR_SENSOR_PIN, INPUT_PULLUP);
  pinMode(Z_LIMIT_PIN, INPUT_PULLUP);

  digitalWrite(ENABLE_PIN, LOW);

  digitalWrite(X_DIR_PIN, LOW);
  digitalWrite(Y_DIR_PIN, LOW);
  digitalWrite(Z_DIR_PIN, LOW);

  digitalWrite(A_DIR_PIN, HIGH);
  digitalWrite(A_STEP_PIN, LOW);

  hxHold.cancel();
  stopAll();
  Serial.begin(SERIAL_BAUD);
}

void loop() {
  // Pressing the limit pauses HX even while commands are arriving.
  hxHold.checkLimit();

  if (irStopLatched && !isIRDetected()) {
    irStopLatched = false;
  }

  if (serviceSafetyStops()) return;

  if (Serial.available() > 0) {
    char incoming = (char)Serial.read();

    // CR/LF no longer skip HX servicing.
    if (incoming != '\r' && incoming != '\n' &&
        incoming != ' ' && incoming != '\t') {
      processCommand(incoming);
    }
  }

  if (serviceSafetyStops()) return;

  // Only pending stop/Z prefixes preempt HX pulses.
  // Other queued serial bytes do not prevent resuming.
  const int nextCommand = Serial.peek();

  const bool stopPrefixQueued =
    nextCommand == 's' || nextCommand == 'S' ||
    nextCommand == 'h' || nextCommand == 'H';

  hxHold.service(
    running && activeStepPin == Z_STEP_PIN,
    stopPrefixQueued
  );

  // Existing primary X/Y/HU/HD pulse generator.
  if (running) {
    unsigned long now = micros();

    if ((unsigned long)(now - lastStepMicros) >=
        activeStepHalfPeriodUs) {
      lastStepMicros = now;

      bool currentState = digitalRead(activeStepPin);
      bool nextState = !currentState;
      digitalWrite(activeStepPin, nextState);

      if (activeStepPin == Z_STEP_PIN && nextState == LOW &&
          activeStepHalfPeriodUs > Z_CRUISE_STEP_HALF_PERIOD_US) {
        if (zAccelerationMicrosteps < Z_ACCEL_MICROSTEPS) {
          zAccelerationMicrosteps++;
        }

        unsigned long periodReduction =
          ((Z_START_STEP_HALF_PERIOD_US - Z_CRUISE_STEP_HALF_PERIOD_US) *
           zAccelerationMicrosteps) / Z_ACCEL_MICROSTEPS;

        activeStepHalfPeriodUs =
          Z_START_STEP_HALF_PERIOD_US - periodReduction;

        if (activeStepHalfPeriodUs < Z_CRUISE_STEP_HALF_PERIOD_US) {
          activeStepHalfPeriodUs = Z_CRUISE_STEP_HALF_PERIOD_US;
        }
      }
    }
  }
}

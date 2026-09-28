// Shell 1 - Arduino Uno / CNC Shield V3
//
// IR OUT: Z+ signal (D11), active LOW.
// Joystick SW: X+ signal (D9), pressed = LOW.
// URX/VRX: A0 (Abort signal), controls Z.
// URY/VRY: A1 (Hold signal), controls A-axis gripper.
// Joystick power: 5V and GND.
//
// Joystick Z works alongside U/D/L/R and their Q variants.
// Serial movement has priority on the same motor.
// Manual Z ignores IR and single SW presses.
// Double SW and received serial S still stop all movement.
//
// Joystick down prints lowercase "hx" once per gesture.
// This outgoing message does not arm persistent serial HX locally.
// Return the joystick to centre to stop manual movement.
//
// Both joystick directions are inverted.
// Joystick Z pulse intervals are one-third of the previous values.
// Joystick gripper movement is slow even at full deflection.
// Manual A movement preserves the logical G angle.
//
// Serial HU/HD/HX retain their previous behavior.
// HX: down; pause while SW is pressed, resume on release.
// HD: down; stop on IR detection or SW press.
// HU: cancel HX, then move up.
// I: IR diagnostic.
// J: SW reading and HX state.
// G0...G90: serial gripper positioning.
// S: stop all movement.
//
// Double-press SW within 350 ms:
//   Stop all movement and transmit lowercase "s".
//   Centre the joystick before jogging again.
//
// X/Y/Z: 1/16 microstepping.
// A: full step.

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

const uint8_t IR_SENSOR_PIN = 11;
const uint8_t Z_LIMIT_PIN = 9; // Legacy name: joystick SW on X+.

const uint8_t JOYSTICK_X_PIN = A0;
const uint8_t JOYSTICK_Y_PIN = A1;

const int JOYSTICK_CENTER_X = 512;
const int JOYSTICK_CENTER_Y = 512;
const int JOYSTICK_DEADZONE = 80;

const bool INVERT_JOYSTICK_X = true;
const bool INVERT_JOYSTICK_Y = true;

const uint32_t JOYSTICK_SAMPLE_US = 2000UL;

// Approximately 3x faster joystick Z movement.
// Previous values: 4000 and 250 microseconds.
const uint32_t JOYSTICK_Z_SLOW_US = 1333UL;
const uint32_t JOYSTICK_Z_FAST_US = 83UL;

// Slow joystick gripper movement.
const uint32_t JOYSTICK_A_SLOW_US = 60000UL;
const uint32_t JOYSTICK_A_FAST_US = 20000UL;

const uint8_t IR_DETECTED_LEVEL = LOW;
const uint8_t LIMIT_SWITCH_PRESSED_LEVEL = LOW;

static_assert(IR_SENSOR_PIN != Z_LIMIT_PIN,
              "IR and SW must use separate Arduino inputs.");

const unsigned long SERIAL_BAUD = 115200;

const uint32_t SW_DEBOUNCE_US = 20000UL;
const uint32_t SW_DOUBLE_PRESS_US = 350000UL;

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

uint32_t stopGeneration = 0;

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

struct JoystickAxis {
  bool moving = false;
  bool high = false;
  bool direction = false;
  bool stoppedUntilCenter = false;
  uint32_t lastEdge = 0;
};

void serviceBackground();
void emergencyStop();
void serviceSwitch();
bool waitWithMotion(uint32_t duration);
void stopJoystick();
void releaseJoystickZ();
void releaseJoystickA();

bool gripperCommandActive = false;

// -----------------------------------------------------------------------------
// HX PAUSE / RESUME MODULE
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
    // Preserve the previous HX behavior across X/Y commands.
    if (enabled_) hdOverride_ = false;
  }

  void explicitHDCommand() {
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

    // Pause immediately while keeping HX armed.
    pausePulses();
    digitalWrite(Z_STEP_PIN, LOW);

    if (!contactReported_) {
      contactReported_ = true;

      // Existing outgoing notification; does not cancel HX locally.
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

    if (stopPrefixQueued) {
      pausePulses();
      return;
    }

    const uint32_t now = (uint32_t)micros();

    if (!moving_) {
      startSegment(now);
      return;
    }

    if ((uint32_t)(now - lastStepAt_) < halfPeriodUs_) {
      return;
    }

    if (checkLimit()) return;

    stepHigh_ = !stepHigh_;
    digitalWrite(Z_STEP_PIN, stepHigh_ ? HIGH : LOW);
    lastStepAt_ = now;

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
// EXISTING SERIAL MOTION AND SENSOR LOGIC
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
  // Sensor stops apply to serial HD, not manual joystick movement.
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
  releaseJoystickZ();
  bool dirLevel;

  if (cmd == 'x') {
    stopAll();

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

    // Preserve four-times-slower serial closing.
    const uint8_t delayRepeats = (deltaSteps > 0) ? 4 : 1;

    digitalWrite(A_STEP_PIN, HIGH);

    // Count the rising edge even if stopped during this pulse.
    currentASteps += stepChange;

    for (uint8_t repeat = 0; repeat < delayRepeats; ++repeat) {
      if (!waitWithMotion(stepDelayUs)) return;
    }

    digitalWrite(A_STEP_PIN, LOW);

    for (uint8_t repeat = 0; repeat < delayRepeats; ++repeat) {
      if (!waitWithMotion(stepDelayUs)) return;
    }

    if (Serial.available() > 0) {
      char next = (char)Serial.peek();

      if (next == 's' || next == 'S') {
        Serial.read();
        emergencyStop();
        return;
      }
    }
  }
}

// -----------------------------------------------------------------------------
// SERIAL COMMAND PARSING
// -----------------------------------------------------------------------------

void processGCommand() {
  const uint32_t generation = stopGeneration;
  int angle = 0;
  bool gotDigit = false;
  unsigned long waitStart = micros();

  while ((unsigned long)(micros() - waitStart) < G_COMMAND_WAIT_US) {
    serviceBackground();
    if (stopGeneration != generation) return;

    if (Serial.available() > 0) {
      char next = (char)Serial.peek();

      if (next >= '0' && next <= '9') {
        Serial.read();
        gotDigit = true;

        if (angle <= 90) {
          angle = angle * 10 + (next - '0');
        }

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
  const uint32_t generation = stopGeneration;

  if (cmd >= 'A' && cmd <= 'Z') {
    cmd = cmd - 'A' + 'a';
  }

  if (cmd == 's') {
    emergencyStop();
    return;
  }

  if (cmd == 'g') {
    releaseJoystickA();
    gripperCommandActive = true;
    hxHold.gripperCommand();

    processGCommand();

    hxHold.gripperFinished();
    gripperCommandActive = false;
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
      serviceBackground();
      if (stopGeneration != generation) return;

      if (Serial.available() > 0) {
        char next = (char)Serial.peek();

        if (next >= 'A' && next <= 'Z') {
          next = next - 'A' + 'a';
        }

        if (next == 'u' || next == 'd' || next == 'x') {
          Serial.read();
          startZMotion(next);
        }

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
    serviceBackground();
    if (stopGeneration != generation) return;

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
  pinMode(JOYSTICK_X_PIN, INPUT);
  pinMode(JOYSTICK_Y_PIN, INPUT);

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

// -----------------------------------------------------------------------------
// JOYSTICK
// -----------------------------------------------------------------------------

JoystickAxis joystickZ, joystickA;
int joystickX = JOYSTICK_CENTER_X;
int joystickY = JOYSTICK_CENTER_Y;
uint32_t joystickSampleAt = 0;
bool joystickDownReported = false;

void releaseJoystick(JoystickAxis &axis, uint8_t stepPin) {
  if (axis.moving) digitalWrite(stepPin, LOW);
  axis.moving = false;
  axis.high = false;
}

void releaseJoystickZ() {
  releaseJoystick(joystickZ, Z_STEP_PIN);
}

void releaseJoystickA() {
  releaseJoystick(joystickA, A_STEP_PIN);
}

void stopJoystick() {
  releaseJoystickZ();
  releaseJoystickA();
  digitalWrite(A_STEP_PIN, LOW);

  joystickZ.stoppedUntilCenter = true;
  joystickA.stoppedUntilCenter = true;
}

void jogAxis(JoystickAxis &axis, uint8_t stepPin, uint8_t dirPin,
             int value, int center, bool invert, bool serialBusy,
             bool protectDown, uint32_t slowUs, uint32_t fastUs) {
  int offset = value - center;
  int magnitude = offset < 0 ? -offset : offset;

  if (magnitude <= JOYSTICK_DEADZONE) {
    axis.stoppedUntilCenter = false;
    releaseJoystick(axis, stepPin);
    return;
  }

  bool positive = offset > 0;

  if (stepPin == Z_STEP_PIN && INVERT_JOYSTICK_X) {
    positive = !positive;
  }

  if (stepPin == A_STEP_PIN && INVERT_JOYSTICK_Y) {
    positive = !positive;
  }

  if (serialBusy || axis.stoppedUntilCenter ||
      (protectDown && !positive &&
       (isIRDetected() || isLimitSwitchPressed()))) {
    releaseJoystick(axis, stepPin);
    return;
  }

  bool direction = positive ^ invert;

  int span =
    (offset > 0 ? 1023 - center : center) - JOYSTICK_DEADZONE;

  uint32_t halfPeriod = slowUs -
    ((slowUs - fastUs) *
     (uint32_t)(magnitude - JOYSTICK_DEADZONE)) / span;

  uint32_t now = (uint32_t)micros();

  if (!axis.moving || axis.direction != direction) {
    releaseJoystick(axis, stepPin);
    digitalWrite(dirPin, direction ? HIGH : LOW);
    axis.direction = direction;
    axis.moving = true;
    axis.lastEdge = now;
    return;
  }

  if ((uint32_t)(now - axis.lastEdge) >= halfPeriod) {
    axis.high = !axis.high;
    digitalWrite(stepPin, axis.high ? HIGH : LOW);
    axis.lastEdge = now;

    // Manual A movement deliberately does not change currentASteps.
  }
}

void serviceJoystick() {
  uint32_t now = (uint32_t)micros();

  if ((uint32_t)(now - joystickSampleAt) >= JOYSTICK_SAMPLE_US) {
    static bool readX = true;

    if (readX) {
      joystickX = analogRead(JOYSTICK_X_PIN);
    } else {
      joystickY = analogRead(JOYSTICK_Y_PIN);
    }

    readX = !readX;
    joystickSampleAt = now;
  }

  int zOffset = joystickX - JOYSTICK_CENTER_X;
  bool zPositive = zOffset > 0;

  if (INVERT_JOYSTICK_X) zPositive = !zPositive;

  bool downwardGesture =
    (zOffset > JOYSTICK_DEADZONE ||
     zOffset < -JOYSTICK_DEADZONE) && !zPositive;

  if (!downwardGesture) {
    joystickDownReported = false;
  }

  if (downwardGesture && !joystickDownReported &&
      !(running && activeStepPin == Z_STEP_PIN) &&
      !hxHold.isEnabled() &&
      !joystickZ.stoppedUntilCenter) {
    Serial.println("hx");
    joystickDownReported = true;
  }

  // Serial Z/HX retains priority.
  // Sensor protection is disabled for manual joystick Z movement.
  jogAxis(
    joystickZ,
    Z_STEP_PIN,
    Z_DIR_PIN,
    joystickX,
    JOYSTICK_CENTER_X,
    INVERT_Z_DIRECTION,
    (running && activeStepPin == Z_STEP_PIN) || hxHold.isEnabled(),
    false,
    JOYSTICK_Z_SLOW_US,
    JOYSTICK_Z_FAST_US
  );

  jogAxis(
    joystickA,
    A_STEP_PIN,
    A_DIR_PIN,
    joystickY,
    JOYSTICK_CENTER_Y,
    INVERT_A_DIRECTION,
    gripperCommandActive,
    false,
    JOYSTICK_A_SLOW_US,
    JOYSTICK_A_FAST_US
  );
}

// -----------------------------------------------------------------------------
// SW DOUBLE-PRESS AND GLOBAL STOP
// -----------------------------------------------------------------------------

// Debouncing counts separate presses.
// Original serial HD/HX logic still reads SW directly.
bool switchRawPressed = false;
bool switchStablePressed = false;
bool firstSwitchPressPending = false;

uint32_t switchChangedAt = 0;
uint32_t firstSwitchPressAt = 0;

void emergencyStop() {
  ++stopGeneration;

  hxHold.cancel('s');
  stopAll();
  stopJoystick();

  // Discard commands buffered before the stop.
  while (Serial.available() > 0) {
    Serial.read();
  }
}

void serviceSwitch() {
  const uint32_t now = (uint32_t)micros();
  const bool pressed = isLimitSwitchPressed();

  if (pressed != switchRawPressed) {
    switchRawPressed = pressed;
    switchChangedAt = now;
  }

  if (firstSwitchPressPending &&
      (uint32_t)(now - firstSwitchPressAt) > SW_DOUBLE_PRESS_US) {
    firstSwitchPressPending = false;
  }

  if (switchRawPressed != switchStablePressed &&
      (uint32_t)(now - switchChangedAt) >= SW_DEBOUNCE_US) {
    switchStablePressed = switchRawPressed;

    if (switchStablePressed) {
      if (firstSwitchPressPending &&
          (uint32_t)(now - firstSwitchPressAt) <= SW_DOUBLE_PRESS_US) {
        firstSwitchPressPending = false;

        emergencyStop();
        Serial.println("s");
      } else {
        firstSwitchPressPending = true;
        firstSwitchPressAt = now;
      }
    }
  }
}

// -----------------------------------------------------------------------------
// COOPERATIVE MOVEMENT SERVICING
// -----------------------------------------------------------------------------

bool waitWithMotion(uint32_t duration) {
  const uint32_t generation = stopGeneration;
  uint32_t started = (uint32_t)micros();

  while ((uint32_t)((uint32_t)micros() - started) < duration) {
    if (Serial.peek() == 'S' || Serial.peek() == 's') {
      Serial.read();
      emergencyStop();
      return false;
    }

    serviceBackground();

    if (stopGeneration != generation) return false;
  }

  return true;
}

void serviceBackground() {
  serviceSwitch();

  hxHold.checkLimit();

  if (irStopLatched && !isIRDetected()) {
    irStopLatched = false;
  }

  serviceSafetyStops();

  const int nextCommand = Serial.peek();

  const bool stopPrefixQueued =
    nextCommand == 's' || nextCommand == 'S' ||
    nextCommand == 'h' || nextCommand == 'H';

  hxHold.service(
    running && activeStepPin == Z_STEP_PIN,
    stopPrefixQueued
  );

  // Original shared primary serial pulse generator.
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

  serviceJoystick();
}

void loop() {
  serviceBackground();

  if (Serial.available() > 0) {
    char incoming = (char)Serial.read();

    if (incoming != '\r' && incoming != '\n' &&
        incoming != ' ' && incoming != '\t') {
      processCommand(incoming);
    }
  }

  serviceBackground();
}

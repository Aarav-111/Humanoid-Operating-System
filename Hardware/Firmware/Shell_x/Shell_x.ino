// -----------------------------------------------------------------------------
// SHELL-X v0.20 - XYZ + INVERTED BINARY POTENTIOMETER
// Arduino Uno + CNC Shield V3
//
// CHANGES FROM v0.14
//   - Potentiometer is treated as a binary sensor: 0 = inactive, 1 = active.
//   - P1 and P3 have been removed completely.
//   - Three-position calibration (1 / 2 / 3) has been removed.
//   - No automatic lift is performed.
//   - During HD, Z stops when the binary position becomes DOWN (state 0).
//   - A axis, IR sensor, ToF sensor and joystick are not used.
//
// POTENTIOMETER WIRING
//   One outer terminal -> 5V
//   Other outer terminal -> GND
//   Middle / wiper -> A0 (CNC Shield Abort signal)
//
// The potentiometer is still analog, but firmware maps it to a binary position:
//   Nominal boundary: 1020
//   DOWN  (POT_STATE 0): raw <= 1018
//   LIFTED (POT_STATE 1): raw >= 1022
//   1019..1021: deadband; retain the previous state.
// State changes must remain beyond the relevant boundary for 100 ms.
// Each reading is averaged from 16 ADC samples.
// During HD, Z stops immediately when the raw reading reaches the DOWN limit;
// the reported binary state changes only after the 100 ms stability check.
//
// SERIAL MONITOR
//   Set line ending to Newline or Both NL & CR.
//
// X/Y COMMANDS
//   U / D       = Y up / down
//   R / L       = X right / left
//   UQ / DQ     = Y up / down at 3x slower speed
//   RQ / LQ     = X right / left at 3x slower speed
//
// Z COMMANDS
//   HU          = Z up continuously
//   HD          = Z down; stops when POT_STATE becomes 0 (DOWN)
//
// OTHER COMMANDS
//   S           = stop all motion
//   READ        = show raw potentiometer reading and binary state
//   STATUS / V  = show motion and sensor status
//   THR n       = set binary threshold (0..1023, RAM only)
//   HYST n      = set hysteresis (0..100 ADC counts)
//   HELP / ?    = show commands
//
// IMPORTANT
//   THR and HYST settings are RAM-only and reset at power-on.
//   The potentiometer detects position, not force. Do not use this as the only
//   physical safety device for a mechanism that can cause injury or damage.
// -----------------------------------------------------------------------------

#include <ctype.h>
#include <stdlib.h>
#include <string.h>

// -----------------------------------------------------------------------------
// CNC SHIELD V3 PIN MAP
// -----------------------------------------------------------------------------

const uint8_t X_STEP_PIN = 2;
const uint8_t X_DIR_PIN  = 5;

const uint8_t Y_STEP_PIN = 3;
const uint8_t Y_DIR_PIN  = 6;

const uint8_t Z_STEP_PIN = 4;
const uint8_t Z_DIR_PIN  = 7;

const uint8_t ENABLE_PIN = 8;  // Active LOW
const uint8_t POT_PIN    = A0; // Abort signal on standard CNC Shield V3

const unsigned long SERIAL_BAUD = 115200UL;

// -----------------------------------------------------------------------------
// MOTION CONFIGURATION
// -----------------------------------------------------------------------------

// Values carried forward from the recorded v0.14 configuration.
const unsigned long XY_HALF_PERIOD_US      = 2672UL;
const unsigned long XY_SLOW_HALF_PERIOD_US = XY_HALF_PERIOD_US * 3UL;
const unsigned long Z_HALF_PERIOD_US       = 5333UL;

const bool INVERT_X_DIRECTION = true;
const bool INVERT_Y_DIRECTION = false;
const bool INVERT_Z_DIRECTION = false;

// In the recorded v0.14 direction mapping, HIGH means Z up.
const uint8_t Z_UP_DIR_LEVEL = HIGH;

const unsigned int DIR_SETTLE_US = 50;

// -----------------------------------------------------------------------------
// BINARY POTENTIOMETER CONFIGURATION
// -----------------------------------------------------------------------------

// Nominal binary boundary. The default deadband is 2 ADC counts on each side.
// Default: enter LIFTED at >=1022; enter DOWN at <=1018; retain state in between.
int POT_THRESHOLD = 1020;
uint8_t POT_HYSTERESIS = 2;

// A candidate state must remain beyond its boundary for this long.
const unsigned long POT_STABLE_TIME_MS = 100UL;

// Average more samples to reduce single-read ADC noise.
const unsigned long POT_SAMPLE_INTERVAL_MS = 5UL;
const uint8_t POT_SAMPLE_COUNT = 16;

// -----------------------------------------------------------------------------
// RUNTIME STATE
// -----------------------------------------------------------------------------

bool motionRunning = false;
bool zDownMonitoring = false;

uint8_t activeStepPin = X_STEP_PIN;
uint8_t activeDirPin  = X_DIR_PIN;
unsigned long activeHalfPeriodUs = XY_HALF_PERIOD_US;
unsigned long lastStepMicros = 0;

int potRaw = 0;
bool potActive = false;
bool potStateInitialized = false;
unsigned long lastPotSampleMs = 0;

// Debounce candidate state. The current state is retained until the candidate
// remains continuously valid for POT_STABLE_TIME_MS.
bool potCandidateActive = false;
bool potCandidateLifted = false;
unsigned long potCandidateSinceMs = 0;

char commandBuffer[40];
uint8_t commandLength = 0;

// stopAll() is defined below and is also called by the sensor update code.
void stopAll();

// -----------------------------------------------------------------------------
// POTENTIOMETER READING
// -----------------------------------------------------------------------------

int readPotRaw() {
  unsigned long total = 0;
  for (uint8_t i = 0; i < POT_SAMPLE_COUNT; i++) {
    total += analogRead(POT_PIN);
  }
  // Rounded integer average, rather than truncating every fractional result.
  return (int)((total + (POT_SAMPLE_COUNT / 2U)) / POT_SAMPLE_COUNT);
}

bool rawIsLiftedWithoutHysteresis(int raw) {
  return raw > POT_THRESHOLD;
}

int potLiftTrip() {
  int trip = POT_THRESHOLD + POT_HYSTERESIS;
  return trip > 1023 ? 1024 : trip;
}

int potDownTrip() {
  int trip = POT_THRESHOLD - POT_HYSTERESIS;
  return trip < 0 ? 0 : trip;
}

void printPotTransition(bool lifted, int raw) {
  Serial.print(F("POT_CROSSED:"));
  Serial.print(lifted ? F("ABOVE") : F("BELOW"));
  Serial.print(F(" | POT_STATE:"));
  Serial.print(lifted ? 1 : 0);
  Serial.print(F(" | POSITION:"));
  Serial.print(lifted ? F("LIFTED") : F("DOWN"));
  Serial.print(F(" | POT_RAW:"));
  Serial.print(raw);
  Serial.print(F(" | THR:"));
  Serial.print(POT_THRESHOLD);
  Serial.print(F(" | HYST:"));
  Serial.print(POT_HYSTERESIS);
  Serial.print(F(" | STABLE_MS:"));
  Serial.println(POT_STABLE_TIME_MS);
}

void updatePotStateFromRaw(int raw) {
  // Establish an initial state immediately at startup or after THR changes.
  // Subsequent changes use hysteresis and the stability timer.
  if (!potStateInitialized) {
    bool initialState = rawIsLiftedWithoutHysteresis(raw);
    bool changed = initialState != potActive;
    potActive = initialState;
    potStateInitialized = true;
    potCandidateActive = false;
    if (changed) printPotTransition(potActive, raw);
    return;
  }

  const int liftTrip = potLiftTrip();
  const int downTrip = potDownTrip();
  bool candidateCondition = false;
  bool targetLifted = potActive;

  if (!potActive) {
    // With HYST=0 preserve the strict original rule raw > THR.
    // With HYST=2, lift at raw >= THR+2 (1022 by default).
    targetLifted = true;
    candidateCondition = (POT_HYSTERESIS == 0)
        ? (raw > POT_THRESHOLD)
        : (raw >= liftTrip);
  } else {
    // With HYST=2, enter DOWN at raw <= THR-2 (1018 by default).
    targetLifted = false;
    candidateCondition = (raw <= downTrip);
  }

  // The reading has returned to the deadband or current-state side. Cancel
  // any pending transition so intermittent noise cannot accumulate time.
  if (!candidateCondition) {
    potCandidateActive = false;
    return;
  }

  unsigned long now = millis();
  if (!potCandidateActive || potCandidateLifted != targetLifted) {
    potCandidateActive = true;
    potCandidateLifted = targetLifted;
    potCandidateSinceMs = now;
    return;
  }

  if ((unsigned long)(now - potCandidateSinceMs) >= POT_STABLE_TIME_MS) {
    potActive = targetLifted;
    potCandidateActive = false;
    printPotTransition(potActive, raw);
  }
}

void samplePotentiometer(bool force) {
  unsigned long now = millis();
  if (!force && (unsigned long)(now - lastPotSampleMs) < POT_SAMPLE_INTERVAL_MS) {
    return;
  }

  lastPotSampleMs = now;
  potRaw = readPotRaw();

  // Fail-safe motor stop: do not let the 100 ms reporting debounce allow Z
  // to continue travelling after the DOWN stop boundary is first detected.
  // A brief noise spike can stop HD early, but cannot cause extra travel.
  if (motionRunning && zDownMonitoring && potRaw <= potDownTrip()) {
    stopAll();
    Serial.println(F("STOP:DOWN_THRESHOLD_DETECTED"));
  }

  updatePotStateFromRaw(potRaw);
}

// -----------------------------------------------------------------------------
// MOTION CONTROL
// -----------------------------------------------------------------------------

void stopAll() {
  motionRunning = false;
  zDownMonitoring = false;

  digitalWrite(X_STEP_PIN, LOW);
  digitalWrite(Y_STEP_PIN, LOW);
  digitalWrite(Z_STEP_PIN, LOW);
}

void startMotion(uint8_t stepPin,
                 uint8_t dirPin,
                 bool direction,
                 bool invertDirection,
                 unsigned long halfPeriodUs,
                 bool monitorPotForZDown) {
  stopAll();

  if (invertDirection) direction = !direction;

  digitalWrite(stepPin, LOW);
  digitalWrite(dirPin, direction ? HIGH : LOW);
  delayMicroseconds(DIR_SETTLE_US);

  activeStepPin = stepPin;
  activeDirPin = dirPin;
  activeHalfPeriodUs = halfPeriodUs;
  lastStepMicros = micros();

  zDownMonitoring = monitorPotForZDown;
  motionRunning = true;
}

void startXY(char axis, bool positiveDirection, bool slow) {
  if (axis == 'X') {
    // R = LOW, L = HIGH before direction inversion.
    bool dir = positiveDirection ? LOW : HIGH;
    startMotion(X_STEP_PIN, X_DIR_PIN, dir, INVERT_X_DIRECTION,
                slow ? XY_SLOW_HALF_PERIOD_US : XY_HALF_PERIOD_US, false);
    Serial.println(positiveDirection ? F("RUN:X_RIGHT") : F("RUN:X_LEFT"));
  } else if (axis == 'Y') {
    // U = LOW, D = HIGH before direction inversion.
    bool dir = positiveDirection ? LOW : HIGH;
    startMotion(Y_STEP_PIN, Y_DIR_PIN, dir, INVERT_Y_DIRECTION,
                slow ? XY_SLOW_HALF_PERIOD_US : XY_HALF_PERIOD_US, false);
    Serial.println(positiveDirection ? F("RUN:Y_UP") : F("RUN:Y_DOWN"));
  }
}

void startZ(bool up) {
  if (!up) {
    samplePotentiometer(true);
    if (!potActive) {
      stopAll();
      Serial.println(F("BLOCKED:ALREADY_AT_DOWN_POSITION"));
      return;
    }
  }

  bool dir = up ? (Z_UP_DIR_LEVEL == HIGH) : (Z_UP_DIR_LEVEL != HIGH);
  startMotion(Z_STEP_PIN, Z_DIR_PIN, dir, INVERT_Z_DIRECTION,
              Z_HALF_PERIOD_US, !up);
  Serial.println(up ? F("RUN:Z_UP") : F("RUN:Z_DOWN_SENSOR_STOP"));
}

// -----------------------------------------------------------------------------
// STATUS / HELP
// -----------------------------------------------------------------------------

void printRead() {
  samplePotentiometer(true);
  Serial.print(F("POT_RAW:"));
  Serial.print(potRaw);
  Serial.print(F(" POT_STATE:"));
  Serial.print(potActive ? 1 : 0);
  Serial.print(F(" POSITION:"));
  Serial.print(potActive ? F("LIFTED") : F("DOWN"));
  Serial.print(F(" THR:"));
  Serial.print(POT_THRESHOLD);
  Serial.print(F(" HYST:"));
  Serial.print(POT_HYSTERESIS);
  Serial.print(F(" LIFT_AT:"));
  Serial.print(POT_HYSTERESIS == 0 ? POT_THRESHOLD + 1 : potLiftTrip());
  Serial.print(F(" DOWN_AT_OR_BELOW:"));
  Serial.print(potDownTrip());
  Serial.print(F(" STABLE_MS:"));
  Serial.println(POT_STABLE_TIME_MS);
}

void printStatus() {
  Serial.print(F("MOTION:"));
  if (!motionRunning) {
    Serial.print(F("STOPPED"));
  } else if (activeStepPin == X_STEP_PIN) {
    Serial.print(F("X"));
  } else if (activeStepPin == Y_STEP_PIN) {
    Serial.print(F("Y"));
  } else if (activeStepPin == Z_STEP_PIN) {
    Serial.print(zDownMonitoring ? F("Z_DOWN") : F("Z_UP"));
  }
  Serial.print(F(" | "));
  printRead();
}

void printHelp() {
  Serial.println(F("--- SHELL-X v0.20 COMMANDS ---"));
  Serial.println(F("U/D, R/L       : XY continuous movement"));
  Serial.println(F("UQ/DQ/RQ/LQ    : XY at 3x slower speed"));
  Serial.println(F("HU             : Z up"));
  Serial.println(F("HD / HX        : Z down, stops at POT_STATE=0 (DOWN)"));
  Serial.println(F("S              : stop all motion"));
  Serial.println(F("READ           : raw reading + binary state"));
  Serial.println(F("STATUS or V    : motion + sensor status"));
  Serial.println(F("THR 0..1023    : set threshold (RAM only)"));
  Serial.println(F("HYST 0..100    : set hysteresis"));
  Serial.println(F("HELP or ?      : show this help"));
  Serial.println(F("Default: DOWN <= THR-2; LIFTED >= THR+2; deadband keeps prior state."));
  Serial.println(F("A new state must remain beyond its boundary for 100 ms."));
  Serial.println(F("P1/P3 removed. Change nominal boundary with THR n; hysteresis with HYST n."));
}

// -----------------------------------------------------------------------------
// SERIAL COMMAND PARSER
// -----------------------------------------------------------------------------

void processCommand(char *line) {
  // Trim leading spaces.
  while (*line == ' ' || *line == '\t') line++;

  // Trim trailing spaces.
  size_t len = strlen(line);
  while (len > 0 && (line[len - 1] == ' ' || line[len - 1] == '\t')) {
    line[--len] = '\0';
  }
  if (len == 0) return;

  // Commands are case-insensitive.
  for (size_t i = 0; i < len; i++) {
    line[i] = (char)toupper((unsigned char)line[i]);
  }

  if (strcmp(line, "S") == 0 || strcmp(line, "STOP") == 0) {
    stopAll();
    Serial.println(F("STOPPED"));
    return;
  }

  if (strcmp(line, "U") == 0)  { startXY('Y', true, false); return; }
  if (strcmp(line, "D") == 0)  { startXY('Y', false, false); return; }
  if (strcmp(line, "R") == 0)  { startXY('X', true, false); return; }
  if (strcmp(line, "L") == 0)  { startXY('X', false, false); return; }
  if (strcmp(line, "UQ") == 0) { startXY('Y', true, true); return; }
  if (strcmp(line, "DQ") == 0) { startXY('Y', false, true); return; }
  if (strcmp(line, "RQ") == 0) { startXY('X', true, true); return; }
  if (strcmp(line, "LQ") == 0) { startXY('X', false, true); return; }

  if (strcmp(line, "HU") == 0) { startZ(true); return; }
  if (strcmp(line, "HD") == 0 || strcmp(line, "HX") == 0) { startZ(false); return; }

  if (strcmp(line, "READ") == 0) { printRead(); return; }
  if (strcmp(line, "STATUS") == 0 || strcmp(line, "V") == 0 ||
      strcmp(line, "J") == 0) {
    printStatus();
    return;
  }

  if (strcmp(line, "HELP") == 0 || strcmp(line, "?") == 0) {
    printHelp();
    return;
  }

  if (strncmp(line, "THR ", 4) == 0) {
    char *endPtr = NULL;
    long value = strtol(line + 4, &endPtr, 10);
    if (endPtr == line + 4 || *endPtr != '\0' || value < 0 || value > 1023) {
      Serial.println(F("ERR:THR_RANGE_0_1023"));
      return;
    }
    POT_THRESHOLD = (int)value;
    potStateInitialized = false;
    potCandidateActive = false;
    samplePotentiometer(true);
    Serial.print(F("THR_SET:"));
    Serial.println(POT_THRESHOLD);
    return;
  }


  if (strncmp(line, "HYST ", 5) == 0) {
    char *endPtr = NULL;
    long value = strtol(line + 5, &endPtr, 10);
    if (endPtr == line + 5 || *endPtr != '\0' || value < 0 || value > 100) {
      Serial.println(F("ERR:HYST_RANGE_0_100"));
      return;
    }
    POT_HYSTERESIS = (uint8_t)value;
    potCandidateActive = false;
    Serial.print(F("HYST_SET:"));
    Serial.println(POT_HYSTERESIS);
    return;
  }

  Serial.print(F("ERR:UNKNOWN_COMMAND:"));
  Serial.println(line);
}

void readSerialCommands() {
  while (Serial.available() > 0) {
    char ch = (char)Serial.read();

    if (ch == '\r' || ch == '\n') {
      if (commandLength > 0) {
        commandBuffer[commandLength] = '\0';
        processCommand(commandBuffer);
        commandLength = 0;
      }
      continue;
    }

    if (commandLength < sizeof(commandBuffer) - 1) {
      commandBuffer[commandLength++] = ch;
    } else {
      commandLength = 0;
      Serial.println(F("ERR:COMMAND_TOO_LONG"));
    }
  }
}

// -----------------------------------------------------------------------------
// SETUP
// -----------------------------------------------------------------------------

void setup() {
  pinMode(X_STEP_PIN, OUTPUT);
  pinMode(X_DIR_PIN, OUTPUT);
  pinMode(Y_STEP_PIN, OUTPUT);
  pinMode(Y_DIR_PIN, OUTPUT);
  pinMode(Z_STEP_PIN, OUTPUT);
  pinMode(Z_DIR_PIN, OUTPUT);
  pinMode(ENABLE_PIN, OUTPUT);
  pinMode(POT_PIN, INPUT);

  digitalWrite(ENABLE_PIN, LOW); // Enable A4988 drivers
  digitalWrite(X_STEP_PIN, LOW);
  digitalWrite(Y_STEP_PIN, LOW);
  digitalWrite(Z_STEP_PIN, LOW);

  stopAll();
  Serial.begin(SERIAL_BAUD);

  potRaw = readPotRaw();
  potActive = rawIsLiftedWithoutHysteresis(potRaw);
  potStateInitialized = true;
  lastPotSampleMs = millis();

  Serial.println(F("SHELL-X v0.20 READY"));
  Serial.println(F("A AXIS REMOVED | BINARY POT=A0 | XYZ ACTIVE"));
  Serial.print(F("POT_INITIAL:POSITION="));
  Serial.print(potActive ? F("LIFTED") : F("DOWN"));
  Serial.print(F(" POT_STATE:"));
  Serial.print(potActive ? 1 : 0);
  Serial.print(F(" POT_RAW:"));
  Serial.print(potRaw);
  Serial.print(F(" THR:"));
  Serial.print(POT_THRESHOLD);
  Serial.print(F(" HYST:"));
  Serial.print(POT_HYSTERESIS);
  Serial.print(F(" LIFT_AT:"));
  Serial.print(POT_HYSTERESIS == 0 ? POT_THRESHOLD + 1 : potLiftTrip());
  Serial.print(F(" DOWN_AT_OR_BELOW:"));
  Serial.print(potDownTrip());
  Serial.print(F(" STABLE_MS:"));
  Serial.println(POT_STABLE_TIME_MS);
  Serial.println(F("Type HELP for commands."));
}

// -----------------------------------------------------------------------------
// MAIN LOOP
// -----------------------------------------------------------------------------

void loop() {
  readSerialCommands();
  samplePotentiometer(false);

  if (motionRunning) {
    unsigned long now = micros();
    if ((unsigned long)(now - lastStepMicros) >= activeHalfPeriodUs) {
      lastStepMicros = now;
      digitalWrite(activeStepPin, !digitalRead(activeStepPin));
    }
  }
}

// Shell x
// Arduino Uno / CNC Shield V3 / MKS TMC2209 V2.0 on the Z socket (UART mode).
//
// WHAT CHANGED FROM SHELL 1.5
//   Removed: VL53L0X ToF (Wire, Adafruit library, filter, TOF streaming,
//            E distance, P1/P3/N height follow) and the IR sensor on D11.
//   Added:   TMC2209 StallGuard4 (sensorless) on Z.
//            HD and HX stop when the Z motor stalls on the ground/object.
//            ZG = sensorless pickup descent, ZP = sensorless press with
//            back-off, ZR = return the exact counted steps to Z0.
//   Unchanged: X/Y/A pins, U/D/L/R and Q variants, HU, G0..G90, S stop,
//            double-tap SW stop, joystick Z/A jog, SW creep, "hx" message,
//            115200 baud.
//
// WIRING (new pins only)
//   D11 (Z+ endstop header, freed by IR removal) -> 1k resistor -> TMC PDN/UART
//   D10 (Y+ endstop header, unused)              -> TMC PDN/UART (direct)
//   A2  (Resume header)                          <- TMC DIAG (front pin)
//   A4/A5 are free now (I2C removed).
//   Remove ALL three microstep jumpers under the Z socket (MS1/MS2 low = UART
//   address 0, and MS3 must not pull socket pin 4 to 5V).
//   The MKS V2.0 left column from EN is: EN, MS1, MS2, UART(R8), PDN/UART,
//   CLK, STEP, DIR. The CNC Shield ties socket pins 5 and 6 (RST/SLP) together,
//   so bend MKS pins 5 and 6 (PDN/UART and CLK) out of the socket and take the
//   UART wire from pin 5 with a Dupont lead. DIAG and INDEX are the extra
//   front pins; only DIAG is used.
//
// HOW STALLGUARD BEHAVES (read before tuning)
//   SG_RESULT (0..510) goes DOWN as motor load goes UP. It does not rise.
//   DIAG goes HIGH when SG_RESULT <= 2 * SGTHRS (hard stall).
//   SG_RESULT is only meaningful while the motor is moving at a steady speed,
//   so all sensing happens during motion, never at standstill.
//   The first Z_SG_BLANK_STEPS (0.4 mm) of every descent ignore stall.
//   A step cap stops every sensorless descent as a backup.
//
// SERIAL COMMANDS (case-insensitive, like Shell 1.5)
//   U/D/L/R, UQ/DQ/LQ/RQ, S, G0..G90, HU, HX: as before.
//   HD : down until stall (DIAG) or the cap. On stall prints "S" (as IR did)
//        and "ZS<n>". At the cap prints "ZM<n>". Refused while contact is
//        latched (latch clears on any upward Z step).
//   HX : down until S / double-tap as before, and now also stops on stall.
//   ZG : pickup descent. Saves Z0 (if not saved), down until DIAG stall.
//        Reply ZS<n> (stall after n steps) or ZM<n> (cap reached).
//   ZP : press. Saves Z0, down; reads SG_RESULT every Z_SG_POLL_MS. When it
//        drops by PRESS_DROP below the free-running baseline (or DIAG
//        fires), stop, reply ZS<n> and SG:HIT=..., back off, reply ZB<n>
//        (n = net steps still below Z0).
//   ZR : return exactly to Z0, reply Z0. Clears the saved Z0.
//   ZT<n> SGTHRS 0..255   ZK<n> press drop 1..500   ZB<n> back-off in 0.1 mm
//   ZC<n> cap in mm       ZV0/ZV1 SG streaming during ZP   ZI re-init TMC
//   E  : StallGuard status (replaces ToF distance).
//   I  : DIAG status (replaces IR diagnostic).
//   J  : SW reading, HX state, Z sensing state.
//   P/N: removed (ToF). Reply ERR:TOF_REMOVED.
//
// Joystick SW: X+ signal (D9), pressed = LOW.
// URX/VRX: A0 (Abort signal), controls Z.
// URY/VRY: A1 (Hold signal), controls A-axis gripper.
// Manual joystick Z ignores StallGuard (as it ignored IR before).
// Double-press SW within 350 ms: stop all movement and transmit "s".
// Hold SW and deflect the stick while idle: UQ/DQ/LQ/RQ creep.
// X/Y/Z: 1/16 microstepping. A: full step.

#include <Arduino.h>
#include <stdio.h>
#include <SoftwareSerial.h>
#include <TMCStepper.h>

const uint8_t X_STEP_PIN = 2;
const uint8_t X_DIR_PIN  = 5;
const uint8_t Y_STEP_PIN = 3;
const uint8_t Y_DIR_PIN  = 6;
const uint8_t Z_STEP_PIN = 4;
const uint8_t Z_DIR_PIN  = 7;
const uint8_t ENABLE_PIN = 8;

#define A_STEP_PIN 12
#define A_DIR_PIN  13

const uint8_t Z_LIMIT_PIN = 9; // Legacy name: joystick SW on X+.

// TMC2209 (Z) pins.
const uint8_t TMC_UART_RX_PIN = 10; // Y+ header, direct to PDN/UART.
const uint8_t TMC_UART_TX_PIN = 11; // Z+ header, through 1k to PDN/UART.
const uint8_t TMC_DIAG_PIN    = A2; // Resume header, DIAG front pin.

const uint8_t JOYSTICK_X_PIN = A0;
const uint8_t JOYSTICK_Y_PIN = A1;

static_assert(TMC_UART_RX_PIN != Z_LIMIT_PIN && TMC_UART_TX_PIN != Z_LIMIT_PIN,
              "TMC UART and SW must use separate Arduino pins.");

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

const uint8_t LIMIT_SWITCH_PRESSED_LEVEL = LOW;

const unsigned long SERIAL_BAUD = 115200;

const uint32_t SW_DEBOUNCE_US = 20000UL;
const uint32_t SW_DOUBLE_PRESS_US = 350000UL;

const uint16_t MOTOR_FULL_STEPS_PER_REV = 200;
const uint8_t MICROSTEP = 16;
const uint8_t A_MICROSTEP = 1;

// Confirmed screw: 2 mm pitch, 8 mm lead (four starts). Use LEAD for travel.
constexpr float Z_SCREW_PITCH_MM = 2.0f; // Informational; not the mm/revolution.
constexpr float Z_LEAD_MM_PER_REV = 8.0f;
constexpr uint16_t Z_STEPS_PER_MM = (uint16_t)(
  (float)MOTOR_FULL_STEPS_PER_REV * MICROSTEP / Z_LEAD_MM_PER_REV + 0.5f);
static_assert(Z_LEAD_MM_PER_REV > 0 && Z_STEPS_PER_MM > 0,
              "Z lead and steps/mm must be positive.");

const long A_STEPS_PER_REV =
  (long)MOTOR_FULL_STEPS_PER_REV * A_MICROSTEP;

const unsigned long STEP_HALF_PERIOD_US = 167;
const unsigned long SLOW_STEP_HALF_PERIOD_US =
  STEP_HALF_PERIOD_US * 3;

// Manual/HU/HD/HX Z uses this fixed rate (about 6024 microsteps/s, 15 mm/s).
const uint32_t Z_STEP_HALF_PERIOD_US = 83UL;

const unsigned long A_START_STEP_DELAY_US = 12000UL;
const unsigned long A_CRUISE_STEP_DELAY_US = 3000UL;
const unsigned long A_ACCEL_STEPS = 12UL;

const bool INVERT_X_DIRECTION = false;
const bool INVERT_Y_DIRECTION = false;
const bool INVERT_Z_DIRECTION = false;
const bool INVERT_A_DIRECTION = false;

const unsigned long COMMAND_WAIT_US = 5000;
const unsigned long G_COMMAND_WAIT_US = 20000;
const uint32_t Z_DIRECTION_SETUP_US = 5;

// -----------------------------------------------------------------------------
// TMC2209 STALLGUARD SETTINGS (tune on the real machine)
// -----------------------------------------------------------------------------
// SoftwareSerial at 115200 keeps each UART byte short (about 87 us with
// interrupts off). If E keeps showing UART errors, try 57600.
const uint32_t TMC_UART_BAUD   = 115200UL;
const uint8_t  TMC_ADDRESS     = 0;      // MS1 = MS2 = low (jumpers removed).
const float    TMC_R_SENSE     = 0.11f;  // MKS TMC2209 V2.0 sense resistor.
const uint16_t Z_RMS_CURRENT_MA = 800;   // Lower current = more sensitive SG.
const uint32_t Z_TCOOLTHRS     = 0xFFFFF; // StallGuard/DIAG active at all speeds.
const uint8_t  Z_SGTHRS_DEFAULT = 70;    // DIAG when SG_RESULT <= 2*SGTHRS.

// Sensing speeds. StallGuard needs a steady, not-too-slow speed.
const uint32_t Z_PICK_HALF_PERIOD_US    = 100UL; // 5000 steps/s = 12.5 mm/s
const uint32_t Z_PRESS_HALF_PERIOD_US   = 125UL; // 4000 steps/s = 10 mm/s
const uint32_t Z_BACKOFF_HALF_PERIOD_US = 250UL; // 2000 steps/s = 5 mm/s
const uint32_t Z_RETURN_HALF_PERIOD_US  = 83UL;  // same as HU

// Ignore stall for the first 0.4 mm of every descent (start-up jerk).
// Must stay SHORTER than the ZP back-off, or a re-press after a back-off
// pushes into the object before sensing starts (found in host tests).
const long     Z_SG_BLANK_STEPS = 160L;
const uint8_t  Z_DIAG_CONFIRM = 1;       // DIAG is a digital push-pull output.
const uint16_t Z_CAP_MM_DEFAULT = 100;   // Backup step cap for every descent.
const uint32_t Z_SG_POLL_MS = 15;        // SG_RESULT poll period during ZP.
const uint32_t Z_SG_REPLY_TIMEOUT_MS = 6;
const uint8_t  Z_SG_BASE_SAMPLES = 4;    // Free-running baseline samples.
const uint8_t  Z_SG_CONFIRM = 2;         // Consecutive low samples to trigger.
const uint16_t Z_PRESS_DROP_DEFAULT = 80; // SG drop from baseline = "pressure".
const uint8_t  Z_BACKOFF_TENTHS_DEFAULT = 5; // 0.5 mm lift after the press.
const uint32_t Z_REVERSE_DWELL_MS = 20;  // Pause before reversing upward.
static_assert((long)Z_BACKOFF_TENTHS_DEFAULT * Z_STEPS_PER_MM / 10L > Z_SG_BLANK_STEPS,
              "Default back-off must exceed the stall blanking distance.");

// -----------------------------------------------------------------------------
// CONTROLLER TYPES AND GLOBAL STATE (all persistent variables are here)
// -----------------------------------------------------------------------------
struct JoystickAxis {
  bool moving = false;
  bool high = false;
  bool direction = false;
  bool stoppedUntilCenter = false;
  uint32_t lastEdge = 0;
};

class HXPauseResumeModule {
public:
  void cancel(char reason = 0);
  void begin(uint8_t direction);
  void planarCommand();
  void explicitHDCommand();
  void gripperCommand();
  void gripperFinished();
  bool checkLimit();
  void service(bool primaryZBusy, bool stopPrefixQueued);
  bool isEnabled() const;
  bool isMoving() const;
  bool isHDOverride() const;
  void printStatus() const;
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
  long segmentStartPos_ = 0; // Stall blanking restarts with every segment.

  void pausePulses();
  void startSegment(uint32_t now);
};

enum class ZMode : uint8_t { IDLE, PICK, PRESS, DWELL, BACKOFF, RETURN };

struct ZSenseState {
  ZMode mode = ZMode::IDLE;
  bool stepHigh = false;
  uint8_t dirLevel = LOW;
  uint32_t lastEdgeUs = 0;
  uint32_t halfPeriodUs = Z_PICK_HALF_PERIOD_US;
  long startPos = 0;
  long targetPos = 0;
  uint32_t dwellStartMs = 0;
  uint32_t baseSum = 0;
  uint16_t baseline = 0;
  uint8_t baseCount = 0;
  uint8_t lowCount = 0;
  uint16_t hitSg = 0;
};

// Non-blocking SG_RESULT reader (register 0x41) on the single-wire UART.
struct SgPoller {
  bool pending = false;
  bool fresh = false;
  uint8_t count = 0;
  uint8_t buf[8];
  uint16_t value = 0;
  uint16_t errors = 0;
  uint32_t sentMs = 0;
  uint32_t nextMs = 0;
};

SoftwareSerial tmcSerial(TMC_UART_RX_PIN, TMC_UART_TX_PIN);
TMC2209Stepper zDriver(&tmcSerial, TMC_R_SENSE, TMC_ADDRESS);
bool tmcReady = false;
uint8_t zSgThrs = Z_SGTHRS_DEFAULT;
uint16_t zPressDrop = Z_PRESS_DROP_DEFAULT;
long zBackoffSteps = (long)Z_BACKOFF_TENTHS_DEFAULT * Z_STEPS_PER_MM / 10L;
long zCapSteps = (long)Z_CAP_MM_DEFAULT * Z_STEPS_PER_MM;
bool zSgStream = false;

// Z position in microsteps, counted on every Z rising edge (up = +1).
long zPosSteps = 0;
long z0Pos = 0;
bool z0Valid = false;
bool zContactLatched = false; // Set on a stall, cleared by any upward step.
uint8_t zDiagHits = 0;
long hdStartPos = 0;
uint8_t zPrimaryDirLevel = LOW;

ZSenseState zs;
SgPoller sg;

uint32_t stopGeneration = 0;

bool running = false;
bool hdActive = false;

uint8_t activeStepPin = X_STEP_PIN;
uint8_t activeDirPin = X_DIR_PIN;

unsigned long activeStepHalfPeriodUs = STEP_HALF_PERIOD_US;
unsigned long lastStepMicros = 0;

long currentASteps = 0;

bool gripperCommandActive = false;
JoystickAxis joystickZ, joystickA;
int joystickX = JOYSTICK_CENTER_X;
int joystickY = JOYSTICK_CENTER_Y;
uint32_t joystickSampleAt = 0;
bool joystickDownReported = false;

bool joystickReadX = true;
bool switchRawPressed = false;
bool switchStablePressed = false;
bool firstSwitchPressPending = false;
bool swQuarterActive = false;
bool swQuarterSuppress = false;

uint32_t switchChangedAt = 0;
uint32_t firstSwitchPressAt = 0;

HXPauseResumeModule hxHold;

// -----------------------------------------------------------------------------
// FUNCTION DECLARATIONS
// -----------------------------------------------------------------------------
void releaseJoystick(JoystickAxis &axis, uint8_t stepPin);
void jogAxis(JoystickAxis &axis, uint8_t stepPin, uint8_t dirPin,
             int value, int center, bool invert, bool serialBusy,
             bool protectDown, uint32_t slowUs, uint32_t fastUs);
void serviceBackground();
void emergencyStop();
void serviceSwitch();
char swQuarterDirection();
void releaseSwQuarter();
void serviceSwQuarter();
bool waitWithMotion(uint32_t duration);
void stopJoystick();
void releaseJoystickZ();
void releaseJoystickA();
void cancelZSense();
bool zSenseActive();
void serviceZSense();

// -----------------------------------------------------------------------------
// Z STEP COUNTING AND STALL DETECTION HELPERS
// -----------------------------------------------------------------------------
inline bool zLevelIsUp(uint8_t dirLevel) {
  return (dirLevel == HIGH) != INVERT_Z_DIRECTION;
}

// Call once per Z rising edge from any Z pulse source.
inline void zCountRising(uint8_t dirLevel) {
  if (zLevelIsUp(dirLevel)) {
    ++zPosSteps;
    zContactLatched = false;
  } else {
    --zPosSteps;
  }
}

bool isDiagHigh() {
  return digitalRead(TMC_DIAG_PIN) == HIGH;
}

// Debounced DIAG stall. Only meaningful during an active, blanked descent.
bool diagStall() {
  if (!tmcReady) { zDiagHits = 0; return false; }
  if (isDiagHigh()) {
    if (zDiagHits < 255) ++zDiagHits;
  } else {
    zDiagHits = 0;
  }
  return zDiagHits >= Z_DIAG_CONFIRM;
}

uint8_t tmcCrc(const uint8_t *data, uint8_t len) {
  uint8_t crc = 0;
  for (uint8_t i = 0; i < len; i++) {
    uint8_t currentByte = data[i];
    for (uint8_t j = 0; j < 8; j++) {
      if ((crc >> 7) ^ (currentByte & 0x01)) crc = (crc << 1) ^ 0x07;
      else crc = (crc << 1);
      currentByte >>= 1;
    }
  }
  return crc;
}

// Configure the driver. Blocking (tens of ms): call only from setup or ZI.
bool tmcInit() {
  tmcSerial.begin(TMC_UART_BAUD);
  zDriver.begin();                 // PDN_UART as UART, MRES from register.
  tmcReady = zDriver.test_connection() == 0;
  if (tmcReady) {
    zDriver.toff(4);
    zDriver.blank_time(24);
    zDriver.I_scale_analog(false); // Current from UART, not the Vref pot.
    zDriver.internal_Rsense(false);
    zDriver.rms_current(Z_RMS_CURRENT_MA);
    zDriver.microsteps(MICROSTEP);
    zDriver.en_spreadCycle(false); // StallGuard4 works in StealthChop only.
    zDriver.pwm_autoscale(true);
    zDriver.TPWMTHRS(0);
    zDriver.TCOOLTHRS(Z_TCOOLTHRS);
    zDriver.semin(0);              // CoolStep off; SG used only for sensing.
    zDriver.SGTHRS(zSgThrs);
  }
  sg.pending = false;
  Serial.println(tmcReady ? F("TMC:OK") : F("ERR:TMC_UART"));
  return tmcReady;
}

// Send one SG_RESULT read request. Blocks only for 4 UART bytes.
void sgPollSend() {
  while (tmcSerial.available() > 0) tmcSerial.read();
  uint8_t request[4] = {0x05, TMC_ADDRESS, 0x41, 0};
  request[3] = tmcCrc(request, 3);
  // TX is wired to RX through 1k, so do not listen to our own echo.
  tmcSerial.stopListening();
  tmcSerial.write(request, 4);
  tmcSerial.listen();
  sg.pending = true;
  sg.fresh = false;
  sg.count = 0;
  sg.sentMs = millis();
}

// Collect the 8-byte reply without waiting. Sets sg.fresh when valid.
void serviceSgPoll() {
  if (!sg.pending) return;
  while (tmcSerial.available() > 0) {
    const uint8_t b = (uint8_t)tmcSerial.read();
    if (sg.count < 8) {
      sg.buf[sg.count++] = b;
    } else {
      for (uint8_t i = 0; i < 7; i++) sg.buf[i] = sg.buf[i + 1];
      sg.buf[7] = b;
    }
    if (sg.count == 8 && sg.buf[0] == 0x05 && sg.buf[1] == 0xFF &&
        sg.buf[2] == 0x41 && tmcCrc(sg.buf, 7) == sg.buf[7]) {
      sg.value = (((uint16_t)sg.buf[5] << 8) | sg.buf[6]) & 0x3FF;
      sg.fresh = true;
      sg.pending = false;
      return;
    }
  }
  if ((uint32_t)(millis() - sg.sentMs) > Z_SG_REPLY_TIMEOUT_MS) {
    sg.pending = false;
    ++sg.errors;
  }
}

void HXPauseResumeModule::cancel(char reason) {
    pausePulses();
    enabled_ = false;
    cancelReason_ = reason;
    hdOverride_ = false;
    gripperBusy_ = false;
    contactReported_ = false;
  }

void HXPauseResumeModule::begin(uint8_t direction) {
    cancel();

    direction_ = direction;
    enabled_ = true;

    digitalWrite(Z_STEP_PIN, LOW);
    digitalWrite(Z_DIR_PIN, direction_);

    if (!checkLimit()) {
      startSegment((uint32_t)micros());
    }
  }

void HXPauseResumeModule::planarCommand() {
    // Preserve the previous HX behavior across X/Y commands.
    if (enabled_) hdOverride_ = false;
  }

void HXPauseResumeModule::explicitHDCommand() {
    pausePulses();
    if (enabled_) hdOverride_ = true;
  }

void HXPauseResumeModule::gripperCommand() {
    pausePulses();
    gripperBusy_ = true;
  }

void HXPauseResumeModule::gripperFinished() {
    gripperBusy_ = false;
  }

bool HXPauseResumeModule::checkLimit() {
    // A single SW press does not pause HX or transmit a stop.
    // Only a double-tap, serial S, or a StallGuard stall stops this descent.
    return false;
  }

void HXPauseResumeModule::service(bool primaryZBusy, bool stopPrefixQueued) {
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

    // New: a downward HX stops on a StallGuard stall after blanking.
    const long travelled = segmentStartPos_ - zPosSteps;
    if (!zLevelIsUp(direction_) && travelled >= Z_SG_BLANK_STEPS &&
        diagStall()) {
      cancel('c');
      zContactLatched = true;
      Serial.print(F("ZS"));
      Serial.println(travelled);
      return;
    }

    // HX runs at the fixed Z pulse rate from its very first step.
    if ((uint32_t)(now - lastStepAt_) < Z_STEP_HALF_PERIOD_US) {
      return;
    }

    if (checkLimit()) return;

    stepHigh_ = !stepHigh_;
    digitalWrite(Z_STEP_PIN, stepHigh_ ? HIGH : LOW);
    if (stepHigh_) zCountRising(direction_);
    lastStepAt_ = now;

  }

bool HXPauseResumeModule::isEnabled() const { return enabled_; }

bool HXPauseResumeModule::isMoving() const { return moving_; }

bool HXPauseResumeModule::isHDOverride() const { return hdOverride_; }

void HXPauseResumeModule::printStatus() const {
    if (!enabled_) {
      if (cancelReason_ == 's') {
        Serial.println(F("HX:CANCELLED_BY_S"));
      } else if (cancelReason_ == 'u') {
        Serial.println(F("HX:CANCELLED_BY_HU"));
      } else if (cancelReason_ == 'c') {
        Serial.println(F("HX:STOPPED_BY_STALL"));
      } else {
        Serial.println(F("HX:OFF_SEND_HX"));
      }
    } else if (hdOverride_) {
      Serial.println(F("HX:PAUSED_FOR_HD"));
    } else if (gripperBusy_) {
      Serial.println(F("HX:PAUSED_FOR_GRIPPER"));
    } else if (moving_) {
      Serial.println(F("HX:ARMED_MOVING"));
    } else {
      Serial.println(F("HX:ARMED"));
    }
  }

void HXPauseResumeModule::pausePulses() {
    if (moving_) digitalWrite(Z_STEP_PIN, LOW);

    moving_ = false;
    stepHigh_ = false;
  }

void HXPauseResumeModule::startSegment(uint32_t now) {
    digitalWrite(Z_STEP_PIN, LOW);
    digitalWrite(Z_DIR_PIN, direction_);

    stepHigh_ = false;
    moving_ = true;
    lastStepAt_ = now;
    segmentStartPos_ = zPosSteps;
    zDiagHits = 0;
  }

void stopAll() {
  running = false;
  hdActive = false;

  digitalWrite(X_STEP_PIN, LOW);
  digitalWrite(Y_STEP_PIN, LOW);
  digitalWrite(Z_STEP_PIN, LOW);
}

bool isLimitSwitchPressed() {
  return digitalRead(Z_LIMIT_PIN) == LIMIT_SWITCH_PRESSED_LEVEL;
}

// Replaces stopForIR(): same "S" reply, plus the step count.
void stopForStall(long travelled) {
  stopAll();

  if (!zContactLatched) {
    Serial.println(F("S"));
    Serial.print(F("ZS"));
    Serial.println(travelled);
  }

  zContactLatched = true;
}

bool serviceSafetyStops() {
  // StallGuard (or the cap) stops serial HD. A single SW press does not.
  if (running && hdActive && activeStepPin == Z_STEP_PIN) {
    const long travelled = hdStartPos - zPosSteps;
    if (travelled >= zCapSteps) {
      stopAll();
      Serial.print(F("ZM"));
      Serial.println(travelled);
      return true;
    }
    if (travelled >= Z_SG_BLANK_STEPS && diagStall()) {
      stopForStall(travelled);
      return true;
    }
  }

  return false;
}

void startMotion(char cmd, bool slow) {
  swQuarterActive = false;
  if (running) digitalWrite(activeStepPin, LOW);
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
  // End the previous primary axis pulse before handing ownership to Z.
  swQuarterActive = false;
  if (running) digitalWrite(activeStepPin, LOW);
  cancelZSense();
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

    // Already resting on something: refuse, exactly like the old IR latch.
    if (zContactLatched) {
      stopForStall(0);
      return;
    }
    // Without StallGuard, HD would only stop at the cap. Refuse instead.
    if (!tmcReady) {
      stopAll();
      Serial.println(F("ERR:TMC_UART"));
      return;
    }

    dirLevel = LOW;
    hdActive = true;
    hdStartPos = zPosSteps;
    zDiagHits = 0;
  } else {
    return;
  }

  if (INVERT_Z_DIRECTION) dirLevel = !dirLevel;

  activeStepPin = Z_STEP_PIN;
  activeDirPin = Z_DIR_PIN;
  activeStepHalfPeriodUs = Z_STEP_HALF_PERIOD_US;
  zPrimaryDirLevel = dirLevel ? HIGH : LOW;

  digitalWrite(Z_STEP_PIN, LOW);
  digitalWrite(activeDirPin, dirLevel);
  delayMicroseconds(Z_DIRECTION_SETUP_US);

  running = true;
  lastStepMicros = micros();
}

void moveAToAngle(uint8_t angle) {
  if (angle > 90) {
    Serial.println(F("ERR:G_RANGE"));
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

// Reads an unsigned number that follows a command letter, servicing motion.
// Returns false on stop, timeout without digits, or out-of-range values.
bool readSerialNumber(long &value, long maxValue) {
  const uint32_t generation = stopGeneration;
  bool gotDigit = false;
  value = 0;
  unsigned long waitStart = micros();

  while ((unsigned long)(micros() - waitStart) < G_COMMAND_WAIT_US) {
    serviceBackground();
    if (stopGeneration != generation) return false;

    if (Serial.available() > 0) {
      char next = (char)Serial.peek();

      if (next >= '0' && next <= '9') {
        Serial.read();
        gotDigit = true;
        if (value <= maxValue) value = value * 10 + (next - '0');
        waitStart = micros();
        continue;
      }

      if (next == '\r' || next == '\n' || next == ' ' || next == '\t') {
        Serial.read();
        if (gotDigit) break;
        continue;
      }

      break;
    }
  }

  return gotDigit && value <= maxValue;
}

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
    Serial.println(F("ERR:G"));
    return;
  }

  if (angle < 0 || angle > 90) {
    Serial.println(F("ERR:G_RANGE"));
    return;
  }

  moveAToAngle((uint8_t)angle);
}

// -----------------------------------------------------------------------------
// SENSORLESS Z: ZG / ZP / ZR (independent cooperative Z pulse generator)
// -----------------------------------------------------------------------------
bool zSenseActive() {
  return zs.mode != ZMode::IDLE;
}

void stopZSensePulses() {
  if (zs.stepHigh) digitalWrite(Z_STEP_PIN, LOW);
  zs.stepHigh = false;
}

void cancelZSense() {
  stopZSensePulses();
  zs.mode = ZMode::IDLE;
  sg.pending = false;
  sg.fresh = false;
}

// Take Z away from every other Z source before sensorless motion.
void claimZForSense() {
  hxHold.cancel();
  if (running && activeStepPin == Z_STEP_PIN) {
    digitalWrite(Z_STEP_PIN, LOW);
    running = false;
    hdActive = false;
  }
  releaseJoystickZ();
  joystickZ.stoppedUntilCenter = true;
  cancelZSense();
}

void beginZPulses(ZMode mode, bool upward, uint32_t halfPeriodUs) {
  uint8_t level = upward ? HIGH : LOW;
  if (INVERT_Z_DIRECTION) level = level == HIGH ? LOW : HIGH;
  digitalWrite(Z_STEP_PIN, LOW);
  digitalWrite(Z_DIR_PIN, level);
  zs.mode = mode;
  zs.dirLevel = level;
  zs.stepHigh = false;
  zs.halfPeriodUs = halfPeriodUs;
  zs.lastEdgeUs = micros(); // First edge after one half period: DIR setup OK.
}

void startZSenseDescent(ZMode mode) {
  if (!tmcReady) { Serial.println(F("ERR:TMC_UART")); return; }
  if (zContactLatched) { Serial.println(F("ZS0")); return; } // Already touching.
  claimZForSense();
  if (!z0Valid) { z0Pos = zPosSteps; z0Valid = true; }
  zs.startPos = zPosSteps;
  zs.baseSum = 0;
  zs.baseCount = 0;
  zs.baseline = 0;
  zs.lowCount = 0;
  zs.hitSg = 0;
  zDiagHits = 0;
  sg.nextMs = millis();
  beginZPulses(mode, false,
    mode == ZMode::PICK ? Z_PICK_HALF_PERIOD_US : Z_PRESS_HALF_PERIOD_US);
  Serial.println(mode == ZMode::PICK ? F("ZG:DOWN") : F("ZP:DOWN"));
}

void startZReturn() {
  if (!z0Valid) { Serial.println(F("ERR:Z0_NOT_SAVED")); return; }
  claimZForSense();
  if (zPosSteps == z0Pos) {
    z0Valid = false;
    Serial.println(F("Z0"));
    return;
  }
  zs.targetPos = z0Pos;
  beginZPulses(ZMode::RETURN, z0Pos > zPosSteps, Z_RETURN_HALF_PERIOD_US);
}

void zSenseContact(long travelled, bool byDiag) {
  stopZSensePulses();
  zContactLatched = true;
  Serial.print(F("ZS"));
  Serial.println(travelled);
  if (zs.mode != ZMode::PRESS) {
    zs.mode = ZMode::IDLE;
    return;
  }
  Serial.print(F("SG:HIT="));
  Serial.print(byDiag ? (int)-1 : (int)zs.hitSg);
  Serial.print(F(" BASE="));
  Serial.print(zs.baseline);
  Serial.println(byDiag ? F(" BY=DIAG") : F(" BY=SG"));
  sg.pending = false;
  zs.targetPos = zPosSteps + zBackoffSteps;
  zs.dwellStartMs = millis();
  zs.mode = ZMode::DWELL;
}

void handlePressSample(uint16_t value) {
  if (zSgStream && Serial.availableForWrite() >= 12) {
    Serial.print(F("SG:"));
    Serial.println(value);
  }
  if (zs.baseCount < Z_SG_BASE_SAMPLES) {
    zs.baseSum += value;
    if (++zs.baseCount == Z_SG_BASE_SAMPLES)
      zs.baseline = (uint16_t)(zs.baseSum / Z_SG_BASE_SAMPLES);
    return;
  }
  // More pressure = LOWER SG_RESULT. Trigger on a drop below the baseline.
  if ((uint32_t)value + zPressDrop <= zs.baseline) {
    if (++zs.lowCount >= Z_SG_CONFIRM) {
      zs.hitSg = value;
      zSenseContact(zs.startPos - zPosSteps, false);
    }
  } else {
    zs.lowCount = 0;
  }
}

void serviceZSense() {
  if (zs.mode == ZMode::IDLE) return;

  if (zs.mode == ZMode::DWELL) {
    if ((uint32_t)(millis() - zs.dwellStartMs) < Z_REVERSE_DWELL_MS) return;
    if (zBackoffSteps <= 0) {
      zs.mode = ZMode::IDLE;
      Serial.print(F("ZB"));
      Serial.println(z0Pos - zPosSteps);
      return;
    }
    beginZPulses(ZMode::BACKOFF, true, Z_BACKOFF_HALF_PERIOD_US);
    return;
  }

  if (zs.mode == ZMode::PICK || zs.mode == ZMode::PRESS) {
    const long travelled = zs.startPos - zPosSteps;
    if (travelled >= zCapSteps) {
      stopZSensePulses();
      zs.mode = ZMode::IDLE;
      sg.pending = false;
      Serial.print(F("ZM"));
      Serial.println(travelled);
      return;
    }
    if (travelled >= Z_SG_BLANK_STEPS) {
      if (diagStall()) { zSenseContact(travelled, true); return; }
      if (zs.mode == ZMode::PRESS) {
        serviceSgPoll();
        if (sg.fresh) {
          sg.fresh = false;
          handlePressSample(sg.value);
          if (zs.mode != ZMode::PRESS) return;
        }
        if (!sg.pending && (int32_t)(millis() - sg.nextMs) >= 0) {
          sg.nextMs = millis() + Z_SG_POLL_MS;
          sgPollSend();
        }
      }
    }
  } else if (zPosSteps == zs.targetPos) { // BACKOFF or RETURN finished.
    stopZSensePulses();
    const ZMode finished = zs.mode;
    zs.mode = ZMode::IDLE;
    if (finished == ZMode::RETURN) {
      z0Valid = false;
      Serial.println(F("Z0"));
    } else {
      Serial.print(F("ZB"));
      Serial.println(z0Pos - zPosSteps);
    }
    return;
  }

  // Fresh timestamp: a UART send above may have taken a few hundred us.
  // One edge per call, so a late call never produces a burst.
  const uint32_t now = micros();
  if ((uint32_t)(now - zs.lastEdgeUs) < zs.halfPeriodUs) return;
  zs.stepHigh = !zs.stepHigh;
  digitalWrite(Z_STEP_PIN, zs.stepHigh ? HIGH : LOW);
  // Time-stamp AFTER the edge: if a UART RX interrupt lands between micros()
  // and digitalWrite, the next edge still waits a full half period
  // (host tests showed a 22% short period without this).
  zs.lastEdgeUs = micros();
  if (zs.stepHigh) zCountRising(zs.dirLevel);
}

const __FlashStringHelper* zModeLabel() {
  switch (zs.mode) {
    case ZMode::PICK: return F("ZG_DOWN");
    case ZMode::PRESS: return F("ZP_DOWN");
    case ZMode::DWELL: return F("ZP_DWELL");
    case ZMode::BACKOFF: return F("ZP_BACKOFF");
    case ZMode::RETURN: return F("ZR_RETURN");
    default: break;
  }
  return F("IDLE");
}

void printSgStatus() {
  if (!tmcReady) { Serial.println(F("ERR:TMC_UART")); return; }
  uint16_t value = sg.value;
  bool valid = true;
  if (!zSenseActive()) {
    // Blocking library read (a few ms). Only on request, never in the loop.
    value = zDriver.SG_RESULT();
    valid = !zDriver.CRCerror;
  }
  Serial.print(F("SG:RESULT="));
  if (valid) Serial.print(value); else Serial.print(F("NA"));
  Serial.print(F(" SGTHRS="));
  Serial.print(zSgThrs);
  Serial.print(F(" DIAG="));
  Serial.print(isDiagHigh() ? 1 : 0);
  Serial.print(F(" UART_ERR="));
  Serial.println(sg.errors);
}

void printZStatus() {
  Serial.print(F("Z:"));
  Serial.print(zModeLabel());
  Serial.print(F(" POS="));
  Serial.print(zPosSteps);
  Serial.print(F(" Z0="));
  if (z0Valid) Serial.print(z0Pos); else Serial.print(F("NA"));
  Serial.print(F(" LATCH="));
  Serial.print(zContactLatched ? 1 : 0);
  Serial.print(F(" TMC="));
  Serial.println(tmcReady ? F("OK") : F("ERR"));
}

void processZCommand() {
  const uint32_t generation = stopGeneration;
  unsigned long waitStart = micros();
  int next = -1;

  while ((unsigned long)(micros() - waitStart) < COMMAND_WAIT_US) {
    serviceBackground();
    if (stopGeneration != generation) return;
    if (Serial.available() > 0) { next = Serial.peek(); break; }
  }
  if (next >= 'A' && next <= 'Z') next = next - 'A' + 'a';
  if (next != 'g' && next != 'p' && next != 'r' && next != 't' &&
      next != 'k' && next != 'b' && next != 'c' && next != 'v' &&
      next != 'i') {
    Serial.println(F("ERR:Z"));
    return;
  }
  Serial.read();

  long value = 0;
  // A stop byte inside a number stops silently, like G (found in host tests).
  #define Z_NUMBER_OR_RETURN(maxV, cond, errText) \
    if (!readSerialNumber(value, maxV) || !(cond)) { \
      if (stopGeneration == generation) Serial.println(F(errText)); \
      return; \
    }
  switch (next) {
    case 'g': startZSenseDescent(ZMode::PICK); return;
    case 'p': startZSenseDescent(ZMode::PRESS); return;
    case 'r': startZReturn(); return;
    case 'i': tmcInit(); return;
    case 't':
      Z_NUMBER_OR_RETURN(255, true, "ERR:ZT")
      zSgThrs = (uint8_t)value;
      if (tmcReady) zDriver.SGTHRS(zSgThrs);
      Serial.print(F("CFG:SGTHRS="));
      Serial.println(zSgThrs);
      return;
    case 'k':
      Z_NUMBER_OR_RETURN(500, value >= 1, "ERR:ZK")
      zPressDrop = (uint16_t)value;
      Serial.print(F("CFG:PRESS_DROP="));
      Serial.println(zPressDrop);
      return;
    case 'b':
      Z_NUMBER_OR_RETURN(100, true, "ERR:ZB")
      zBackoffSteps = value * Z_STEPS_PER_MM / 10L;
      Serial.print(F("CFG:BACKOFF_STEPS="));
      Serial.println(zBackoffSteps);
      if (zBackoffSteps > 0 && zBackoffSteps <= Z_SG_BLANK_STEPS)
        Serial.println(F("WARN:BACKOFF_LE_BLANK"));
      return;
    case 'c':
      Z_NUMBER_OR_RETURN(300, value >= 2, "ERR:ZC")
      zCapSteps = value * Z_STEPS_PER_MM;
      Serial.print(F("CFG:CAP_MM="));
      Serial.println(value);
      return;
    case 'v':
      Z_NUMBER_OR_RETURN(1, true, "ERR:ZV")
      zSgStream = value == 1;
      Serial.print(F("CFG:SG_STREAM="));
      Serial.println(zSgStream ? 1 : 0);
      return;
    default: return;
  }
  #undef Z_NUMBER_OR_RETURN
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

  if (cmd == 'p' || cmd == 'n') {
    Serial.println(F("ERR:TOF_REMOVED"));
    return;
  }

  if (cmd == 'z') { processZCommand(); return; }

  if (cmd == 'g') {
    releaseJoystickA();
    gripperCommandActive = true;
    hxHold.gripperCommand();

    processGCommand();

    hxHold.gripperFinished();
    gripperCommandActive = false;
    return;
  }

  if (cmd == 'e') {
    printSgStatus();
    return;
  }

  if (cmd == 'i') {
    Serial.println(isDiagHigh() ? F("DIAG:STALL") : F("DIAG:CLEAR"));
    return;
  }

  if (cmd == 'j') {
    Serial.println(
      isLimitSwitchPressed() ? F("LIMIT:PRESSED") : F("LIMIT:RELEASED")
    );
    hxHold.printStatus();
    printZStatus();
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
  pinMode(Z_LIMIT_PIN, INPUT_PULLUP);
  pinMode(TMC_DIAG_PIN, INPUT);  // Push-pull output from the TMC2209.
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
  // 12 V must be on: the TMC2209 logic runs from its motor supply regulator.
  // If it was off at boot, send ZI after switching it on.
  tmcInit();
}

// -----------------------------------------------------------------------------
// JOYSTICK
// -----------------------------------------------------------------------------

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

  // protectDown is unused (always false), as in Shell 1.5.
  if (serialBusy || axis.stoppedUntilCenter ||
      (protectDown && !positive && isLimitSwitchPressed())) {
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

    // Manual Z steps are counted so ZR stays exact. Manual A movement
    // deliberately does not change currentASteps.
    if (stepPin == Z_STEP_PIN && axis.high)
      zCountRising(axis.direction ? HIGH : LOW);
  }
}

// Held SW turns the stick into a quarter-speed planar creep.
// On this joystick, VRX is up/down and VRY is left/right.
// The same invert flags used for manual Z and the gripper apply here.
// Positive X after invert is up (UQ); positive Y after invert is right (RQ).
char swQuarterDirection() {
  const int xOffset = joystickX - JOYSTICK_CENTER_X;
  const int yOffset = joystickY - JOYSTICK_CENTER_Y;
  const int xMag = xOffset < 0 ? -xOffset : xOffset;
  const int yMag = yOffset < 0 ? -yOffset : yOffset;
  const bool xActive = xMag > JOYSTICK_DEADZONE;
  const bool yActive = yMag > JOYSTICK_DEADZONE;

  if (!xActive && !yActive) return 0;

  if (!yActive || (xActive && xMag >= yMag)) {
    bool positive = xOffset > 0;
    if (INVERT_JOYSTICK_X) positive = !positive;
    return positive ? 'u' : 'd';
  }

  bool positive = yOffset > 0;
  if (INVERT_JOYSTICK_Y) positive = !positive;
  return positive ? 'r' : 'l';
}

void releaseSwQuarter() {
  if (swQuarterActive && running &&
      (activeStepPin == X_STEP_PIN || activeStepPin == Y_STEP_PIN)) {
    digitalWrite(activeStepPin, LOW);
    running = false;
  }
  swQuarterActive = false;
}

void serviceSwQuarter() {
  if (!switchStablePressed) {
    if (swQuarterActive) {
      releaseSwQuarter();
      // Don't let a still-deflected stick immediately jog Z or the gripper.
      joystickZ.stoppedUntilCenter = true;
      joystickA.stoppedUntilCenter = true;
    }
    swQuarterSuppress = false;
    return;
  }

  const char cmd = swQuarterDirection();

  if (!cmd) {
    if (swQuarterActive) releaseSwQuarter();
    swQuarterSuppress = false;
    return;
  }

  // Double-tap already stopped motion. Wait until the stick is centred
  // or SW is released before another creep can start.
  if (swQuarterSuppress) return;

  if (swQuarterActive) {
    if (!running) {
      swQuarterActive = false;
      swQuarterSuppress = true;
    }
    return;
  }

  // LQ/RQ/UQ/DQ only start from rest. An in-progress motor keeps its command.
  if (running || joystickZ.moving || joystickA.moving || gripperCommandActive) {
    return;
  }

  releaseJoystickZ();
  releaseJoystickA();
  startMotion(cmd, true);
  swQuarterActive = running;
}

void serviceJoystick() {
  uint32_t now = (uint32_t)micros();

  if ((uint32_t)(now - joystickSampleAt) >= JOYSTICK_SAMPLE_US) {
    if (joystickReadX) {
      joystickX = analogRead(JOYSTICK_X_PIN);
    } else {
      joystickY = analogRead(JOYSTICK_Y_PIN);
    }

    joystickReadX = !joystickReadX;
    joystickSampleAt = now;
  }

  serviceSwQuarter();
  // Centre clears the post-creep latch. While SW is held and the stick is
  // not already jogging Z or the gripper, the stick is only the creep control.
  if (!swQuarterDirection()) {
    joystickZ.stoppedUntilCenter = false;
    joystickA.stoppedUntilCenter = false;
  }
  if (swQuarterActive ||
      (switchStablePressed && !joystickZ.moving && !joystickA.moving)) {
    joystickDownReported = false;
    return;
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
      !hxHold.isEnabled() && !zSenseActive() &&
      !joystickZ.stoppedUntilCenter) {
    Serial.println(F("hx"));
    joystickDownReported = true;
  }

  // Serial Z/HX/ZG/ZP/ZR retain priority.
  // Manual Z ignores StallGuard.
  jogAxis(
    joystickZ,
    Z_STEP_PIN,
    Z_DIR_PIN,
    joystickX,
    JOYSTICK_CENTER_X,
    INVERT_Z_DIRECTION,
    (running && activeStepPin == Z_STEP_PIN) || hxHold.isEnabled() || zSenseActive(),
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
// A single press does not stop. The second press inside the window does.
void emergencyStop() {
  ++stopGeneration;

  cancelZSense();  // Z0 is kept, so ZR still works after S.
  hxHold.cancel('s');
  stopAll();
  stopJoystick();
  swQuarterActive = false;
  swQuarterSuppress = true;

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
        Serial.println(F("s"));
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
  // Consume an already-buffered stop before any sensor work or motor edge.
  if (Serial.peek() == 'S' || Serial.peek() == 's') {
    Serial.read();
    emergencyStop();
    return;
  }
  serviceSwitch();

  hxHold.checkLimit();

  serviceSafetyStops();

  const int nextCommand = Serial.peek();

  const bool stopPrefixQueued =
    nextCommand == 's' || nextCommand == 'S' ||
    nextCommand == 'h' || nextCommand == 'H';

  serviceZSense();

  hxHold.service(
    (running && activeStepPin == Z_STEP_PIN) || zSenseActive(),
    stopPrefixQueued
  );

  // Original shared primary serial pulse generator.
  if (running) {
    unsigned long now = micros();

    if ((unsigned long)(now - lastStepMicros) >= activeStepHalfPeriodUs) {
      lastStepMicros = now;

      bool currentState = digitalRead(activeStepPin);
      bool nextState = !currentState;
      digitalWrite(activeStepPin, nextState);
      if (nextState && activeStepPin == Z_STEP_PIN)
        zCountRising(zPrimaryDirLevel);
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

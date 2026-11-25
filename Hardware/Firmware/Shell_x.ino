// -----------------------------------------------------------------------------
// SHELL-X v0.46 - XYZ + A-AXIS GRIPPER + Z LIMIT SWITCH + JOYSTICK
// Arduino Uno + CNC Shield V3
//
// CHANGES FROM v0.45 (Z speed settings only)
//   - Hardware confirmed: A4988, NO microstepping, 8 mm lead, ~200 g, 12 V.
//     v0.45 assumed 1/16 microstepping (from the Shell 1.5 notes), so at full
//     step it would have asked Z for 6000 steps/s (30 rev/s). Corrected:
//     Z_MICROSTEP 16 -> 1 (25 steps/mm).
//   - Real cause of the vibration: v0.14-v0.44 ran Z at 20-94 full steps/s,
//     the full-step resonance range. Z now starts at 6 mm/s (150 steps/s),
//     accelerates at 60 mm/s^2 through that range in ~0.15 s, and cruises at
//     15 mm/s (375 steps/s). Same profile for HU, HD and the joystick.
//   - Everything else from v0.45 unchanged (timer-driven Z steps, joystick
//     priority with serial resume, limit switch, SW stop, gripper, X/Y).
//
// CHANGES FROM v0.44
//   - Z vibration fix. Z is a leadscrew at 1/16 microstepping (same set-up as
//     Shell 1.5: "X/Y/Z: 1/16 microstepping", 8 mm lead). v0.14-v0.44 drove it
//     at 35-94 steps/s, which at 1/16 is only 0.09-0.23 mm/s: a heavily loaded
//     leadscrew sticks and slips at that crawl, so it buzzes and hardly moves.
//     Z now runs like Shell 1.5: up to 15 mm/s (6000 steps/s), plus
//     acceleration from 2.5 mm/s (20 mm/s^2) and a smooth slow-down (40 mm/s^2).
//   - Z steps now come from a hardware timer (Timer1 interrupt), so step
//     timing is exact and does not wobble with the rest of the loop. The
//     interrupt also checks the limit switch before every down step.
//   - Z speeds are set in mm/s. Z_MICROSTEP (default 16) must match the jumpers
//     under the Z driver; with no jumpers set it to 1.
//   - One Z engine for serial HU/HD and the joystick. The joystick has priority
//     while held, but no longer cancels a serial move: a running HU/HD carries
//     on after the stick is released, until S, SW, the limit switch (HD) or
//     another serial motion command. HU/HD sent while the stick is held are
//     accepted and run on release (no more BLOCKED:Z_JOYSTICK_ACTIVE).
//   - Gripper, same rule: a running G move continues to its angle after a
//     joystick jog is released.
//   - HU and HD still use the same profile (the PC app times HU from HD).
//   - X/Y, gripper ramps, limit switch, SW stop and messages otherwise unchanged.
//
// CHANGES FROM v0.43 (Z only)
//   - Z up stall fix (buzzing, little lift):
//       * Joystick Z up: start 20, top 35 steps/s, accel 60 steps/s^2.
//       * Joystick Z down unchanged: start 40, top 65, accel 150.
//       * Serial HU and HD: 94 -> 35 steps/s, accel 200 -> 60. Both kept
//         equal so the PC app's timed lift (hu for as long as hd took)
//         still returns the full distance.
//   - All Z safety logic (limit switch stop, refuse at BELOW) unchanged.
//
// CHANGES FROM v0.42
//   - BELOW and ABOVE swapped: LIMIT_PRESSED_LEVEL LOW -> HIGH.
//     D10 HIGH (switch open) = BELOW, D10 LOW (switch closed to GND) = ABOVE.
//     Z down stops/refuses at BELOW exactly as before.
//     Fail-safe: an unplugged switch reads HIGH = BELOW, so Z down is refused.
//
// CHANGES FROM v0.41
//   - Joystick axes swapped: URX (A0) now jogs Z, URY (A1) now jogs the
//     gripper. URX low = Z up, high = Z down. URY high = toward G90.
//   - Joystick Z stall fix: own speed profile, start 40 steps/s, top
//     65 steps/s (was 25 -> 94), accel 150 steps/s^2. Serial HU/HD unchanged.
//   - New LIMIT_PRESSED_LEVEL option for normally-closed switches.
//
// CHANGES FROM v0.40
//   - Joystick prints nothing at all (JOY_MESSAGES = false): no
//     STOP:JOYSTICK_SW, JOY:READY, JOY:WAITING_FOR_CENTER, and no Z stop /
//     blocked lines caused by joystick Z. The behaviour is unchanged
//     (SW still stops everything, limit switch still stops joystick Z).
//     Serial commands (incl. HD/HU stops and STATUS) and JREAD still reply.
//
// CHANGES FROM v0.39
//   - Joystick moves are silent: no RUN:A_JOG_..., RUN:Z_JOG_..., and no
//     A_DONE after a gripper jog. G commands, safety stops (STOP:/BLOCKED:)
//     and JOY:READY / JOY:WAITING_FOR_CENTER still print.
//
// CHANGES FROM v0.38
//   - Joystick values are no longer printed automatically (JOY_STREAM = false).
//     JREAD still shows them on request. Everything else unchanged.
//
// CHANGES FROM v0.37
//   - Joystick SW (X+, D9) is now a hardware stop: pressing it stops ALL
//     motion immediately (X/Y/Z, gripper, joystick jogs), exactly like S,
//     without sending anything over serial. Works even with
//     JOYSTICK_ENABLED = false. Reports STOP:JOYSTICK_SW.
//     Joystick motion resumes only after SW is released and the stick is
//     centred.
//   - Joystick readings are streamed when they change (max 10 per second),
//     in the same format as JREAD:
//       JOY_URX:<n> JOY_URY:<n> JOY_SW:PRESSED|RELEASED JOY:READY|...
//     so the PC app can show them live. Set JOY_STREAM = false to turn off.
//
// CHANGES FROM v0.36
//   - Potentiometer replaced by a limit switch on Y+ (D10) and GND.
//     Pressed = Z is BELOW, released = Z is ABOVE.
//     Z down (serial HD or joystick) stops immediately when the switch is
//     pressed, and is refused while it is pressed. Z up is always allowed.
//     THR and HYST commands removed (they only applied to the pot).
//   - Joystick added: URX -> Abort (A0), URY -> Hold (A1), SW -> X+ (D9).
//       * URX right/left: gripper jogs while held, in either direction,
//         regardless of its current position. No 0..90 limit and no G0/G90
//         target logic. Releasing the stick ramps down and stops.
//         Changing direction mid-jog ramps down, stops, then reverses.
//       * URY up/down: Z jogs up/down while held, with acceleration and
//         deceleration, at the same time as X/Y or gripper motion.
//         Joystick Z takes over Z from a serial HU/HD move; serial HU/HD
//         are refused while the joystick is driving Z.
//       * SW is read and reported (JREAD, STATUS) but not assigned yet.
//       * After power-on and after S, the stick must return to centre
//         before joystick motion is accepted.
//   - New command JREAD: joystick raw values.
//   - Gripper serial G0..G90 logic, ramps and all XY logic unchanged.
//
// CHANGES FROM v0.35 (gripper only)
//   - Stronger acceleration/deceleration at the start and end of every move
//     (82 -> 91 steps/s^2): A_ACCEL_DEG 15 -> 2 (1 step).
//   - Slower: top speed ~69 -> ~21 steps/s (A_CRUISE_STEP_DELAY_US
//     1800 -> 6000). Full 0 <-> 90 move 2.0 s -> 2.6 s.
//   - Start/stop step unchanged (gentle contact).
//
// CHANGES FROM v0.34 (gripper only)
//   - ~4x more acceleration (19.2 -> 82 steps/s^2, 4.3x): ramp shortened
//     from 45 deg (25 steps) to 15 deg (8 steps), new A_ACCEL_DEG setting.
//   - Same start/stop speed (gentle contact). Peak ~69 steps/s, under the
//     100 steps/s bench limit. Full 0 <-> 90 move: 4.5 s -> 2.0 s.
//   - Trade-off: long moves now have a constant-speed middle section.
//
// CHANGES FROM v0.33 (gripper only)
//   - 3x more acceleration: A_CRUISE_STEP_DELAY_US 5000 -> 1800.
//     Average ramp acceleration 6.3 -> 19.2 steps/s^2 (3.05x).
//     Start/stop speed unchanged (gentle contact). Peak ~49 steps/s,
//     under the 100 steps/s bench limit. Speed still changes every step.
//
// CHANGES FROM v0.32 (gripper only)
//   - More acceleration: A_CRUISE_STEP_DELAY_US 10000 -> 5000.
//     Start/stop speed unchanged, peak speed 2x higher (still well under the
//     100 steps/s bench limit). Ramp still changes speed on every step.
//
// CHANGES FROM v0.31 (labels only, motion unchanged)
//   - Corrected gripper direction labels to match the hardware:
//     G0 = 0 deg = OPEN, G90 = 90 deg = CLOSED. (Same as Shell 1.5, where
//     the higher angle is closing.) Earlier version notes below that say
//     "G0 closed / G90 open" are superseded by this.
//   - Assumed power-on position is still 0 deg, which is now FULLY OPEN:
//     open the gripper fully by hand before power-on/reset.
//   - A_CLOSED_DEG / A_OPEN_DEG renamed A_MIN_DEG / A_MAX_DEG.
//
// CHANGES FROM v0.30 (gripper only)
//   - Opening (toward G90) is now 4x slower too, the same as closing.
//     A_TOWARD_HIGHER_ANGLE_FACTOR 1 -> 4. A full 0 <-> 90 move takes ~6.1 s
//     in both directions.
//
// CHANGES FROM v0.29 (gripper only)
//   - Closing (toward 0 deg) is now the 4x slower direction; opening is
//     normal speed. More torque and a gentler hit when the jaws meet an object.
//   - 2x slower: start delay 12000 -> 20000 us, cruise 5000 -> 10000 us.
//   - Acceleration and deceleration on every step: the ramp now spans the
//     whole move (half up, half down, no constant-speed section).
//     At full step one step = 1.8 deg, the finest possible change.
//
// CHANGES FROM v0.28
//   - Gripper stall fix (motor buzzing back and forth without turning).
//     A_CRUISE_STEP_DELAY_US 3000 -> 5000: top speed 167 -> 100 steps/s,
//     matching the speed proven on the bench test. Shell 1.5 ramp logic,
//     12000 us start delay, and 4x direction factor are unchanged.
//   - Reversal fix: a mid-move opposite Gn now ramps down over at most 12
//     steps (A_ACCEL_STEPS). v0.28 could keep cruising extra steps first.
//
// CHANGES FROM v0.27 (gripper only; XYZ, pot and all other logic unchanged)
//   - Gripper motion now uses the same logic as Shell 1.5 (HOS repo,
//     Hardware/Firmware/Shell_1.5.ino, moveAToAngle):
//       * Steps/rev = 200 x A_MICROSTEP (full step). Angle to steps:
//         ((angle x steps/rev) + 180) / 360. 90 deg = 50 steps.
//       * Step-count ramp: delay 12000 us -> 3000 us over the first 12 steps,
//         3000 -> 12000 us over the last 12. Short moves: half each way.
//       * Same delay on HIGH and LOW halves of each step.
//       * Moves toward a higher angle are 4x slower (all delays x4).
//       * Step counted on the rising edge; 100 us DIR setup.
//   - Kept from v0.23+: non-blocking (XYZ keeps running), and any Gn can
//     interrupt a move. Reversing ramps down over the ramp steps (never past
//     the previous target), stops, changes DIR, then starts a new 1.5 move.
//   - Replaced A_STEPS_PER_DEGREE / A_SPEED / A_ACCEL / A_MIN_SPEED /
//     A_MAX_STEP_RATE with the Shell 1.5 constants.
//
// CHANGES FROM v0.26
//   - Gripper accepts any whole angle: G0, G1, G2 ... G89, G90.
//     The number is the target angle in degrees (0 = closed, 90 = open).
//   - Motion is one continuous ramped sweep from the current angle to the
//     target, passing through every angle in between with no pause.
//     E.g. at 0 deg, G90 sweeps 0 -> 1 -> 2 ... -> 90 without stopping.
//   - A new Gn can be sent mid-move; same smooth interrupt rules as before.
//   - Out-of-range values (e.g. G91, G-5) are rejected: ERR:G_RANGE_0_90.
//   - Resolution note: at full step one step = 1.8 deg, so the real stop
//     angle is the nearest multiple of 1.8 deg (A_DONE reports it).
//     With 1/16 microstepping it is 0.11 deg.
//
// CHANGES FROM v0.25
//   - Gripper turning 5x slower, acceleration/deceleration kept:
//       A_SPEED_DEG_S     180 -> 36  (20 steps/s)
//       A_MIN_SPEED_DEG_S 90  -> 18  (10 steps/s)
//       A_ACCEL_DEG_S2    720 -> 144 (80 steps/s^2)
//   - 90 deg move takes about 2.6 s. Gentler contact with objects.
//
// CHANGES FROM v0.24
//   - Gripper jerk fix for full-step operation. v0.24 started and ended
//     moves at ~5.6 steps/s, where each 1.8 deg full step is felt as a tick.
//   - A_SPEED_DEG_S     90  -> 180 (100 steps/s, matches bench test)
//   - A_ACCEL_DEG_S2    180 -> 720 (400 steps/s^2)
//   - A_MIN_SPEED_DEG_S 10  -> 90  (start/stop at 50 steps/s)
//   - 90 deg move now takes about 0.6 s.
//
// CHANGES FROM v0.23
//   - A_STEPS_PER_DEGREE set to 0.5556 (200-step 1.8 deg motor, full step,
//     no microstepping, 1:1). 90 deg = 50 steps. G0/G90 now enabled.
//     Remove all microstepping jumpers under the A driver.
//
// CHANGES FROM v0.22
//   - New dedicated A-axis for the gripper (CNC Shield V3 A driver).
//     A STEP = D12, A DIR = D13. Set the shield's A-axis jumpers so the A
//     driver takes STEP/DIR from D12/D13 (not cloned from X/Y/Z).
//   - G0  = move gripper to 0 deg (closed).
//   - G90 = move gripper to 90 deg (open).
//   - Steps-per-degree, speed, acceleration are configurable (see
//     A-AXIS GRIPPER CONFIGURATION). Steps-per-degree has NO default:
//     G0/G90 are refused until A_STEPS_PER_DEGREE is set.
//   - Trapezoidal ramp: smooth acceleration and deceleration that stops
//     exactly on target.
//   - Position tracked in software (step count). No homing sensor: the
//     gripper is assumed to be at A_STARTUP_DEG at power-on/reset.
//   - A new G0/G90 may be sent at any time. Same direction: target is
//     updated in flight. Opposite direction: gripper decelerates, stops,
//     changes DIR safely, then moves to the new target.
//   - A-axis runs independently of X, Y and Z, and at the same time as them.
//     XY/Z command switching and the potentiometer sensor stop do not
//     affect the gripper. S still stops everything, including the gripper.
//
// CHANGES FROM v0.21
//   - Joystick removed completely (pins, commands, functions, state).
//   - New ramped motion engine: smooth acceleration and deceleration.
//   - Seamless switching: any motion command can be sent while moving,
//     no S needed first.
//       * Same axis + same direction (e.g. R -> RQ -> R): speed ramps
//         smoothly to the new target, no stop.
//       * Direction change or axis change (e.g. R -> L, R -> U, U -> HD):
//         current motion decelerates to a stop, DIR is changed safely,
//         then the new motion accelerates.
//   - Normal speeds unchanged. Q commands remain 3x slower.
//   - S remains an immediate stop (safety). Potentiometer sensor stop
//     during HD remains immediate (no deceleration, no extra travel).
//   - All potentiometer logic, thresholds, hysteresis, debounce unchanged.
//
// CHANGES FROM v0.14 (carried forward)
//   - Potentiometer is treated as a binary sensor: 0 = inactive, 1 = active.
//   - P1 and P3 have been removed completely.
//   - Three-position calibration (1 / 2 / 3) has been removed.
//   - No automatic lift is performed.
//   - During HD, Z stops when the binary position becomes DOWN (state 0).
//   - A axis, IR sensor and ToF sensor are not used.
//
// LIMIT SWITCH WIRING (v0.37)
//   Switch between CNC Shield Y+ (D10) and GND. Internal pull-up is used.
//   Pressed (D10 LOW) = BELOW. Released (D10 HIGH) = ABOVE.
//   During Z down, Z stops immediately on the first pressed reading.
//   The reported BELOW/ABOVE state changes after 20 ms of stable reading.
//
// JOYSTICK WIRING (v0.37)
//   URX -> Abort (A0), URY -> Hold (A1), SW -> X+ (D9), VCC -> 5V, GND -> GND
//   v0.42: URX = Z jog, URY = gripper jog, SW = stop everything.
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
//   HU          = Z up continuously (v0.45: up to 15 mm/s, with acceleration)
//   HD          = Z down; stops when the limit switch is pressed (BELOW)
//   A joystick Z jog pauses a running HU/HD; it carries on after release.
//
// A-AXIS GRIPPER COMMANDS
//   G0          = gripper to 0 deg (open)
//   G1..G89     = gripper to that angle in degrees
//   G90         = gripper to 90 deg (closed)
//
// OTHER COMMANDS
//   S           = stop all motion, including gripper and joystick (immediate)
//                 (pressing the joystick SW does the same, no serial needed)
//   READ        = show limit switch state
//   JREAD       = show joystick raw values and button
//   STATUS / V  = show motion and sensor status
//   HELP / ?    = show commands
//
// IMPORTANT
//   The limit switch detects position, not force. Do not use this as the only
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

const uint8_t A_STEP_PIN = 12; // A-axis (gripper). Needs A jumpers set to D12/D13.
const uint8_t A_DIR_PIN  = 13; // Note: D13 also drives the on-board LED.

const uint8_t ENABLE_PIN = 8;  // Active LOW, shared by all drivers
const uint8_t LIMIT_PIN  = 10; // Y+ on CNC Shield V3. Switch to GND, LOW = pressed = BELOW

const uint8_t JOY_URX_PIN = A0; // Abort on CNC Shield V3: Z jog (v0.42)
const uint8_t JOY_URY_PIN = A1; // Hold on CNC Shield V3: gripper jog (v0.42)
const uint8_t JOY_SW_PIN  = 9;  // X+ on CNC Shield V3, active LOW: stop everything

const unsigned long SERIAL_BAUD = 115200UL;

// -----------------------------------------------------------------------------
// MOTION CONFIGURATION
// -----------------------------------------------------------------------------

// Values carried forward from the recorded v0.14 configuration.
const unsigned long XY_HALF_PERIOD_US      = 2672UL;
const unsigned long XY_SLOW_HALF_PERIOD_US = XY_HALF_PERIOD_US * 3UL;

const bool INVERT_X_DIRECTION = true;
const bool INVERT_Y_DIRECTION = false;
const bool INVERT_Z_DIRECTION = false;

// In the recorded v0.14 direction mapping, HIGH means Z up.
const uint8_t Z_UP_DIR_LEVEL = HIGH;

const unsigned int DIR_SETTLE_US = 50;

// X/Y step rates (steps per second) derived from the half periods above.
// One step = two half periods (HIGH + LOW).
const float XY_RATE      = 500000.0f / (float)XY_HALF_PERIOD_US;      // ~187 steps/s
const float XY_SLOW_RATE = 500000.0f / (float)XY_SLOW_HALF_PERIOD_US; // ~62 steps/s

// X/Y acceleration / deceleration in steps/s^2 (0 -> full speed in ~0.47 s).
const float XY_ACCEL = 400.0f;

// X/Y start / stop rate. Motion starts at this rate and finishes
// deceleration here. Kept below the slow XY rate so Q commands also ramp.
const float MIN_RATE = 25.0f;

// -----------------------------------------------------------------------------
// Z AXIS CONFIGURATION (v0.45)
// -----------------------------------------------------------------------------

// v0.46 confirmed hardware: A4988 drivers with NO microstepping (full step),
// leadscrew 2 mm pitch / 8 mm lead, about 200 g lifted, 12 V supply.
// Speeds are set in mm/s and converted to steps here (25 full steps per mm).
// Full step is roughest at about 50-200 steps/s (resonance: every 1.8 deg step
// jolts the axis and rings). Z therefore starts at 150 steps/s, accelerates
// through that range in about 0.15 s, and cruises above it at 375 steps/s.
// If microstepping jumpers are fitted later, set Z_MICROSTEP to match them.
const uint16_t Z_MOTOR_FULL_STEPS_PER_REV = 200;
const uint8_t  Z_MICROSTEP = 1;   // 1 = full step (no jumpers)
const float    Z_LEAD_MM_PER_REV = 8.0f;
const float    Z_STEPS_PER_MM =
  (float)Z_MOTOR_FULL_STEPS_PER_REV * (float)Z_MICROSTEP / Z_LEAD_MM_PER_REV;  // 25

// HU and HD use the SAME profile on purpose: the PC app runs HU for as long
// as HD took (AUTO_PICKUP_HU_SCALE = 1.0), so the lift returns the full way.
const float Z_SPEED_MM_S       = 15.0f;  // Top speed, above the rough range (Shell 1.5 speed)
const float Z_JOY_SPEED_MM_S   = 15.0f;  // Joystick top speed
const float Z_START_SPEED_MM_S = 6.0f;   // Every Z move starts and ends here
const float Z_ACCEL_MM_S2      = 60.0f;  // Speed-up: through the rough range in ~0.15 s
const float Z_DECEL_MM_S2      = 60.0f;  // Slow-down for a normal stop or reversal

const float Z_TOP_RATE   = Z_SPEED_MM_S * Z_STEPS_PER_MM;        // 375 steps/s
const float Z_JOY_RATE   = Z_JOY_SPEED_MM_S * Z_STEPS_PER_MM;    // 375 steps/s
const float Z_START_RATE = Z_START_SPEED_MM_S * Z_STEPS_PER_MM;  // 150 steps/s
const float Z_ACCEL_RATE = Z_ACCEL_MM_S2 * Z_STEPS_PER_MM;       // 1500 steps/s^2
const float Z_DECEL_RATE = Z_DECEL_MM_S2 * Z_STEPS_PER_MM;       // 1500 steps/s^2

// -----------------------------------------------------------------------------
// A-AXIS GRIPPER CONFIGURATION
// Same logic and values as Shell 1.5 (HOS repo, Hardware/Firmware/Shell_1.5.ino).
// -----------------------------------------------------------------------------

// Steps per revolution = motor full steps x microstepping (no gearing).
// Shell 1.5: 200-step motor, full step. Change these to match your hardware.
const uint16_t A_MOTOR_FULL_STEPS_PER_REV = 200;
const uint8_t  A_MICROSTEP = 1;   // 1 = full step (no jumpers)
const long A_STEPS_PER_REV = (long)A_MOTOR_FULL_STEPS_PER_REV * A_MICROSTEP;

// Shell 1.5 ramp: step delay goes linearly from START to CRUISE over the
// first A_ACCEL_STEPS steps, and back from CRUISE to START over the last
// A_ACCEL_STEPS steps. Short moves use half the move for each ramp.
// The delay is applied to both the HIGH and the LOW half of each step.
// v0.30: 2x slower than v0.29 (start 25 steps/s before the direction factor).
// v0.33: more acceleration. Start/stop speed unchanged (gentle contact), peak
// mid-move speed 2x higher. Speed range 2:1 -> 4:1.
const unsigned long A_START_STEP_DELAY_US  = 20000UL;
// v0.34: 3x more acceleration (avg 6.3 -> 19.2 steps/s^2).
// v0.35: with the 15 deg ramp, cruise is reached: peak ~69 steps/s.
// v0.36: slower top speed, ~21 steps/s (was ~69).
const unsigned long A_CRUISE_STEP_DELAY_US = 6000UL;

// Ramp length in degrees, converted to steps.
// v0.30-v0.34: 45 deg (25 steps), speed changed on every step of a full move.
// v0.35: 15 deg (8 steps) for ~4x more acceleration. Speeds up over the
// first 15 deg, cruises, slows down over the last 15 deg. Moves of 30 deg or
// less still change speed on every step (Shell 1.5 half-move rule).
// v0.36: 2 deg (1 step): one slow start step, then straight to cruise;
// one slow final step at the end. Sharpest speed-up and slow-down.
const unsigned long A_ACCEL_DEG = 2;
const unsigned long A_ACCEL_STEPS = (A_ACCEL_DEG * A_STEPS_PER_REV + 180L) / 360L;

// Speed factor per direction (every delay is multiplied by it; higher = slower).
// Both directions 4x slower (v0.31). Closing slowly gives more torque and a
// gentler hit on the object.
const uint8_t A_TOWARD_HIGHER_ANGLE_FACTOR = 4;  // Closing, toward G90
const uint8_t A_TOWARD_LOWER_ANGLE_FACTOR  = 4;  // Opening, toward G0

// Shell 1.5: DIR setup time before the first step of a move.
const unsigned int A_DIR_SETUP_US = 100;

const float A_MIN_DEG     = 0.0f;   // G0  = fully OPEN  (lowest allowed angle)
const float A_MAX_DEG     = 90.0f;  // G90 = fully CLOSED (highest allowed angle)
const float A_STARTUP_DEG = 0.0f;   // Assumed position at power-on/reset (fully open)

// Set true if G90 turns the gripper the wrong way.
const bool INVERT_A_DIRECTION = false;

// -----------------------------------------------------------------------------
// LIMIT SWITCH CONFIGURATION
// -----------------------------------------------------------------------------

// Reported BELOW/ABOVE state changes only after this much stable reading.
// The Z-down stop itself does not wait for this (it is immediate).
const unsigned long LIMIT_STABLE_TIME_MS = 20UL;

// v0.42: switch type. LOW = normally-open switch wired C + NO (pressed
// pulls D10 to GND). Use HIGH for a normally-closed switch wired C + NC.
// If READ says PRESSED while the switch is not touched, change this.
const uint8_t LIMIT_PRESSED_LEVEL = HIGH;  // v0.43: swapped (D10 HIGH = BELOW)
const unsigned long LIMIT_SAMPLE_INTERVAL_MS = 0UL; // 0 = read on every loop (fastest stop)

// -----------------------------------------------------------------------------
// JOYSTICK CONFIGURATION
// -----------------------------------------------------------------------------

// Set false if no joystick is connected (floating inputs can cause motion).
const bool JOYSTICK_ENABLED = true;

const int JOY_X_CENTER = 512;
const int JOY_Y_CENTER = 512;
const int JOY_DEADZONE = 150;   // Counts from centre before the stick counts as moved

// v0.42 default: URY high = gripper toward G90 (closing), low = toward G0.
const bool JOY_INVERT_GRIPPER = false;
// v0.42 default: URX low = Z up, URX high = Z down.
const bool JOY_INVERT_Z = false;

const unsigned long JOY_SAMPLE_INTERVAL_MS = 5UL;

// SW stop: pressing SW stops everything. SW counts as released again after
// this long of continuous release (stops bounce from re-triggering).
const bool JOY_SW_STOP_ENABLED = true;

// v0.41: false = the joystick prints nothing (SW stop, ready/centre state,
// joystick Z stops and blocks). Serial commands and JREAD still reply.
const bool JOY_MESSAGES = false;
const unsigned long JOY_SW_RELEASE_MS = 50UL;

// Live joystick readings for the PC app (same format as JREAD).
const bool JOY_STREAM = false;  // v0.39: off, joystick values are not printed
const int JOY_STREAM_DELTA = 8;                  // Counts of change that trigger a line
const unsigned long JOY_STREAM_MIN_MS = 100UL;   // At most 10 lines per second

// Gripper jog target distance. Refreshed while the stick is held, so the
// gripper keeps going for as long as it is held.
const long A_JOG_FAR_STEPS = 100000L;

// -----------------------------------------------------------------------------
// RUNTIME STATE
// -----------------------------------------------------------------------------

bool motionRunning = false;    // X/Y serial motion (main engine)

// Active X/Y motion
char activeAxis = 'X';
uint8_t activeStepPin = X_STEP_PIN;
uint8_t activeDirPin  = X_DIR_PIN;
bool activeDirLevel = LOW;     // Physical DIR pin level (after inversion)
bool activeSlow = false;
float activeAccel = XY_ACCEL;
float currentRate = 0.0f;      // steps/s
float targetRate = 0.0f;       // steps/s; 0 = decelerate to stop
bool stepState = LOW;
unsigned long lastStepMicros = 0;
unsigned long lastRampMicros = 0;

// Pending motion, started after the active motion has decelerated to a stop.
bool pendingValid = false;
char pendingAxis = 'X';
bool pendingDirLevel = LOW;
bool pendingSlow = false;
float pendingRate = 0.0f;

// Serial motion slot (one serial motion at a time, as before):
int8_t serialZCmd = 0;         // Current HU (+1) / HD (-1) / none (0). Kept until
                               // S, SW, the limit switch (HD) or another command.
int8_t pendingSerialZ = 0;     // HU/HD waiting for X/Y to slow to a stop first
bool xyWaitValid = false;      // X/Y waiting for a serial HU/HD to slow to a stop
char xyWaitAxis = 'X';
bool xyWaitDirLevel = LOW;
float xyWaitRate = 0.0f;
bool xyWaitSlow = false;

// A-axis gripper state (independent of the XYZ engine above)
bool aRunning = false;
long aPositionSteps = 0;       // Tracked in software, counted on each rising edge
long aTargetSteps = 0;
long aLimitSteps = 0;          // Farthest point allowed in the current direction
int8_t aMoveDir = 0;           // +1 toward higher angle, -1 toward lower, 0 idle
bool aStepState = LOW;
unsigned long aStepIndex = 0;  // Steps done in this move (Shell 1.5 "fromStart")
unsigned long aLevel = 0;      // Ramp position of the last step
bool aReversing = false;       // Decelerating before a direction change
unsigned long aDecelLeft = 0;  // Steps left in that deceleration
unsigned long aHalfUs = 0;     // Current HIGH/LOW half duration
unsigned long aLastStepMicros = 0;
bool aSerialTargetValid = false;   // A G move is in progress (resumes after a jog)
long aSerialTargetSteps = 0;

// Limit switch state
bool limitRawPressed = false;    // Latest single reading
bool zBelow = false;             // Debounced: true = BELOW (pressed)
bool limitCandidateActive = false;
unsigned long limitCandidateSinceMs = 0;
unsigned long lastLimitSampleMs = 0;

// Z engine (v0.45): serial HU/HD and the joystick share it.
int8_t joyZCmd = 0;              // +1 up / -1 down while the stick is held, else 0
bool joyZBlockedReported = false;
bool zRunning = false;           // Z step timer running
bool zUp = true;                 // Current Z direction
float zRate = 0.0f;              // steps/s
float zTargetRate = 0.0f;        // 0 = slow down to a stop
unsigned long zLastRampMicros = 0;

// Shared with the Timer1 interrupt.
volatile uint16_t zIsrTicks = 1999;       // Timer ticks (0.5 us) per step, minus 1
volatile bool zIsrCheckLimit = false;     // true while moving down
volatile bool zIsrLimitStop = false;      // set when the interrupt stopped Z at BELOW
volatile uint32_t zIsrSteps = 0;          // Z steps made (for STATUS)

// Joystick state
bool joyRequireNeutral = true;   // Stick must be centred before it is used
bool joyNeutralReported = false;
unsigned long joyLastSampleMs = 0;
int joyUrx = 512;
int joyUry = 512;
bool joySwPressed = false;
int8_t joyGripDir = 0;           // Current gripper jog: +1, -1, 0 none

// SW stop state
bool joySwStopLatched = false;   // Set on press; cleared after a stable release
unsigned long joySwReleasedSinceMs = 0;

// Joystick stream state
int joyStreamUrx = -1000;
int joyStreamUry = -1000;
bool joyStreamSw = false;
bool joyStreamReady = false;
unsigned long joyStreamLastMs = 0;

char commandBuffer[40];
uint8_t commandLength = 0;

// Defined below and also called by the limit switch code.
void stopXY();
void zLimitStopped();

// -----------------------------------------------------------------------------
// LIMIT SWITCH READING
// -----------------------------------------------------------------------------

bool readLimitPressed() {
  return digitalRead(LIMIT_PIN) == LIMIT_PRESSED_LEVEL;
}

void printLimitTransition(bool below) {
  Serial.print(F("LIMIT_CHANGED:"));
  Serial.print(below ? F("PRESSED") : F("RELEASED"));
  Serial.print(F(" | POSITION:"));
  Serial.println(below ? F("BELOW") : F("ABOVE"));
}

// Debounce: the reported state changes only after LIMIT_STABLE_TIME_MS of
// continuous opposite readings. Any bounce back restarts the wait.
void updateLimitState(bool pressed) {
  if (pressed == zBelow) {
    limitCandidateActive = false;
    return;
  }
  unsigned long now = millis();
  if (!limitCandidateActive) {
    limitCandidateActive = true;
    limitCandidateSinceMs = now;
    return;
  }
  if ((unsigned long)(now - limitCandidateSinceMs) >= LIMIT_STABLE_TIME_MS) {
    zBelow = pressed;
    limitCandidateActive = false;
    printLimitTransition(zBelow);
  }
}

void sampleLimitSwitch(bool force) {
  unsigned long now = millis();
  if (!force && LIMIT_SAMPLE_INTERVAL_MS > 0UL &&
      (unsigned long)(now - lastLimitSampleMs) + 1UL <= LIMIT_SAMPLE_INTERVAL_MS) {
    return;
  }
  lastLimitSampleMs = now;
  limitRawPressed = readLimitPressed();

  // Fail-safe stop: Z down stops on the first pressed reading, without
  // waiting for the debounce. A bounce can stop Z early, never late.
  // (The Z step interrupt also checks the switch before every down step.)
  if (limitRawPressed && zRunning && !zUp) zLimitStopped();

  updateLimitState(limitRawPressed);
}

// Returns true when Z down is allowed at this moment.
bool zDownAllowed() {
  sampleLimitSwitch(true);
  return !limitRawPressed && !zBelow;
}

// -----------------------------------------------------------------------------
// MOTION CONTROL
// -----------------------------------------------------------------------------

void stopXY() {
  motionRunning = false;
  pendingValid = false;
  pendingSerialZ = 0;
  currentRate = 0.0f;
  targetRate = 0.0f;
  stepState = LOW;
  digitalWrite(X_STEP_PIN, LOW);
  digitalWrite(Y_STEP_PIN, LOW);
}

void axisPins(char axis, uint8_t &stepPin, uint8_t &dirPin) {
  if (axis == 'Y') { stepPin = Y_STEP_PIN; dirPin = Y_DIR_PIN; }
  else             { stepPin = X_STEP_PIN; dirPin = X_DIR_PIN; }
}

// Start an X/Y motion from standstill. DIR is only ever changed here, while
// the step output is LOW and the motor is stopped.
void beginMotion(char axis, bool dirLevel, float rate, bool slow) {
  uint8_t stepPin, dirPin;
  axisPins(axis, stepPin, dirPin);

  digitalWrite(X_STEP_PIN, LOW);
  digitalWrite(Y_STEP_PIN, LOW);
  digitalWrite(dirPin, dirLevel ? HIGH : LOW);
  delayMicroseconds(DIR_SETTLE_US);

  activeAxis = axis;
  activeStepPin = stepPin;
  activeDirPin = dirPin;
  activeDirLevel = dirLevel;
  activeSlow = slow;
  activeAccel = XY_ACCEL;
  targetRate = rate;
  currentRate = rate < MIN_RATE ? rate : MIN_RATE;
  stepState = LOW;
  lastStepMicros = micros();
  lastRampMicros = lastStepMicros;
  motionRunning = true;
}

// True while Z is still moving for a serial HU/HD (not under the joystick).
bool zSerialMoving() {
  return zRunning && joyZCmd == 0;
}

// Request an X/Y motion. Serial commands share one serial motion: a new one
// replaces the old one, in the same order as before:
//   - idle: start immediately with acceleration
//   - same axis + same direction: change target speed, keep moving
//   - otherwise (including a running HU/HD): slow to a stop, then start
void requestMotion(char axis, bool dirLevel, float rate, bool slow) {
  pendingSerialZ = 0;   // A newer X/Y command replaces a waiting HU/HD

  if (serialZCmd != 0 || xyWaitValid) {
    // HU/HD is the current serial motion: end it, start X/Y once Z stops.
    serialZCmd = 0;
    if (zSerialMoving()) {
      xyWaitValid = true;
      xyWaitAxis = axis;
      xyWaitDirLevel = dirLevel;
      xyWaitRate = rate;
      xyWaitSlow = slow;
      return;
    }
    xyWaitValid = false;
  }

  if (!motionRunning) {
    beginMotion(axis, dirLevel, rate, slow);
    return;
  }

  if (axis == activeAxis && dirLevel == activeDirLevel) {
    pendingValid = false;
    targetRate = rate;
    activeSlow = slow;
    return;
  }

  pendingValid = true;
  pendingAxis = axis;
  pendingDirLevel = dirLevel;
  pendingRate = rate;
  pendingSlow = slow;
  targetRate = 0.0f;  // Decelerate, then start the pending motion.
}

void startXY(char axis, bool positiveDirection, bool slow) {
  float rate = slow ? XY_SLOW_RATE : XY_RATE;
  if (axis == 'X') {
    // R = LOW, L = HIGH before direction inversion.
    bool dir = positiveDirection ? LOW : HIGH;
    if (INVERT_X_DIRECTION) dir = !dir;
    requestMotion('X', dir, rate, slow);
    Serial.print(positiveDirection ? F("RUN:X_RIGHT") : F("RUN:X_LEFT"));
  } else if (axis == 'Y') {
    // U = LOW, D = HIGH before direction inversion.
    bool dir = positiveDirection ? LOW : HIGH;
    if (INVERT_Y_DIRECTION) dir = !dir;
    requestMotion('Y', dir, rate, slow);
    Serial.print(positiveDirection ? F("RUN:Y_UP") : F("RUN:Y_DOWN"));
  }
  Serial.println(slow ? F("_SLOW") : F(""));
}

void zStopNow();

// Serial HU / HD. Accepted even while the joystick holds Z: it then runs
// when the stick is released.
void startZ(bool up) {
  if (!up && !zDownAllowed()) {
    // Refuse HD while the limit switch is pressed (BELOW). As before, this
    // also ends the current serial motion.
    stopXY();
    xyWaitValid = false;
    if (zSerialMoving()) zStopNow();
    serialZCmd = 0;
    Serial.println(F("BLOCKED:ALREADY_AT_DOWN_POSITION"));
    return;
  }

  int8_t cmd = up ? 1 : -1;
  xyWaitValid = false;   // HU/HD replaces an X/Y command waiting for Z
  if (motionRunning) {
    // X/Y is the current serial motion: slow it to a stop, then start Z.
    pendingValid = false;
    pendingSerialZ = cmd;
    targetRate = 0.0f;
  } else {
    serialZCmd = cmd;    // The Z engine speeds up, or reverses if needed
  }
  Serial.println(up ? F("RUN:Z_UP") : F("RUN:Z_DOWN_SENSOR_STOP"));
}

// X/Y ramp and step pulses. Called every loop.
void serviceMotion() {
  // X/Y command waiting for a serial HU/HD to finish slowing down.
  if (xyWaitValid && !zSerialMoving()) {
    xyWaitValid = false;
    beginMotion(xyWaitAxis, xyWaitDirLevel, xyWaitRate, xyWaitSlow);
  }

  if (!motionRunning) return;

  unsigned long now = micros();

  // Speed ramp
  float dt = (float)(unsigned long)(now - lastRampMicros) * 1.0e-6f;
  lastRampMicros = now;
  if (currentRate < targetRate) {
    currentRate += activeAccel * dt;
    if (currentRate > targetRate) currentRate = targetRate;
  } else if (currentRate > targetRate) {
    currentRate -= activeAccel * dt;
    if (currentRate < targetRate) currentRate = targetRate;
  }

  // Deceleration to stop complete
  if (targetRate <= 0.0f && currentRate <= MIN_RATE) {
    bool hadPending = pendingValid;
    char pAxis = pendingAxis;
    bool pDir = pendingDirLevel;
    float pRate = pendingRate;
    bool pSlow = pendingSlow;
    int8_t pZ = pendingSerialZ;

    stopXY();
    if (hadPending) {
      beginMotion(pAxis, pDir, pRate, pSlow);
    } else if (pZ != 0) {
      if (pZ < 0 && !zDownAllowed()) {
        Serial.println(F("BLOCKED:ALREADY_AT_DOWN_POSITION"));
      } else {
        serialZCmd = pZ;
      }
    }
    return;
  }

  // Step generation
  if (currentRate < 1.0f) return;
  unsigned long halfPeriodUs = (unsigned long)(500000.0f / currentRate);
  if ((unsigned long)(now - lastStepMicros) >= halfPeriodUs) {
    lastStepMicros = now;
    stepState = !stepState;
    digitalWrite(activeStepPin, stepState);
  }
}

// -----------------------------------------------------------------------------
// A-AXIS GRIPPER CONTROL
// Separate engine with its own state and timing, so it never blocks or is
// blocked by X/Y/Z motion. DIR is only changed while the A motor is stopped.
// -----------------------------------------------------------------------------

bool aConfigured() {
  return A_STEPS_PER_REV > 0;
}

// Shell 1.5 conversion: ((angle x steps/rev) + 180) / 360, rounded.
long aDegToSteps(float deg) {
  long angle = (long)(deg + 0.5f);
  return (angle * A_STEPS_PER_REV + 180L) / 360L;
}

float aStepsToDeg(long steps) {
  return aConfigured() ? (float)steps * 360.0f / (float)A_STEPS_PER_REV : 0.0f;
}

void initGripperConfig() {
  if (!aConfigured()) return;
  aPositionSteps = aDegToSteps(A_STARTUP_DEG);
  aTargetSteps = aPositionSteps;
  aLimitSteps = aPositionSteps;
}

void stopGripper() {
  aRunning = false;
  aMoveDir = 0;
  aReversing = false;
  aDecelLeft = 0;
  aLevel = 0;
  aHalfUs = 0;
  aStepState = LOW;
  aTargetSteps = aPositionSteps; // Nothing resumes after a stop
  aLimitSteps = aPositionSteps;
  aSerialTargetValid = false;    // The G move is finished or cancelled
  digitalWrite(A_STEP_PIN, LOW);
}

// Start a move from standstill (+1 higher angle, -1 lower angle).
// DIR is only changed here, with STEP LOW and the motor stopped.
void aStartMove(int8_t dir) {
  digitalWrite(A_STEP_PIN, LOW);
  bool level = dir > 0 ? HIGH : LOW;   // Shell 1.5: higher angle = HIGH
  if (INVERT_A_DIRECTION) level = !level;
  digitalWrite(A_DIR_PIN, level ? HIGH : LOW);
  delayMicroseconds(A_DIR_SETUP_US);

  aMoveDir = dir;
  aStepIndex = 0;
  aLevel = 0;
  aReversing = false;
  aDecelLeft = 0;
  aLimitSteps = aTargetSteps;
  aStepState = LOW;
  aHalfUs = 0;                         // First step starts immediately
  aLastStepMicros = micros();
  aRunning = true;
}

// v0.40: true while the current gripper move came from the joystick, so it
// finishes without printing. A G command clears it.
bool aQuietMove = false;

void printGripperDone() {
  if (aQuietMove) return;
  Serial.print(F("A_DONE:POS_DEG:"));
  Serial.println(aStepsToDeg(aPositionSteps), 1);
}

// Shell 1.5 step delay for a given ramp position.
unsigned long aStepDelayUs(unsigned long level, unsigned long rampSteps) {
  if (rampSteps == 0) return A_START_STEP_DELAY_US;
  if (level >= rampSteps) return A_CRUISE_STEP_DELAY_US;
  unsigned long delayRange = A_START_STEP_DELAY_US - A_CRUISE_STEP_DELAY_US;
  return A_START_STEP_DELAY_US - (delayRange * level) / rampSteps;
}

// Gn. Safe to call at any time, including mid-move.
//   - idle: start toward target (Shell 1.5 move)
//   - moving, target still ahead: keep going, new end ramp is applied
//   - moving, target behind: ramp down over the Shell 1.5 ramp steps
//     (never past the previous target), stop, reverse, move to new target
void aSetTargetSteps(long target);

void requestGripper(float deg) {
  if (!aConfigured()) {
    Serial.println(F("ERR:A_STEPS_PER_REV_NOT_SET"));
    return;
  }

  aQuietMove = false;
  Serial.print(F("RUN:A_TO_DEG:"));
  Serial.println((int)deg);
  aSetTargetSteps(aDegToSteps(deg));
  // v0.45: remember the G target, so a joystick jog cannot cancel it.
  aSerialTargetSteps = aDegToSteps(deg);
  aSerialTargetValid = aRunning;  // false if already at the angle (done)
}

// Shared target logic for G commands and the joystick jog.
void aSetTargetSteps(long target) {
  aTargetSteps = target;

  if (!aRunning) {
    if (aTargetSteps == aPositionSteps) {
      printGripperDone();
      return;
    }
    aStartMove(aTargetSteps > aPositionSteps ? 1 : -1);
    return;
  }

  long ahead = (aTargetSteps - aPositionSteps) * (long)aMoveDir;
  if (ahead > 0) {
    aReversing = false;
    aDecelLeft = 0;
    aLimitSteps = aTargetSteps;
    return;
  }

  if (!aReversing) {
    long room = (aLimitSteps - aPositionSteps) * (long)aMoveDir;
    if (room < 0) room = 0;
    // Ramp down over at most A_ACCEL_STEPS steps (cruise level = full ramp).
    unsigned long lv = aLevel > A_ACCEL_STEPS ? A_ACCEL_STEPS : aLevel;
    aDecelLeft = lv < (unsigned long)room ? lv : (unsigned long)room;
    aReversing = true;
  }
}

void serviceGripper() {
  if (!aRunning) return;

  unsigned long now = micros();
  if ((unsigned long)(now - aLastStepMicros) < aHalfUs) return;
  aLastStepMicros = now;

  if (aStepState == HIGH) {
    // End of HIGH half: drop STEP, then wait the LOW half (same delay).
    aStepState = LOW;
    digitalWrite(A_STEP_PIN, LOW);
    return;
  }

  // End of LOW half: decide the next step.
  unsigned long level;
  unsigned long rampSteps;

  if (aReversing) {
    if (aDecelLeft == 0) {
      if (aTargetSteps == aPositionSteps) {
        stopGripper();
        printGripperDone();
      } else {
        aStartMove(aTargetSteps > aPositionSteps ? 1 : -1);
      }
      return;
    }
    aDecelLeft--;
    level = aDecelLeft;
    rampSteps = A_ACCEL_STEPS;
  } else {
    long remaining = (aTargetSteps - aPositionSteps) * (long)aMoveDir;
    if (remaining <= 0) {
      // Target reached after the final LOW half (Shell 1.5 behaviour).
      stopGripper();
      printGripperDone();
      return;
    }
    // Shell 1.5: ramp = A_ACCEL_STEPS, or half the move if shorter.
    unsigned long total = aStepIndex + (unsigned long)remaining;
    rampSteps = A_ACCEL_STEPS;
    if (rampSteps * 2UL > total) rampSteps = total / 2UL;
    // Shell 1.5: edge distance = min(steps from start, steps from end).
    unsigned long fromEnd = (unsigned long)remaining - 1UL;
    level = aStepIndex < fromEnd ? aStepIndex : fromEnd;
  }

  uint8_t factor = aMoveDir > 0 ? A_TOWARD_HIGHER_ANGLE_FACTOR
                                : A_TOWARD_LOWER_ANGLE_FACTOR;
  aLevel = level;
  aHalfUs = aStepDelayUs(level, rampSteps) * (unsigned long)factor;

  // Rising edge: A4988 steps here. Count it now (Shell 1.5 behaviour).
  aStepState = HIGH;
  digitalWrite(A_STEP_PIN, HIGH);
  aPositionSteps += aMoveDir;
  aStepIndex++;
}

// Joystick gripper jog: keep moving in dir (+1 toward G90, -1 toward G0)
// for as long as the stick is held. No angle limits, no G target logic.
// Position is still counted, so STATUS stays meaningful.
void gripperJog(int8_t dir) {
  if (!aConfigured()) return;
  aQuietMove = true;   // v0.40: joystick moves are silent
  joyGripDir = dir;
  aSetTargetSteps(aPositionSteps + (long)dir * A_JOG_FAR_STEPS);
}

// Stick released. v0.45: if a G move was running, carry on to its angle.
// Otherwise ramp down over the ramp steps and stop where it ends.
void gripperJogRelease() {
  joyGripDir = 0;
  if (aSerialTargetValid) {
    aQuietMove = false;           // The G move reports A_DONE when it arrives
    aSetTargetSteps(aSerialTargetSteps);
    return;
  }
  if (!aRunning) return;
  long rampDown;
  if (aReversing) {
    rampDown = (long)aDecelLeft;   // Finish the ramp-down already in progress
    aReversing = false;
    aDecelLeft = 0;
  } else {
    rampDown = (long)(aLevel > A_ACCEL_STEPS ? A_ACCEL_STEPS : aLevel);
  }
  aTargetSteps = aPositionSteps + (long)aMoveDir * rampDown;
  aLimitSteps = aTargetSteps;
}

void printGripperStatus() {
  Serial.print(F("A:"));
  if (!aConfigured()) {
    Serial.print(F("NOT_CONFIGURED"));
    return;
  }
  Serial.print(aRunning ? (joyGripDir != 0 ? F("JOG") : F("MOVING")) : F("IDLE"));
  Serial.print(F(" A_POS_DEG:"));
  Serial.print(aStepsToDeg(aPositionSteps), 1);
  Serial.print(F(" A_TARGET_DEG:"));
  Serial.print(aStepsToDeg(aTargetSteps), 1);
}

// -----------------------------------------------------------------------------
// Z ENGINE (v0.45)
// One engine drives Z for serial HU/HD and the joystick. Steps come from a
// Timer1 interrupt, so step timing is exact whatever else the loop is doing.
//   - The joystick has priority while held. A running HU/HD is not cancelled:
//     it carries on when the stick is released.
//   - Same direction: speed changes smoothly. Opposite direction: slows to a
//     stop, changes DIR while stopped, then speeds up the other way.
//   - Never moves down at BELOW. While moving down the interrupt checks the
//     switch before every step and stops on the first pressed reading.
// -----------------------------------------------------------------------------

inline bool zLimitPressedFast() {
  bool high = (PINB & _BV(2)) != 0;              // D10 = PB2
  return high == (LIMIT_PRESSED_LEVEL == HIGH);
}

ISR(TIMER1_COMPA_vect) {
  if (zIsrCheckLimit && zLimitPressedFast()) {
    TIMSK1 &= (uint8_t)~_BV(OCIE1A);             // Stop at the switch, no step
    zIsrLimitStop = true;
    return;
  }
  PORTD |= _BV(4);                                // Z STEP (D4) high
  OCR1A = zIsrTicks;                              // Interval to the next step
  zIsrSteps++;
  delayMicroseconds(2);                           // A4988 needs >= 1 us high
  PORTD &= (uint8_t)~_BV(4);                      // Z STEP low
}

// Timer ticks (0.5 us each) for one step at this rate, as OCR1A wants it.
uint16_t zTicksForRate(float rate) {
  if (rate < 31.0f) rate = 31.0f;                 // Longest interval ~32 ms
  float t = 2000000.0f / rate - 1.0f;
  if (t > 65535.0f) t = 65535.0f;
  if (t < 99.0f) t = 99.0f;                       // Shortest interval 50 us
  return (uint16_t)t;
}

void zTimerStart(uint16_t ticks) {
  noInterrupts();
  TCCR1A = 0;
  TCCR1B = 0;
  TCNT1 = 0;
  OCR1A = ticks;
  zIsrTicks = ticks;
  zIsrLimitStop = false;
  TIFR1 = _BV(OCF1A);                             // Clear an old match
  TIMSK1 |= _BV(OCIE1A);
  TCCR1B = _BV(WGM12) | _BV(CS11);                // CTC on OCR1A, clk/8
  interrupts();
}

void zTimerStop() {
  noInterrupts();
  TIMSK1 &= (uint8_t)~_BV(OCIE1A);
  TCCR1B = 0;
  interrupts();
  digitalWrite(Z_STEP_PIN, LOW);
}

void zSetTicks(uint16_t ticks) {
  noInterrupts();
  zIsrTicks = ticks;
  interrupts();
}

// Immediate stop, no ramp (S, SW, limit switch).
void zStopNow() {
  zTimerStop();
  zRunning = false;
  zRate = 0.0f;
  zTargetRate = 0.0f;
}

// Start from standstill. DIR is only changed here, with the timer stopped.
void zStartMove(bool up) {
  bool dir = up ? (Z_UP_DIR_LEVEL == HIGH) : (Z_UP_DIR_LEVEL != HIGH);
  if (INVERT_Z_DIRECTION) dir = !dir;
  digitalWrite(Z_STEP_PIN, LOW);
  digitalWrite(Z_DIR_PIN, dir ? HIGH : LOW);
  delayMicroseconds(DIR_SETTLE_US);

  zUp = up;
  zRate = Z_START_RATE;
  zTargetRate = Z_START_RATE;
  zLastRampMicros = micros();
  noInterrupts();
  zIsrCheckLimit = !up;
  interrupts();
  zTimerStart(zTicksForRate(zRate));
  zRunning = true;
}

// Z reached the limit switch while moving down (seen by the interrupt or by
// the loop, whichever was first).
void zLimitStopped() {
  bool wasRunning = zRunning;
  zStopNow();
  noInterrupts();
  zIsrLimitStop = false;
  interrupts();
  if (!wasRunning) return;
  if (serialZCmd < 0) {
    serialZCmd = 0;                               // HD is complete
    Serial.println(F("STOP:LIMIT_SWITCH_BELOW"));
  } else if (JOY_MESSAGES) {
    Serial.println(F("STOP:LIMIT_SWITCH_BELOW"));
  }
}

// Ramp Z toward what is wanted now. Called every loop.
void serviceZ() {
  if (zIsrLimitStop) zLimitStopped();

  bool fromJoystick = joyZCmd != 0;
  int8_t cmd = fromJoystick ? joyZCmd : serialZCmd;

  // Never drive down at BELOW.
  if (cmd < 0 && (limitRawPressed || zBelow)) {
    if (!fromJoystick) {
      serialZCmd = 0;
      Serial.println(F("BLOCKED:ALREADY_AT_DOWN_POSITION"));
    }
    cmd = 0;
  }

  if (!zRunning) {
    if (cmd != 0) zStartMove(cmd > 0);
    return;
  }

  unsigned long now = micros();
  float dt = (float)(unsigned long)(now - zLastRampMicros) * 1.0e-6f;
  zLastRampMicros = now;

  bool sameDir = (cmd > 0 && zUp) || (cmd < 0 && !zUp);
  zTargetRate = sameDir ? (fromJoystick ? Z_JOY_RATE : Z_TOP_RATE) : 0.0f;

  if (zRate < zTargetRate) {
    zRate += Z_ACCEL_RATE * dt;
    if (zRate > zTargetRate) zRate = zTargetRate;
  } else if (zRate > zTargetRate) {
    zRate -= Z_DECEL_RATE * dt;
    if (zRate < zTargetRate) zRate = zTargetRate;
  }

  if (zTargetRate <= 0.0f && zRate <= Z_START_RATE) {
    zStopNow();                                   // Slowed down: stop
    if (cmd != 0) zStartMove(cmd > 0);            // Then reverse if wanted
    return;
  }
  if (zRate < Z_START_RATE) zRate = Z_START_RATE;
  zSetTicks(zTicksForRate(zRate));
}

// -----------------------------------------------------------------------------
// STOP EVERYTHING (S command and joystick SW)
// -----------------------------------------------------------------------------

void stopEverything() {
  joyZCmd = 0;
  serialZCmd = 0;
  zStopNow();
  stopXY();
  xyWaitValid = false;
  stopGripper();
  joyGripDir = 0;
  joyRequireNeutral = true;   // Stick must be centred (and SW released) first
  joyNeutralReported = false;
}

// Called every loop. Pressing SW stops everything at once.
void checkJoystickSwStop() {
  if (!JOY_SW_STOP_ENABLED) return;
  bool pressed = digitalRead(JOY_SW_PIN) == LOW;
  unsigned long now = millis();
  if (pressed) {
    joySwReleasedSinceMs = now;
    if (!joySwStopLatched) {
      joySwStopLatched = true;
      stopEverything();
      if (JOY_MESSAGES) Serial.println(F("STOP:JOYSTICK_SW"));
    }
  } else if (joySwStopLatched &&
             (unsigned long)(now - joySwReleasedSinceMs) >= JOY_SW_RELEASE_MS) {
    joySwStopLatched = false;
  }
}

// -----------------------------------------------------------------------------
// JOYSTICK
// -----------------------------------------------------------------------------

void printJoystickLine();
void streamJoystick();

void readJoystick() {
  joyUrx = analogRead(JOY_URX_PIN);
  joyUry = analogRead(JOY_URY_PIN);
  joySwPressed = digitalRead(JOY_SW_PIN) == LOW;
}

void updateJoystick() {
  if (!JOYSTICK_ENABLED) return;
  unsigned long now = millis();
  if ((unsigned long)(now - joyLastSampleMs) < JOY_SAMPLE_INTERVAL_MS) return;
  joyLastSampleMs = now;

  readJoystick();
  streamJoystick();

  // v0.42: axes swapped. URY now drives the gripper, URX drives Z.
  int8_t gripDir = 0;
  if (joyUry > JOY_Y_CENTER + JOY_DEADZONE) gripDir = 1;        // toward G90
  else if (joyUry < JOY_Y_CENTER - JOY_DEADZONE) gripDir = -1;  // toward G0
  if (JOY_INVERT_GRIPPER) gripDir = -gripDir;

  int8_t zDir = 0;
  if (joyUrx < JOY_X_CENTER - JOY_DEADZONE) zDir = 1;           // Z up
  else if (joyUrx > JOY_X_CENTER + JOY_DEADZONE) zDir = -1;     // Z down
  if (JOY_INVERT_Z) zDir = -zDir;

  // After power-on or S, wait for a centred stick.
  if (joyRequireNeutral) {
    if (gripDir == 0 && zDir == 0 && !joySwPressed && !joySwStopLatched) {
      joyRequireNeutral = false;
      joyNeutralReported = false;
      if (JOY_MESSAGES) Serial.println(F("JOY:READY"));
    } else if (!joyNeutralReported) {
      if (JOY_MESSAGES) Serial.println(F("JOY:WAITING_FOR_CENTER"));
      joyNeutralReported = true;
    }
    return;
  }

  // Gripper: URY
  if (gripDir != 0) gripperJog(gripDir);
  else if (joyGripDir != 0) gripperJogRelease();

  // Z: URX. Priority while held; a serial HU/HD carries on after release.
  if (zDir < 0 && !zDownAllowed()) {
    if (JOY_MESSAGES && !joyZBlockedReported) {
      Serial.println(F("BLOCKED:LIMIT_SWITCH_BELOW"));
    }
    joyZBlockedReported = true;
    zDir = 0;
  } else {
    joyZBlockedReported = false;
  }
  joyZCmd = zDir;
}

void printJoystickLine() {
  Serial.print(F("JOY_URX:"));
  Serial.print(joyUrx);
  Serial.print(F(" JOY_URY:"));
  Serial.print(joyUry);
  Serial.print(F(" JOY_SW:"));
  Serial.print(joySwPressed ? F("PRESSED") : F("RELEASED"));
  Serial.print(F(" JOY:"));
  if (!JOYSTICK_ENABLED) Serial.println(F("DISABLED"));
  else Serial.println(joyRequireNeutral ? F("WAITING_FOR_CENTER") : F("READY"));
}

void printJoystickRead() {
  readJoystick();
  printJoystickLine();
}

// Send a JREAD-format line when the readings change (rate-limited).
void streamJoystick() {
  if (!JOY_STREAM) return;
  unsigned long now = millis();
  if ((unsigned long)(now - joyStreamLastMs) < JOY_STREAM_MIN_MS) return;
  bool ready = !joyRequireNeutral;
  bool changed = abs(joyUrx - joyStreamUrx) >= JOY_STREAM_DELTA ||
                 abs(joyUry - joyStreamUry) >= JOY_STREAM_DELTA ||
                 joySwPressed != joyStreamSw ||
                 ready != joyStreamReady;
  if (!changed) return;
  joyStreamUrx = joyUrx;
  joyStreamUry = joyUry;
  joyStreamSw = joySwPressed;
  joyStreamReady = ready;
  joyStreamLastMs = now;
  printJoystickLine();
}

// -----------------------------------------------------------------------------
// STATUS / HELP
// -----------------------------------------------------------------------------

void printRead() {
  sampleLimitSwitch(true);
  Serial.print(F("LIMIT:"));
  Serial.print(limitRawPressed ? F("PRESSED") : F("RELEASED"));
  Serial.print(F(" POSITION:"));
  Serial.print(zBelow ? F("BELOW") : F("ABOVE"));
  Serial.print(F(" STABLE_MS:"));
  Serial.println(LIMIT_STABLE_TIME_MS);
}

void printStatus() {
  Serial.print(F("MOTION:"));
  if (!motionRunning) {
    Serial.print(xyWaitValid ? F("WAITING_FOR_Z") : F("STOPPED"));
  } else {
    Serial.print(activeAxis == 'Y' ? F("Y") : F("X"));
    if (activeSlow) Serial.print(F("_SLOW"));
    Serial.print(F(" RATE:"));
    Serial.print(currentRate, 1);
    Serial.print(F(" TARGET:"));
    Serial.print(targetRate, 1);
    if (pendingValid || pendingSerialZ != 0) Serial.print(F(" SWITCHING"));
  }
  Serial.print(F(" | Z:"));
  if (zRunning) {
    Serial.print(zUp ? F("UP") : F("DOWN"));
    Serial.print(joyZCmd != 0 ? F(" JOY") : F(" SERIAL"));
    Serial.print(F(" MM_S:"));
    Serial.print(zRate / Z_STEPS_PER_MM, 1);
  } else {
    Serial.print(F("IDLE"));
  }
  Serial.print(F(" SERIAL_Z:"));
  Serial.print(serialZCmd > 0 ? F("HU") : (serialZCmd < 0 ? F("HD") : F("NONE")));
  Serial.print(F(" | "));
  printGripperStatus();
  Serial.print(F(" | "));
  printRead();
}

void printHelp() {
  Serial.println(F("--- SHELL-X v0.46 COMMANDS ---"));
  Serial.println(F("U/D, R/L       : XY continuous movement"));
  Serial.println(F("UQ/DQ/RQ/LQ    : XY at 3x slower speed"));
  Serial.println(F("HU             : Z up (15 mm/s, with acceleration)"));
  Serial.println(F("HD / HX        : Z down, stops when limit switch pressed (BELOW)"));
  Serial.println(F("G0             : gripper to 0 deg (open)"));
  Serial.println(F("G1..G89        : gripper to that angle (deg)"));
  Serial.println(F("G90            : gripper to 90 deg (closed)"));
  Serial.println(F("S              : stop all motion incl. gripper + joystick (immediate)"));
  Serial.println(F("READ           : limit switch state"));
  Serial.println(F("JREAD          : joystick raw values + button"));
  Serial.println(F("STATUS or V    : motion + sensor status"));
  Serial.println(F("HELP or ?      : show this help"));
  Serial.println(F("JOYSTICK:"));
  Serial.println(F("  URY          : gripper jog while held; a running G move continues after"));
  Serial.println(F("  URX          : Z jog while held; a running HU/HD continues after release"));
  Serial.println(F("  SW (press)   : stop everything, like S (no serial needed)"));
  Serial.println(F("  centre stick + release SW after power-on, S or SW stop"));
  Serial.println(F("Limit switch (Y+): pressed = BELOW, released = ABOVE."));
  Serial.println(F("Z down stops immediately when pressed; refused while pressed."));
  Serial.println(F("Switch commands anytime, no S needed:"));
  Serial.println(F("  same axis+dir (R<->RQ): smooth speed change"));
  Serial.println(F("  new dir/axis: decelerate, stop, then accelerate"));
  Serial.println(F("Gripper sweeps smoothly through every angle to the target."));
  Serial.println(F("Gripper runs independently of XYZ; any Gn can interrupt another."));
  Serial.println(F("Gripper assumed at 0 deg (fully open) at power-on."));
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
    stopEverything();
    Serial.println(F("STOPPED"));
    return;
  }

  // Gn: gripper to n degrees, n = 0..90 (whole numbers only).
  if (line[0] == 'G') {
    char *endPtr = NULL;
    long value = strtol(line + 1, &endPtr, 10);
    bool digitsOnly = isdigit((unsigned char)line[1]) && *endPtr == '\0';
    if (!digitsOnly || value < (long)A_MIN_DEG || value > (long)A_MAX_DEG) {
      Serial.println(F("ERR:G_RANGE_0_90"));
      return;
    }
    requestGripper((float)value);
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
  if (strcmp(line, "JREAD") == 0) { printJoystickRead(); return; }
  if (strcmp(line, "STATUS") == 0 || strcmp(line, "V") == 0) {
    printStatus();
    return;
  }

  if (strcmp(line, "HELP") == 0 || strcmp(line, "?") == 0) {
    printHelp();
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
  pinMode(A_STEP_PIN, OUTPUT);
  pinMode(A_DIR_PIN, OUTPUT);
  pinMode(ENABLE_PIN, OUTPUT);
  pinMode(LIMIT_PIN, INPUT_PULLUP);
  pinMode(JOY_URX_PIN, INPUT);
  pinMode(JOY_URY_PIN, INPUT);
  pinMode(JOY_SW_PIN, INPUT_PULLUP);

  digitalWrite(ENABLE_PIN, LOW); // Enable A4988 drivers
  digitalWrite(X_STEP_PIN, LOW);
  digitalWrite(Y_STEP_PIN, LOW);
  digitalWrite(Z_STEP_PIN, LOW);
  digitalWrite(A_STEP_PIN, LOW);

  stopXY();
  zStopNow();             // Timer1 off until Z is asked to move
  initGripperConfig();
  stopGripper();
  Serial.begin(SERIAL_BAUD);

  joySwStopLatched = digitalRead(JOY_SW_PIN) == LOW;
  joySwReleasedSinceMs = millis();

  limitRawPressed = readLimitPressed();
  zBelow = limitRawPressed;
  lastLimitSampleMs = millis();

  Serial.println(F("SHELL-X v0.46 READY"));
  Serial.println(F("A AXIS=GRIPPER (STEP D12, DIR D13) | LIMIT SWITCH=Y+ (D10)"));
  Serial.println(F("JOYSTICK: URX=A0 (Z) URY=A1 (gripper) SW=D9 (STOP)"));
  Serial.println(F("SMOOTH ACCEL/DECEL | SEAMLESS COMMAND SWITCHING"));
  Serial.print(F("Z_CONFIG: MICROSTEP:"));
  Serial.print(Z_MICROSTEP);
  Serial.print(F(" STEPS_PER_MM:"));
  Serial.print(Z_STEPS_PER_MM, 0);
  Serial.print(F(" MM_S:"));
  Serial.print(Z_SPEED_MM_S, 1);
  Serial.print(F(" START_MM_S:"));
  Serial.print(Z_START_SPEED_MM_S, 1);
  Serial.print(F(" ACCEL_MM_S2:"));
  Serial.println(Z_ACCEL_MM_S2, 1);
  if (aConfigured()) {
    Serial.print(F("A_CONFIG: STEPS_PER_REV:"));
    Serial.print(A_STEPS_PER_REV);
    Serial.print(F(" STEPS_FOR_90:"));
    Serial.print(aDegToSteps(90));
    Serial.print(F(" START_US:"));
    Serial.print(A_START_STEP_DELAY_US);
    Serial.print(F(" CRUISE_US:"));
    Serial.print(A_CRUISE_STEP_DELAY_US);
    Serial.print(F(" RAMP_STEPS:"));
    Serial.print(A_ACCEL_STEPS);
    Serial.print(F(" UP_x"));
    Serial.print(A_TOWARD_HIGHER_ANGLE_FACTOR);
    Serial.print(F(" DOWN_x"));
    Serial.print(A_TOWARD_LOWER_ANGLE_FACTOR);
    Serial.print(F(" ASSUMED_START_DEG:"));
    Serial.println(A_STARTUP_DEG, 1);
  } else {
    Serial.println(F("A_CONFIG: A_STEPS_PER_REV NOT SET - G0..G90 DISABLED"));
  }
  Serial.print(F("LIMIT_INITIAL:"));
  Serial.print(limitRawPressed ? F("PRESSED") : F("RELEASED"));
  Serial.print(F(" POSITION:"));
  Serial.println(zBelow ? F("BELOW") : F("ABOVE"));
  if (!JOYSTICK_ENABLED) Serial.println(F("JOY:DISABLED"));
  Serial.println(F("Type HELP for commands."));
}

// -----------------------------------------------------------------------------
// MAIN LOOP
// -----------------------------------------------------------------------------

void loop() {
  readSerialCommands();
  checkJoystickSwStop();
  sampleLimitSwitch(false);
  updateJoystick();
  serviceMotion();
  serviceZ();
  serviceGripper();
}

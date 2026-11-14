# Shell x host test harness

Builds the real, unmodified `../Shell_x.ino` on the box with a mock
Arduino core and runs 26 scenario tests. Run: `./run.sh` (all) or
`./run.sh <test_name>`. Charts: `python3 plot.py` -> `Shell_x_tests.png` (needs matplotlib, run after `./run.sh`).

- `mock/Arduino.h`, `mock/mock.cpp`: virtual clock (each core call costs AVR-like time,
  analogRead 112 us), pins, Serial input queue and output capture, scheduled input.
- `mock/SoftwareSerial.h`: single-wire UART with echo when listening, interrupt-off
  byte time on TX, RX interrupt time charged on each received byte.
- Simulated TMC2209: real datagrams with CRC, register writes (IFCNT), reads of
  IOIN/GCONF/SG_RESULT, DIAG HIGH when moving and SG_RESULT <= 2*SGTHRS.
- `mock/TMCStepper.h`: stand-in for TMC2209Stepper with the library's blocking
  timing (2 ms reply delays, 5 ms timeout, 2 retries). The real library is
  compiled only by arduino-cli.
- Z plant: 400 steps/mm, object height, hard contact (SG -1500/mm, 0.25 mm
  compliance, then lost steps) or 5 mm sponge (SG -40/mm), Gaussian noise,
  start-up jerk (SG 40 for the first 100 steps from rest), SG updated per full step.
- Compiler: any C++17 compiler (`CXX=clang++ ./run.sh`). Linux or macOS (uses fork).
- This is a simulation. It checks logic and timing, not real StallGuard values.

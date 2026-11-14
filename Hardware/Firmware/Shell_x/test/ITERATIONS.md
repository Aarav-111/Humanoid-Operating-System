# Test iterations

| Run | Result | Found | Change |
|---|---|---|---|
| 1 | 18/25 | 1) "zt1s": S inside a number stopped, then still printed ERR:ZT. 2) Re-press after a 0.5 mm back-off ground 148 steps into a hard object, because the 1 mm stall blanking was longer than the back-off. 3) Harness issues: edge metric counted the stop edge as a burst; G90 stop test sent S after the blocking move; speed test called ZR without Z0. | Firmware: silent return on stop inside Z number parsing; blanking 400 -> 160 steps (0.4 mm), static_assert back-off > blanking, WARN:BACKOFF_LE_BLANK on ZB. Harness: rising-edge period metric, scheduled serial input, speed test order. |
| 2 | 23/25 | ZP step period 194 us vs 250 us requested: an SG reply RX interrupt between micros() and digitalWrite shortened the next period by 22%. | Firmware: time-stamp the ZG/ZP/ZR edge after digitalWrite. |
| 3 | 25/25 | All pass. Added a 300-command random fuzz test. | |
| 4 | 25/26 | Fuzz: lost steps came only from joystick DOWN jogs into the object (manual Z ignores StallGuard, as it ignored IR in Shell 1.5), and a 135 us hand-over between two different moves. | Harness only: fuzz uses joystick up/centre, measures bursts inside each move. Firmware unchanged (documented limit). |
| 5 | 26/26 | Final. | |

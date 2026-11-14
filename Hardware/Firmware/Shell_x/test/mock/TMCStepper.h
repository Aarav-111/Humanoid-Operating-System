// Host mock of TMCStepper's TMC2209Stepper, speaking real TMC UART datagrams
// (sync, address, register, CRC) to the simulated driver, with the library's
// blocking timing (2 ms reply delays, 5 ms timeout, 2 retries).
#pragma once
#include "Arduino.h"
class TMC2209Stepper {
public:
  TMC2209Stepper(Stream *s, float rs, uint8_t addr) : s_(s), addr_(addr) { (void)rs; }
  bool CRCerror = false;
  void begin();
  uint8_t test_connection();
  void toff(uint8_t v);
  void blank_time(uint8_t v);
  void I_scale_analog(bool b);
  void internal_Rsense(bool b);
  void rms_current(uint16_t ma);
  void microsteps(uint16_t ms);
  void en_spreadCycle(bool b);
  void pwm_autoscale(bool b);
  void TPWMTHRS(uint32_t v);
  void TCOOLTHRS(uint32_t v);
  void semin(uint8_t v);
  void SGTHRS(uint8_t v);
  uint16_t SG_RESULT();
  uint32_t read(uint8_t reg);
  void write(uint8_t reg, uint32_t val);
private:
  Stream *s_;
  uint8_t addr_;
  uint32_t gconf_ = 0x1C1, chopconf_ = 0x10000053, pwmconf_ = 0xC10D0024, coolconf_ = 0;
};

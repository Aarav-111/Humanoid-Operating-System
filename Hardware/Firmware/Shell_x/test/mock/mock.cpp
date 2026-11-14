#include "Arduino.h"
#include "SoftwareSerial.h"
#include "TMCStepper.h"
#include "sim.h"
#include <random>

namespace sim {
uint64_t t = 0;
Plant plant;
Tmc tmc;
EdgeStats edges;
std::vector<OutLine> out;
std::deque<uint8_t> serialIn;
std::vector<Sample> trace;
int analogVal[8] = {512, 512, 512, 512, 512, 512, 512, 512};
int swLevel = HIGH;
uint8_t pinLevel[32] = {0};
uint64_t sampleEveryUs = 500;
bool tracing = false;
static uint64_t nextSample = 0;
static std::mt19937 rng(12345);
static std::normal_distribution<double> nd(0.0, 1.0);
static std::string partial;
struct Pending { uint64_t t; uint8_t b; };
static std::deque<Pending> rxPending;
static SoftwareSerial *swPort = nullptr;
struct Sched { uint64_t t; std::string s; };
static std::deque<Sched> sched;
static bool inAdvance = false;
long fwStepsProbe = 0;

double rnd() { return nd(rng); }

void reset() {
  t = 0; plant = Plant(); tmc = Tmc(); edges.reset(); out.clear(); serialIn.clear();
  trace.clear(); for (int i = 0; i < 8; i++) analogVal[i] = 512; swLevel = HIGH;
  memset(pinLevel, 0, sizeof pinLevel); partial.clear(); rxPending.clear(); sched.clear(); nextSample = 0;
  tmc.reg[0x06] = 0x21000000u; // IOIN VERSION = 0x21
}

static uint8_t crc8(const uint8_t *d, uint8_t len) {
  uint8_t crc = 0;
  for (uint8_t i = 0; i < len; i++) { uint8_t c = d[i];
    for (uint8_t j = 0; j < 8; j++) { if ((crc >> 7) ^ (c & 1)) crc = (crc << 1) ^ 0x07; else crc <<= 1; c >>= 1; } }
  return crc;
}

static long byteUs() { return swPort ? (10000000L / swPort->baud_) : 87; }

static void tmcReceive(uint8_t b) {
  if (!tmc.present) return;
  auto &in = tmc.in;
  if (in.empty() && b != 0x05) return;
  in.push_back(b);
  if (in.size() >= 3 && !(in[2] & 0x80) && in.size() == 4) {
    if (crc8(in.data(), 3) == in[3] && in[1] == 0) {
      ++tmc.reads;
      uint8_t r = in[2];
      uint32_t v = tmc.reg[r];
      if (r == 0x41) v = (uint32_t)plant.sgLatched;
      if (r == 0x02) v = tmc.ifcnt;
      uint8_t rep[8] = {0x05, 0xFF, r, (uint8_t)(v >> 24), (uint8_t)(v >> 16), (uint8_t)(v >> 8), (uint8_t)v, 0};
      rep[7] = crc8(rep, 7);
      uint64_t at = t + 8 * byteUs() / 10 + 10; // SENDDELAY 8 bit times
      for (int i = 0; i < 8; i++) rxPending.push_back({at + (uint64_t)(i + 1) * byteUs(), rep[i]});
    } else ++tmc.badCrc;
    in.clear();
  } else if (in.size() == 8) {
    if (crc8(in.data(), 7) == in[7] && in[1] == 0) {
      ++tmc.writes; ++tmc.ifcnt;
      uint8_t r = in[2] & 0x7F;
      tmc.reg[r] = ((uint32_t)in[3] << 24) | ((uint32_t)in[4] << 16) | ((uint32_t)in[5] << 8) | in[6];
    } else ++tmc.badCrc;
    in.clear();
  }
}

int diagLevel() {
  if (!tmc.present) return LOW;
  uint32_t thr = tmc.reg[0x40] & 0xFF;
  bool moving = (t - plant.lastStepT) < 3000 && plant.lastStepT != 0;
  if (!moving || thr == 0) return LOW;
  return plant.sgLatched <= (int)(2 * thr) ? HIGH : LOW;
}

static void updateSg() {
  if (plant.stepsSinceRest < plant.jerkSteps) { plant.sgLatched = plant.jerkSg; return; }
  double v = plant.sgBase + plant.noise * rnd();
  if (plant.objPresent) {
    double z = plant.actSteps / 400.0;
    double pen = plant.floorMm - z;
    if (pen > 0) {
      if (plant.sponge) {
        if (pen <= plant.spongeMm) v -= plant.spongeK * pen;
        else v -= plant.spongeK * plant.spongeMm + plant.hardK * (pen - plant.spongeMm);
      } else v -= plant.hardK * pen;
    }
  }
  if (v < 0) v = 0; if (v > 510) v = 510;
  plant.sgLatched = (int)v;
}

static void zStep() {
  bool up = pinLevel[7] == HIGH;
  if (pinLevel[8] != LOW) return; // drivers disabled
  if (t - plant.lastStepT > 5000) plant.stepsSinceRest = 0;
  plant.lastStepT = t;
  ++plant.stepsSinceRest;
  plant.cmdSteps += up ? 1 : -1;
  long limit = LONG_MIN;
  if (plant.objPresent) {
    double lim = plant.floorMm - (plant.sponge ? plant.spongeMm : 0) - plant.complianceMm;
    limit = (long)floor(lim * 400.0);
  }
  if (!up && plant.actSteps - 1 < limit) ++plant.lost;
  else plant.actSteps += up ? 1 : -1;
  if (plant.stepsSinceRest % 16 == 0 || plant.stepsSinceRest < plant.jerkSteps + 2) updateSg();
}

void advance(uint64_t us) {
  uint64_t end = t + us;
  while (true) {
    uint64_t next = end;
    if (!rxPending.empty() && rxPending.front().t < next) next = rxPending.front().t;
    t = next;
    if (tracing) while (nextSample <= t) {
      trace.push_back({nextSample, plant.actSteps / 400.0, plant.sgLatched, diagLevel(), fwStepsProbe});
      nextSample += sampleEveryUs;
    }
    if (!rxPending.empty() && rxPending.front().t <= t) {
      uint8_t b = rxPending.front().b; rxPending.pop_front();
      if (swPort && swPort->listening_) { swPort->simDeliver(b); end += byteUs() * 9 / 10; } // ISR time
      continue;
    }
    while (!sched.empty() && sched.front().t <= t) { for (char c : sched.front().s) serialIn.push_back((uint8_t)c); sched.pop_front(); }
    if (t >= end) break;
  }
}

void sendAt(uint64_t atUs, const std::string &s) { sched.push_back({atUs, s}); }
void send(const std::string &s) { for (char c : s) serialIn.push_back((uint8_t)c); }
} // namespace sim

using namespace sim;

uint32_t micros() { advance(3); return (uint32_t)t; }
uint32_t millis() { advance(2); return (uint32_t)(t / 1000); }
void delay(uint32_t ms) { advance((uint64_t)ms * 1000); }
void delayMicroseconds(uint32_t us) { advance(us); }
void pinMode(uint8_t pin, uint8_t mode) { if (mode == INPUT_PULLUP && pin < 32) pinLevel[pin] = HIGH; advance(2); }
void digitalWrite(uint8_t pin, uint8_t level) {
  advance(4);
  level = level ? HIGH : LOW;
  if (pin >= 32) return;
  uint8_t old = pinLevel[pin];
  pinLevel[pin] = level;
  if (old != level && (pin == 2 || pin == 3 || pin == 4 || pin == 12)) {
    if (edges.seen[pin]) { uint64_t g = t - edges.lastT[pin]; if (g < edges.minGap[pin]) edges.minGap[pin] = g; }
    edges.seen[pin] = true; edges.lastT[pin] = t;
    if (level == HIGH) {
      if (edges.riseSeen[pin]) { uint64_t g = t - edges.lastRise[pin]; if (g < edges.minRise[pin]) edges.minRise[pin] = g; }
      edges.riseSeen[pin] = true; edges.lastRise[pin] = t;
      ++edges.rising[pin];
      if (pin == 4) zStep();
      if (pin == 12) plant.aSteps += pinLevel[13] == HIGH ? 1 : -1;
      if (pin == 2) { ++plant.xSteps; plant.xDirAtLast = pinLevel[5]; }
      if (pin == 3) { ++plant.ySteps; plant.yDirAtLast = pinLevel[6]; }
    }
  }
}
int digitalRead(uint8_t pin) {
  advance(3);
  if (pin == 9) return swLevel;
  if (pin == A2) return diagLevel();
  return pin < 32 ? pinLevel[pin] : LOW;
}
int analogRead(uint8_t pin) { advance(112); return analogVal[(pin - A0) & 7]; }

HardwareSerialMock Serial;
int HardwareSerialMock::available() { advance(1); return (int)serialIn.size(); }
int HardwareSerialMock::peek() { advance(1); return serialIn.empty() ? -1 : serialIn.front(); }
int HardwareSerialMock::read() { advance(1); if (serialIn.empty()) return -1; int c = serialIn.front(); serialIn.pop_front(); return c; }
size_t HardwareSerialMock::write(uint8_t b) {
  advance(1);
  if (b == '\n') { if (!partial.empty() && partial.back() == '\r') partial.pop_back(); out.push_back({t, partial}); partial.clear(); }
  else partial += (char)b;
  return 1;
}

SoftwareSerial::SoftwareSerial(uint8_t, uint8_t) { swPort = this; }
void SoftwareSerial::begin(long baud) { baud_ = baud; listen(); }
void SoftwareSerial::end() { stopListening(); }
bool SoftwareSerial::listen() { if (listening_) return false; listening_ = true; head_ = tail_ = 0; return true; }
bool SoftwareSerial::stopListening() { bool w = listening_; listening_ = false; return w; }
int SoftwareSerial::available() { advance(1); return (uint8_t)(tail_ - head_ + 64) % 64; }
int SoftwareSerial::read() { advance(1); if (head_ == tail_) return -1; uint8_t b = buf_[head_]; head_ = (head_ + 1) % 64; return b; }
int SoftwareSerial::peek() { return head_ == tail_ ? -1 : buf_[head_]; }
void SoftwareSerial::simDeliver(uint8_t b) { uint8_t n = (tail_ + 1) % 64; if (n != head_) { buf_[tail_] = b; tail_ = n; } }
size_t SoftwareSerial::write(uint8_t b) {
  // Interrupts are off for the whole byte: no RX delivery during it.
  t += byteUs();
  if (listening_) simDeliver(b);          // echo through the 1k resistor
  tmcReceive(b);
  return 1;
}

// ---- TMC2209Stepper mock (library-like timing) ----
namespace sim { uint8_t crc8pub(const uint8_t *d, uint8_t l) { return crc8(d, l); } }
void TMC2209Stepper::write(uint8_t reg, uint32_t val) {
  uint8_t d[8] = {0x05, addr_, (uint8_t)(reg | 0x80), (uint8_t)(val >> 24), (uint8_t)(val >> 16), (uint8_t)(val >> 8), (uint8_t)val, 0};
  d[7] = sim::crc8pub(d, 7);
  for (int i = 0; i < 8; i++) s_->write(d[i]);
  delay(2);
}
uint32_t TMC2209Stepper::read(uint8_t reg) {
  uint8_t d[4] = {0x05, addr_, reg, 0};
  d[3] = sim::crc8pub(d, 3);
  uint64_t outv = 0;
  for (int attempt = 0; attempt < 2; attempt++) {
    while (s_->available() > 0) s_->read();
    for (int i = 0; i < 4; i++) s_->write(d[i]);
    delay(2);
    uint32_t ms = millis(); int timeout = 5; uint32_t sync = 0, target = (0x05u << 16) | 0xFF00u | reg;
    bool ok = false;
    while (timeout > 0) {
      uint32_t ms2 = millis(); if (ms2 != ms) { ms = ms2; --timeout; }
      int r = s_->read(); if (r < 0) continue;
      sync = ((sync << 8) | (uint8_t)r) & 0xFFFFFF;
      if (sync == target) { ok = true; break; }
    }
    outv = 0;
    if (ok) {
      outv = sync; int got = 0; timeout = 5; ms = millis();
      while (got < 5 && timeout > 0) {
        uint32_t ms2 = millis(); if (ms2 != ms) { ms = ms2; --timeout; }
        int r = s_->read(); if (r < 0) continue;
        outv = (outv << 8) | (uint8_t)r; ++got;
      }
      if (got < 5) outv = 0;
    }
    while (s_->available() > 0) s_->read();
    delay(2);
    uint8_t od[8]; for (int i = 0; i < 8; i++) od[i] = (uint8_t)(outv >> (56 - 8 * i));
    uint8_t c = sim::crc8pub(od, 7);
    CRCerror = (c != (uint8_t)outv) || c == 0;
    if (!CRCerror) break;
    outv = 0;
  }
  return (uint32_t)(outv >> 8);
}
void TMC2209Stepper::begin() { gconf_ |= (1u << 6) | (1u << 7); write(0x00, gconf_); }
uint8_t TMC2209Stepper::test_connection() { uint32_t v = read(0x06); if (v == 0xFFFFFFFFu) return 1; if (v == 0) return 2; return 0; }
void TMC2209Stepper::toff(uint8_t v) { chopconf_ = (chopconf_ & ~0xFu) | (v & 0xF); write(0x6C, chopconf_); }
void TMC2209Stepper::blank_time(uint8_t) { write(0x6C, chopconf_); }
void TMC2209Stepper::I_scale_analog(bool b) { gconf_ = b ? (gconf_ | 1) : (gconf_ & ~1u); write(0x00, gconf_); }
void TMC2209Stepper::internal_Rsense(bool b) { gconf_ = b ? (gconf_ | 2) : (gconf_ & ~2u); write(0x00, gconf_); }
void TMC2209Stepper::rms_current(uint16_t) { write(0x10, 0x00011F10); }
void TMC2209Stepper::microsteps(uint16_t ms) { uint32_t mres = ms == 16 ? 4 : 0; chopconf_ = (chopconf_ & ~(0xFu << 24)) | (mres << 24); write(0x6C, chopconf_); }
void TMC2209Stepper::en_spreadCycle(bool b) { gconf_ = b ? (gconf_ | 4) : (gconf_ & ~4u); write(0x00, gconf_); }
void TMC2209Stepper::pwm_autoscale(bool b) { pwmconf_ = b ? (pwmconf_ | (1u << 18)) : (pwmconf_ & ~(1u << 18)); write(0x70, pwmconf_); }
void TMC2209Stepper::TPWMTHRS(uint32_t v) { write(0x13, v); }
void TMC2209Stepper::TCOOLTHRS(uint32_t v) { write(0x14, v); }
void TMC2209Stepper::semin(uint8_t v) { coolconf_ = (coolconf_ & ~0xFu) | v; write(0x42, coolconf_); }
void TMC2209Stepper::SGTHRS(uint8_t v) { write(0x40, v); }
uint16_t TMC2209Stepper::SG_RESULT() { return (uint16_t)read(0x41); }

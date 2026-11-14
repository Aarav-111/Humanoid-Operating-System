// Shell x host test harness. Compiles the real Shell_x.ino with a mock core,
// a simulated TMC2209 (UART registers + CRC + DIAG) and a Z-axis plant.
#include "Arduino.h"
#include "../Shell_x.ino"
#include "sim.h"
#include <string>
#include <vector>
#include <functional>
#include <unistd.h>
#include <sys/wait.h>

using namespace sim;
namespace sim { extern long fwStepsProbe; }

static std::vector<std::string> fails;
static std::vector<std::string> notes;
#define CHECK(cond, msg) do { if (!(cond)) { fails.push_back(std::string(msg)); } } while (0)
static std::string fmt(const char *f, ...) { char b[512]; va_list a; va_start(a, f); vsnprintf(b, sizeof b, f, a); va_end(a); return b; }

static void stepFw() { loop(); fwStepsProbe = zPosSteps; }
static void runMs(double ms) { uint64_t end = t + (uint64_t)(ms * 1000); while (t < end) stepFw(); }
static void runUs(double us) { uint64_t end = t + (uint64_t)us; while (t < end) stepFw(); }
static int findLine(const std::string &pre, size_t from) {
  for (size_t i = from; i < out.size(); i++) if (out[i].text.compare(0, pre.size(), pre) == 0) return (int)i;
  return -1;
}
static int waitLine(const std::string &pre, double timeoutMs, size_t from) {
  uint64_t end = t + (uint64_t)(timeoutMs * 1000);
  while (t < end) { int i = findLine(pre, from); if (i >= 0) return i; stepFw(); }
  return findLine(pre, from);
}
static long numAfter(const std::string &s, size_t pos) { return atol(s.c_str() + pos); }
static std::string lineText(int i) { return i >= 0 ? out[i].text : std::string("<none>"); }
static void boot(bool present = true) { tmc.present = present; setup(); }
static void cmd(const std::string &c) { send(c); }
static std::string jStatus() { size_t m = out.size(); cmd("j"); runMs(30); std::string s; for (size_t i = m; i < out.size(); i++) s += out[i].text + " | "; return s; }
static long zEdgesDuring(double ms) { long r0 = edges.rising[4]; runMs(ms); return edges.rising[4] - r0; }
static double rateDuring(double ms) { uint64_t t0 = t; long r0 = edges.rising[4]; runMs(ms); return (edges.rising[4] - r0) * 1e6 / (double)(t - t0); }
static void gapCheck(uint64_t halfUs, const char *what) {
  // A burst = two rising STEP edges closer than one requested period.
  // (A short HIGH pulse when a move is stopped is not a burst.)
  uint64_t g = edges.minRise[4];
  notes.push_back(fmt("%s: min Z step period %llu us (requested %llu)", what, (unsigned long long)g, (unsigned long long)(2 * halfUs)));
  CHECK(g + 8 >= 2 * halfUs, fmt("%s: step burst, min step period %llu us < %llu us", what, (unsigned long long)g, (unsigned long long)(2 * halfUs)));
}
static void dumpTrace(const char *name, size_t outFrom) {
  FILE *f = fopen((std::string("traces/") + name + ".csv").c_str(), "w");
  if (!f) return;
  fprintf(f, "t_ms,z_mm,sg,diag,fw_steps\n");
  for (auto &s : trace) fprintf(f, "%.3f,%.4f,%d,%d,%ld\n", s.t / 1000.0, s.zMm, s.sg, s.diag, s.fwSteps);
  fclose(f);
  f = fopen((std::string("traces/") + name + "_events.csv").c_str(), "w");
  fprintf(f, "t_ms,line\n");
  for (size_t i = outFrom; i < out.size(); i++) fprintf(f, "%.3f,%s\n", out[i].t / 1000.0, out[i].text.c_str());
  fclose(f);
}

// ---------------------------------------------------------------- tests
static void t_boot_ok() {
  boot();
  CHECK(findLine("TMC:OK", 0) >= 0, "no TMC:OK at boot");
  CHECK((tmc.reg[0x40] & 0xFF) == 70, fmt("SGTHRS reg %u != 70", tmc.reg[0x40]));
  CHECK(tmc.reg[0x14] == 0xFFFFF, "TCOOLTHRS not 0xFFFFF");
  CHECK((tmc.reg[0x00] & 1) == 0, "I_scale_analog still on");
  CHECK((tmc.reg[0x00] & 4) == 0, "spreadCycle on (StallGuard needs StealthChop)");
  CHECK((tmc.reg[0x00] & 0xC0) == 0xC0, "pdn_disable / mstep_reg_select not set");
  CHECK(((tmc.reg[0x6C] >> 24) & 0xF) == 4, "MRES not 16 microsteps");
  CHECK(tmc.badCrc == 0, fmt("TMC saw %u bad CRC datagrams", tmc.badCrc));
}
static void t_boot_absent() {
  boot(false);
  CHECK(findLine("ERR:TMC_UART", 0) >= 0, "no ERR:TMC_UART when UART absent");
  size_t m = out.size(); cmd("hd"); runMs(50);
  CHECK(findLine("ERR:TMC_UART", m) >= 0, "HD not refused without TMC");
  CHECK(edges.rising[4] == 0, "Z moved without TMC");
  m = out.size(); cmd("zg"); runMs(30); CHECK(findLine("ERR:TMC_UART", m) >= 0, "ZG not refused");
  m = out.size(); cmd("zp"); runMs(30); CHECK(findLine("ERR:TMC_UART", m) >= 0, "ZP not refused");
  CHECK(jStatus().find("TMC=ERR") != std::string::npos, "J does not show TMC=ERR");
  tmc.present = true;
  m = out.size(); cmd("zi"); CHECK(waitLine("TMC:OK", 200, m) >= 0, "ZI did not recover TMC");
  m = out.size(); cmd("zg"); CHECK(waitLine("ZG:DOWN", 50, m) >= 0, "ZG not working after ZI");
}
static void t_hd_stall() {
  boot(); plant.objPresent = true; plant.floorMm = -20; tracing = true;
  size_t m = out.size(); cmd("hd"); edges.reset();
  int zs = waitLine("ZS", 3000, m);
  CHECK(zs >= 0, "HD never reported ZS");
  if (zs >= 0) {
    CHECK(zs > 0 && out[zs - 1].text == "S", fmt("HD stall line before ZS is '%s', not S", out[zs - 1].text.c_str()));
    long n = numAfter(out[zs].text, 2);
    CHECK(n > 7950 && n < 8100, fmt("HD ZS n=%ld not about 8000", n));
    double pen = plant.floorMm - plant.actSteps / 400.0;
    notes.push_back(fmt("HD stall: n=%ld, penetration %.3f mm, lost %ld steps", n, pen, plant.lost));
    CHECK(pen < 0.3, fmt("HD overshoot %.3f mm", pen));
    CHECK(plant.lost < 40, fmt("HD lost %ld steps grinding", plant.lost));
  }
  CHECK(zEdgesDuring(100) == 0, "Z still stepping after HD stall");
  gapCheck(Z_STEP_HALF_PERIOD_US, "HD");
}
static void t_hd_cap() {
  boot();
  size_t m = out.size(); cmd("zc20"); CHECK(waitLine("CFG:CAP_MM=20", 50, m) >= 0, "ZC20 no CFG reply");
  m = out.size(); cmd("hd"); int i = waitLine("ZM", 3000, m);
  CHECK(i >= 0, "HD did not stop at cap");
  if (i >= 0) CHECK(numAfter(out[i].text, 2) == 8000, "HD cap " + out[i].text + " != ZM8000");
  CHECK(findLine("S", m) < 0 || out[findLine("S", m)].text != "S", "HD printed S at cap without contact");
  CHECK(plant.cmdSteps == -8000, fmt("HD commanded %ld steps, expected -8000", plant.cmdSteps));
  CHECK(zEdgesDuring(100) == 0, "Z still stepping after cap");
}
static void t_hd_latch() {
  boot(); plant.objPresent = true; plant.floorMm = -10;
  size_t m = out.size(); cmd("hd"); CHECK(waitLine("ZS", 2000, m) >= 0, "first HD no ZS");
  m = out.size(); cmd("hd"); long e = zEdgesDuring(200);
  CHECK(e == 0, fmt("HD in latch moved %ld steps", e));
  CHECK(findLine("ZS", m) < 0, "HD in latch printed a second ZS");
  CHECK(jStatus().find("LATCH=1") != std::string::npos, "J LATCH not 1");
  cmd("hu"); runMs(60); cmd("s"); runMs(5);
  CHECK(jStatus().find("LATCH=0") != std::string::npos, "latch not cleared by HU");
  m = out.size(); cmd("hd"); int zs = waitLine("ZS", 1000, m);
  CHECK(zs >= 0 && zs > 0 && out[zs - 1].text == "S", "HD after unlatch did not stall with S + ZS");
}
static void t_hx_stall() {
  boot(); plant.objPresent = true; plant.floorMm = -15;
  size_t m = out.size(); cmd("hx"); int zs = waitLine("ZS", 3000, m);
  CHECK(zs >= 0, "HX did not stop on stall");
  CHECK(zEdgesDuring(100) == 0, "Z moving after HX stall");
  CHECK(jStatus().find("HX:STOPPED_BY_STALL") != std::string::npos, "J not HX:STOPPED_BY_STALL");
  CHECK(plant.lost < 40, fmt("HX lost %ld steps", plant.lost));
}
static void t_hx_s() {
  boot();
  cmd("hx"); runMs(300); long e = edges.rising[4];
  CHECK(e > 500, fmt("HX only made %ld steps in 300 ms", e));
  cmd("s"); runUs(300); long e2 = edges.rising[4]; runMs(100);
  CHECK(edges.rising[4] == e2, "Z kept stepping after S during HX");
  CHECK(jStatus().find("HX:CANCELLED_BY_S") != std::string::npos, "J not HX:CANCELLED_BY_S");
}
static void t_zg_g45() {
  boot(); plant.objPresent = true; plant.floorMm = -10; tracing = true;
  size_t m0 = out.size();
  size_t m = out.size(); cmd("zg"); CHECK(waitLine("ZG:DOWN", 30, m) >= 0, "no ZG:DOWN");
  int zs = waitLine("ZS", 3000, m);
  CHECK(zs >= 0, "ZG no ZS");
  if (zs >= 0) { long n = numAfter(out[zs].text, 2); CHECK(n > 3950 && n < 4100, fmt("ZG n=%ld", n));
    notes.push_back(fmt("ZG stall at n=%ld, pen %.3f mm, lost %ld", n, plant.floorMm - plant.actSteps / 400.0, plant.lost)); }
  gapCheck(Z_PICK_HALF_PERIOD_US, "ZG");
  long z = edges.rising[4];
  cmd("g45\n"); runMs(2500);
  CHECK(plant.aSteps == 25, fmt("G45 moved A to %ld steps, expected 25", plant.aSteps));
  CHECK(edges.rising[4] == z, "Z moved during G45");
  m = out.size(); cmd("zr"); CHECK(waitLine("Z0", 2000, m) >= 0, "ZR after pickup no Z0");
  CHECK(plant.cmdSteps == 0, fmt("after ZR commanded net %ld", plant.cmdSteps));
  runMs(50);
  dumpTrace("zg", m0);
}
static void t_zp_hard() {
  boot(); plant.objPresent = true; plant.floorMm = -12;
  size_t m = out.size(); cmd("zp");
  int zs = waitLine("ZS", 3000, m), hit = waitLine("SG:HIT", 50, m), zb = waitLine("ZB", 500, m);
  CHECK(zs >= 0 && hit >= 0 && zb >= 0, "ZP hard: missing ZS/SG:HIT/ZB");
  if (zs >= 0 && zb >= 0) {
    long n = numAfter(out[zs].text, 2), b = numAfter(out[zb].text, 2);
    CHECK(b == n - zBackoffSteps, fmt("ZB %ld != ZS %ld - %ld", b, n, zBackoffSteps));
  }
  notes.push_back("ZP hard: " + lineText(hit) + fmt(", lost %ld", plant.lost));
  CHECK(plant.lost < 60, fmt("ZP hard lost %ld steps", plant.lost));
}
static void t_zp_sponge() {
  boot(); plant.objPresent = true; plant.sponge = true; plant.floorMm = -12; tracing = true;
  size_t m = out.size(); cmd("zp"); edges.reset();
  int zs = waitLine("ZS", 4000, m);
  long risingAtContact = edges.rising[4];
  long posAtContact = zPosSteps;
  int hit = waitLine("SG:HIT", 50, m), zb = waitLine("ZB", 1000, m);
  CHECK(zs >= 0 && hit >= 0 && zb >= 0, "ZP sponge: missing ZS/SG:HIT/ZB");
  if (hit >= 0) {
    const std::string &h = out[hit].text;
    CHECK(h.find("BY=SG") != std::string::npos, "ZP sponge not triggered by SG: " + h);
    long v = atol(h.c_str() + 7); size_t bp = h.find("BASE="); long base = bp != std::string::npos ? atol(h.c_str() + bp + 5) : -1;
    CHECK(base > 250 && base < 350, fmt("baseline %ld not near 300", base));
    CHECK(v + 80 <= base, fmt("hit %ld not below base-80 (%ld)", v, base));
    notes.push_back("ZP sponge: " + h + fmt(", depth into sponge %.2f mm", plant.floorMm - (posAtContact / 400.0)));
  }
  if (zs >= 0 && zb >= 0) {
    long n = numAfter(out[zs].text, 2), b = numAfter(out[zb].text, 2);
    CHECK(b == n - 200, fmt("ZB %ld != ZS %ld - 200", b, n));
    CHECK(edges.rising[4] - risingAtContact == 200, fmt("back-off made %ld steps, expected 200", edges.rising[4] - risingAtContact));
    CHECK(zPosSteps == posAtContact + 200, "back-off position wrong");
  }
  gapCheck(Z_PRESS_HALF_PERIOD_US, "ZP");
  CHECK(zEdgesDuring(100) == 0, "Z moving after ZB");
  m = out.size(); cmd("zr"); CHECK(waitLine("Z0", 2000, m) >= 0, "ZR after press no Z0");
  CHECK(plant.cmdSteps == 0, "ZR after press not exact");
  runMs(50);
  dumpTrace("zp", 0);
}
static void t_zr_exact_jog() {
  boot(); plant.objPresent = true; plant.floorMm = -10;
  size_t m = out.size(); cmd("zg"); CHECK(waitLine("ZS", 3000, m) >= 0, "ZG no ZS");
  long atStall = zPosSteps;
  runMs(20);
  analogVal[0] = 0; runMs(300); analogVal[0] = 512; runMs(30);   // joystick up jog
  long afterUp = zPosSteps;
  CHECK(afterUp > atStall + 100, fmt("joystick up jog did not move Z (%ld -> %ld)", atStall, afterUp));
  analogVal[0] = 1023; runMs(100); analogVal[0] = 512; runMs(30); // joystick down jog
  CHECK(findLine("hx", m) >= 0, "joystick down did not print hx");
  CHECK(zPosSteps < afterUp, "joystick down jog did not move Z");
  notes.push_back(fmt("ZR jog test: stall %ld, after up jog %ld, after down jog %ld", atStall, afterUp, zPosSteps));
  CHECK(zPosSteps == plant.cmdSteps, fmt("firmware count %ld != commanded %ld", zPosSteps, plant.cmdSteps));
  m = out.size(); cmd("zr"); CHECK(waitLine("Z0", 3000, m) >= 0, "ZR no Z0");
  CHECK(zPosSteps == 0 && plant.cmdSteps == 0, fmt("ZR not exact: fw %ld, commanded %ld", zPosSteps, plant.cmdSteps));
  CHECK(jStatus().find("Z0=NA") != std::string::npos, "Z0 not cleared after ZR");
  m = out.size(); cmd("zr"); runMs(30); CHECK(findLine("ERR:Z0_NOT_SAVED", m) >= 0, "second ZR not refused");
}
static void t_s_mid_zp() {
  boot();
  cmd("zp"); runMs(150);
  CHECK(edges.rising[4] > 300, "ZP not moving");
  cmd("s"); runUs(300); long e = edges.rising[4]; runMs(100);
  CHECK(edges.rising[4] == e, "Z kept stepping after S in ZP");
  std::string j = jStatus();
  CHECK(j.find("Z:IDLE") != std::string::npos, "Z mode not IDLE after S: " + j);
  CHECK(j.find("Z0=0") != std::string::npos, "Z0 lost after S: " + j);
  size_t m = out.size(); cmd("zr"); CHECK(waitLine("Z0", 2000, m) >= 0, "ZR after S no Z0");
  CHECK(plant.cmdSteps == 0, "ZR after S not exact");
}
static void t_settings() {
  boot();
  struct C { const char *c; const char *expect; } cs[] = {
    {"zt100\n", "CFG:SGTHRS=100"}, {"zt300\n", "ERR:ZT"}, {"zk0\n", "ERR:ZK"}, {"zk50\n", "CFG:PRESS_DROP=50"},
    {"zk501\n", "ERR:ZK"}, {"zb10\n", "CFG:BACKOFF_STEPS=400"}, {"zb101\n", "ERR:ZB"}, {"zb0\n", "CFG:BACKOFF_STEPS=0"},
    {"zc1\n", "ERR:ZC"}, {"zc50\n", "CFG:CAP_MM=50"}, {"zc301\n", "ERR:ZC"}, {"zv1\n", "CFG:SG_STREAM=1"},
    {"zv2\n", "ERR:ZV"}, {"zv0\n", "CFG:SG_STREAM=0"}, {"zi", "TMC:OK"}, {"zx", "ERR:Z"}, {"ZT90\n", "CFG:SGTHRS=90"},
    {"zt\n", "ERR:ZT"}};
  for (auto &c : cs) {
    size_t m = out.size(); cmd(c.c); int i = waitLine(c.expect, 300, m);
    CHECK(i >= 0, std::string("'") + c.c + "' expected " + c.expect + ", got " + (out.size() > m ? out[m].text : "<nothing>"));
  }
  CHECK((tmc.reg[0x40] & 0xFF) == 90, fmt("SGTHRS register %u != 90 after ZI + ZT90", tmc.reg[0x40] & 0xFF));
  CHECK(zCapSteps == 50L * 400 && zPressDrop == 50 && zBackoffSteps == 0, "settings not stored");
}
static void t_s_parsing() {
  boot();
  // A stop byte inside a number must stop silently, like G.
  cmd("zp"); runMs(50);
  size_t m = out.size(); cmd("zt1s"); runMs(50);
  CHECK(!zSenseActive(), "S inside ZT did not stop ZP");
  CHECK(findLine("ERR:ZT", m) < 0, "S inside ZT printed ERR:ZT after the stop");
  CHECK(findLine("CFG:SGTHRS", m) < 0, "ZT applied despite S");
  // Uppercase S
  cmd("hx"); runMs(50); cmd("S"); runUs(300); long e = edges.rising[4]; runMs(50);
  CHECK(edges.rising[4] == e, "uppercase S did not stop HX");
  // "zs" = Z prefix then stop
  cmd("zp"); runMs(50); m = out.size(); cmd("zs"); runUs(300); e = edges.rising[4]; runMs(50);
  CHECK(edges.rising[4] == e, "zs did not stop");
  CHECK(findLine("ERR:Z", m) < 0, "zs printed ERR:Z");
  // S during G move stops the gripper
  long a0 = plant.aSteps; sendAt(t + 150000, "s"); cmd("g90\n"); runMs(160); long a1 = plant.aSteps; runMs(500);
  CHECK(plant.aSteps == a1 && a1 > a0 && a1 < 50, fmt("S during G90 did not stop A (%ld -> %ld -> %ld)", a0, a1, plant.aSteps));
  // no new command or reply begins with s
  for (auto &o : out) CHECK(!(o.text.size() > 1 && (o.text[0] == 's')), "a reply begins with lowercase s: " + o.text);
}
static void t_udlr() {
  boot();
  struct M { const char *c; int pin; int dirPin; int dir; double half; } ms[] = {
    {"u", 3, 6, LOW, 167}, {"d", 3, 6, HIGH, 167}, {"r", 2, 5, LOW, 167}, {"l", 2, 5, HIGH, 167},
    {"uq", 3, 6, LOW, 501}, {"dq", 3, 6, HIGH, 501}, {"rq", 2, 5, LOW, 501}, {"lq", 2, 5, HIGH, 501}};
  for (auto &mv : ms) {
    edges.reset(); cmd(mv.c); runMs(20); long r0 = edges.rising[mv.pin]; uint64_t t0 = t; runMs(200);
    double rate = (edges.rising[mv.pin] - r0) * 1e6 / (double)(t - t0);
    double want = 1e6 / (2 * mv.half);
    CHECK(pinLevel[mv.dirPin] == mv.dir, std::string(mv.c) + " wrong DIR level");
    CHECK(rate > want * 0.8 && rate < want * 1.02, fmt("%s rate %.0f steps/s, expected about %.0f", mv.c, rate, want));
    CHECK(edges.rising[4] == 0, std::string(mv.c) + " moved Z");
    notes.push_back(fmt("%s: %.0f steps/s (requested %.0f)", mv.c, rate, want));
    cmd("s"); runMs(10);
  }
}
static void t_removed_cmds() {
  boot();
  size_t m = out.size(); cmd("p1"); CHECK(waitLine("ERR:TOF_REMOVED", 50, m) >= 0, "P1 not ERR:TOF_REMOVED");
  m = out.size(); cmd("p3"); CHECK(waitLine("ERR:TOF_REMOVED", 50, m) >= 0, "P3 not ERR:TOF_REMOVED");
  m = out.size(); cmd("n"); CHECK(waitLine("ERR:TOF_REMOVED", 50, m) >= 0, "N not ERR:TOF_REMOVED");
  m = out.size(); cmd("e"); int i = waitLine("SG:RESULT=", 50, m); CHECK(i >= 0, "E no SG:RESULT");
  notes.push_back("E at rest: " + lineText(i));
  m = out.size(); cmd("i"); CHECK(waitLine("DIAG:CLEAR", 50, m) >= 0, "I not DIAG:CLEAR at rest");
  CHECK(edges.rising[4] == 0 && plant.xSteps == 0 && plant.ySteps == 0, "removed commands moved a motor");
}
static void t_no_burst_blocking() {
  boot();
  cmd("zc60\n"); runMs(30);
  cmd("zp"); runMs(100); edges.reset(); runMs(50);
  cmd("zt60\n"); runMs(50); cmd("e"); runMs(50); cmd("j"); runMs(50);
  gapCheck(Z_PRESS_HALF_PERIOD_US, "ZP with blocking ZT/E/J");
  CHECK(zSenseActive(), "ZP stopped by ZT/E/J");
  cmd("s"); runMs(5);
  cmd("hd"); runMs(20); edges.reset(); runMs(30); cmd("e"); runMs(50);
  gapCheck(Z_STEP_HALF_PERIOD_US, "HD with E");
}
static void t_free_air_noise() {
  boot(); plant.noise = 25; tracing = false;
  size_t m = out.size(); cmd("zc40\n"); runMs(20);
  cmd("zg"); int i = waitLine("ZM", 6000, m);
  CHECK(i >= 0 && numAfter(out[i].text, 2) == 16000, "ZG noisy free air did not reach ZM16000: " + lineText(i));
  CHECK(findLine("ZS", m) < 0, "ZG false stall in noisy free air");
  cmd("zr"); runMs(2000);
  m = out.size(); cmd("zp"); i = waitLine("ZM", 6000, m);
  CHECK(i >= 0, "ZP noisy free air did not reach cap");
  CHECK(findLine("ZS", m) < 0, "ZP false trigger in noisy free air");
  cmd("zr"); runMs(2000);
  m = out.size(); cmd("hd"); i = waitLine("ZM", 6000, m);
  CHECK(i >= 0 && findLine("ZS", m) < 0, "HD false stall in noisy free air");
}
static void t_sponge_zg() {
  boot(); plant.objPresent = true; plant.sponge = true; plant.floorMm = -10;
  size_t m = out.size(); cmd("zg"); int i = waitLine("ZS", 4000, m);
  CHECK(i >= 0, "ZG never detected the sponge-covered object");
  double depth = plant.floorMm - plant.actSteps / 400.0;
  notes.push_back(fmt("ZG on sponge: stopped %.2f mm into a 5 mm sponge (late, as expected), lost %ld", depth, plant.lost));
  CHECK(depth <= plant.spongeMm + plant.complianceMm + 0.01, fmt("ZG on sponge overshot to %.2f mm", depth));
}
static void t_missed_cap_default() {
  boot();
  size_t m = out.size(); cmd("zg"); int i = waitLine("ZM", 12000, m);
  CHECK(i >= 0 && numAfter(out[i].text, 2) == 40000, "ZG default cap not ZM40000: " + lineText(i));
  CHECK(zEdgesDuring(100) == 0, "Z moving after cap");
  CHECK(plant.cmdSteps == -40000, fmt("cap commanded %ld", plant.cmdSteps));
}
static void t_speeds() {
  boot();
  cmd("zc100\n"); runMs(20);
  cmd("zg"); runMs(20); double zg = rateDuring(300); cmd("s"); runMs(10);
  cmd("zr"); runMs(5); double ret = rateDuring(200); runMs(3000);
  cmd("hd"); runMs(20); double hd = rateDuring(300); cmd("s"); runMs(10);
  cmd("hu"); runMs(400); cmd("s"); runMs(10);
  cmd("zp"); runMs(150); double zp = rateDuring(300); cmd("s"); runMs(10);
  cmd("zr"); runMs(3000);
  plant.objPresent = true; plant.sponge = true; plant.floorMm = -6; cmd("zb40\n"); runMs(20);
  size_t m = out.size(); cmd("zp"); waitLine("ZS", 3000, m); runMs(25); double bo = rateDuring(150);
  struct R { const char *n; double got, want; } rs[] = {{"HD", hd, 6024}, {"ZR", ret, 6024}, {"ZG", zg, 5000}, {"ZP", zp, 4000}, {"back-off", bo, 2000}};
  for (auto &r : rs) {
    notes.push_back(fmt("%s: %.0f steps/s = %.1f mm/s (requested %.0f)", r.n, r.got, r.got / 400, r.want));
    CHECK(r.got > r.want * 0.75 && r.got < r.want * 1.02, fmt("%s rate %.0f vs %.0f", r.n, r.got, r.want));
  }
}
static void t_sg_stream() {
  boot(); plant.objPresent = true; plant.sponge = true; plant.floorMm = -8;
  size_t m = out.size(); cmd("zv1\n"); runMs(30); cmd("zp"); waitLine("ZB", 4000, m);
  int n = 0; for (size_t i = m; i < out.size(); i++) if (out[i].text.compare(0, 3, "SG:") == 0 && out[i].text.compare(0, 7, "SG:HIT=") != 0) ++n;
  notes.push_back(fmt("SG stream lines during ZP: %d", n));
  CHECK(n > 20, fmt("only %d SG stream lines", n));
  CHECK(sg.errors == 0, fmt("SG poll UART errors %u", sg.errors));
}
static void t_repress() {
  boot(); plant.objPresent = true; plant.floorMm = -8;
  size_t m = out.size(); cmd("zp"); CHECK(waitLine("ZB", 3000, m) >= 0, "first ZP no ZB");
  long lost1 = plant.lost;
  m = out.size(); cmd("zp"); int zs = waitLine("ZS", 3000, m);
  CHECK(zs >= 0, "second ZP never detected the object");
  int zb = waitLine("ZB", 1000, m);
  CHECK(zb >= 0, "second ZP no ZB");
  long extra = plant.lost - lost1;
  notes.push_back(fmt("re-press after back-off: extra lost steps %ld (grinding while blanked)", extra));
  CHECK(extra < 40, fmt("re-press ground %ld steps into the object during stall blanking", extra));
}
static void t_hd_zg_mutual() {
  boot(); plant.objPresent = true; plant.floorMm = -20;
  cmd("zg"); runMs(100);
  size_t m = out.size(); cmd("hd"); runMs(30);
  CHECK(!zSenseActive(), "HD did not take over from ZG");
  int zs = waitLine("ZS", 3000, m);
  CHECK(zs >= 0 && out[zs - 1].text == "S", "HD after ZG did not stall normally");
  CHECK(plant.cmdSteps == zPosSteps, "count mismatch after takeover");
  cmd("hu"); runMs(100); cmd("s"); runMs(5);
  m = out.size(); cmd("zr"); CHECK(waitLine("Z0", 3000, m) >= 0, "ZR after mixed moves no Z0");
  CHECK(plant.cmdSteps == 0, fmt("ZR after HD/HU not exact (%ld)", plant.cmdSteps));
}
static void t_double_tap() {
  boot();
  cmd("zp"); runMs(60);
  swLevel = LOW; runMs(40); swLevel = HIGH; runMs(60); swLevel = LOW; runMs(40); swLevel = HIGH;
  long e = edges.rising[4]; runMs(50);
  CHECK(edges.rising[4] == e, "double-tap did not stop ZP");
  CHECK(findLine("s", 0) >= 0 && out[findLine("s", 0)].text == "s", "double-tap did not send s");
}

static void t_fuzz() {
  // 300 random commands and joystick moves; the firmware step count must
  // always equal the steps the plant really received, and nothing may burst.
  boot(); plant.objPresent = true; plant.sponge = true; plant.floorMm = -15; plant.noise = 10;
  const char *pool[] = {"hd", "hu", "hx", "zg", "zp", "zr", "s", "u", "dq", "r", "lq", "g30\n", "g0\n", "e", "j", "i",
                        "zt60\n", "zt70\n", "zk60\n", "zb8\n", "zc40\n", "zv1\n", "zv0\n", "p1", "n", "S", "zs", "q"};
  unsigned seed = 777; long mismatches = 0; uint64_t fuzzMinRise = UINT64_MAX;
  for (int k = 0; k < 300; k++) {
    seed = seed * 1103515245u + 12345u;
    unsigned r = (seed >> 8) % 34;
    if (r < 28) cmd(pool[r]);
    // Joystick UP or centre only: manual down-jog ignores StallGuard by design
    // (as it ignored IR in Shell 1.5) and would grind; covered as a known limit.
    else if (r < 31) analogVal[0] = (r == 28) ? 0 : 512;
    else analogVal[0] = 512;
    long l0 = plant.lost;
    // Ignore the hand-over edge between two different moves; measure bursts
    // inside each move.
    runMs(1); edges.minRise[4] = UINT64_MAX; edges.riseSeen[4] = false; uint64_t mr0 = edges.minRise[4];
    runMs(20 + (seed >> 20) % 120);
    if (edges.minRise[4] < fuzzMinRise) fuzzMinRise = edges.minRise[4];
    if (getenv("FUZZDBG") && (plant.lost != l0 || edges.minRise[4] != mr0))
      fprintf(stderr, "k=%d r=%u cmd=%s joy=%d lost+%ld minRise=%llu mode=%d running=%d act=%d hx=%d joyZ=%d\n", k, r, r < 28 ? pool[r] : "joy", analogVal[0], plant.lost - l0,
        (unsigned long long)edges.minRise[4], (int)zs.mode, running, activeStepPin, hxHold.isEnabled(), joystickZ.moving);
    if (zPosSteps != plant.cmdSteps) ++mismatches;
    if (plant.actSteps / 400.0 > 5.0) { cmd("s"); analogVal[0] = 512; runMs(5); }
  }
  cmd("s"); analogVal[0] = 512; runMs(50);
  CHECK(mismatches == 0, fmt("firmware Z count != plant commanded steps %ld times", mismatches));
  notes.push_back(fmt("fuzz: %zu output lines, lost %ld steps, min Z step period %llu us", out.size(), plant.lost, (unsigned long long)fuzzMinRise));
  CHECK(fuzzMinRise + 8 >= 2 * 83, "fuzz: Z step burst inside a move");
  CHECK(plant.lost < 200, fmt("fuzz lost %ld steps", plant.lost));
}

struct T { const char *name; void (*fn)(); };
static T tests[] = {
  {"boot_tmc_ok", t_boot_ok}, {"boot_uart_absent_and_ZI", t_boot_absent}, {"HD_stall_S_ZS", t_hd_stall},
  {"HD_cap_ZM", t_hd_cap}, {"HD_contact_latch", t_hd_latch}, {"HX_stall", t_hx_stall}, {"HX_S_stop", t_hx_s},
  {"ZG_pickup_then_G45_ZR", t_zg_g45}, {"ZP_hard_object", t_zp_hard}, {"ZP_sponge_SG_threshold_backoff", t_zp_sponge},
  {"ZR_exact_after_joystick_jogs", t_zr_exact_jog}, {"S_mid_ZP_keeps_Z0", t_s_mid_zp}, {"settings_CFG_and_ranges", t_settings},
  {"s_never_misparsed", t_s_parsing}, {"UDLR_Q_unchanged", t_udlr}, {"P_N_removed_E_I", t_removed_cmds},
  {"no_step_bursts_with_blocking_cmds", t_no_burst_blocking}, {"noise_free_air_no_false_trigger", t_free_air_noise},
  {"sponge_ZG_detects", t_sponge_zg}, {"missed_object_default_cap", t_missed_cap_default}, {"step_speeds", t_speeds},
  {"SG_streaming_ZV1", t_sg_stream}, {"repress_after_backoff", t_repress}, {"HD_takes_over_ZG_and_ZR", t_hd_zg_mutual},
  {"SW_double_tap_stops_ZP", t_double_tap}, {"random_command_fuzz", t_fuzz}};

int main(int argc, char **argv) {
  const char *only = argc > 1 ? argv[1] : nullptr;
  int pass = 0, total = 0;
  for (auto &tc : tests) {
    if (only && strcmp(only, tc.name) != 0) continue;
    ++total;
    int pfd[2]; if (pipe(pfd) != 0) return 2;
    pid_t pid = fork();
    if (pid == 0) {
      close(pfd[0]);
      sim::reset();
      tc.fn();
      std::string r;
      for (auto &n : notes) r += "    note: " + n + "\n";
      for (auto &f : fails) r += "    FAIL: " + f + "\n";
      r += fails.empty() ? "P" : "F";
      if (write(pfd[1], r.data(), r.size()) < 0) {}
      _exit(fails.empty() ? 0 : 1);
    }
    close(pfd[1]);
    std::string r; char b[4096]; ssize_t k; while ((k = read(pfd[0], b, sizeof b)) > 0) r.append(b, k);
    close(pfd[0]); int st = 0; waitpid(pid, &st, 0);
    bool ok = WIFEXITED(st) && WEXITSTATUS(st) == 0;
    if (!WIFEXITED(st)) r += "    FAIL: crashed\n";
    if (!r.empty() && (r.back() == 'P' || r.back() == 'F')) r.pop_back();
    printf("[%s] %s\n%s", ok ? "PASS" : "FAIL", tc.name, r.c_str());
    if (ok) ++pass;
  }
  printf("RESULT %d/%d passed\n", pass, total);
  return pass == total ? 0 : 1;
}

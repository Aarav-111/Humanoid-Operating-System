// Simulation state shared by the mock core and the test harness.
#pragma once
#include <stdint.h>
#include <string>
#include <vector>
#include <deque>

namespace sim {
struct OutLine { uint64_t t; std::string text; };
struct Sample { uint64_t t; double zMm; int sg; int diag; long fwSteps; };

struct Plant {
  long cmdSteps = 0;        // net commanded Z steps (up +)
  long actSteps = 0;        // physical position in steps
  long lost = 0;            // steps lost against a hard surface
  bool objPresent = false;
  double floorMm = -20.0;   // top of object/ground relative to start
  bool sponge = false;
  double spongeMm = 5.0;
  double spongeK = 40.0;    // SG drop per mm in sponge
  double hardK = 1500.0;    // SG drop per mm in hard contact
  double complianceMm = 0.25;
  double sgBase = 300.0;
  double noise = 4.0;
  int jerkSteps = 100;      // low SG just after starting from rest
  int jerkSg = 40;
  long stepsSinceRest = 0;
  uint64_t lastStepT = 0;
  int sgLatched = 0;        // updated every full step (16 microsteps)
  long aSteps = 0;
  long xSteps = 0, ySteps = 0;
  int xDirAtLast = -1, yDirAtLast = -1;
};

struct Tmc {
  bool present = true;
  uint32_t reg[128] = {0};
  uint32_t ifcnt = 0;
  std::vector<uint8_t> in;
  uint32_t badCrc = 0, reads = 0, writes = 0;
};

struct EdgeStats {
  uint64_t lastT[32] = {0};
  bool seen[32] = {false};
  uint64_t minGap[32];
  long rising[32] = {0};
  uint64_t lastRise[32] = {0};
  bool riseSeen[32] = {false};
  uint64_t minRise[32];
  void reset() { for (int i = 0; i < 32; i++) { minGap[i] = UINT64_MAX; minRise[i] = UINT64_MAX; seen[i] = false; riseSeen[i] = false; rising[i] = 0; } }
};

extern uint64_t t;
extern Plant plant;
extern Tmc tmc;
extern EdgeStats edges;
extern std::vector<OutLine> out;
extern std::deque<uint8_t> serialIn;
extern std::vector<Sample> trace;
extern int analogVal[8];
extern int swLevel;
extern uint8_t pinLevel[32];
extern uint64_t sampleEveryUs;
extern bool tracing;

void reset();
void advance(uint64_t us);
void send(const std::string &s);
void sendAt(uint64_t atUs, const std::string &s);
double rnd();
int diagLevel();
}

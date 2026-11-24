# HOS-BT Scores: Calculation and Justification

This folder holds the working behind every HOS-BT score, one file per HOS model.

| Model | Status | File |
| --- | --- | --- |
| HOS 1.5 | Current release (11 October 2026). **Scored 29.8%** | [HOS-1.5.md](HOS-1.5.md) |
| HOS X | Launching December 2026. Expected **60%** | [HOS-X.md](HOS-X.md) |
| HOS 2.0 | Planned for late January or early February 2027 | [HOS-2.0.md](HOS-2.0.md) |

HOS 1.0 and earlier retire on 30 November 2026 and are not scored.

---

## How a score is calculated

**1. Trial score (out of 100)**

```
Trial score = Plan (20) + Perception (15) + Execution (40) + Safety (15) + Efficiency (10)
              - Human help penalty
              - ERR penalty
```

- Strict safety failure: the trial score is **0**.
- A trial score cannot go below 0.

**2. Task score**

```
Task score = (Trial 1 + Trial 2 + Trial 3 + Trial 4 + Trial 5) / 5
```

**3. HOS-BT score**

```
HOS-BT score = (T1 + T2 + ... + T10) / 10
```

**4. Other numbers reported**

| Number | How it is worked out |
| --- | --- |
| Pass rate | Trials scoring 70 or more / 50 trials |
| Safety rate | Trials with no strict safety failure / 50 trials |
| Cost per trial | Total API cost of the run / 50 trials |

Full rules: [HOS-BT README, section 6](../README.md#6-scoring).

---

## How a score is justified

Every score must be backed by the following, kept by the team (model files show final scores only):

1. **Evidence:** start and end photos, the plan HOS showed, the ERR result and the `[timing]` log for each trial.
2. **Reason for each lost point:** one short line per deduction, for example "Plan -4: missed step 6, put broom back".
3. **Human help log:** every YES, NO, typed hint or hand move.
4. **Hardware and software versions:** HOS version, simulator or hardware build, and firmware.

A score without this evidence is not published.

---

## Rules for this folder

- Only real, logged runs are written here. No estimated or made-up scores.
- Old scores are never edited. If a run is redone, the new run is added below the old one with the reason.
- Every model is scored at **L2 Tabletop** (real hardware) only, so all scores compare directly.
- Scores are shown as percentages. Each model file keeps only the final scores.

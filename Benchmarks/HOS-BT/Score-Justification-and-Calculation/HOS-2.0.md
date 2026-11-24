# HOS 2.0: HOS-BT Score Calculation and Justification

| Item | Value |
| --- | --- |
| Model | HOS 2.0 |
| Status | Planned for late January or early February 2027 |
| HOS-BT version | 1.0 |
| Planned levels | L1, L2, and L3 when hardware is ready |
| Run status | Not yet run |

HOS 2.0 will be scored after release. It is the first model planned for L3 full-scale runs.

---

## Summary

| Level | HOS-BT score | Pass rate | Safety rate | Cost per trial | Date |
| --- | --- | --- | --- | --- | --- |
| L1 Simulation | Not yet run | | | | |
| L2 Tabletop | Not yet run | | | | |

---

## Score calculation per task (L1)

Each cell is the average of 5 trials. Task score = Plan + Perception + Execution + Safety + Efficiency - Help - ERR.

| Task | Plan /20 | Perception /15 | Execution /40 | Safety /15 | Efficiency /10 | Help | ERR | Task score /100 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T1 Sweeping | | | | | | | | |
| T2 Mopping | | | | | | | | |
| T3 Washing utensils | | | | | | | | |
| T4 Cooking | | | | | | | | |
| T5 Washing clothes by machine | | | | | | | | |
| T6 Folding and ironing clothes | | | | | | | | |
| T7 Sorting clothes | | | | | | | | |
| T8 Bathroom and toilet | | | | | | | | |
| T9 Dusting | | | | | | | | |
| T10 Tidying up the board | | | | | | | | |
| **HOS-BT score** | | | | | | | | |

---

## Score calculation per task (L2)

| Task | Plan /20 | Perception /15 | Execution /40 | Safety /15 | Efficiency /10 | Help | ERR | Task score /100 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T1 Sweeping | | | | | | | | |
| T2 Mopping | | | | | | | | |
| T3 Washing utensils | | | | | | | | |
| T4 Cooking | | | | | | | | |
| T5 Washing clothes by machine | | | | | | | | |
| T6 Folding and ironing clothes | | | | | | | | |
| T7 Sorting clothes | | | | | | | | |
| T8 Bathroom and toilet | | | | | | | | |
| T9 Dusting | | | | | | | | |
| T10 Tidying up the board | | | | | | | | |
| **HOS-BT score** | | | | | | | | |

---

## Trial log (fill one block per task)

### T_ Task name, Level L_

| Trial | Seed | Plan | Perception | Execution | Safety | Efficiency | Help | ERR | Score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | | | | | | | | |
| 2 | 2 | | | | | | | | |
| 3 | 3 | | | | | | | | |
| 4 | 4 | | | | | | | | |
| 5 | 5 | | | | | | | | |
| **Average** | | | | | | | | | |

**Justification:**
- Plan: (reason for each point lost)
- Perception: (objects missed or wrongly named)
- Execution: (success check result, for example 16 of 20 items placed)
- Safety: (any issue, or "all checks passed")
- Efficiency: (time, replans, API calls)
- Human help: (each YES, NO, hint or hand move)
- ERR: (what ERR said vs the real result)

**Evidence:** link to photos, plan text and `[timing]` log.

---

## Versions used

| Item | Version |
| --- | --- |
| HOS software | |
| Simulator (L1) | |
| Hardware and firmware (L2) | |
| Planner model | |

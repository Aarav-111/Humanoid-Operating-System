# HOS 1.5: HOS-BT Score Calculation and Justification

| Item | Value |
| --- | --- |
| Model | HOS 1.5 |
| Status | Current release (11 October 2026) |
| HOS-BT version | 1.0 |
| Planned levels | L1, L2 |
| Run status | Ran - 21st October 2026|

HOS 1.5 is the first model to be scored on HOS-BT. Its results set the baseline that HOS X and HOS 2.0 are compared against.

---

## Summary

| Level | HOS-BT score | Pass rate | Safety rate | Cost per trial | Date |
| --- | --- | --- | --- | --- | --- |
| L2 Tabletop | Run | NA | NA | ~0.1c/task | 21st October 2026 |

---

## Score calculation per task (L1)

Each cell is the average of 5 trials. Task score = Plan + Perception + Execution + Safety + Efficiency - Help - ERR.

| Task | Plan /20 | Perception /15 | Execution /40 | Safety /15 | Efficiency /10 | Help | ERR | Task score /100 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T1 Sweeping | | | | | | | | 80% |
| T2 Mopping | | | | | | | | 30% |
| T3 Washing utensils | | | | | | | | 25% |
| T4 Cooking | | | | | | | | 2% |
| T5 Washing clothes by machine | | | | | | | | 60% |
| T6 Folding and ironing clothes | | | | | | | | 20% |
| T7 Sorting clothes | | | | | | | | 100% |
| T8 Bathroom and toilet | | | | | | | | 40% |
| T9 Dusting | | | | | | | | 70% |
| T10 Tidying up the board | | | | | | | | 20% |
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

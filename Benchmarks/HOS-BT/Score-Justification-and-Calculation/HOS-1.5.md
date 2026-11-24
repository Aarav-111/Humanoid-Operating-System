# HOS 1.5: HOS-BT Score Calculation and Justification

| Item | Value |
| --- | --- |
| Model | HOS 1.5 |
| Status | Current release (11 October 2026) |
| HOS-BT version | 1.0 |
| Planned levels | L2 Physical-execution |
| Run status | Ran - 21st October 2026|

HOS 1.5 is the first model to be scored on HOS-BT. Its results set the baseline that HOS X and HOS 2.0 are compared against.

---

## Summary

| Level | HOS-BT score | Pass rate | Safety rate | Cost per trial | Date |
| --- | --- | --- | --- | --- | --- |
| L2 Tabletop | Run | NA | NA | ~0.1c/task | 21st October 2026 |

---

## Score calculation per task (L2)

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
| **HOS-BT score** | | | | | | | | 44.7% |

---

**Justification:**
- Plan: (reason for each point lost)
- Perception: avg per task ~0 to ~1 times.
- Execution: full execution task accuracy (considering dot-simulation = 100%) = simple tasks: 10%, difficult tasks: 2%.
- Safety: Jamming & getting stuck sometimes.
- Efficiency: avg task time ~1minute/task
- Human help: YES, human help required for positioning.
- ERR: 80% of the times ERR & results matched.

**Evidence:** link to photos, plan text and `[timing]` log.

---

## Versions used

| Item | Version |
| --- | --- |
| HOS software | S1.5-SRC |
| Hardware and firmware (L2) | HOS-Trigonometry & Shell-1.5 |
| Planner model | GPT-6-luna |

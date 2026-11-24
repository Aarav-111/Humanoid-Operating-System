# HOS-BT Benchmarking Tasks

> **Benchmark:** HOS-BT (HOS Benchmark Tasks) · **Version:** 1.0 · **Released:** 24 November 2026
> **Team:** Prolabs Robotics · **Contact:** prolabsrobotics@gmail.com

These are the 10 household tasks used by the **HOS-BT benchmark** to compare HOS models with each other. Every HOS release runs the same tasks, with the same rules and the same scoring.

Full task cards, scoring and rules: [HOS-BT README](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/Benchmarks/HOS-BT/README.md)

---

## Task List

| # | Task | Area | Difficulty | What the robot must do |
| :-: | --- | --- | :-: | --- |
| T1 | **Sweeping** | Floor cleaning | Hard | Sweep all debris in a marked area into a dustpan |
| T2 | **Mopping** | Floor cleaning | Hard | Mop away all marks without leaving puddles |
| T3 | **Washing utensils** | Kitchen | Super hard | Scrub, rinse and rack a set of dirty utensils |
| T4 | **Cooking** | Kitchen | Near-impossible | Cook a simple fixed recipe and turn the heat off |
| T5 | **Washing clothes by machine** | Laundry | Hard | Load, add detergent, pick the right program, unload |
| T6 | **Folding and ironing clothes** | Laundry | Near-impossible | Iron and neatly fold a set of clothes |
| T7 | **Sorting clothes into black and white** | Laundry | Hard | Split a mixed pile into dark and light baskets |
| T8 | **Cleaning the bathroom and toilet** | Cleaning | Super hard | Clean sink, toilet and floor with separate tools |
| T9 | **Dusting furniture and surfaces** | Cleaning | Hard | Dust surfaces and put every object back in place |
| T10 | **Tidying up the board** | Organising | Hard | Move every item on the board to its marked cell |

---

## Tasks by Area

| Area | Tasks |
| --- | --- |
| Floor cleaning | T1 Sweeping, T2 Mopping |
| Kitchen | T3 Washing utensils, T4 Cooking |
| Laundry | T5 Washing clothes by machine, T6 Folding and ironing, T7 Sorting clothes |
| Cleaning | T8 Bathroom and toilet, T9 Dusting |
| Organising | T10 Tidying up the board |

---

## Difficulty Levels

No HOS-BT task is easy. Every task asks a robot to do something people find simple but robots find very hard.

| Level | Meaning | Tasks |
| --- | --- | --- |
| Hard | Rigid objects or large areas, many steps, low to medium risk | T1, T2, T5, T7, T9, T10 |
| Super hard | Hard-to-grasp objects, water or chemicals, medium risk | T3, T8 |
| Near-impossible | Long sequences, soft objects or heat, high risk | T4, T6 |

---

## Scoring at a Glance

Each task is scored out of **100**:

| Part | Points |
| --- | :-: |
| Plan | 20 |
| Perception | 15 |
| Execution | 40 |
| Safety | 15 |
| Efficiency | 10 |

- Each task runs **5 trials** with fixed random scenes.
- The **HOS-BT score** is the average of all 10 task scores.
- A **strict safety failure** (for example, heat left on in T4 or iron left face down in T6) sets that trial to **0**.

---

## Changelog

| Date | Change |
| --- | --- |
| 24 Nov 2026 | Formatted task list for HOS-BT 1.0 |
| 24 Nov 2026 | Added T10 Tidying up the board |

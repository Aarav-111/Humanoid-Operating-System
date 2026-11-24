# HOS-BT Benchmarking Tasks

> **Benchmark:** HOS-BT (HOS Benchmark Tasks) · **Version:** 1.0 · **Released:** 24 November 2026
> **Team:** Prolabs Robotics · **Contact:** prolabsrobotics@gmail.com

These are the 10 household tasks used by the **HOS-BT benchmark** to compare HOS models with each other. Every HOS release runs the same tasks, with the same rules and the same scoring.

Full task cards, scoring and rules: [HOS-BT README](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/Benchmarks/HOS-BT/README.md)

---

## Task List

| # | Task | Area | Difficulty | What the robot must do |
| :-: | --- | --- | :-: | --- |
| T1 | **Sweeping** | Floor cleaning | Medium | Sweep all debris in a marked area into a dustpan |
| T2 | **Mopping** | Floor cleaning | Medium | Mop away all marks without leaving puddles |
| T3 | **Washing utensils** | Kitchen | Hard | Scrub, rinse and rack a set of dirty utensils |
| T4 | **Cooking** | Kitchen | Very hard | Cook a simple fixed recipe and turn the heat off |
| T5 | **Washing clothes by machine** | Laundry | Medium | Load, add detergent, pick the right program, unload |
| T6 | **Folding and ironing clothes** | Laundry | Very hard | Iron and neatly fold a set of clothes |
| T7 | **Sorting clothes into black and white** | Laundry | Easy | Split a mixed pile into dark and light baskets |
| T8 | **Cleaning the bathroom and toilet** | Cleaning | Hard | Clean sink, toilet and floor with separate tools |
| T9 | **Dusting furniture and surfaces** | Cleaning | Easy | Dust surfaces and put every object back in place |
| T10 | **Tidying up the board** | Organising | Easy | Move every item on the board to its marked cell |

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

| Level | Meaning | Tasks |
| --- | --- | --- |
| Easy | Few steps, rigid objects, low risk | T7, T9, T10 |
| Medium | Many steps or a large area | T1, T2, T5 |
| Hard | Hard-to-grasp objects, water or chemicals | T3, T8 |
| Very hard | Long sequences, soft objects or heat | T4, T6 |

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

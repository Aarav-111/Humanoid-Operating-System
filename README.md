# Humanoid Operating System (HOS)

An LLM-powered control layer and modular operating system for humanoid robots.

---

## Overview

NVIDIA's CEO has spoken about the need for a general-purpose robot breakthrough before humanoids can scale. HOS is our team's attempt at that: a foundational software and hardware framework that gives humanoid robots a generalized, reasoning-driven "mind."

Instead of training isolated models per task (the approach used by most VLA models, including Gemini Robotics and π0.5), HOS uses an LLM-driven control layer for multi-modal decision-making. This repository covers the full HOS system: the mobile base for locomotion and spatial movement, and the robotic arm for manipulation.

---

## HOS Architecture

A complete HOS humanoid has two primary hardware components:

| Component | Role | Description |
|---|---|---|
| Robotic Arm | Worker | Manipulation and task execution |
| Mobile Base | Mover | Locomotion and orientation |

---

## How HOS Works

HOS v2.0 uses a 2D coordinate system paired with an LLM. A top-down image of the workspace is sent to the LLM, which returns structured commands for function calling.

Example output:
```
{goto_coordinate = T,8}
{pickup}
{goto_coordinate = K,8}
{keep}
{Task_Completed}
```

For tasks outside the core "keep, pickup, up, down" set, HOS supports special functions such as `{pour}` and `{pick_up_from_spoon}`. These are used less often since most tasks reduce to X/Y movement plus keep, pickup, up, down.

---

## Roadmap

- [x] HOS concept design
- [x] Navigation logic and system prompting
- [ ] Arm integration (in progress)
  - [x] Virtual simulator: Pro series, K3D, K5D
  - [ ] Physical simulator (in progress): A1, A2, A2.3–A2.6-Sol done; A3-Terra in progress
  - [ ] Physical robot: S1, S1.1, S2

---

## Simulators

Before building the physical robot, we build simulators to test and improve the LLM's planning. This speeds up prototyping and lets us debug issues in advance.

**Virtual simulator series**

- **Pro (v1–v8)** — Initial prototyping phase exploring different LLM control approaches. Accuracy was low; this series established what didn't work.
- **K1** — First shift to 2D coordinate output instead of directional commands (left, right, forward, back). This significantly improved accuracy and task planning.
- **K1.5** — Added more task types and longer multi-step planning.
- **K3D** — First 3D version. Added tasks like pouring, dishwashing, and dusting.
- **K3.5D** — Expanded task range and longer-horizon planning.
- **K5D** — Current simulator. Supports complex multi-step tasks (cooking, sweeping, mopping, dishwashing, dusting, cutting, laundry, machine operation) and adds a plan-and-approve workflow with memory, so the user can correct the AI and the system can learn from that. Fully 3D, including re-orienting to approach objects from the side.

**Physical simulators**

Physical simulators combine a live camera feed and coordinate planning with an actual actuated arm carrying out the actions. This surfaces real-world problems before we commit to a final robot design. The hardware connector is now built into the physical simulator, so no external extensions are needed.

- **A1** — First physical simulator, 2D.
- **A2** — Enhanced version of A1, adds vision-prompt AI.
- **A2.6-Sol** — Full 3D task planning in a physical rig, mirroring K5D's capability.
- **A3-Terra** *(in development)* — Planned improvements over A2.6-Sol:
  1. Component-level detection (e.g., targeting the washing machine's start button rather than the machine itself)
  2. Gripper AI
  3. Broader hardware compatibility
  4. Custom-build mode
  5. Stronger task planner
  6. Improved vision-prompt AI
  7. Expanded task compatibility

**Physical models before HOS 2.0**
- HOS 1.1
- HOS 1.2
- HOS 1.4
- HOS 1.5
- HOS 1.7
- HOS 1.9
- HOS 1.9.5

---

## Benchmarking

Our K5D simulator scored 99% on the MMRO benchmark, a self-administered benchmark for general-purpose robot intelligence, as no independent MMRO evaluation body currently exists. We're publishing our methodology and scoring so others can review and reproduce it: https://drive.google.com/drive/folders/1bAwEW-q3GPSAHZffDW0udatJOwSDtqaD?usp=sharing

We want to be upfront that this is a self-reported result, not third-party verified. We see this as a strong internal benchmark and a starting point for external validation, not a final claim of superiority.

---

## Planned Physical Robot Versions

**v2.0 — Full Cartesian system** *(in progress)*
A 3D Cartesian setup capable of general tabletop tasks.
- Cut vegetables and add to a pan for sautéing
- Retrieve water from the refrigerator
- Sort and load laundry into the washing machine

**v3.0 — Advanced intelligence**
Improved high-level planners, error-recovery systems, and contextual planning.
- Cook a full meal (vegetables, dal-rice, cucumber salad)
- All tasks from v2.0

**v4.0 — Wheeled humanoid navigation**
Adds wheels, LiDAR, and cameras for navigating a controlled mini-room environment.
- Brings the system meaningfully closer to a true humanoid robot

**v5.0 — Full-room humanoid autonomy**
Legged humanoid navigating a full-sized bedroom, with upgraded error correction, LLMs, and vision systems.
- Mop the room
- Clean the toilet
- All tasks from previous versions

**v6.0 — Full humanoid autonomy**
Legged humanoid navigating a whole house, with 1.5x stronger error-recovery systems and scenario-specific planning.
- Mop the whole house
- Retrieve a family member from another room
- All tasks from previous versions

---

## Credits and Contact

Developed by Prolabs Robotics.

**Project Lead:** Aarav Jaisingh
**Project Co-lead:** Siyona Chicker

**Collaborators:** 
1) Vivan Rajpuria
2) Ray Archer
3) Job San Jose
4) Abhinav Thomas
5) Sachin Sai

**Contact:** prolabsrobotics@gmail.com

---

## About

Part of the Humanoid Operating System (HOS) initiative, building scalable, LLM-driven humanoid intelligence and control systems.

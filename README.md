# Humanoid Operating System (HOS)

> An LLM-powered control layer and modular operating system for humanoid robots.

## Overview

Jensen Huang has spoken about the need for a general-purpose robot breakthrough before humanoids can scale. HOS is our attempt at that: a foundational software and hardware framework that gives humanoid robots a generalized, reasoning-driven "mind."

Instead of training isolated models per task (the approach used by most VLA models, including Gemini Robotics and π0.5), HOS uses an LLM-driven control layer for multi-modal decision-making. This repository covers the full HOS system: the mobile base for locomotion and spatial movement, and the robotic arm for manipulation.

> **Status:** HOS 1.5 released (11 October 2026). Active research and prototyping continue.

---

## Table of contents

- [Why HOS](#why-hos)
- [Recent Updates](#recent-updates)
- [Demo Videos](#demo-videos)
- [System architecture](#system-architecture)
- [A3-Terra at a glance](#a3-terra-at-a-glance)
- [How the planning loop works](#how-the-planning-loop-works)
- [What is new in A3-Terra](#what-is-new-in-a3-terra)
- [Supported interaction model](#supported-interaction-model)
- [Navigate this repository](#navigate-this-repository)
- [Simulator history](#simulator-history)
- [Roadmap](#roadmap)
- [Benchmarking](#benchmarking)
- [Running Cost](#running-cost)
- [Safety and responsible use](#safety-and-responsible-use)
- [Team and contact](#team-and-contact)

---

## Why HOS

Robots operating in homes and workspaces need more than a fixed sequence of moves. They need to interpret a changing scene, reason about the requested outcome, understand which part of an object is actionable, decide whether a move is feasible, and make that decision visible to an operator before motion starts.

HOS explores that control problem through an LLM-driven orchestration layer. The goal is not to claim that an LLM alone solves robotics; the goal is to give an operator a coherent workflow that connects perception, planning, simulation, and hardware control while preserving clear review points.

HOS is organized around two physical roles:

| Component | Role | Responsibility |
| --- | --- | --- |
| **Robotic arm** | Worker | Manipulation, contact, pickup, placement, tool-oriented actions, and task execution. |
| **Mobile base** | Mover | Locomotion, positioning, orientation, and eventually navigation beyond a tabletop workspace. |

The A-series physical simulators concentrate first on the arm-and-workspace layer: a bounded, camera-visible scene where perception and action can be measured, rehearsed, and improved before deployment to a broader robot platform.

**Latest development (11 October 2026):** S1.5-SRC source now lives at [Software/S1.5-SRC.py](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/Software/S1.5-SRC.py) (renamed from the earlier preview file and expanded). [Shell 1.5 firmware](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/Hardware/Shell_1.5.ino) adds P3 continuous height following: the Z axis tracks a saved VL53L0X distance target, pauses Z and XY on missing or stale sensor readings, and rejects targets below 35 mm. Z travel is now calculated from the confirmed 8 mm lead screw. The [Hardware](https://github.com/Aarav-111/Humanoid-Operating-System/tree/main/Hardware) folder now includes HOS-Trigonometry-1.5 hardware documentation (PDF) and [3D Models](https://github.com/Aarav-111/Humanoid-Operating-System/tree/main/Hardware/3D%20Models) with printable STL parts for the gantry, gripper, and AprilTag connector. These parts make up the HOS 1.5 release (11 October 2026). The release does not by itself prove hardware reliability. A later S1.5-SRC update on the same day moved every AI stage (vision naming, dexterity, planner, and ERR) to OpenAI `gpt-6-luna` at low reasoning effort and turned on ERR on the Go and the final ERR check by default.

HOS 1.5 is also a lot cheaper than HOS-1!


- Vision AI is 1000x cheaper!
- Task planner is 8x cheaper
- ERR is 3x cheaper
---

## Recent Updates

- **11 October 2026:** Large [S1.5-SRC](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/Software/S1.5-SRC.py) update (about 5,600 lines added, 1,100 removed). All AI stages now use OpenAI `gpt-6-luna` at low reasoning effort (the planner used `gpt-5.6-terra` and vision naming used `gpt-5.4-mini` before). ERR on the Go is now on by default: after each pickup the operator gets YES / NO, and NO runs the new `gpt-6-luna` Vision AI Sequence (park, look again, re-name the objects, retry the pickup). The final ERR check is on by default, with an optional ERR redo (off by default, at most 2). Also added: saved automatic gripper timing, an AprilTag search when the tag is out of view, and placement handling for words such as "between", "line up", and "side". ([7fe076e](https://github.com/Aarav-111/Humanoid-Operating-System/commit/7fe076e6622cab2954850d361ee9b7810eea0f29))
- **11 October 2026:** HOS 1.5 released. It brings together S1.5-SRC software, Shell 1.5 firmware, HOS-Trigonometry-1.5 hardware documentation, and the 3D-printable models.
- **11 October 2026:** Published the [HOS 1.5 task compilation](https://www.youtube.com/watch?v=wpmh6HE-oz8) demo video on the Prolabs Robotics YouTube channel.
- **9 October 2026:** Added [3D Models](https://github.com/Aarav-111/Humanoid-Operating-System/tree/main/Hardware/3D%20Models) with STL files: AprilTag connector, basic robot, gripper parts (including a sponge gripper part), hub, L-bracket, legs, pulley mount, XY inter-axis connector, Y-axis holder, and Z-axis mounter. ([639e62a](https://github.com/Aarav-111/Humanoid-Operating-System/commit/639e62aad5e9a11a8b92fb78df90f71074acb815))
- **8 to 9 October 2026:** Added HOS-Trigonometry-1.5 hardware documentation to the [Hardware](https://github.com/Aarav-111/Humanoid-Operating-System/tree/main/Hardware) folder, including an updated v2 file. ([ed2d997](https://github.com/Aarav-111/Humanoid-Operating-System/commit/ed2d997), [3b786a4](https://github.com/Aarav-111/Humanoid-Operating-System/commit/3b786a4))
- **7 to 8 October 2026:** Renamed `S1.5-SRC-Preview.py` to [`S1.5-SRC.py`](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/Software/S1.5-SRC.py) and expanded the source. ([d3a7a41](https://github.com/Aarav-111/Humanoid-Operating-System/commit/d3a7a41), [bfbd408](https://github.com/Aarav-111/Humanoid-Operating-System/commit/bfbd408))
- **5 October 2026:** Shell 1.5 firmware gained P3 continuous height following with sensor-based pause and recovery, plus Z steps per mm based on the 8 mm lead screw. ([2929d86](https://github.com/Aarav-111/Humanoid-Operating-System/commit/2929d86))
- **4 October 2026:** Added the S1.5-SRC preview (live-camera ERR-3 verification, a cannot-verify verdict, optional step or task checks, and failed-step replanning limited to two automatic attempts) and Shell 1.5 firmware (VL53L0X distance sensing, saved distance targets, distance telemetry). Older A-series and Shell files were removed from the current tree.

---

## Demo Videos

- **11 October 2026:** [HOS 1.5 task compilation](https://www.youtube.com/watch?v=wpmh6HE-oz8)

---

## System architecture

```text
 Scene image / USB camera / operator input
                    |
                    v
       Scene intake and visual normalization
                    |
                    v
  Vision and object localization on a working grid
                    |
                    v
 Component, dexterity, and grip reasoning
                    |
                    v
   Board-aware task planner and command sequence
                    |
          +---------+----------+
          |                    |
          v                    v
  Visual simulation      Guarded USB serial output
          |                    |
          +-------- operator review --------+
```

Each stage has a distinct job:

1. **Scene intake** loads a supported image or starts a live camera feed. A3-Terra normalizes common real-world input variations, including grayscale, RGBA, and higher-bit-depth images.
2. **Vision** identifies discrete objects and maps their observed location to a fixed 20 x 11 board grid.
3. **Component reasoning** can focus on actionable parts, such as a handle, rim, button, or control surface, rather than treating the entire object as a single target.
4. **Dexterity and gripper reasoning** evaluate whether the interaction is plausible and help select a safer contact or grip location.
5. **Planning** turns the operator's requested outcome into an ordered sequence of board-aware actions. If an object is missing from the visible scene, the system should report that limitation instead of inventing a location.
6. **Simulation and hardware output** use the same parsed command sequence. The simulator is the default rehearsal surface; USB output is a separately armed action.

---

## How the planning loop works

The planning loop is intentionally layered. The operator's request is grounded against the observed scene instead of being handled as a generic text completion.

| Stage | What it contributes | What the operator should check |
| --- | --- | --- |
| **Vision** | Detects and outlines discrete objects; converts their position to the board. | Does the outline contain the right object? |
| **Component inspection** | Identifies useful object parts, including handles, rims, and controls. | Is the selected sub-part the one a robot should interact with? |
| **Dexterity** | Assesses whether the requested movement is physically plausible under the current operating constraints. | Does the action make sense for the tool, object, and available space? |
| **Gripper AI** | Suggests safer grip cells or contact locations. | Is the proposed contact away from hazards and on a stable region? |
| **Planner** | Produces an ordered command sequence tied to board coordinates. | Are the order, destination, waits, and release steps correct? |
| **Simulator / serial link** | Replays or transmits the same parsed commands. | Has the plan been rehearsed, calibrated, and deliberately armed? |

### Command model

HOS plans are represented as small, composable actions. A basic manipulation sequence can be expressed as:

```text
goto_coordinate(T,8)
pickup()
goto_coordinate(K,8)
keep()
complete()
```

Depending on the task and hardware, the action vocabulary can also include operations such as `contact`, `pour`, `slice`, `press`, `release`, and `wait`. Command syntax and device support are implementation-specific; generated plans should always be reviewed before use.

---

## Supported interaction model

The HOS action model is intentionally compact. Most tabletop manipulation tasks can be expressed as a sequence of movement, interaction, and completion states.

| Action category | Examples | Intended use |
| --- | --- | --- |
| **Positioning** | `goto_coordinate(...)`, `contact(...)` | Move toward a board location or establish controlled contact with a working surface. |
| **Manipulation** | `pickup()`, `keep()`, `release()` | Acquire, carry, place, or let go of an object. |
| **Task-specific actions** | `pour()`, `slice()`, `press(...)` | Represent interactions that need a distinct device-side behavior beyond simple pick-and-place. |
| **Timing and state** | `wait(...)`, `complete()` | Hold for a required duration, then communicate the end of the planned task. |

The physical meaning of each command depends on the connected robot, end effector, controller firmware, and calibration. A plan that looks coherent on the board is still not sufficient proof of safe motion in the real world.

---

## Navigate this repository

This repository captures a research journey across multiple simulator and hardware generations. It is best navigated as a set of tracks rather than as a single application directory.

| Start here | What you will find | When to use it |
| --- | --- | --- |
| [README.md](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/README.md) | Project purpose, system architecture, roadmap, simulator history, benchmarks, and team context. | Begin here if you are new to HOS. |
| [Simulation](https://github.com/Aarav-111/Humanoid-Operating-System/tree/main/Simulation) | Virtual-simulator work and the evolution of planning experiments. | Use this track to understand the Pro, K-series, and simulation-first research direction. |
| [Physical Simulators](https://github.com/Aarav-111/Humanoid-Operating-System/tree/main/Physical%20Simulators) | Physical-simulator implementations and iterations across the A-series. | Start here for camera-to-grid operation and real-world arm experimentation. |
| [Software](https://github.com/Aarav-111/Humanoid-Operating-System/tree/main/Software) | S1-SRC and S1.5-SRC, including camera-grounded planning and execution verification. | Use this track for the SRC software-control workflow. |
| [Hardware](https://github.com/Aarav-111/Humanoid-Operating-System/tree/main/Hardware) | Shell firmware (Shell 1 and Shell 1.5), HOS-Trigonometry-1.5 hardware documentation, and 3D-printable STL models. | Use this when working on controllers, mechanical systems, connections, or physical setup. |
| [Benchmarks](https://github.com/Aarav-111/Humanoid-Operating-System/tree/main/Benchmarks) | Benchmark assets and supporting material. | Use this to understand evaluation inputs and reported results. |
| [Benchmarking tasks](https://github.com/Aarav-111/Humanoid-Operating-System/tree/main/Benchmarking%20tasks) | Task definitions used in benchmarking. | Use this when reproducing, extending, or reviewing task-level evaluation. |
| [Other](https://github.com/Aarav-111/Humanoid-Operating-System/tree/main/Other) | Supporting experiments, notes, and material that does not belong to the main tracks. | Check here when a referenced asset is not in a simulator, hardware, or benchmark folder. |

### Recommended path for a new contributor

1. Read this README for the vocabulary and high-level architecture.
2. Open **Simulation** to see how coordinate-based planning evolved before it was tested against physical hardware.
3. Move to **Physical Simulators** for A-series work. Begin with the newest relevant entry point, then trace scene intake, overlay/grid logic, planning, simulation, and serial output in that order.
4. Review **Hardware** before connecting a simulator to a device. Keep the controller, calibration, port, and safety assumptions explicit.
5. Use **Benchmarking tasks** together with **Benchmarks** whenever discussing a performance result or attempting to reproduce an evaluation.

### Finding your way quickly on GitHub

- Use GitHub's **Go to file** control (`t`) to jump to a known filename, class, or script.
- Use the repository search (`/`) for terms such as `SerialLink`, `Hardware Connect`, `GridOverlay`, `AprilTag`, `AI_INSTRUCTIONS`, or the simulator version you are investigating.
- Read commit history before modifying a legacy simulator. Many folders capture successive experiments, so a newer-looking file is not automatically the active implementation.
- Keep changes scoped to one track where possible: simulator logic, hardware integration, and benchmark definitions should be reviewed independently.

---

## Simulator history

Simulation is how the HOS team tests planning behavior before committing it to a physical robot. The series below records the evolution of the project rather than claiming feature parity across every version. Some early A-series files and older Shell/auxiliary directories were removed from the current tree on 4 October 2026; use Git history to inspect those archived implementations.

### Virtual simulator series

| Version | Focus |
| --- | --- |
| **Pro v1-v8** | Early exploration of LLM control approaches. This series established limitations in initial planning strategies and informed later coordinate-based designs. |
| **K1** | First transition from directional language to 2D coordinate output, improving repeatability for spatial tasks. |
| **K1.5** | Expanded supported task types and longer multi-step plans. |
| **K3D** | First 3D simulator; added task categories such as pouring, dishwashing, and dusting. |
| **K3.5D** | Broader task range and longer-horizon planning experiments. |
| **K5D** | Current virtual simulator direction, exploring complex multi-step tasks, a plan-and-approve workflow, memory for operator corrections, and 3D re-orientation for side approaches. |
| **K9D** | Upcoming virtual simulator direction, exploring complex 3D manipulation tasks. (Will be released after launch of HOS-1) |

### Physical simulator series

| Version | Focus |
| --- | --- |
| **A1** | First 2D physical-simulator prototype. |
| **A2** | Expanded A1 with vision-prompt AI. |
| **A2.3 - A2.6-Sol** | Progressive physical-simulation iterations; A2.6-Sol established the direction for richer task planning in a physical simulator. |
| **A3-Terra** | Current A-series evolution, emphasizing robust image intake, measured scene localization, component-level reasoning, gripper guidance, simulation-first review, and guarded hardware connection. |
| **A4-Astra** | Upcoming A-series evolution, for complex 3D manuplation |

---

## Roadmap

Roadmap items are research goals, not shipping commitments.

### Platform and simulator

- [x] HOS concept design and prompt-driven navigation experiments
- [x] Virtual simulator series through K5D
- [x] Hardware connector integrated into the physical-simulator workflow
- [x] A2.6-Sol physical-simulation milestone
- [x] A3-Terra launch
- [x] S1-SRC (Software Robot Control)
- [x] HOS 1
- [x] S1.5-SRC (released with HOS 1.5; source in `Software/S1.5-SRC.py`)
- [x] HOS 1.5
- [ ] HOS-2.0

### Planned physical robot versions

| Version | Direction | Illustrative goals |
| --- | --- | --- |
| **v1** | Basic Cartesian system | General tabletop manipulation: Sweeping, sorting and loading laundry, folding clothes, dusting etc.|
| **v2.0** | Full Robotic arm 3D system | Tabletop manipulation: better Physical accuracy, full error recovery system, interactive robot|
| **v3.0** | Advanced intelligence | Stronger high-level planners, error recovery, and contextual task planning. |
| **v4.0** | Wheeled humanoid navigation | Wheels, LiDAR, and cameras for a controlled mini-room environment. |
| **v5.0** | Full-room humanoid autonomy | Legged navigation in a full-sized room with upgraded perception and correction loops. |
| **v6.0** | Whole-home autonomy research | Scenario-specific planning and stronger recovery for larger, more variable home environments. |

---

## Benchmarking

The K5D simulator scored **99% on the MMRO benchmark** for general-purpose robot intelligence.

Benchmark methodology and scoring material are available here: [MMRO materials](https://drive.google.com/drive/folders/1bAwEW-q3GPSAHZffDW0udatJOwSDtqaD?usp=sharing).

---

## Running Cost

All numbers below are **estimates**, not measured bills. They cover the AI API only and were worked out from the code in [`Software/S1.5-SRC.py`](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/Software/S1.5-SRC.py) at commit [7fe076e](https://github.com/Aarav-111/Humanoid-Operating-System/commit/7fe076e6622cab2954850d361ee9b7810eea0f29).

### What HOS calls

- **Provider:** OpenAI API (Chat Completions, your own API key).
- **Model:** `gpt-6-luna` for every reasoning and vision stage, at `low` reasoning effort, standard tier (the priority tier is off).
- **Optional voice input:** `gpt-4o-transcribe` (fallback `whisper-1`). Not included below.

### Price used

`gpt-6-luna`, standard tier: **$0.10 per 1M input tokens**, $0.01 per 1M cached input tokens, **$0.50 per 1M output tokens**. Source: [OpenAI gpt-6-luna model page](https://developers.openai.com/api/docs/models/gpt-6-luna), checked 11 October 2026. Exchange rate used: 1 USD = 96.78 INR ([dollarrupee.in](https://dollarrupee.in/), 10 October 2026).

### Cost per model call

| Call | When it runs | Tokens in (est.) | Tokens out incl. reasoning (est.) | Cost (USD) | Cost (INR) |
| --- | --- | --- | --- | --- | --- |
| Vision naming | Start of a task (2 high-detail photos) | 5,000 | 1,500 | $0.0013 | Rs 0.12 |
| Dexterity check | Once per task | 2,000 | 500 | $0.0005 | Rs 0.04 |
| Planner | Once per task (a plain sweep skips it) | 20,000 | 3,000 | $0.0035 | Rs 0.34 |
| ERR final check | End of task (1 photo) | 3,500 | 1,000 | $0.0009 | Rs 0.08 |
| Vision AI Sequence | Only after an operator NO | 3,500 | 1,000 | $0.0009 | Rs 0.08 |

ERR on the Go asks the operator YES / NO after each pickup. A YES makes no model call.

### Cost per task

| Scenario | Model calls | Per task (USD) | Per task (INR) | Per 100 tasks (USD) | Per 100 tasks (INR) |
| --- | --- | --- | --- | --- | --- |
| Typical (no failures) | 4 | about $0.006 | about Rs 0.59 | about $0.60 | about Rs 59 |
| Worst case (2 replans, each with a Vision AI Sequence and a new plan) | 8 | about $0.015 | about Rs 1.43 | about $1.47 | about Rs 143 |

**Assumptions:** planner input of about 20,000 tokens (the size noted in the code); photo token counts are rough guesses for high-detail images; no prompt caching (caching would lower input cost); output includes reasoning tokens at low effort; taxes and transcription are not included. Real costs change with the task, the scene, and OpenAI pricing. Check the `[timing]` lines S1.5-SRC prints, which show real tokens in and out for each call.

### Hardware

The [HOS-Trigonometry-1.5 hardware documentation](https://github.com/Aarav-111/Humanoid-Operating-System/tree/main/Hardware) has a bill of materials but no part prices, so no hardware cost is given here. Main parts:

- Arduino Uno and CNC Shield V3, with 3 or 4 A4988 stepper drivers
- 3 or 4 NEMA 17 stepper motors and a 12 V, 10 A power supply
- 2020 V-slot frame, GT2 belts and pulleys (X and Y), T8 lead screw (Z), 8 mm smooth rods
- VL53L0X-class time-of-flight sensor, IR object sensor, sponge grip face
- Analog joystick, AprilTag 36h11, 3D-printed brackets and carriage parts, wiring

---

## Safety and responsible use

HOS is experimental robotics software. Use it responsibly.

- Keep a human operator present during any physical test.
- Treat every generated plan as a proposal, not an authorization to move hardware.
- Use simulation before enabling USB output.
- Complete workspace/camera calibration before relying on board coordinates.
- Confirm the selected serial device and baud rate before arming output.
- Keep clear exclusion zones around moving hardware, maintain an accessible emergency stop, and follow the safety requirements of the connected robot, controller, and tools.
- Do not use the project for uncontrolled operation around people, animals, fragile property, sharp tools, high heat, or hazardous materials unless the full physical safety system has been independently designed and validated for that use.

---

## Team and contact

Developed by **Prolabs Robotics**.

| Role | Name |
| --- | --- |
| Project Manager | Mathew Tony |
| Project Lead | Aarav Jaisingh |
| Project Co-lead | Siyona Chicker |
| Collaborators | Job San Jose, Sai Sachin, Aarush Wagh|

For collaboration, research, or project questions: **prolabsrobotics@gmail.com**

---

**Humanoid Operating System**  
Building an inspectable path from scene understanding to supervised robot action.

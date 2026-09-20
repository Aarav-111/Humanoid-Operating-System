# Humanoid Operating System (HOS)

> An LLM-powered control layer and modular operating system for humanoid robots.

## Overview

NVIDIA's CEO has spoken about the need for a general-purpose robot breakthrough before humanoids can scale. HOS is our team's attempt at that: a foundational software and hardware framework that gives humanoid robots a generalized, reasoning-driven "mind."

Instead of training isolated models per task (the approach used by most VLA models, including Gemini Robotics and π0.5), HOS uses an LLM-driven control layer for multi-modal decision-making. This repository covers the full HOS system: the mobile base for locomotion and spatial movement, and the robotic arm for manipulation.

> **Status:** Active research and prototyping.

---

## Table of contents

- [Why HOS](#why-hos)
- [System architecture](#system-architecture)
- [A3-Terra at a glance](#a3-terra-at-a-glance)
- [How the planning loop works](#how-the-planning-loop-works)
- [What is new in A3-Terra](#what-is-new-in-a3-terra)
- [Supported interaction model](#supported-interaction-model)
- [Navigate this repository](#navigate-this-repository)
- [Simulator history](#simulator-history)
- [Roadmap](#roadmap)
- [Benchmarking](#benchmarking)
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
7. 
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
| [Hardware](https://github.com/Aarav-111/Humanoid-Operating-System/tree/main/Hardware) | Hardware-related material for robot and simulator integration. | Use this when working on controllers, mechanical systems, connections, or physical setup. |
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

Simulation is how the HOS team tests planning behavior before committing it to a physical robot. The series below records the evolution of the project rather than claiming feature parity across every version.

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
- [ ] S1-SRC (Software Robot Control)
- [ ] HOS 1
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
| Project Lead | Aarav Jaisingh |
| Project Co-lead | Siyona Chicker |
| Collaborators | Job San Jose, Sachin Sai

For collaboration, research, or project questions: **prolabsrobotics@gmail.com**

---

**Humanoid Operating System**  
Building an inspectable path from scene understanding to supervised robot action.

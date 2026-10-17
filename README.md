<p align="center">
  <img src="assets/hos-banner-4k.png" alt="Humanoid Operating System banner" width="80%">
</p>

<p align="center">
  <a href="https://github.com/Aarav-111/Humanoid-Operating-System#recent-updates"><img src="assets/badges/hos-latest.svg" alt="Latest: HOS 1.5"></a>
  <a href="https://github.com/Aarav-111/Humanoid-Operating-System#benchmarking"><img src="assets/badges/hos-mmro.svg" alt="MMRO (K5D): 99%"></a>
  <a href="https://github.com/Aarav-111/Humanoid-Operating-System#camera-ready-gripper"><img src="assets/badges/hos-gripper.svg" alt="New: Camera-Ready Gripper"></a>
  <a href="https://github.com/Aarav-111/Humanoid-Operating-System/tree/main/Software"><img src="assets/badges/hos-python.svg" alt="Python: 3"></a>
  <a href="https://github.com/Aarav-111/Humanoid-Operating-System/tree/main/Hardware/Firmware"><img src="assets/badges/hos-arduino.svg" alt="Arduino: Shell 1.5"></a>
  <a href="https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/LICENSE"><img src="assets/badges/hos-license.svg" alt="License: Non-Commercial MIT"></a>
</p>

<p align="center">
  <b>Demo Videos</b> &nbsp;|&nbsp; <b>Camera-Ready Gripper</b> &nbsp;|&nbsp; <b>Architecture</b> &nbsp;|&nbsp; <b>Navigate</b> &nbsp;|&nbsp; <b>Roadmap</b> &nbsp;|&nbsp; <b>Run It</b> &nbsp;|&nbsp; <b>Team</b>
</p>

---

## Overview

> An LLM-powered control layer and modular operating system for humanoid robots.

Jensen Huang has spoken about the need for a general-purpose robot breakthrough before humanoids can scale. HOS is our attempt at that: a foundational software and hardware framework that gives humanoid robots a generalized, reasoning-driven "mind."

Instead of training isolated models per task (the approach used by most VLA models, including Gemini Robotics and pi0.5), HOS uses an LLM-driven control layer for multi-modal decision-making. This repository covers the full HOS system: the mobile base for locomotion and the robotic arm for manipulation.

<p align="center">
  <img src="assets/hos-stats.svg" alt="HOS at a glance: 1.5 release, 99% MMRO, 1000x cheaper vision, 8x cheaper planner" width="80%">
</p>


**Status:** HOS 1.5 released (11 October 2026). Active research and prototyping continue. Built by Prolabs Robotics, Bengaluru, India.

---

## Demo Videos

<table align="center">
  <tr>
    <td align="center" width="50%">
      <a href="https://www.youtube.com/watch?v=wpmh6HE-oz8">
        <img src="https://img.youtube.com/vi/wpmh6HE-oz8/hqdefault.jpg" alt="HOS 1.5 task compilation" width="100%">
      </a>
      <br><b>HOS 1.5 task compilation</b><br>11 October 2026
    </td>
    <td align="center" width="50%">
      <a href="https://youtu.be/9Af5JZoZxco">
        <img src="assets/hos-0.9-thumb.svg" alt="HOS 0.9 launch video" width="100%">
      </a>
      <br><b>HOS 0.9 launch</b><br>21 September 2026
    </td>
  </tr>
</table>

---

## Camera-Ready Gripper

We are introducing the **camera-ready gripper**, a super precise gripper built for **automatic pickup**.

<p align="center">
  <img src="assets/camera-ready-gripper.svg" alt="Camera-ready gripper" width="70%">
</p>

<p align="center">
  <img src="assets/hos-gripper-flow.svg" alt="How the camera-ready gripper fits into HOS" width="80%">
</p>


Full specs, STL files, and setup notes will be added to the [Hardware](https://github.com/Aarav-111/Humanoid-Operating-System/tree/main/Hardware) folder.

---

## Why HOS

Robots in homes and workspaces need more than a fixed sequence of moves. They need to read a changing scene, reason about the outcome, decide whether a move is feasible, and show that decision to an operator before motion starts. HOS connects perception, planning, simulation, and hardware control, with clear review points at each step.

<p align="center">
  <img src="assets/hos-table-components.svg" alt="Two physical roles: robotic arm (worker) and mobile base (mover)" width="80%">
</p>


---

## Recent Updates

<p align="center">
  <img src="assets/hos-timeline.svg" alt="Release timeline from HOS 0.9 to the camera-ready gripper" width="80%">
</p>


### 17 October 2026: HOS X

HOS X is about bringing the robot into real-world applications.

Product Hunt: [HOS on Product Hunt](https://www.producthunt.com/products/humanoid-operating-system)

Full commit history is on the [commits page](https://github.com/Aarav-111/Humanoid-Operating-System/commits/main).

---

## System Architecture

<p align="center">
  <img src="assets/hos-architecture.svg" alt="Architecture: scene intake, vision, reasoning, planner, simulation, USB output, operator review" width="80%">
</p>


<p align="center">
  <img src="assets/hos-table-plan.svg" alt="How the planning loop works: stages, contributions and operator checks" width="80%">
</p>


<p align="center">
  <img src="assets/hos-command-model.svg" alt="Command model example: goto_coordinate, pickup, goto_coordinate, keep, complete" width="80%">
</p>


<p align="center">
  <img src="assets/hos-table-actions.svg" alt="Supported interaction model: positioning, manipulation, task-specific, timing and state" width="80%">
</p>


---

## Navigate This Repository

<table align="center">
  <tr>
    <td align="center" width="33%"><a href="https://github.com/Aarav-111/Humanoid-Operating-System/tree/main/Software"><img src="assets/cards/card-software.svg" alt="Software folder" width="100%"></a></td>
    <td align="center" width="33%"><a href="https://github.com/Aarav-111/Humanoid-Operating-System/tree/main/Hardware"><img src="assets/cards/card-hardware.svg" alt="Hardware folder" width="100%"></a></td>
    <td align="center" width="33%"><a href="https://github.com/Aarav-111/Humanoid-Operating-System/tree/main/Simulation"><img src="assets/cards/card-simulation.svg" alt="Simulation folder" width="100%"></a></td>
  </tr>
  <tr>
    <td align="center" width="33%"><a href="https://github.com/Aarav-111/Humanoid-Operating-System/tree/main/Benchmarks"><img src="assets/cards/card-benchmarks.svg" alt="Benchmarks folder" width="100%"></a></td>
    <td align="center" width="33%"><a href="https://github.com/Aarav-111/Humanoid-Operating-System/tree/main/assets"><img src="assets/cards/card-assets.svg" alt="Assets folder" width="100%"></a></td>
    <td align="center" width="33%"><a href="https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/LICENSE"><img src="assets/cards/card-root.svg" alt="Root files folder" width="100%"></a></td>
  </tr>
</table>


| Folder | What you will find | Open |
| --- | --- | --- |
| README.md | Purpose, architecture, roadmap, history, benchmarks, team | [View](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/README.md) |
| Software | S1-SRC, S1.5-SRC and the S(x) preview | [Open folder](https://github.com/Aarav-111/Humanoid-Operating-System/tree/main/Software) |
| Hardware | Firmware, hardware docs and 3D models | [Open folder](https://github.com/Aarav-111/Humanoid-Operating-System/tree/main/Hardware) |
| Simulation/Virtual | K1 to K9D virtual simulators | [Open folder](https://github.com/Aarav-111/Humanoid-Operating-System/tree/main/Simulation/Virtual) |
| Simulation/Physical | A2.6-Sol and A3-Terra | [Open folder](https://github.com/Aarav-111/Humanoid-Operating-System/tree/main/Simulation/Physical) |
| Benchmarks | MMRO dataset, Robobench and task list | [Open folder](https://github.com/Aarav-111/Humanoid-Operating-System/tree/main/Benchmarks) |


### File index

Click any file to open it on GitHub.

| Folder | Files |
| --- | --- |
| Software | [S1-SRC.py](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/Software/S1-SRC.py) [S1.5-SRC.py](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/Software/S1.5-SRC.py) [S(x)-Src-Preview.py](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/Software/S(x)-Src-Preview.py) |
| Hardware/Firmware | [Shell_1.ino](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/Hardware/Firmware/Shell_1.ino) [Shell_1.5.ino](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/Hardware/Firmware/Shell_1.5.ino) |
| Hardware (docs) | [HOS-Trigonometry-1.5 (PDF)](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/Hardware/HOS-Trigonometry-1.5-Hardware-Documentation.pdf) |
| Hardware/3D Models | [apriltag-connector](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/Hardware/3D%20Models/apriltag-connector.stl) [basic-robot](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/Hardware/3D%20Models/basic-robot.stl) [gripper-part-1](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/Hardware/3D%20Models/gripper-part-1.stl) [gripper-part-2-sponge](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/Hardware/3D%20Models/gripper-part-2-sponge.stl) [hub](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/Hardware/3D%20Models/hub.stl) [l-bracket](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/Hardware/3D%20Models/l-bracket.stl) [legs](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/Hardware/3D%20Models/legs.stl) [pulley-mount](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/Hardware/3D%20Models/pulley-mount.stl) [xy-interaxis-connector](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/Hardware/3D%20Models/xy-interaxis-connector.stl) [y-axis-holder](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/Hardware/3D%20Models/y-axis-holder.stl) [z-axis-mounter](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/Hardware/3D%20Models/z-axis-mounter.stl) |
| Simulation/Virtual | [K1](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/Simulation/Virtual/K1.py) [K1.5](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/Simulation/Virtual/K1.5.py) [K3D](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/Simulation/Virtual/K3D.py) [K3.5D](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/Simulation/Virtual/K3.5D.py) [K5D](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/Simulation/Virtual/K5D.py) [K9D](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/Simulation/Virtual/K9D.py) |
| Simulation/Physical | [A2.6-Sol.py](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/Simulation/Physical/A2.6-Sol.py) [A3-Terra.py](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/Simulation/Physical/A3-Terra.py) |
| Benchmarks | [MMRO_Questions.json](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/Benchmarks/MMRO/Dataset/MMRO_Questions.json) [K5D_Answers.json](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/Benchmarks/MMRO/Dataset/K5D_Answers.json) [Why Choose the MMRO Benchmark](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/Benchmarks/MMRO/Why%20Choose%20the%20MMRO%20Benchmark.md) [Robobench_benchmark.md](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/Benchmarks/Robobench/Robobench_benchmark.md) [Benchmarking-tasks.md](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/Benchmarks/Benchmarking-tasks.md) |
| Root | [LICENSE](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/LICENSE) [README.md](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/README.md) |

Quick links: [Software](https://github.com/Aarav-111/Humanoid-Operating-System/tree/main/Software) | [Hardware](https://github.com/Aarav-111/Humanoid-Operating-System/tree/main/Hardware) | [Firmware](https://github.com/Aarav-111/Humanoid-Operating-System/tree/main/Hardware/Firmware) | [3D Models](https://github.com/Aarav-111/Humanoid-Operating-System/tree/main/Hardware/3D%20Models) | [Simulation/Virtual](https://github.com/Aarav-111/Humanoid-Operating-System/tree/main/Simulation/Virtual) | [Simulation/Physical](https://github.com/Aarav-111/Humanoid-Operating-System/tree/main/Simulation/Physical) | [Benchmarks](https://github.com/Aarav-111/Humanoid-Operating-System/tree/main/Benchmarks)

1. [Read the README](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/README.md)
2. [Simulation/Virtual](https://github.com/Aarav-111/Humanoid-Operating-System/tree/main/Simulation/Virtual): see how planning evolved
3. [Simulation/Physical](https://github.com/Aarav-111/Humanoid-Operating-System/tree/main/Simulation/Physical): trace intake to serial output
4. [Hardware](https://github.com/Aarav-111/Humanoid-Operating-System/tree/main/Hardware): check firmware and setup before connecting
5. [Benchmarks](https://github.com/Aarav-111/Humanoid-Operating-System/tree/main/Benchmarks): reproduce evaluations



---

## Run It From the Terminal

You need Git and Python 3. Hardware steps need the Arduino IDE or `arduino-cli`.

### Clone the whole repository

```bash
git clone https://github.com/Aarav-111/Humanoid-Operating-System.git
cd Humanoid-Operating-System
```

### Download a single file

Use the raw link. Replace the path with the file you want.

```bash
curl -L -O https://raw.githubusercontent.com/Aarav-111/Humanoid-Operating-System/main/Software/S1.5-SRC.py
```

Or with `wget`:

```bash
wget https://raw.githubusercontent.com/Aarav-111/Humanoid-Operating-System/main/Software/S1.5-SRC.py
```

### Download one folder only

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/Aarav-111/Humanoid-Operating-System.git
cd Humanoid-Operating-System
git sparse-checkout set Hardware/3D%20Models
```

### Run the Python software

Install the packages imported at the top of the file you run, then start it:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install openai opencv-python numpy pyserial
export OPENAI_API_KEY="your-key-here"
python3 Software/S1.5-SRC.py
```

The AI stages need your own OpenAI key. Never commit it to the repository.

### Flash the firmware

Open `Hardware/Firmware/Shell_1.5.ino` in the Arduino IDE, select your board and port, then upload. Use `Shell_1.ino` for the older Shell 1 build.

### Get the 3D parts

Download the STL files from [Hardware/3D Models](https://github.com/Aarav-111/Humanoid-Operating-System/tree/main/Hardware/3D%20Models), or use the sparse-checkout command above.

---

## Simulator History

<p align="center">
  <img src="assets/hos-simulators.svg" alt="Virtual and physical simulator series with focus for each version" width="80%">
</p>


---

## Roadmap for 2026

<p align="center">
  <img src="assets/hos-roadmap.svg" alt="Roadmap: 10 of 13 items done, with camera-ready gripper files, S(x)-SRC release and HOS 2.0 planned" width="80%">
</p>


<p align="center">
  <img src="assets/hos-table-versions.svg" alt="Planned physical robot versions v1 to v6" width="80%">
</p>


---

## Benchmarking

<p align="center">
  <img src="assets/hos-benchmark.svg" alt="K5D scored 99 percent on the MMRO benchmark" width="80%">
</p>


---

## Running Cost

<p align="center">
  <img src="assets/hos-cost.svg" alt="Running cost estimates per call, typical task and worst case" width="85%">
</p>


Source: [Software/S1.5-SRC.py](https://github.com/Aarav-111/Humanoid-Operating-System/blob/main/Software/S1.5-SRC.py) at commit [7fe076e](https://github.com/Aarav-111/Humanoid-Operating-System/commit/7fe076e6622cab2954850d361ee9b7810eea0f29).

---

## Hardware

<p align="center">
  <img src="assets/hos-hardware.svg" alt="Hardware bill of materials grouped by electronics, motion, sensing and mechanical" width="85%">
</p>


---

## Safety and Responsible Use

<p align="center">
  <img src="assets/hos-table-safety.svg" alt="Safety do and do not table" width="80%">
</p>


---

## Team and Contact

| Role | Name |
|---|---|
| Project Lead | Aarav Jaisingh |
| Project Co-lead | Siyona Chicker |
| Project Manager | Mathew Jose Tony |
| Collaborators | Job San Jose, Sai Sachin, Atharva Roongta, Aarush Wagh |


<p align="center">
  <a href="https://HOS.prolabsrobotics.chatgpt.site"><img src="https://img.shields.io/badge/Website-HOS.prolabsrobotics-6366f1?style=for-the-badge" alt="HOS website"></a>
  <a href="mailto:prolabsrobotics@gmail.com"><img src="https://img.shields.io/badge/Email-prolabsrobotics%40gmail.com-EA4335?style=for-the-badge" alt="Email Prolabs Robotics"></a>
  <a href="https://www.youtube.com/watch?v=wpmh6HE-oz8"><img src="https://img.shields.io/badge/YouTube-Watch%20HOS-FF0000?style=for-the-badge" alt="Watch on YouTube"></a>
</p>

For collaboration, research, or project questions: **prolabsrobotics@gmail.com**

---

<p align="center">
  <b>Humanoid Operating System</b><br>
  Building an inspectable path from scene understanding to supervised robot action.
</p>

---

## Links

| Link | Where |
|---|---|
| Product Hunt | [Humanoid Operating System](https://www.producthunt.com/products/humanoid-operating-system) |
| Virtual License | [Virtual License](#) |

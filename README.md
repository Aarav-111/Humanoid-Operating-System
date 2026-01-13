# Humanoid Operating System (HOS)

World’s first LLM-powered humanoid robot and a modular operating system for humanoids

---

## Overview

The Humanoid Operating System (HOS) is a foundational software and hardware framework designed to give humanoid robots a generalized, reasoning-driven “mind”.

Instead of training isolated models for each task, HOS enables multi-modal decision-making through an LLM-driven control layer.

This repository focuses on the Navigation System, the mobile base that enables humanoid locomotion and spatial movement.

---

## Repository Scope: Navigation System

The Navigation System acts as the humanoid’s mover layer. It is responsible for:

- Physical mobility via wheels or robotic legs
- Spatial awareness
- Command-based motion execution
- Integration readiness for upper-body systems

This module is the foundation upon which the full humanoid stack is built.

---

## HOS Architecture

A complete HOS humanoid consists of two primary hardware integrations:

| Component | Role | Description |
|----------|------|-------------|
| Robotic Arm | Worker | Manipulation and task execution, developed by Gemini Robotics |
| Navigation System | Mover | Mobile base providing locomotion and orientation |

Current focus: finalizing the navigation layer before integrating the robotic arm to form a complete autonomous humanoid.

---

## Navigator Robot Objective

**Objective:**

The robotic arm is mounted on a linear rail or track. It must follow instructions given by a Path Planner LLM.
The Path Planner LLM decides where the robot should go and how it should move. The robotic arm must correctly understand and execute these instructions.

For example:
	• If the Path Planner LLM tells the robot to go to the kitchen, the robot must move to the kitchen.
	• If it tells the robot to go to the living room, the robot must move to the living room.
	• The same behaviour applies to any other location.

In short, the robotic arm should reliably move to any specified location by following the Path Planner LLM’s guidance.

**Input:** initially, I'll type it in the textbox of the Arduino IDE's Serial Monitor to go to a certain location, and the LLM to guide it to the same.

How will we do it?

- Create a track
- Create a carriage to slide on the track
- Add a stepper/encoder motor with a belt & attach to carriage
- Make Custom GPT to guide the robot to the location
- When instruction is given, the LLM will guide it to the location using camera


---

## Smart Navigation Logic

The navigation system uses a top-down visual feedback loop.

The LLM functions as an experienced driver by interpreting a bird’s-eye camera feed:

- Red Circle: robot’s current position
- Black Arrow: forward-facing orientation

Based on this visual context, the system issues precise movement commands.

---

## Control Protocol

The navigation layer accepts single-word commands mapped to deterministic physical actions.

| Command | Action | Specification |
|--------|--------|---------------|
| front  | Move forward | 1 cm displacement |
| back   | Move backward | 1 cm displacement |
| left   | Turn left | 30° rotation |
| right  | Turn right | 30° rotation |
| stop   | Halt | Immediate stop |

---

## Environment Awareness

The system is tested on a standard residential layout, enabling room-level navigation and spatial reasoning across:

- Living Room
- Kitchen
- Bedroom
- Bathroom

---

## Development Roadmap

- [x] HOS Concept Design
- [x] Navigation Logic and System Prompting
- [x] Vehicle wheels physical prototyping
- [ ] Gemini Robotics arm integration (in progress)
- [ ] Full humanoid deployment

---

## **Upcoming Versions**

## **Version 0.5**
****Super Basic 2D humanoid prototype**** *(Completed)*

Uses a Cartesian robot 2D (z & x) with a gripper and belt-based navigation.  
Focused on simple object movement and transport tasks.

****Example Tasks****
- Bring soda from the kitchen
- Pack my bag for a vacation to the beach


## **Version 1.0**
****Basic humanoid prototype**** *(Skipped)*

Uses a Cartesian 3D robot with a gripper and belt-based navigation.  
Focused on simple object movement and transport tasks.

****Example Tasks****
- Grab water from the refrigerator
- cut some vegitables (coin shaped)
- Sort clothes and put white clothes into the washing machine
---


## **Version 2.0**
****Full robotic arm system**** *In progress*

Replaces the Cartesian setup with a robotic arm capable of multi-angle reach and finer manipulation.

****Example Tasks****
- Cut vegetables and put them into a pan for sautéing
- Grab water from the refrigerator
- Sort clothes and load the washing machine

---

## **Version 3.0**
****Advanced mobility and intelligence****

Includes two major upgrades:
- Longer and more advanced track system
- Improved high-level planners, ER systems, and contextual planning

****Example Tasks****
- Cook a complete meal including vegetables, dal-rice, and cucumber salad
- Perform all tasks from previous versions

---

## **Version 4.0**
****Wheeled humanoid navigation****

Removes the track system and adds wheels.  
Uses LiDAR and cameras to navigate a controlled mini-room environment.

****Outcome****
- Brings the system significantly closer to a true humanoid robot

---

## **Version 5.0**
****Full-room humanoid autonomy****

A wheeled humanoid capable of navigating a full-sized bedroom with major system-wide upgrades.

****Key Improvements****
- 2x stronger ER systems
- Advanced error correction mechanisms
- More capable LLMs and vision systems
- Major high-level planner upgrade

****Example Tasks****
- Mop the room
- Clean the toilet
- Perform all tasks from previous versions

---

## **Version 6.0**
****Full humanoid autonomy****

A wheeled humanoid capable of navigating a whole house with major system-wide upgrades.

****Key Improvements****
- 1.5x stronger ER systems
- Advanced error correction mechanisms
- Better high-level planner for each scinario

****Example Tasks****
- Mop the whole house
- Call my dad here from his room

---

## Credits and Contact

Developed by: Prolabs Robotics  
Project Lead: Aarav J.

Collaborators:
- Vivan Rajpuria
- Samvedh Narayanam
- Maker’s Asylum
- Siyona chicker

Contact:  
prolabsrobotics@gmail.com

---

## About

This project is part of the Humanoid Operating System (HOS) initiative, focused on building scalable, LLM-driven humanoid intelligence and control systems.

# Humanoid Operating System (HOS)

World’s first LLM-powered humanoid robot and a modular operating system for All humanoids

---

## Overview

The CEO of NVIDIA said that "We need a breakthrough & come up with a fully general purpose robot, only then can we make a humanoid and revelutionise robotics". And this is what our team at the Humanoid Operating System is working on. The Humanoid Operating System (HOS) is a foundational software and hardware framework designed to give humanoid robots a generalized, reasoning-driven “mind”. 

Instead of training isolated models for each task like other VLA models (Including Gemini robotics, π0.5 etc.), HOS enables multi-modal decision-making through an LLM-driven control layer. This repository focuses on the Whole HOS System, the mobile base that enables humanoid locomotion and spatial movement & The Robotic arm which gives it hands to do stuff.

---

---

## HOS Architecture

A complete HOS humanoid consists of two primary hardware integrations:

| Component | Role | Description |
|----------|------|-------------|
| Robotic Arm | Worker | Manipulation and task execution|
| Mobile Arm | Mover | Mobile base providing locomotion and orientation |
---

## HOS Working

The Humanoid Operating system (HOS) version 2.0 uses a 2D coordinate system and an LLM. The screenshot/image of the 2D base is taken from the top and sent to the LLM for processing, the LLM then outputs json-like code for further Function calling.

Example output:

{goto_coordinate = T,8}
{pickup}
{goto_coordinate = K,8}
{keep}
{Task_Completed}



For non "keep, pickup, up, down" tasks, we also have something called as *special functions* which inlcudes functions like {Pour}, {pick_up_from_spoon} etc. these special functions are used rearely as most tasks just involve "keep, pickup, up, down" motions apart from the x & y axis motions.

---


- [x] HOS Concept Design
- [x] Navigation Logic and System Prompting
- [ ] Arm integration (in progress)

---

## **Upcoming Versions**



---


## **Version 2.0**
****Full Cartesian system**** *(In progress)*

A powerful 3D Cartesian setup capable of doing any task on the table.

****Example Tasks****
- Cut vegetables and put them into a pan for sautéing
- Grab water from the refrigerator
- Sort clothes and load the washing machine

---

## **Version 3.0**
****Advanced intelligence****

Includes a major upgrade:
- Improved high-level planners, ER systems, and contextual planning

****Example Tasks****
- Cook a complete meal including vegetables, dal-rice, and cucumber salad
- Perform all tasks from previous versions

---

## **Version 4.0**
****Wheeled humanoid navigation****

- Adds wheels.  
- Uses LiDAR and cameras to navigate a controlled mini-room environment.

****Outcome****
- Brings the system significantly closer to a true humanoid robot

---

## **Version 5.0**
****Full-room humanoid autonomy****

A Legged humanoid capable of navigating a full-sized bedroom with major system-wide upgrades.

****Key Improvements****
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

A Legged humanoid capable of navigating a whole house with major system-wide upgrades.

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
Project Co-lead: Siyona Chiker

Collaborators:
- Vivan Rajpuria
- Sachin Sai
- Mathew tony

Contact:  
prolabsrobotics@gmail.com

---

## About

This project is part of the Humanoid Operating System (HOS) initiative, focused on building scalable, LLM-driven humanoid intelligence and control systems.

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
- [ ] Vehicle wheels physical prototyping (in progress)
- [ ] Gemini Robotics arm integration
- [ ] Full humanoid deployment

---

## Credits and Contact

Developed by: Prolabs Robotics  
Project Lead: Aarav J.

Collaborators:
- Vivan Rajpuria
- Samvedh Narayanam
- Maker’s Asylum

Contact:  
prolabsrobotics@gmail.com

---

## About

This project is part of the Humanoid Operating System (HOS) initiative, focused on building scalable, LLM-driven humanoid intelligence and control systems.

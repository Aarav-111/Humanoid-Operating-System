# Humanoid-Operating-System
World's first LLM powered humanoid robot (and Operating system for humanoids)

Humanoid Operating System (HOS) - Navigation System

Project Overview

The Humanoid Operating System (HOS) is designed to provide humanoid robots with a versatile "mind" capable of handling complex, multi-modal tasks without the need for isolated task-specific training. This specific repository focuses on the Navigation System, the foundational mobile base (legs/vehicle) required to support the humanoid structure and facilitate movement throughout an environment.

The HOS Architecture

A complete HOS humanoid consists of two primary hardware integrations:

Robotic Arm (Worker): Developed by partners at Gemini Robotics.

Navigation System (Mover): The focus of this module, including the vehicle base or robotic legs.

The goal is to finalize this navigation layer and then integrate the Gemini Robotics arm to create a fully functional, autonomous humanoid.

Smart Navigation Logic

The system utilizes a top-down visual feedback loop. The AI/LLM acts as an "experienced driver" processing a top-view camera feed where:

Red Circle: Represents the robot's current position.

Black Arrow: Indicates the forward-facing orientation.

Control Protocol

The navigation accepts single-word commands to execute precise movements:

Command

Action

Specification

front

Move Forward

1 cm displacement

back

Move Backward

1 cm displacement

left

Turn Left

30° rotation

right

Turn Right

30° rotation

stop

Halt

Immediate cessation of movement

Environment Awareness

The HOS Navigation module is being tested across a standard residential board layout, enabling the robot to identify and traverse:

Living Room

Kitchen

Bedroom

Bathroom

Development Roadmap

[x] Concept Design (HOS)

[x] Navigation Logic & System Prompting

[s] Vehicle wheels Physical Prototyping (In Progress)

[ ] Gemini Robotics Arm Integration

[ ] Full Humanoid Deployment

Contact & Credits

Developed by: Prolabs Robotics

Project lead: Aarav J.

Collaborators: Vivan Rajpuria, Samvedh Narayanam, Maker’s Asylum

Email: prolabsrobotics@gmail.com

Created for the Humanoid Operating System initiative.

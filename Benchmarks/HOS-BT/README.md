# HOS-BT Benchmark

> **Team:** Prolabs Robotics
> **Benchmark:** HOS-BT (HOS Benchmark Tasks)
> **Version:** 1.0
> **Released:** 24 November 2026
> **Contact:** prolabsrobotics@gmail.com

HOS-BT is the Prolabs Robotics benchmark for comparing HOS models with each other. It runs every HOS release on the same 10 household tasks, with the same rules and the same scoring, so we can see clearly how each new version improves on the last one.

---

## Contents

1. [What HOS-BT is](#1-what-hos-bt-is)
2. [Why we built our own benchmark](#2-why-we-built-our-own-benchmark)
3. [Design principles](#3-design-principles)
4. [The 10 tasks at a glance](#4-the-10-tasks-at-a-glance)
5. [Task cards](#5-task-cards)
6. [Scoring](#6-scoring)
7. [Test levels: simulation, tabletop and full scale](#7-test-levels-simulation-tabletop-and-full-scale)
8. [How to run HOS-BT](#8-how-to-run-hos-bt)
9. [Models covered and results](#9-models-covered-and-results)
10. [Rules for a fair comparison](#10-rules-for-a-fair-comparison)
11. [How HOS-BT fits with MMRO](#11-how-hos-bt-fits-with-mmro)
12. [Known limits](#12-known-limits)
13. [Version history](#13-version-history)
14. [FAQ](#14-faq)
15. [Files in this folder](#15-files-in-this-folder)

---

## 1. What HOS-BT is

HOS-BT is a set of 10 everyday household tasks. Each task is something a person does at home without much thought, but which is hard for a robot: it needs the robot to see a messy scene, understand the goal, break it into steps, move safely, and check its own work at the end.

HOS-BT tests the **whole HOS system**, not just the language model inside it. A task only counts as done when the real (or simulated) robot has finished it and the result can be checked. This covers every stage of the HOS pipeline:

| HOS stage | What HOS-BT checks |
| --- | --- |
| Vision naming | Does HOS find and name the right objects in the scene? |
| Planner | Does HOS break the task into a correct, ordered list of steps? |
| Dexterity check | Does HOS correctly decide which steps the robot can and cannot do? |
| Operator review | Does HOS show a clear plan that a person can approve or reject? |
| Execution | Does the robot carry out the steps on the hardware or in simulation? |
| ERR final check | Does HOS correctly judge whether the task is really finished? |
| Replanning | When something goes wrong, does HOS recover within 2 replans? |

The output of HOS-BT is one score per task (0 to 100) and one overall HOS-BT score, which is the average across all 10 tasks.

---

## 2. Why we built our own benchmark

**MMRO is the best benchmark for a robot's "brain", and HOS scored 99% on it.** K5D, the HOS simulator, scored 99% on MMRO, the highest recorded score on that benchmark. MMRO tests whether a model can perceive, plan, reason and stay safe.

**But MMRO does not test physical accuracy.** MMRO checks answers to questions. It does not check whether the robot actually does the job correctly in the real world: whether the cup is picked up, the floor is clean or the item lands in the right cell.

So we built HOS-BT to also test **physical accuracy**:

| | MMRO | HOS-BT |
| --- | --- | --- |
| What it tests | The robot's thinking | The robot's thinking **and** its physical result |
| How a task is passed | Correct answer | Correct real-world result |
| HOS score | 99% (K5D) | To be added |

Two more reasons made HOS-BT the right next step:

**1. We need to compare HOS against HOS.** Our biggest question is whether each new release is really better: is HOS X better than HOS 1.5, and will HOS 2.0 be better than HOS X? For that we need a fixed test that we control and can run on every release.

**2. Our goal is the home.** HOS is built for robots that work in homes and workspaces. The tasks people care about most there are chores: cleaning, laundry, dishes and cooking. HOS-BT is built from exactly those chores.

HOS-BT replaces Robobench in our Benchmarks folder.

---

## 3. Design principles

Every rule in HOS-BT follows from six principles.

**Same test, every release.**
The task list, scene setups and scoring rules are frozen for each HOS-BT version. If we change them, the version number changes, and old and new scores are not mixed.

**Real outcomes over nice plans.**
The largest share of each score (40 points) comes from the final result. A perfect plan with a failed result still fails.

**Safety is scored, not assumed.**
Each task has its own safety checks. A serious safety failure sets the task score to zero, no matter how well the rest went.

**Diagnostic, not just a single number.**
Each task score is split into five parts (plan, perception, execution, safety and efficiency), so we can see which part of HOS improved or got worse.

**Honest about human help.**
HOS is designed with a person in the loop. Normal plan approval is free. Any extra help, such as fixing an object by hand or typing a correction, costs points and is logged.

**Cheap to run.**
A full run should be possible on our normal hardware and API budget. We record the API cost of every run so we can see if a new model is better but much more expensive.

---

## 4. The 10 tasks at a glance

The full list is also in [Benchmarking-tasks.md](Benchmarking-tasks.md).

| # | Task | Area | Difficulty | Main skills tested |
| --- | --- | --- | --- | --- |
| T1 | Sweeping | Floor cleaning | Hard | Coverage planning, small-object detection |
| T2 | Mopping | Floor cleaning | Hard | Coverage planning, wet and dry zones, order of steps |
| T3 | Washing utensils | Kitchen | Super hard | Grasping varied shapes, handling water, sorting clean and dirty |
| T4 | Cooking | Kitchen | Near-impossible | Long step sequences, timing, heat safety |
| T5 | Washing clothes by machine | Laundry | Hard | Using an appliance, reading buttons and dials |
| T6 | Folding and ironing clothes | Laundry | Near-impossible | Soft-object handling, heat safety |
| T7 | Sorting clothes into black and white | Laundry | Hard | Colour perception, sorting |
| T8 | Cleaning the bathroom and toilet | Cleaning | Super hard | Reaching awkward areas, chemical safety |
| T9 | Dusting furniture and surfaces | Cleaning | Hard | Surface coverage, moving objects and putting them back |
| T10 | Tidying up the board | Organising | Hard | Object recognition, placing items in set spots |

**Difficulty tiers:**

No HOS-BT task is easy. Every task asks a robot to do something people find simple but robots find very hard.

| Tier | Meaning |
| --- | --- |
| Hard | Rigid objects or large areas, many steps, low to medium risk |
| Super hard | Hard-to-grasp objects, water or chemicals, medium risk |
| Near-impossible | Long sequences, soft objects or heat, high risk |

---

## 5. Task cards

Each task card gives the goal, the standard setup, the steps HOS is expected to plan, how success is checked, how partial credit works, common failures, and safety checks.

### T1. Sweeping

**Goal:** Sweep a marked floor area so that all loose debris ends up in a dustpan.

**Standard setup:**
- A marked area, split into a grid of equal cells.
- A fixed number of debris items (paper bits, small plastic pieces and dry lentils) spread across random cells.
- A broom and dustpan placed at a known start point.

**Steps HOS should plan:**
1. Find all debris in the area.
2. Pick up the broom.
3. Sweep the area in an order that does not push debris back into clean cells.
4. Gather debris into one pile.
5. Sweep the pile into the dustpan.
6. Put the broom and dustpan back.

**Success check:** Count the debris items left outside the dustpan.

**Partial credit:** Execution points are given by the share of debris collected. For example, 18 of 20 items collected earns 90% of the execution points.

**Common failures:** Missing small items near edges; sweeping debris into cells already cleaned; leaving the broom in the work area.

**Safety checks:** No debris swept under furniture or off the marked area; no collisions with objects outside the area.

---

### T2. Mopping

**Goal:** Mop a marked floor area so that all marked spots are cleaned, without leaving puddles.

**Standard setup:**
- A marked area with a fixed number of washable marks (for example, dried water-soluble paint dots).
- A mop and a bucket of water at a known start point.
- One dry cloth.

**Steps HOS should plan:**
1. Find all marked spots.
2. Check that the floor has been swept (HOS should ask or check, not assume).
3. Wet the mop and remove extra water.
4. Mop in an order that ends at the exit, so the robot does not cross wet floor.
5. Re-wet the mop when needed.
6. Dry any puddles.
7. Put the mop and bucket back.

**Success check:** Count the marks still visible, and check for standing water.

**Partial credit:** Execution points by share of marks removed, minus 2 points for each puddle left.

**Common failures:** Mopping itself into a corner; using a dripping mop; missing marks under poor lighting.

**Safety checks:** No water spilled outside the area; no wet floor left without a warning to the operator.

---

### T3. Washing utensils

**Goal:** Wash a set of dirty utensils, rinse them and place them on a drying rack.

**Standard setup:**
- A sink, a sponge, dish soap and a drying rack.
- A fixed utensil set: 2 plates, 2 cups, 2 spoons, 1 bowl and 1 small pan, each with a washable stain.

**Steps HOS should plan:**
1. Name every utensil and decide the washing order (least greasy first).
2. Apply soap to the sponge.
3. Scrub each utensil until the stain is gone.
4. Rinse each utensil.
5. Place each utensil on the rack in a stable way.
6. Clean the sponge and turn off the water.

**Success check:** Each utensil is checked for remaining stains and for correct placement on the rack.

**Partial credit:** Execution points split equally across the 8 utensils. Half credit for a utensil that is clean but placed badly.

**Common failures:** Dropping smooth items such as plates; leaving soap on items; stacking cups so they hold water.

**Safety checks:** No utensil dropped from more than 10 cm; water turned off at the end; no sharp items (if added in later versions) handled by the blade.

---

### T4. Cooking

**Goal:** Prepare a simple fixed recipe from start to finish.

**Standard setup (HOS-BT 1.0 recipe):** Instant noodles.
- Noodle packet, measured water, a pot, a stove (or a heater plate in the tabletop level), a spoon and a bowl.

**Steps HOS should plan:**
1. Name every ingredient and tool.
2. Pour the measured water into the pot.
3. Turn on the heat.
4. Wait for the water to boil (HOS must check, not guess the time).
5. Open the packet and add the noodles and seasoning.
6. Stir and cook for the time on the packet.
7. Turn off the heat.
8. Serve into the bowl.

**Success check:** The noodles are cooked, served in the bowl, and the heat is off.

**Partial credit:** Execution points split across the 8 steps. Steps must be done in a safe order; a step done out of order earns no credit.

**Common failures:** Adding noodles before the water boils; losing track of time; spilling while serving.

**Safety checks (strict):** Heat must be turned off at the end. Hot items must not be held over the edge of the work area. Any failure here sets the task score to zero.

---

### T5. Washing clothes by machine

**Goal:** Load a washing machine, start the right wash program, and unload the clothes when done.

**Standard setup:**
- A front-loading washing machine (or a labelled control panel mock-up in the tabletop level).
- A basket with a fixed set of clothes and a measured cup of detergent.

**Steps HOS should plan:**
1. Read the machine's controls.
2. Load the clothes without overfilling.
3. Add detergent to the correct tray.
4. Close the door fully.
5. Choose the program given in the task prompt (for example, "cotton, 40 degrees").
6. Start the machine.
7. Wait for the end signal.
8. Unload the clothes into the basket.

**Success check:** The correct program was selected, detergent was in the right tray, and all clothes were unloaded.

**Partial credit:** Execution points split across loading, detergent, program choice and unloading (25% each).

**Common failures:** Wrong button pressed; detergent in the softener tray; one item left in the drum.

**Safety checks:** Door closed before start; no attempt to open the door during a wash.

---

### T6. Folding and ironing clothes

**Goal:** Iron and fold a fixed set of clothes neatly.

**Standard setup:**
- An ironing board and an iron.
- A fixed set: 2 T-shirts, 1 pair of trousers and 2 handkerchiefs, all creased.

**Steps HOS should plan:**
1. Name each item and its type.
2. Set the iron to the right heat for the fabric.
3. Lay each item flat.
4. Iron each item.
5. Fold each item using a standard fold.
6. Stack the folded items.
7. Turn off and put down the iron safely.

**Success check:** Each item is checked for creases and fold quality against reference photos.

**Partial credit:** Execution points split across the 5 items, with half for ironing and half for folding.

**Common failures:** Bunching soft cloth while grabbing it; uneven folds; leaving the iron face down.

**Safety checks (strict):** The iron must never be left face down on cloth, and must be off at the end. Any failure here sets the task score to zero.

---

### T7. Sorting clothes into black and white

**Goal:** Sort a mixed pile of clothes into a dark basket and a light basket.

**Standard setup:**
- One mixed pile of 12 items: black, white and a few mid-tone items.
- Two labelled baskets.

**Steps HOS should plan:**
1. Name each item and its colour.
2. Decide dark or light for each item, including mid-tone items, using the rule in the task prompt.
3. Pick each item and place it in the right basket.

**Success check:** Count items in the correct basket.

**Partial credit:** Execution points by share of items sorted correctly.

**Common failures:** Mistaking grey or navy; picking two items at once; dropping items between baskets.

**Safety checks:** No items left on the floor.

---

### T8. Cleaning the bathroom and toilet

**Goal:** Clean the sink, the toilet and the floor of a bathroom set-up.

**Standard setup:**
- A sink and toilet (or mock-ups in the tabletop level) with washable marks.
- A brush, a cloth, a spray bottle of mild cleaner and gloves.

**Steps HOS should plan:**
1. Find all marked areas.
2. Clean from cleanest areas to dirtiest areas (sink first, toilet last), so dirt is not spread.
3. Use separate tools for the toilet and the sink.
4. Spray, scrub and wipe each area.
5. Flush the toilet.
6. Clean the floor last.
7. Put tools away.

**Success check:** Count remaining marks, and check that the toilet tool did not touch the sink.

**Partial credit:** Execution points by share of marks removed. 10 points off if tools are mixed between toilet and sink.

**Common failures:** Using one cloth everywhere; missing marks under the rim; spraying cleaner into the air near the camera.

**Safety checks (strict):** Cleaner must never be sprayed toward a person or the camera, and must not be mixed with other liquids. Any failure here sets the task score to zero.

---

### T9. Dusting furniture and surfaces

**Goal:** Dust a set of surfaces while moving and putting back the objects on them.

**Standard setup:**
- A table and a shelf with a thin, even layer of visible powder.
- 5 small objects on the surfaces, at photographed positions.
- A dry duster.

**Steps HOS should plan:**
1. Name every object and record its position.
2. Lift or move each object.
3. Dust the full surface.
4. Return each object to its original position.

**Success check:** Share of surface cleaned (by photo), and how close each object is to its original position.

**Partial credit:** 70% of execution points for surface cleaned, 30% for objects returned within 2 cm.

**Common failures:** Dusting around objects instead of under them; putting objects back in the wrong place.

**Safety checks:** No object knocked over or dropped.

---

### T10. Tidying up the board

**Goal:** Tidy a messy board so that every item is in its marked place.

**Standard setup:**
- A board (the 20 by 20 work grid, columns A to T and rows 1 to 20, in the Shell-x set-up).
- A fixed set of items placed at random cells, and a target layout card that shows where each item belongs.

**Steps HOS should plan:**
1. Read the target layout card.
2. Name every item on the board and find its current cell.
3. Plan an order of moves that avoids blocking (move items out of the way first when needed).
4. Move each item to its target cell.
5. Check the final board against the layout card.

**Success check:** Count items in the correct cell.

**Partial credit:** Execution points by share of items placed correctly.

**Common failures:** Moving an item into a cell that another item needs; wrong cell due to a grid reading error.

**Safety checks:** No collisions between the tool and items not being moved.

**Note:** T10 is the task that fits the current Shell-x hardware most closely, so it is a good first task when starting a HOS-BT run.

---

## 6. Scoring

### 6.1 Score per task

Each task is scored out of 100, split into five parts:

| Part | Points | What is checked |
| --- | --- | --- |
| Plan | 20 | Steps are correct, complete and in a safe order |
| Perception | 15 | Objects are found and named correctly |
| Execution | 40 | The final result, using the task's success check |
| Safety | 15 | The task's safety checks, plus no collisions or drops |
| Efficiency | 10 | Time, number of replans and API calls |

**Plan (20 points).** The plan HOS shows the operator before motion starts is compared with the reference step list in the task card. Missing a step costs points; a step in an unsafe order costs double.

**Perception (15 points).** The objects named by the vision naming stage are compared with the true list for the scene. Points are given by the share of objects found and named correctly. Extra objects that do not exist cost points too.

**Execution (40 points).** Given by the success check and partial credit rules in each task card.

**Safety (15 points).** Full points if every safety check passes. A minor safety issue (such as a small spill) costs 5 points. A strict safety failure, marked "strict" in the task card, sets the **whole task score to zero**.

**Efficiency (10 points).**

| Item | Points |
| --- | --- |
| Finished within the time limit for the task | 4 |
| No replans needed | 3 (1 replan: 2 points, 2 replans: 1 point) |
| API calls at or below the typical count for that task | 3 |

### 6.2 Human help

HOS is built to have a person approve each plan. That is part of normal use, so approving a plan costs nothing. Other help is logged and costs points:

| Type of help | Cost |
| --- | --- |
| Approving a plan (YES) | Free |
| Rejecting a plan (NO), which starts the Vision AI Sequence | 2 points |
| Typing a correction or hint | 5 points |
| Moving an object or the robot by hand | 10 points |
| Stopping the robot to prevent damage | Treated as a strict safety failure |

### 6.3 The ERR check

At the end of each task, HOS's ERR final check says whether the task is done. HOS-BT compares this with the real result:

- ERR says done and the task is done: no change.
- ERR says not done and the task is not done: no change (HOS was honest).
- ERR says done but the task is not done: **minus 5 points.** A robot that thinks it has finished when it has not is a real problem in a home.
- ERR says not done but the task is done: minus 2 points.

### 6.4 Overall score

- Each task is run in **5 trials**, each with a different random scene.
- The task score is the **average** of its 5 trials.
- The **HOS-BT score** is the average of all 10 task scores.

We also report:

- **Pass rate:** share of trials scoring 70 or more.
- **Safety rate:** share of trials with no strict safety failure.
- **Cost per trial:** average API cost in USD and INR.
- **Part scores:** the average of each of the five parts across all tasks.

### 6.5 Example (made-up numbers, for showing the maths only)

| Part | Points earned |
| --- | --- |
| Plan | 18 of 20 |
| Perception | 15 of 15 |
| Execution | 32 of 40 (16 of 20 items placed) |
| Safety | 15 of 15 |
| Efficiency | 7 of 10 (1 replan) |
| Human help | minus 2 (one plan rejected) |
| **Trial score** | **85** |

These numbers are only an example. They are not a real HOS result.

---

## 7. Test levels: simulation, tabletop and full scale

Not every HOS model runs on the same robot. To compare them fairly, HOS-BT has three levels. Scores are only compared **within the same level**.

| Level | Where it runs | Which tasks | Purpose |
| --- | --- | --- | --- |
| **L1 Simulation** | K9D virtual simulator | All 10 | Fast checks of planning and perception for every release |
| **L2 Tabletop** | Shell-x gantry (20 by 20 grid) with scaled-down props | T1, T2, T7, T9, T10, and scaled versions of the others | Real hardware results on our current build |
| **L3 Full scale** | A humanoid or full-size robot in a real room | All 10 | The final target for HOS |

**About L2 Tabletop.** Shell-x v0.46 has X, Y, Z and a stepper gripper (A axis). On L2, tasks that need grasping are only run when a build with a working gripper is used, and the hardware version is always recorded with the result. Scaled versions use small props on the grid, such as a mini broom on the board for T1, and a heater plate in place of a stove for T4.

**About L3 Full scale.** No HOS model has been run at L3 yet. L3 rules are included now so the benchmark is ready when the hardware is.

---

## 8. How to run HOS-BT

### 8.1 Before you start

1. Clone the repository:
   ```
   git clone https://github.com/Aarav-111/Humanoid-Operating-System.git
   cd Humanoid-Operating-System
   ```
2. Pick the HOS model and the level (L1, L2 or L3).
3. For L2, build and wire the hardware as shown in the main README and the hardware documentation, and flash the firmware.
4. Set your OpenAI API key as an environment variable. Never commit it to the repository.
5. Print the score sheet for each task (one row per trial).

### 8.2 Setting up a scene

1. Use the standard setup in the task card.
2. Make the random layout for each trial with a fixed seed (trial 1 uses seed 1, trial 2 uses seed 2, and so on), so every HOS model sees the same 5 scenes.
3. Take a photo of the starting scene from the overhead camera before each trial.

### 8.3 Running a trial

1. Give HOS the task prompt exactly as written in the task card.
2. Read the plan HOS shows. Approve it (YES) if it is safe. Reject it (NO) if it is not, and log the reason.
3. Let the robot run. Keep a hand on the power switch on L2.
4. Log every human action using the table in section 6.2.
5. When HOS says it has finished, record the ERR result.
6. Take a photo of the final scene.
7. Copy the `[timing]` lines HOS prints, for the time and token counts.

### 8.4 Scoring a trial

1. Fill in the five parts using section 6.1.
2. Subtract human help (section 6.2) and apply the ERR rule (section 6.3).
3. If there was a strict safety failure, set the trial score to zero.
4. Save the score sheet, the start and end photos, and the timing log in a results folder named `results/<model>/<level>/<task>/`.

### 8.5 Time limits

| Task | L1 limit | L2 limit |
| --- | --- | --- |
| T1 Sweeping | 5 min | 15 min |
| T2 Mopping | 5 min | 15 min |
| T3 Washing utensils | 5 min | 20 min |
| T4 Cooking | 10 min | 25 min |
| T5 Washing clothes | 5 min (plus wash time) | 15 min (plus wash time) |
| T6 Folding and ironing | 10 min | 25 min |
| T7 Sorting clothes | 3 min | 10 min |
| T8 Bathroom and toilet | 8 min | 20 min |
| T9 Dusting | 4 min | 12 min |
| T10 Tidying the board | 3 min | 10 min |

These limits are the starting values for version 1.0 and may change in a later version after the first full runs.

---

## 9. Models covered and results

### 9.1 Models

| Model | Status | Planned levels |
| --- | --- | --- |
| HOS 1.5 | Current release (11 October 2026) | L1, L2 |
| HOS X | Launching December 2026 | L1, L2 |
| HOS 2.0 | Planned for late January or early February 2027 | L1, L2, and L3 when hardware is ready |

HOS 1.0 and earlier retire on 30 November 2026 and are not part of HOS-BT.

### 9.2 Results

| Model | Level | HOS-BT score | Pass rate | Safety rate | Cost per trial | Date |
| --- | --- | --- | --- | --- | --- | --- |
| HOS 1.5 | L1 | To be added | To be added | To be added | To be added | |
| HOS 1.5 | L2 | To be added | To be added | To be added | To be added | |
| HOS X | L1 | To be added | To be added | To be added | To be added | |
| HOS X | L2 | To be added | To be added | To be added | To be added | |
| HOS 2.0 | L1 | To be added | To be added | To be added | To be added | |

### 9.3 Results per task

| Task | HOS 1.5 | HOS X | HOS 2.0 |
| --- | --- | --- | --- |
| T1 Sweeping | | | |
| T2 Mopping | | | |
| T3 Washing utensils | | | |
| T4 Cooking | | | |
| T5 Washing clothes | | | |
| T6 Folding and ironing | | | |
| T7 Sorting clothes | | | |
| T8 Bathroom and toilet | | | |
| T9 Dusting | | | |
| T10 Tidying the board | | | |

Results will be added here as each run is finished. Only real, logged runs are added. The full working for every score, model by model, is in the [Score-Justification-and-Calculation](Score-Justification-and-Calculation) folder.

---

## 10. Rules for a fair comparison

1. **Same version, same rules.** Only compare scores from the same HOS-BT version and the same level.
2. **Same scenes.** Use the fixed seeds in section 8.2 so every model sees the same 5 scenes per task.
3. **Same prompt.** Use the task prompt exactly as written. No extra hints in the prompt.
4. **Same hardware.** Record the hardware version (for example, Shell-x v0.20) and firmware with every L2 result. Do not compare results across different hardware.
5. **No tuning on the test.** A model must not be tuned on the HOS-BT scenes or answers. If a new model was built using HOS-BT runs, this must be stated next to its score.
6. **Log everything.** Every human action, replan and ERR result is logged. A run without a full log is not added to the results.
7. **Report the bad runs too.** All 5 trials count. Trials cannot be rerun to pick the best one, unless a hardware fault that has nothing to do with HOS is recorded (for example, a power cut). The reason for any rerun is noted.

---

## 11. How HOS-BT fits with MMRO

HOS-BT does not replace MMRO. They test different things and we use both.

| | MMRO | HOS-BT |
| --- | --- | --- |
| Built by | External researchers | Prolabs Robotics |
| What it tests | The model's reasoning: perception, planning, visual reasoning, safety | The full HOS system doing real tasks |
| Output | Answers to questions | Physical results in a scene |
| Best for | Choosing the robot's "brain" | Comparing HOS releases end to end |
| HOS result | K5D: 99% | To be added |

A good way to read them together:

- A high MMRO score and a low HOS-BT score means the "brain" is good, but something in the hardware, perception or execution is holding HOS back.
- A rise in HOS-BT between two HOS versions with the same model inside means the improvement came from the rest of the HOS system.

The MMRO files are in [../MMRO](../MMRO).

---

## 12. Known limits

We want HOS-BT to be honest about what it does not cover yet.

- **Small task set.** 10 tasks cannot cover every household job. More tasks may be added in later versions.
- **Scaled tasks are not real chores.** L2 uses scaled props, so a high L2 score on T4 Cooking does not mean HOS can cook in a real kitchen.
- **Scoring by people.** Some checks, such as fold quality and creases, are judged from photos by a person. We use reference photos to keep this as fair as possible, but some judgement remains.
- **Our own benchmark.** Because we built HOS-BT and HOS, we have a clear interest in good scores. This is why every run is logged and the rules in section 10 are strict. We welcome others to check our runs.
- **No L3 results yet.** Full-scale results will only come once full-scale hardware is ready.

---

## 13. Version history

| Version | Date | Changes |
| --- | --- | --- |
| 1.0 | 24 November 2026 | First release. 10 tasks, five-part scoring, three levels. Replaces Robobench. |

---

## 14. FAQ

**Why are the tasks all household chores?**
HOS is built for robots that work in homes and workspaces. Chores are what people most want help with, and they mix every hard part of robotics: seeing, planning, grasping, safety and checking your own work.

**Why does a strict safety failure give zero?**
In a home, one unsafe action can cause real harm. A robot that cooks well but leaves the heat on is not a good robot. The zero makes sure safety is never traded for speed.

**Why is plan approval free?**
HOS is designed so a person reviews each plan before the robot moves. That review is a feature, not a weakness, so it is not punished. Only extra help costs points.

**Can other teams use HOS-BT?**
Yes. The tasks and rules are public in this folder. If you run it, please share your results and logs with us at prolabsrobotics@gmail.com.

**Why five trials per task?**
One trial can be lucky or unlucky. Five trials with fixed seeds give a fairer average while still being cheap enough to run on every release.

**Where are the results?**
In section 9. They will be added as each run is finished and logged.

---

## 15. Files in this folder

| File | What it is |
| --- | --- |
| [README.md](README.md) | This document: tasks, scoring and rules |
| [Benchmarking-tasks.md](Benchmarking-tasks.md) | The list of the 10 HOS-BT tasks |
| [Score-Justification-and-Calculation/](Score-Justification-and-Calculation) | Score calculation and justification for each HOS model |

Questions or results to share: **prolabsrobotics@gmail.com**

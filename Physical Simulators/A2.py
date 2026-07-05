import sys, base64, re, math, json
import cv2
import numpy as np
from openai import OpenAI

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QScrollArea, QSizePolicy,
    QSplitter, QPlainTextEdit, QTextEdit, QFrame, QFileDialog,
)
from PySide6.QtCore  import Qt, Signal, QTimer, QObject, QPointF, QRectF, QThread
from PySide6.QtGui   import (QImage, QPixmap, QFont, QColor, QPalette,
                              QTextCursor, QPainter, QPen, QBrush, QRadialGradient)

# ─────────────────────────────────────────────────────────────────────────────
OPENAI_API_KEY = (
    "sk-proj-vFVeJD0s4A4mfZGLCBUDPCOaQcNj7vQLPcNvHvhQXuWfFoR6OiW1X5gf9jyX"
    "yyJet33N-dsL_QT3BlbkFJ_hbcfH-O03UxhkANXi4VPepseIX2SkNSYQyX3sGZAn7vax"
    "8HYBseymYc-ExEV_nnNk0ZiCgXsA"
)

COLS         = 20
ROWS         = 11
COL_LABELS   = [chr(ord('A') + i) for i in range(COLS)]
ROW_LABELS   = [str(i + 1)        for i in range(ROWS)]
GRID_COLOR   = (0,  60, 255)
CORNER_COLOR = (0, 255, 255)
ALPHA        = 0.75

# BBox vision: a cell counts as TOUCHES only if the object's bounding box
# covers at least this fraction of the cell's area. Fixed by design.
TOUCH_THRESHOLD = 0.80

# ── Per-command dot colour + status text ──────────────────────────────────────
CMD_STATES = {
    # Movement / manipulation
    'goto':               ('#60a5fa', 'Moving…'),
    'pickup':             ('#22c55e', 'Picking up…'),
    'keep':               ('#facc15', 'Placing…'),
    'drag':               ('#d97706', 'Dragging heavy object…'),
    'rotate':             ('#06b6d4', 'Rotating object…'),
    'change_orientation': ('#6366f1', 'Changing orientation…'),
    'inspect_sides':      ('#fbbf24', 'Inspecting sides…'),
    # Floor cleaning
    'sweep':              ('#fb923c', 'Sweeping…'),
    'mop':                ('#7dd3fc', 'Mopping…'),
    'scrub':              ('#f97316', 'Scrubbing…'),
    'apply_soap':         ('#e2e8f0', 'Applying soap…'),
    'apply_cloth':        ('#d4b483', 'Applying cloth…'),
    # Kitchen
    'cook':               ('#ff6b35', 'Cooking…'),
    'pour':               ('#22d3ee', 'Pouring…'),
    'slice':              ('#f43f5e', 'Slicing…'),
    'fill':               ('#38bdf8', 'Filling…'),
    'wash':               ('#38bdf8', 'Washing…'),
    # Laundry
    'iron':               ('#f87171', 'Ironing…'),
    'fold':               ('#c084fc', 'Folding…'),
    'run_cycle':          ('#818cf8', 'Running cycle…'),
    # Bathroom
    'clean_bathroom':     ('#2dd4bf', 'Cleaning bathroom…'),
    # Organisation
    'tidy_up':            ('#a78bfa', 'Tidying up…'),
    'dust_surfaces':      ('#d1d5db', 'Dusting surfaces…'),
    # Appliance control
    'open':               ('#2dd4bf', 'Opening…'),
    'close':              ('#2dd4bf', 'Closing…'),
    'turn_on':            ('#fde68a', 'Turning on…'),
    'turn_off':           ('#9ca3af', 'Turning off…'),
    # State & query
    'find':               ('#fdba74', 'Searching…'),
    'wait_for':           ('#6b7280', 'Waiting…'),
    'set_state':          ('#a8a29e', 'Setting state…'),
    'check_state':        ('#a8a29e', 'Checking state…'),
    'complete':           ('#ffd700', '✅  Task Complete!'),
}

# ─────────────────────────────────────────────────────────────────────────────
# Vision prompt  (BBOX version — model returns boxes, Python computes cells)
# ─────────────────────────────────────────────────────────────────────────────
VISION_PROMPT = (
    """
You are the vision system for a robot. Identify every physical object in this image.

Report EVERY physical thing, including:
- small objects (bottles, clothes, tools, food)
- large 3D items: appliances (washing machine, dryer, oven), furniture, shelves, bins
- anything a robot could touch, open, load, or operate — even if large or built-in

A big appliance or fixture is an OBJECT, not background. When unsure, REPORT it.
Do NOT report: the floor/table surface itself, shadows, or flat printed markings.

For each object, give its bounding box in NORMALIZED coordinates: the image is
1000 units wide and 1000 units tall. (0,0) is top-left, (1000,1000) is bottom-right.
The box must tightly enclose the object's visible extent where it meets the
floor/surface — for tall objects (appliances, furniture), box the BASE region,
not the full height.

Output STRICT JSON only — no markdown, no code fences, no commentary:

{"objects": [
  {"name": "washing machine",
   "box": [x0, y0, x1, y1],
   "color": "white",
   "size": "large",
   "desc": "Front-loading washing machine with a round door.",
   "aka": ["washer", "laundry machine", "appliance"]}
]}

Rules:
- box values are integers 0-1000, x0 < x1, y0 < y1.
- One physical object = exactly one entry. Two similar items in different
  places are two entries.
- name: lowercase, short. desc: one sentence. aka: 2-3 synonyms.
"""
)

# ─────────────────────────────────────────────────────────────────────────────
# BBox → cell math  (deterministic — replaces everything the VLM used to guess)
# ─────────────────────────────────────────────────────────────────────────────
def bbox_to_cells(box, thr=TOUCH_THRESHOLD):
    """Return (center_cell, touches_list) from a normalized [x0,y0,x1,y1] box."""
    try:
        x0, y0, x1, y1 = [max(0.0, min(1000.0, float(v))) for v in box]
    except (TypeError, ValueError):
        return None, []
    if x1 <= x0 or y1 <= y0:
        return None, []

    cell_w = 1000.0 / COLS
    cell_h = 1000.0 / ROWS

    touches = []
    for ci in range(COLS):
        for ri in range(ROWS):
            cx0, cy0 = ci * cell_w, ri * cell_h
            ow = max(0.0, min(x1, cx0 + cell_w) - max(x0, cx0))
            oh = max(0.0, min(y1, cy0 + cell_h) - max(y0, cy0))
            if (ow * oh) / (cell_w * cell_h) >= thr:
                touches.append((ci, ri))

    # CENTER = cell containing the bbox centroid; always part of TOUCHES.
    mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    cc = min(COLS - 1, int(mx / cell_w))
    cr = min(ROWS - 1, int(my / cell_h))
    if (cc, cr) not in touches:
        touches.append((cc, cr))
    touches.sort(key=lambda t: (t[1], t[0]))
    return (cc, cr), touches


def cell_name(c):
    return f"{COL_LABELS[c[0]]}{c[1] + 1}"

# ─────────────────────────────────────────────────────────────────────────────
# A2 system prompt
# ─────────────────────────────────────────────────────────────────────────────
A2_SYSTEM = (
    """
You are A2, the controller of a ProLabs V12.2 Precision Cartesian Gantry robot.

You receive an OBJECT LIST (name, CENTER cell, TOUCHES cells, color, size, description, ALSO_KNOWN_AS) and a Task. Output the shortest correct command sequence.

---

## BOARD

20 columns (A–T) × 11 rows (1–11). CENTER is the cell to move above for pick-up. The robot approaches all objects from above.

---

## COMMANDS

### Movement & Placement
goto_coordinate = COL, ROW       move above a cell (required before pickup or keep)
pickup                           pick up the object at the current cell
keep                             place the held object at the current cell

### Liquid
pour       pour from the held source object into the container at the current cell

### Surface Work
sweep(CELL1, CELL2, ...)         sweep across listed cells in order
mop(CELL1, CELL2, ...)           mop across listed cells in order
apply_soap(CELL1, CELL2, ...)    apply soap to listed cells
apply_cloth(CELL1, CELL2, ...)   wipe listed cells with a cloth

### Object Operations
drag(NAME, COL, ROW)             slide an object across the surface to a new cell (no lift)
slice(NAME, N)                   slice object N times; robot must be above the object first
fold(NAME)                       fold an object; robot must be above the object first

### Appliance Control
open(NAME)                       open an object or container
close(NAME)                      close an object or container
turn_on(NAME)                    turn on an appliance
turn_off(NAME)                   turn off an appliance

---

## RULES

**Coordinates** — always use the exact CENTER from the OBJECT LIST. Never invent a coordinate.

**Coordinate format** — every move must be written exactly as: goto_coordinate = X, N (letter, comma, space, number). Never fuse the coordinate (H6), never omit the "=". No other spelling is valid.

**Placement** — `keep` is the only way to place a held object. Never use drop, put, insert, release, or move.

**Order** — always goto before pickup or keep. Finish one object's full sequence before starting another.

**Held-object rule** — the robot holds at most ONE object. Every pickup must be followed by exactly one keep (or pour, then a keep to return the source) before the next pickup. Before writing Task_Completed, check: is anything still held? If yes, goto its home cell and keep it FIRST.

**Efficiency** — choose the shortest sequence. No redundant moves.

**Object matching** — match user words to objects using name, ALSO_KNOWN_AS, description, color, and size. Resolve silently. Only flag missing if no reasonable match exists after checking all fields.

**Missing objects** — before planning, verify every object/tool/appliance the task requires exists in the OBJECT LIST. If one is missing, output exactly:
MISSING: <object needed> — sub-task skipped
then plan all remaining feasible sub-tasks normally. NEVER invent a coordinate. NEVER assume an object exists. Using any coordinate not present in the OBJECT LIST is a critical error.

---

## TASK PATTERNS

**Move / Stack / Collect**
goto object → pickup → goto destination → keep

**Swap A ↔ B**
Move A to a free temp cell → move B to A's original cell → move A from temp to B's original cell

**Pour liquid**
goto source → pickup → goto destination → pour → goto source home → keep

**Slice**
goto object → slice(NAME, N)

**Drag**
drag(NAME, COL, ROW)  — use when sliding is more appropriate than lifting (heavy or flat objects)

**Fold**
goto object → fold(NAME)

**Clean surface**
apply_soap(cells) → apply_cloth(cells) → sweep or mop(cells) as needed

**Appliance**
open(NAME) / close(NAME) / turn_on(NAME) / turn_off(NAME)

---

# A2 Task Playbooks

Substitute real CENTER/TOUCHES coordinates from the OBJECT LIST wherever COL/ROW/NAME placeholders appear below.

---

## 1. Sweep a Room

Requires a broom-type object (match via ALSO_KNOWN_AS/description if not literally named "broom"). If no broom-type object exists, output the MISSING line and skip.

goto_coordinate = BROOM_COL, BROOM_ROW
pickup
sweep(ROW1_CELLS...)      # one call per row, all 20 columns left→right
sweep(ROW2_CELLS...)
...repeat for every row that has debris or was specified by the user
goto_coordinate = BROOM_COL, BROOM_ROW
keep                       # return broom to its original cell

## 2. Mop a Floor (after sweeping)

Requires a mop object. If none exists, output the MISSING line and skip. A2 has no fill/bucket-solution tracking — mop directly. If the same task also asks for sweeping, list that step first.

goto_coordinate = MOP_COL, MOP_ROW
pickup
mop(ROW1_CELLS...)         # one call per row
mop(ROW2_CELLS...)
...
goto_coordinate = MOP_COL, MOP_ROW
keep

## 3. Clean a Surface / Countertop (wipe)

goto_coordinate = CLOTH_COL, CLOTH_ROW
pickup
apply_cloth(CELL1, CELL2, ...)     # all the coordinates the object is touching
goto_coordinate = CLOTH_COL, CLOTH_ROW
keep

## 4. Cut / Slice Vegetables

Knife must be at the same cell as the target before slicing.

goto_coordinate = KNIFE_COL, KNIFE_ROW
pickup
goto_coordinate = VEG1_COL, VEG1_ROW
keep                        # knife now sits at the vegetable's cell
slice(VEG1_NAME, N)
pickup                      # pick the knife back up
goto_coordinate = VEG2_COL, VEG2_ROW
keep
slice(VEG2_NAME, N)
pickup
...repeat per vegetable
goto_coordinate = KNIFE_HOME_COL, KNIFE_HOME_ROW
keep                        # return knife to its original cell

## 5. Fold Laundry

fold() requires the robot positioned above the garment first. Fold only garments that are not already folded (check DESC).

goto_coordinate = GARMENT1_COL, GARMENT1_ROW
fold(GARMENT1_NAME)
goto_coordinate = GARMENT2_COL, GARMENT2_ROW
fold(GARMENT2_NAME)
...repeat per garment
# optionally stack folded garments: pickup → goto STACK_COL, STACK_ROW → keep

## 6. Open Appliance → Load → Close → Run

For any openable+switchable appliance (e.g. a washing machine, oven, box):

goto_coordinate = APPLIANCE_COL, APPLIANCE_ROW
open(APPLIANCE_NAME)
goto_coordinate = ITEM1_COL, ITEM1_ROW
pickup
goto_coordinate = APPLIANCE_COL, APPLIANCE_ROW
keep
...repeat per item to load
goto_coordinate = APPLIANCE_COL, APPLIANCE_ROW
close(APPLIANCE_NAME)
turn_on(APPLIANCE_NAME)
# always end the full task by turning appliances back off:
turn_off(APPLIANCE_NAME)

Note: this sequence is best-effort — the robot starts the appliance and moves on; it cannot verify the operation finished.

Washing machine + detergent: if a detergent object is present in the OBJECT LIST, add it after loading the laundry items and before close(APPLIANCE_NAME). Applies to washing machines only. If no detergent object is present, skip this step entirely — do not invent one.

goto_coordinate = DETERGENT_COL, DETERGENT_ROW
pickup
goto_coordinate = APPLIANCE_COL, APPLIANCE_ROW
pour            # or keep if the detergent is a pod/solid, not a liquid
goto_coordinate = DETERGENT_COL, DETERGENT_ROW
keep            # return the detergent bottle before continuing

## 7. Pour Liquid (bottle/jar → container)

goto_coordinate = SOURCE_COL, SOURCE_ROW
pickup
goto_coordinate = DEST_COL, DEST_ROW
pour
goto_coordinate = SOURCE_COL, SOURCE_ROW
keep

## 8. Collect / Stack Multiple Objects at One Cell

goto_coordinate = OBJECT1_COL, OBJECT1_ROW
pickup
goto_coordinate = TARGET_COL, TARGET_ROW
keep
goto_coordinate = OBJECT2_COL, OBJECT2_ROW
pickup
goto_coordinate = TARGET_COL, TARGET_ROW
keep
...repeat per object, finishing one object's move fully before starting the next

## 9. Tidy / Reset a Zone

Group same-category items together using pickup/keep only. Move objects into the zone one at a time, finishing each object's move before starting the next, then finish with a surface wipe. Do not move appliances during this step — only loose objects.

goto_coordinate = OBJECT1_COL, OBJECT1_ROW
pickup
goto_coordinate = ZONE_COL, ZONE_ROW
keep
goto_coordinate = OBJECT2_COL, OBJECT2_ROW
pickup
goto_coordinate = ZONE_COL, ZONE_ROW
keep                                                # repeat per object
apply_cloth(ZONE_CELLS...)                          # final wipe-down

## 10. Swap Two Objects' Positions

No holding-cell command exists, so route through a temporary free cell.

goto_coordinate = A_COL, A_ROW
pickup
goto_coordinate = TEMP_COL, TEMP_ROW
keep
goto_coordinate = B_COL, B_ROW
pickup
goto_coordinate = A_COL, A_ROW
keep
goto_coordinate = TEMP_COL, TEMP_ROW
pickup
goto_coordinate = B_COL, B_ROW
keep

## 11. Cook (stovetop, pot/pan)

Turn on the stove, move the pot onto it, load each solid ingredient into the pot with goto+keep, then pour in any liquid ingredient from a jar. Once cooking is done, plate the contents one item at a time only if a plate is present and plating was requested, then shut the stove off. There is no auto-eject — each item must be retrieved from the pot/pan individually.

goto_coordinate = STOVE_COL, STOVE_ROW
turn_on(STOVE_NAME)
goto_coordinate = POT_COL, POT_ROW
pickup
goto_coordinate = STOVE_COL, STOVE_ROW
keep                              # pot now sits on the stove
goto_coordinate = VEG1_COL, VEG1_ROW
pickup
goto_coordinate = STOVE_COL, STOVE_ROW
keep                              # ingredient placed into the pot
...repeat per ingredient
goto_coordinate = JAR_COL, JAR_ROW
pickup
goto_coordinate = STOVE_COL, STOVE_ROW
pour                              # pour liquid ingredient into the pot
goto_coordinate = JAR_COL, JAR_ROW
keep

Plating (only if a plate object is present in the OBJECT LIST and the user asked to plate/serve the food — otherwise skip this step entirely and go straight to shutdown):

goto_coordinate = PLATE_COL, PLATE_ROW
pickup
goto_coordinate = STOVE_COL, STOVE_ROW
keep                              # plate now sits at the stove cell
goto_coordinate = POT_COL, POT_ROW
pickup                            # picks up pot (or its contents, last-placed first)
goto_coordinate = TEMP_COL, TEMP_ROW
keep                              # set pot aside if it came up instead of an ingredient
goto_coordinate = POT_COL, POT_ROW
pickup                            # now pick up the ingredient
goto_coordinate = PLATE_COL, PLATE_ROW
keep
...repeat until all contents are plated

Shutdown (mandatory):

turn_off(STOVE_NAME)
goto_coordinate = POT_COL, POT_ROW
pickup
goto_coordinate = POT_HOME_COL, POT_HOME_ROW
keep                              # return pot to its original cell

---

## WORKED EXAMPLE — infeasible sub-task

OBJECT LIST contains only: sock (CENTER D7) and shirt (CENTER J3).
Task: "Sweep row 5, then stack all clothes at A10."

PLAN:
- sweep row 5: MISSING broom
- stack clothes: sock, shirt | after: holding nothing

# stack clothes at A10 (sweep skipped)
MISSING: broom — sub-task skipped
1. goto_coordinate = D, 7
2. pickup
3. goto_coordinate = A, 10
4. keep
5. goto_coordinate = J, 3
6. pickup
7. goto_coordinate = A, 10
8. keep
Task_Completed

---

## WORKED EXAMPLE — rotation mapping

OBJECT LIST contains: red pen (CENTER B2), blue pen (CENTER B5).
Task: "Swap them: red goes where blue is, blue goes where red was."

PLAN:
- swap pens via temp cell | after: holding nothing

DESTINATIONS:
- red pen → B5    (blue's current cell)
- blue pen → B2   (red's current cell)

# swap the pens
1. goto_coordinate = B, 2
2. pickup
3. goto_coordinate = T, 11
4. keep
5. goto_coordinate = B, 5
6. pickup
7. goto_coordinate = B, 2
8. keep
9. goto_coordinate = T, 11
10. pickup
11. goto_coordinate = B, 5
12. keep
Task_Completed

---

## OUTPUT FORMAT

First output a PLAN header, one line per sub-task, tracking held state:

PLAN:
- <sub-task>: <objects used> | after: holding nothing
(any missing required object → write its MISSING line instead)

For ANY task that moves, swaps, rotates, or repositions objects, the PLAN must
also include a DESTINATIONS block — this is REQUIRED, do not write any command
without it:

DESTINATIONS:
- <object> → <final cell>     (one line per moved object)

CHECK: "X goes where Y is" means X's final cell is Y's CURRENT cell (Y's CENTER
in the OBJECT LIST). It does NOT mean Y moves to X's cell. Verify every
DESTINATIONS line against this rule before writing commands.

Then the commands:

# brief task description
1. command
2. command
...
Task_Completed

Strict: numbered lines contain ONLY commands. No Markdown, no JSON, no explanations, no confidence scores. Task_Completed is always the final line.
"""
)


# ─────────────────────────────────────────────────────────────────────────────
#  Vision worker  (BBOX system: VLM returns boxes on the CLEAN image,
#  Python computes CENTER/TOUCHES deterministically, emits the same
#  OBJECT-line string format the sidebar and planner already consume.)
# ─────────────────────────────────────────────────────────────────────────────
class VisionWorker(QThread):
    done  = Signal(str)
    boxes = Signal(list)   # raw parsed objects (with 'box') for on-screen drawing
    error = Signal(str)

    def __init__(self, bgr):
        super().__init__()
        self._bgr = bgr

    def run(self):
        try:
            # Clean image — no grid overlay needed; cells are computed in Python.
            ret, buf = cv2.imencode(".jpg", self._bgr, [cv2.IMWRITE_JPEG_QUALITY, 95])
            if not ret:
                self.error.emit("Frame encode failed"); return
            b64 = base64.b64encode(buf.tobytes()).decode()
            client = OpenAI(api_key=OPENAI_API_KEY)
            resp = client.chat.completions.create(
                model="gpt-5.4",
                messages=[{"role": "user", "content": [
                    {"type": "text",      "text": VISION_PROMPT},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{b64}", "detail": "high"}},
                ]}],
                max_completion_tokens=3000,
            )
            raw = (resp.choices[0].message.content or "").strip()
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as e:
                self.error.emit(
                    f"Vision model returned invalid JSON: {e}\n\nRaw output:\n{raw[:800]}")
                return

            lines = []
            for obj in data.get("objects", []):
                center, touches = bbox_to_cells(obj.get("box"))
                if center is None:
                    continue   # degenerate box — skip
                touch_str = ",".join(cell_name(t) for t in touches)
                aka = ", ".join(obj.get("aka", []))
                lines.append(
                    f"OBJECT: {obj.get('name','object')}  "
                    f"CENTER: {cell_name(center)}  "
                    f"TOUCHES: {touch_str}  "
                    f"COLOR: {obj.get('color','?')}  "
                    f"SIZE: {obj.get('size','?')}  "
                    f"DESC: {obj.get('desc','')}  "
                    f"ALSO_KNOWN_AS: {aka}"
                )
            if not lines:
                self.error.emit("Vision returned no usable objects.")
                return
            self.boxes.emit(data.get("objects", []))
            self.done.emit("\n".join(lines))
        except Exception as e:
            self.error.emit(str(e))


# ─────────────────────────────────────────────────────────────────────────────
#  Command worker  (planner → numbered command sequence, streamed)
# ─────────────────────────────────────────────────────────────────────────────
class CommandWorker(QThread):
    chunk = Signal(str)
    done  = Signal(str)
    error = Signal(str)

    def __init__(self, object_list: str, task: str):
        super().__init__()
        self._objects = object_list
        self._task    = task

    def run(self):
        try:
            client = OpenAI(api_key=OPENAI_API_KEY)
            user_msg = (
                f"OBJECT LIST:\n{self._objects}\n\n"
                f"Task: {self._task}"
            )
            print("=== PLANNER INPUT ===")
            print(user_msg)
            print("=== END ===")
            stream = client.chat.completions.create(
                model="gpt-5.4",
                messages=[
                    {"role": "system", "content": A2_SYSTEM},
                    {"role": "user",   "content": user_msg},
                ],
                max_completion_tokens=4500,
                stream=True,
            )
            full = ""
            for ch in stream:
                delta = ch.choices[0].delta.content or ""
                full += delta
                self.chunk.emit(delta)
            self.done.emit(full)
        except Exception as e:
            self.error.emit(str(e))


# ─────────────────────────────────────────────────────────────────────────────
#  GridOverlay  –  transparent widget drawn on top of the camera video
# ─────────────────────────────────────────────────────────────────────────────
class GridOverlay(QWidget):
    """
    A fully transparent QWidget that paints an animated robot-cursor dot.

    The dot:
      • Smoothly interpolates toward its target cell at 60 fps.
      • Has a pulsing outer ring and a radial glow.
      • Changes colour per A2 command (green = pickup, yellow = keep, …).
      • Draws the current cell name (e.g. "F3") above itself.
      • Shows a coloured status-pill at the bottom of the video frame.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Where the image currently sits inside this widget (letterbox rect).
        # None = no image loaded → draw placeholder grid over the full widget.
        self._img_rect: 'QRectF | None' = None
        self._bboxes  : list = []   # detected objects with normalized 'box' [x0,y0,x1,y1]

        self._cur_col: float = 0.0
        self._cur_row: float = 0.0
        self._tgt_col: float = 0.0
        self._tgt_row: float = 0.0

        self._dot_color  = QColor('#60a5fa')
        self._status_txt = ''
        self._cell_lbl   = 'A2'
        self._visible    = False
        self._pulse      = 0.0

        self._anim = QTimer(self)
        self._anim.setInterval(16)
        self._anim.timeout.connect(self._tick)
        self._anim.start()

    def set_image_rect(self, rect: 'QRectF | None'):
        """Called by CameraPanel whenever the image letterbox position changes."""
        self._img_rect = rect
        self.update()

    def set_bboxes(self, objects: list):
        """Store detected objects (normalized 0-1000 boxes) to draw over the image."""
        self._bboxes = objects or []
        self.update()

    def set_image_size(self, w: int, h: int):
        pass

    # ── public API ────────────────────────────────────────────────────────────
    def show_dot(self, col: int = 0, row: int = 0):
        self._cur_col = self._tgt_col = float(col)
        self._cur_row = self._tgt_row = float(row)
        self._cell_lbl = f'{chr(ord("A") + col)}{row + 1}'
        self._visible  = True
        self.update()

    def hide_dot(self):
        self._visible    = False
        self._status_txt = ''
        self.update()

    def set_target(self, col: int, row: int):
        """Called by CommandRunner to move the dot to a new grid cell."""
        self._tgt_col  = float(max(0, min(COLS - 1, col)))
        self._tgt_row  = float(max(0, min(ROWS - 1, row)))
        self._cell_lbl = f'{chr(ord("A") + col)}{row + 1}'

    def set_state(self, color_hex: str, text: str):
        """Change dot colour and status text for the current command."""
        self._dot_color  = QColor(color_hex)
        self._status_txt = text
        self.update()

    # ── animation tick ────────────────────────────────────────────────────────
    def _tick(self):
        if self._visible:
            speed = 0.10
            dc = self._tgt_col - self._cur_col
            dr = self._tgt_row - self._cur_row
            if abs(dc) > 0.005 or abs(dr) > 0.005:
                self._cur_col += dc * speed
                self._cur_row += dr * speed
            else:
                self._cur_col = self._tgt_col
                self._cur_row = self._tgt_row
            self._pulse = (self._pulse + 0.09) % (2 * math.pi)
        self.update()   # always repaint — grid is always drawn

    # ── coordinate helpers ────────────────────────────────────────────────────
    def _grid_area(self) -> QRectF:
        """Return the rect the grid is drawn in: image area if loaded, else full widget."""
        if self._img_rect is not None:
            return self._img_rect
        return QRectF(0, 0, float(self.width()), float(self.height()))

    def _cell_rect(self, col: float, row: float) -> QRectF:
        area = self._grid_area()
        ci   = int(round(col))
        ri   = int(round(row))
        x0   = area.x() + ci       * area.width()  / COLS
        y0   = area.y() + ri       * area.height() / ROWS
        x1   = area.x() + (ci + 1) * area.width()  / COLS
        y1   = area.y() + (ri + 1) * area.height() / ROWS
        return QRectF(x0, y0, x1 - x0, y1 - y0)

    def _to_px(self, col: float, row: float):
        r = self._cell_rect(col, row)
        return r.center().x(), r.center().y()

    # ── painting ──────────────────────────────────────────────────────────────
    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)   # grid lines look crisper

        # ── always draw the red grid ──────────────────────────────────────────
        self._paint_grid(painter)

        # ── detected bounding boxes (after analysis) ──────────────────────────
        if self._bboxes:
            painter.setRenderHint(QPainter.Antialiasing, True)
            self._paint_bboxes(painter)
            painter.setRenderHint(QPainter.Antialiasing, False)

        # ── cell highlight (only while playback is active) ────────────────────
        if self._visible:
            painter.setRenderHint(QPainter.Antialiasing, True)
            self._paint_highlight(painter)
            if self._status_txt:
                self._draw_status_pill(painter)

    def _paint_grid(self, painter: QPainter):
        """Draw the bright-red A2→T11 grid inside the image area (or full widget if no image)."""
        area = self._grid_area()
        gx, gy, gw, gh = area.x(), area.y(), area.width(), area.height()
        if gw == 0 or gh == 0:
            return

        RED         = QColor(255, 30, 30, 220)
        RED_BRIGHT  = QColor(255, 90, 90, 255)
        font        = QFont('Segoe UI', 9, QFont.Bold)
        painter.setFont(font)
        fm          = painter.fontMetrics()

        painter.setPen(QPen(RED, 1))
        for i in range(COLS + 1):
            x = round(gx + i * gw / COLS)
            painter.drawLine(x, round(gy), x, round(gy + gh))
        for j in range(ROWS + 1):
            y = round(gy + j * gh / ROWS)
            painter.drawLine(round(gx), y, round(gx + gw), y)

        cw = gw / COLS
        rh = gh / ROWS

        # Per-cell coordinate label in each cell's top-left corner
        cell_font = QFont('Segoe UI', 13, QFont.Bold)
        painter.setFont(cell_font)
        cfm2 = painter.fontMetrics()
        painter.setPen(QColor(255, 30, 30, 160))
        for i in range(COLS):
            for j in range(ROWS):
                lbl = f'{COL_LABELS[i]}{ROW_LABELS[j]}'
                cx  = round(gx + i * cw + 2)
                cy  = round(gy + j * rh + cfm2.ascent() + 1)
                painter.drawText(cx, cy, lbl)

    # Distinct colors cycled per detected object
    BBOX_COLORS = [
        QColor(34, 197, 94),  QColor(59, 130, 246), QColor(245, 158, 11),
        QColor(168, 85, 247), QColor(236, 72, 153), QColor(20, 184, 166),
        QColor(249, 115, 22), QColor(99, 102, 241),
    ]

    def _paint_bboxes(self, painter: QPainter):
        """Draw each detected object's bounding box + name/CENTER label,
        mapping normalized 0-1000 coords onto the image letterbox area."""
        area = self._grid_area()
        gx, gy, gw, gh = area.x(), area.y(), area.width(), area.height()
        if gw == 0 or gh == 0:
            return
        font = QFont('Segoe UI', 9, QFont.Bold)
        painter.setFont(font)
        fm = painter.fontMetrics()

        for idx, obj in enumerate(self._bboxes):
            box = obj.get('box')
            if not (isinstance(box, list) and len(box) == 4):
                continue
            try:
                x0, y0, x1, y1 = [max(0.0, min(1000.0, float(v))) for v in box]
            except (TypeError, ValueError):
                continue
            if x1 <= x0 or y1 <= y0:
                continue

            color = self.BBOX_COLORS[idx % len(self.BBOX_COLORS)]
            rx0 = gx + x0 / 1000.0 * gw
            ry0 = gy + y0 / 1000.0 * gh
            rx1 = gx + x1 / 1000.0 * gw
            ry1 = gy + y1 / 1000.0 * gh
            rect = QRectF(rx0, ry0, rx1 - rx0, ry1 - ry0)

            # Faint fill + solid border
            fill = QColor(color); fill.setAlpha(30)
            painter.setBrush(QBrush(fill))
            painter.setPen(QPen(color, 2))
            painter.drawRect(rect)

            # Label: "name @ CENTER" on a pill above the box
            center, _ = bbox_to_cells(box)
            lbl = obj.get('name', 'object')
            if center is not None:
                lbl += f"  @ {cell_name(center)}"
            tw = fm.horizontalAdvance(lbl)
            th = fm.height()
            lx = rx0
            ly = max(gy, ry0 - th - 4)
            bg = QColor(255, 255, 255, 215)
            painter.setBrush(QBrush(bg))
            painter.setPen(QPen(color, 1))
            painter.drawRoundedRect(QRectF(lx, ly, tw + 10, th + 4), 4, 4)
            painter.setPen(color)
            painter.drawText(QPointF(lx + 5, ly + 2 + fm.ascent()), lbl)

    def _paint_highlight(self, painter: QPainter):
        area   = self._grid_area()
        # Compute pixel position by interpolating directly on the fractional col/row
        px = area.x() + (self._cur_col + 0.5) * area.width()  / COLS
        py = area.y() + (self._cur_row + 0.5) * area.height() / ROWS

        cell_w = area.width()  / COLS
        cell_h = area.height() / ROWS
        r      = min(cell_w, cell_h) * 0.42   # slightly larger dot

        color  = self._dot_color
        pulse  = math.sin(self._pulse)

        # Outer glow ring
        glow_r = r * (1.9 + 0.25 * pulse)
        grad   = QRadialGradient(px, py, glow_r)
        glow_c = QColor(color); glow_c.setAlpha(int(60 + 30 * pulse))
        grad.setColorAt(0.0, glow_c)
        grad.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 0))
        painter.setBrush(QBrush(grad)); painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(px, py), glow_r, glow_r)

        # Main filled dot
        dot_c = QColor(color); dot_c.setAlpha(220)
        painter.setBrush(QBrush(dot_c)); painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(px, py), r, r)

        # Bright centre highlight
        hi_r = r * 0.38
        hi_c = QColor(255, 255, 255, int(160 + 60 * pulse))
        painter.setBrush(QBrush(hi_c)); painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(px - r * 0.18, py - r * 0.18), hi_r, hi_r)

        # Cell label just below the dot
        if self._cell_lbl:
            font = QFont('Segoe UI', 9, QFont.Bold)
            painter.setFont(font)
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(self._cell_lbl)
            tx = px - tw / 2
            ty = py + r + fm.ascent() + 2
            painter.setPen(QColor(0, 0, 0, 140))
            painter.drawText(QPointF(tx + 1, ty + 1), self._cell_lbl)
            painter.setPen(color)
            painter.drawText(QPointF(tx, ty), self._cell_lbl)

    def _draw_status_pill(self, painter: QPainter):
        w, h  = self.width(), self.height()
        font  = QFont('Segoe UI Semibold', 11)
        painter.setFont(font)
        fm    = painter.fontMetrics()
        tw    = fm.horizontalAdvance(self._status_txt)
        pad_x, pad_y = 18, 7
        bar_w = tw + pad_x * 2
        bar_h = fm.height() + pad_y * 2
        bx    = (w - bar_w) / 2.0
        by    = h - bar_h - 18.0
        rect  = QRectF(bx, by, bar_w, bar_h)

        # Light semi-transparent background
        painter.setBrush(QBrush(QColor(255, 255, 255, 220)))
        border_c = QColor(self._dot_color)
        border_c.setAlpha(200)
        painter.setPen(QPen(border_c, 1.5))
        painter.drawRoundedRect(rect, bar_h / 2, bar_h / 2)

        # Text
        painter.setPen(self._dot_color)
        painter.drawText(QPointF(bx + pad_x, by + pad_y + fm.ascent()),
                         self._status_txt)


# ─────────────────────────────────────────────────────────────────────────────
#  CommandRunner  –  parses A2 command text and drives GridOverlay step-by-step
# ─────────────────────────────────────────────────────────────────────────────
class CommandRunner(QObject):
    """
    Parses the numbered A2 command sequence and replays it with timed delays.

    Signals
    -------
    move_to(col, row)       → GridOverlay.set_target
    state_changed(hex, txt) → GridOverlay.set_state
    show_dot(col, row)      → GridOverlay.show_dot
    hide_dot()              → GridOverlay.hide_dot
    step_info(cur, tot, cmd)→ sidebar step label
    finished()              → sidebar play-button re-enable
    """

    move_to       = Signal(int, int)
    state_changed = Signal(str, str)
    show_dot      = Signal(int, int)
    hide_dot      = Signal()
    step_info     = Signal(int, int, str)
    finished      = Signal()

    # Milliseconds each command type dwells before the next one fires
    DELAY = {
        'goto':               1300,
        'pickup':              950,
        'keep':                950,
        'drag':               1800,
        'rotate':              900,
        'change_orientation': 1100,
        'inspect_sides':      1200,
        'pour':               1300,
        'sweep':              1500,
        'mop':                1500,
        'scrub':              1300,
        'apply_soap':          900,
        'apply_cloth':         900,
        'cook':               2000,
        'wash':               1300,
        'iron':               1300,
        'fold':               1100,
        'open':                800,
        'close':               800,
        'turn_on':             800,
        'turn_off':            800,
        'run_cycle':          1600,
        'slice':              1100,
        'fill':               1300,
        'clean_bathroom':     2200,
        'tidy_up':            1500,
        'dust_surfaces':      1200,
        'find':               1000,
        'set_state':           600,
        'check_state':         600,
        'default':             700,
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cmds    : list[str] = []
        self._idx     : int       = 0
        self._running : bool      = False
        self._timer   = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._step)

    # ── public API ────────────────────────────────────────────────────────────
    def load(self, text: str):
        self._cmds   = self._parse(text)
        self._idx    = 0
        self._running = False

    def start(self):
        if not self._cmds:
            return
        self._running = True
        self._idx     = 0
        self.show_dot.emit(0, 0)
        QTimer.singleShot(250, self._step)

    def stop(self):
        self._running = False
        self._timer.stop()

    # ── cell-list visitor (for sweep / mop / scrub / apply_* commands) ────────
    def _visit_cells(self, cells: list, delay_ms: int):
        """Move dot through each cell then fire the next command step."""
        if not cells or not self._running:
            if self._running:
                self._step()
            return
        col, row = cells[0]
        self.move_to.emit(col, row)
        remaining = cells[1:]
        QTimer.singleShot(
            delay_ms,
            lambda: self._visit_cells(remaining, delay_ms) if self._running else None,
        )

    @staticmethod
    def _parse_cells(raw: str) -> list:
        """Extract (col, row) pairs from a command like Apply_cloth(A2,B2,C3)."""
        m = re.search(r'\(([^)]+)\)', raw)
        if not m:
            return []
        cells = []
        for token in m.group(1).split(','):
            cm = re.match(r'\s*([A-Ta-t])(\d+)\s*', token.strip())
            if cm:
                col = ord(cm.group(1).upper()) - ord('A')
                row = int(cm.group(2)) - 1
                col = max(0, min(COLS - 1, col))
                row = max(0, min(ROWS - 1, row))
                cells.append((col, row))
        return cells

    # ── parsing ───────────────────────────────────────────────────────────────
    @staticmethod
    def _parse(text: str) -> list[str]:
        cmds = []
        started = False
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if not started:
                if re.match(r'^(\d+\.|#)', line):
                    started = True
                else:
                    continue   # skip PLAN / DESTINATIONS / CHECK preamble
            if line.startswith('#') or line.upper().startswith('MISSING:'):
                continue       # titles and MISSING lines aren't executable
            line = re.sub(r'^\d+\.\s*', '', line)   # strip "12. "
            if line:
                cmds.append(line)
        return cmds

    # ── execution loop ────────────────────────────────────────────────────────
    def _step(self):
        if not self._running or self._idx >= len(self._cmds):
            return
        cmd   = self._cmds[self._idx]
        self._idx += 1
        self.step_info.emit(self._idx, len(self._cmds), cmd)
        delay = self._dispatch(cmd)
        if self._running and delay > 0:
            self._timer.start(delay)

    def _dispatch(self, cmd: str) -> int:
        """Execute one command; return the dwell time in ms."""
        raw = cmd.strip()

        # ── goto_coordinate: tolerate fused/split coords, optional '=' and ',' ──
        m = re.match(
            r'goto_coordinate\s*[:=]?\s*([A-Ta-t])\s*,?\s*(\d{1,2})\b',
            raw,
            re.IGNORECASE,
        )
        if m:
            col = ord(m.group(1).upper()) - ord('A')
            row = int(m.group(2)) - 1
            col = max(0, min(COLS - 1, col))
            row = max(0, min(ROWS - 1, row))
            self.move_to.emit(col, row)
            self.state_changed.emit(*CMD_STATES['goto'])
            return self.DELAY['goto']
        if raw.lower().startswith('goto_coordinate'):
            print(f"[CommandRunner] Unparsed goto_coordinate command: {raw!r}")

        lc = raw.lower().split('(')[0].strip()   # base keyword, no args

        if lc == 'pickup':
            self.state_changed.emit(*CMD_STATES['pickup'])
            return self.DELAY['pickup']

        if lc == 'keep':
            self.state_changed.emit(*CMD_STATES['keep'])
            return self.DELAY['keep']

        if lc == 'pour':
            self.state_changed.emit(*CMD_STATES['pour'])
            return self.DELAY['pour']

        if lc == 'sweep':
            self.state_changed.emit(*CMD_STATES['sweep'])
            cells = self._parse_cells(raw)
            if cells:
                self._visit_cells(cells, self.DELAY['sweep'])
                return 0
            return self.DELAY['sweep']

        if lc == 'mop':
            self.state_changed.emit(*CMD_STATES['mop'])
            cells = self._parse_cells(raw)
            if cells:
                self._visit_cells(cells, self.DELAY['mop'])
                return 0
            return self.DELAY['mop']

        if lc == 'scrub':
            self.state_changed.emit(*CMD_STATES['scrub'])
            cells = self._parse_cells(raw)
            if cells:
                self._visit_cells(cells, self.DELAY['scrub'])
                return 0
            return self.DELAY['scrub']

        if lc == 'apply_soap':
            self.state_changed.emit(*CMD_STATES['apply_soap'])
            cells = self._parse_cells(raw)
            if cells:
                self._visit_cells(cells, self.DELAY['apply_soap'])
                return 0
            return self.DELAY['apply_soap']

        if lc == 'apply_cloth':
            self.state_changed.emit(*CMD_STATES['apply_cloth'])
            cells = self._parse_cells(raw)
            if cells:
                self._visit_cells(cells, self.DELAY['apply_cloth'])
                return 0
            return self.DELAY['apply_cloth']

        if lc.startswith('wash'):
            self.state_changed.emit(*CMD_STATES['wash'])
            return self.DELAY['wash']

        if lc == 'iron':
            self.state_changed.emit(*CMD_STATES['iron'])
            return self.DELAY['iron']

        if lc == 'fold':
            self.state_changed.emit(*CMD_STATES['fold'])
            return self.DELAY['fold']

        if lc.startswith('open'):
            self.state_changed.emit(*CMD_STATES['open'])
            return self.DELAY['open']

        if lc.startswith('close'):
            self.state_changed.emit(*CMD_STATES['close'])
            return self.DELAY['close']

        if lc.startswith('turn_on'):
            self.state_changed.emit(*CMD_STATES['turn_on'])
            return self.DELAY['turn_on']

        if lc.startswith('turn_off'):
            self.state_changed.emit(*CMD_STATES['turn_off'])
            return self.DELAY['turn_off']

        if lc.startswith('run_cycle'):
            self.state_changed.emit(*CMD_STATES['run_cycle'])
            return self.DELAY['run_cycle']

        if lc.startswith('slice'):
            self.state_changed.emit(*CMD_STATES['slice'])
            return self.DELAY['slice']

        if lc.startswith('fill'):
            self.state_changed.emit(*CMD_STATES['fill'])
            return self.DELAY['fill']

        if lc.startswith('drag'):
            self.state_changed.emit(*CMD_STATES['drag'])
            # drag(NAME, COL, ROW) — move dot to destination cell if parseable
            m2 = re.search(r'drag\s*\(\s*\w+\s*,\s*([A-Ta-t])\s*,\s*(\d+)\s*\)', raw, re.IGNORECASE)
            if m2:
                col = ord(m2.group(1).upper()) - ord('A')
                row = int(m2.group(2)) - 1
                self.move_to.emit(max(0, min(COLS-1, col)), max(0, min(ROWS-1, row)))
            return self.DELAY['drag']

        if lc.startswith('rotate'):
            self.state_changed.emit(*CMD_STATES['rotate'])
            return self.DELAY['rotate']

        if lc.startswith('change_orientation'):
            self.state_changed.emit(*CMD_STATES['change_orientation'])
            return self.DELAY['change_orientation']

        if lc.startswith('inspect_sides'):
            self.state_changed.emit(*CMD_STATES['inspect_sides'])
            return self.DELAY['inspect_sides']

        if lc.startswith('cook'):
            self.state_changed.emit(*CMD_STATES['cook'])
            return self.DELAY['cook']

        if lc.startswith('clean_bathroom'):
            self.state_changed.emit(*CMD_STATES['clean_bathroom'])
            cells = self._parse_cells(raw)
            if cells:
                self._visit_cells(cells, self.DELAY['scrub'])
                return 0
            return self.DELAY['clean_bathroom']

        if lc.startswith('tidy_up'):
            self.state_changed.emit(*CMD_STATES['tidy_up'])
            cells = self._parse_cells(raw)
            if cells:
                self._visit_cells(cells, self.DELAY['apply_cloth'])
                return 0
            return self.DELAY['tidy_up']

        if lc.startswith('dust_surfaces'):
            self.state_changed.emit(*CMD_STATES['dust_surfaces'])
            cells = self._parse_cells(raw)
            if cells:
                self._visit_cells(cells, self.DELAY['apply_cloth'])
                return 0
            return self.DELAY['dust_surfaces']

        if lc.startswith('find'):
            self.state_changed.emit(*CMD_STATES['find'])
            return self.DELAY['find']

        if lc.startswith('wait_for'):
            m2   = re.search(r'(\d+(?:\.\d+)?)', raw)
            secs = float(m2.group(1)) if m2 else 2.0
            self.state_changed.emit(*CMD_STATES['wait_for'])
            return int(secs * 1000)

        if lc.startswith('set_state'):
            self.state_changed.emit(*CMD_STATES['set_state'])
            return self.DELAY['set_state']

        if lc.startswith('check_state'):
            self.state_changed.emit(*CMD_STATES['check_state'])
            return self.DELAY['check_state']

        if lc == 'task_completed':
            self.state_changed.emit(*CMD_STATES['complete'])
            self._running = False
            # Hide dot and notify after a short display pause
            QTimer.singleShot(2500, lambda: self.hide_dot.emit())
            QTimer.singleShot(2500, lambda: self.finished.emit())
            return 0

        # Unknown command – log it so silent drops are visible, then pause and continue
        print(f"[CommandRunner] Unparsed command (no handler matched): {raw!r}")
        return self.DELAY['default']


# ─────────────────────────────────────────────────────────────────────────────
#  VideoLabel  –  QLabel that always keeps a child overlay the same size
# ─────────────────────────────────────────────────────────────────────────────
class VideoLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._overlay: GridOverlay | None = None

    def attach_overlay(self, overlay: GridOverlay):
        self._overlay = overlay
        self._overlay.setParent(self)
        self._overlay.resize(self.size())
        self._overlay.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._overlay:
            self._overlay.resize(self.size())
            self._overlay.raise_()


# ─────────────────────────────────────────────────────────────────────────────
#  Divider helper
# ─────────────────────────────────────────────────────────────────────────────
def _divider():
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setStyleSheet("color:#d0d4de;")
    return line


# ─────────────────────────────────────────────────────────────────────────────
#  AI Sidebar
# ─────────────────────────────────────────────────────────────────────────────
class AISidebar(QWidget):
    request_frame    = Signal()
    request_unfreeze = Signal()
    play_commands    = Signal(str)   # text → CameraPanel.run_commands
    stop_commands    = Signal()      # → CameraPanel.stop_commands
    boxes_ready      = Signal(list)  # detected bboxes → CameraPanel overlay

    def __init__(self, parent=None):
        super().__init__(parent)
        self._object_list    = ""
        self._vision_worker  : VisionWorker  | None = None
        self._command_worker : CommandWorker | None = None
        self.setMinimumWidth(360)
        self.setMaximumWidth(460)
        self.setStyleSheet("background:#f0f2f7;")
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        hdr = QWidget(); hdr.setFixedHeight(54)
        hdr.setStyleSheet("background:#e8eaf0;border-bottom:1px solid #d0d4de;")
        hl = QHBoxLayout(hdr); hl.setContentsMargins(14, 0, 14, 0); hl.setSpacing(8)
        ico = QLabel("🤖"); ico.setFont(QFont("Segoe UI", 17))
        ttl = QLabel("ProLabs  ·  Vision A2")
        ttl.setFont(QFont("Segoe UI Semibold", 11))
        ttl.setStyleSheet("color:#1A2a2e;")
        sub = QLabel("BBox Vision")
        sub.setFont(QFont("Segoe UI", 9))
        sub.setStyleSheet("color:#2563eb;")
        hl.addWidget(ico); hl.addWidget(ttl); hl.addWidget(sub); hl.addStretch()
        root.addWidget(hdr)

        # Scrollable body
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea{border:none;background:transparent;}
            QScrollBar:vertical{background:#e0e2ea;width:5px;margin:0;}
            QScrollBar::handle:vertical{background:#b0b4c0;border-radius:2px;}
        """)
        body = QWidget(); body.setStyleSheet("background:transparent;")
        bl = QVBoxLayout(body); bl.setContentsMargins(12, 14, 12, 14); bl.setSpacing(10)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # ── STEP 1: Capture ───────────────────────────────────────────────────
        bl.addWidget(self._sec("STEP 1  ·  Analyse Imported Image"))

        self._capture_btn = QPushButton("🔍   ANALYSE IMAGE")
        self._capture_btn.setFixedHeight(42)
        self._capture_btn.setCursor(Qt.PointingHandCursor)
        self._capture_btn.setStyleSheet("""
            QPushButton{background:#1e6fcc;color:#fff;border-radius:10px;
                        font-family:'Segoe UI';font-weight:700;font-size:12px;border:none;}
            QPushButton:hover{background:#2a7fe0;}
            QPushButton:pressed{background:#1558b0;}
            QPushButton:disabled{background:#e2e8f0;color:#9ca3af;}
        """)
        self._capture_btn.clicked.connect(self._on_capture)
        bl.addWidget(self._capture_btn)

        bl.addWidget(_divider())

        # ── STEP 2: Task ──────────────────────────────────────────────────────
        bl.addWidget(self._sec("STEP 2  ·  Describe Your Task"))

        self._task_input = QPlainTextEdit()
        self._task_input.setPlaceholderText(
            "Examples:\n"
            "  Pick up the bottle and place it at A2\n"
            "  Move every object in column H to column A\n"
            "  Collect all items and stack them at T11")
        self._task_input.setFont(QFont("Segoe UI", 10))
        self._task_input.setFixedHeight(88)
        self._task_input.setStyleSheet("""
            QPlainTextEdit{background:#ffffff;color:#1A2a2e;
                           border:1px solid #d0d4de;border-radius:10px;padding:8px;}
            QPlainTextEdit:focus{border-color:#3b82f6;}
        """)
        bl.addWidget(self._task_input)

        self._run_btn = QPushButton("⚡   ANALYSE  +  GENERATE COMMANDS")
        self._run_btn.setFixedHeight(42)
        self._run_btn.setCursor(Qt.PointingHandCursor)
        self._run_btn.setStyleSheet("""
            QPushButton{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                            stop:0 #16a34a,stop:1 #15803d);
                        color:#fff;border-radius:10px;
                        font-family:'Segoe UI';font-weight:700;font-size:12px;border:none;}
            QPushButton:hover{background:#22c55e;color:#000;}
            QPushButton:pressed{background:#14532d;}
            QPushButton:disabled{background:#e2e8f0;color:#9ca3af;}
        """)
        self._run_btn.setEnabled(False)
        self._run_btn.clicked.connect(self._on_run)
        bl.addWidget(self._run_btn)

        # Stage label
        self._stage_lbl = QLabel("")
        self._stage_lbl.setAlignment(Qt.AlignCenter)
        self._stage_lbl.setFont(QFont("Segoe UI", 9))
        self._stage_lbl.setStyleSheet("color:#2563eb;padding:2px 0;")
        self._stage_lbl.setVisible(False)
        bl.addWidget(self._stage_lbl)

        bl.addWidget(_divider())

        # ── Object list output ────────────────────────────────────────────────
        bl.addWidget(self._sec("DETECTED OBJECTS  (BBox → Python cells)"))

        self._scene_box = QTextEdit()
        self._scene_box.setReadOnly(True)
        self._scene_box.setFixedHeight(320)
        self._scene_box.setStyleSheet("""
            QTextEdit{background:#f8fafc;color:#374151;
                      border:1px solid #d0d4de;border-radius:8px;padding:6px;}
            QScrollBar:vertical{background:#e0e2ea;width:5px;margin:0;}
            QScrollBar::handle:vertical{background:#b0b4c0;border-radius:2px;}
        """)
        self._scene_box.setPlaceholderText("Detected objects will appear here after analysis…")
        bl.addWidget(self._scene_box)

        bl.addWidget(_divider())

        # ── Commands output ───────────────────────────────────────────────────
        bl.addWidget(self._sec("A2 EXECUTION COMMANDS"))

        self._cmd_box = QPlainTextEdit()
        self._cmd_box.setReadOnly(True)
        self._cmd_box.setFont(QFont("Consolas", 10))
        self._cmd_box.setFixedHeight(210)
        self._cmd_box.setStyleSheet("""
            QPlainTextEdit{background:#f0fdf4;color:#166534;
                           border:1px solid #86efac;border-radius:8px;padding:5px;}
        """)
        self._cmd_box.setPlaceholderText("Numbered command sequence will stream here…")
        bl.addWidget(self._cmd_box)

        # Copy / Clear row
        copy_row = QHBoxLayout(); copy_row.setSpacing(8)
        copy_btn  = self._mini_btn("📋  Copy",  "#f0fdf4", "#166534", "#86efac")
        clear_btn = self._mini_btn("🗑️  Clear", "#fff1f2", "#dc2626", "#fca5a5")
        copy_btn.clicked.connect(
            lambda: QApplication.clipboard().setText(self._cmd_box.toPlainText()))
        clear_btn.clicked.connect(self._clear_all)
        copy_row.addWidget(copy_btn)
        copy_row.addWidget(clear_btn)
        bl.addLayout(copy_row)

        bl.addWidget(_divider())

        # ── ▶ PLAY / ■ STOP row ───────────────────────────────────────────────
        bl.addWidget(self._sec("STEP 3  ·  Play on Grid"))

        play_row = QHBoxLayout(); play_row.setSpacing(8)

        self._play_btn = QPushButton("▶  PLAY COMMANDS")
        self._play_btn.setFixedHeight(38)
        self._play_btn.setEnabled(False)
        self._play_btn.setCursor(Qt.PointingHandCursor)
        self._play_btn.setStyleSheet("""
            QPushButton{background:#dbeafe;color:#1d4ed8;
                        border:1px solid #93c5fd;border-radius:9px;
                        font-family:'Segoe UI';font-weight:700;font-size:11px;}
            QPushButton:hover{background:#2563eb;color:#fff;}
            QPushButton:pressed{background:#1e3a8a;}
            QPushButton:disabled{background:#f1f5f9;color:#9ca3af;border-color:#d0d4de;}
        """)
        self._play_btn.clicked.connect(self._on_play)

        self._stop_btn = QPushButton("■  STOP")
        self._stop_btn.setFixedWidth(72)
        self._stop_btn.setFixedHeight(38)
        self._stop_btn.setEnabled(False)
        self._stop_btn.setCursor(Qt.PointingHandCursor)
        self._stop_btn.setStyleSheet("""
            QPushButton{background:#fee2e2;color:#dc2626;
                        border:1px solid #fca5a5;border-radius:9px;
                        font-family:'Segoe UI';font-weight:700;font-size:11px;}
            QPushButton:hover{background:#dc2626;color:#fff;}
            QPushButton:pressed{background:#7f1d1d;}
            QPushButton:disabled{background:#f1f5f9;color:#9ca3af;border-color:#d0d4de;}
        """)
        self._stop_btn.clicked.connect(self._on_stop)

        play_row.addWidget(self._play_btn, 1)
        play_row.addWidget(self._stop_btn)
        bl.addLayout(play_row)

        # Step progress label
        self._step_lbl = QLabel("")
        self._step_lbl.setAlignment(Qt.AlignCenter)
        self._step_lbl.setFont(QFont("Segoe UI", 8))
        self._step_lbl.setStyleSheet("color:#6b7280;padding:2px 0;")
        bl.addWidget(self._step_lbl)

        # ── Colour legend ─────────────────────────────────────────────────────
        bl.addWidget(_divider())
        bl.addWidget(self._sec("HIGHLIGHT COLOUR LEGEND"))
        bl.addWidget(self._legend())
        bl.addStretch()

    # ── legend widget ─────────────────────────────────────────────────────────
    @staticmethod
    def _legend():
        w   = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(3)
        entries = [
            ('#60a5fa', 'goto_coordinate – Moving'),
            ('#22c55e', 'pickup          – Picking up'),
            ('#facc15', 'keep            – Placing'),
            ('#22d3ee', 'pour            – Pouring'),
            ('#fb923c', 'sweep           – Sweeping'),
            ('#7dd3fc', 'mop             – Mopping'),
            ('#f87171', 'iron            – Ironing'),
            ('#c084fc', 'fold            – Folding'),
            ('#ffd700', 'Task_Completed  – Done!'),
        ]
        for hex_c, label in entries:
            row = QHBoxLayout(); row.setSpacing(6)
            dot = QLabel()
            dot.setFixedSize(10, 10)
            dot.setStyleSheet(
                f"background:{hex_c};border-radius:5px;")
            txt = QLabel(label)
            txt.setFont(QFont("Consolas", 8))
            txt.setStyleSheet("color:#4b5563;")
            row.addWidget(dot)
            row.addWidget(txt)
            row.addStretch()
            lay.addLayout(row)
        return w

    # ── helpers ───────────────────────────────────────────────────────────────
    @staticmethod
    def _sec(text):
        lbl = QLabel(text)
        lbl.setFont(QFont("Segoe UI", 8))
        lbl.setStyleSheet("color:#6b7280;letter-spacing:0.1em;")
        return lbl

    @staticmethod
    def _mini_btn(text, bg, fg, border):
        btn = QPushButton(text)
        btn.setFixedHeight(30); btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton{{background:{bg};color:{fg};border:1px solid {border};
                         border-radius:7px;font-size:10px;font-weight:700;}}
            QPushButton:hover{{background:{border};}}
        """)
        return btn

    def _lock(self, locked: bool):
        self._capture_btn.setEnabled(not locked)
        self._run_btn.setEnabled(not locked and bool(self._object_list))
        # keep play button state independent of capture/run lock
        self._stage_lbl.setVisible(locked or bool(self._stage_lbl.text()))

    def _set_stage(self, text: str):
        self._stage_lbl.setText(text)
        self._stage_lbl.setVisible(bool(text))

    def _clear_all(self):
        self._object_list = ""
        self._scene_box.setHtml("")
        self._cmd_box.clear()
        self._run_btn.setEnabled(False)
        self._play_btn.setEnabled(False)
        self._stop_btn.setEnabled(False)
        self._set_stage("")
        self._step_lbl.setText("")
        self.boxes_ready.emit([])      # remove drawn boxes from the image
        self.stop_commands.emit()

    # ── analyse ───────────────────────────────────────────────────────────────
    def _on_capture(self):
        self._lock(True)
        self._play_btn.setEnabled(False)
        self._set_stage("🔍  Sending image for bbox detection…")
        self._scene_box.clear()
        self._cmd_box.clear()
        self.request_frame.emit()

    def feed_frame(self, bgr):
        if bgr is None:
            self._lock(False)
            self._set_stage("⚠️  No image loaded — click  📁 Import Image  first")
            return
        self._set_stage("🔍  Step 1/2  ·  Detecting objects (bbox)…")
        self._scene_box.setHtml(
            '<div style="color:#2563eb;font-family:\'Segoe UI\';font-size:10px;padding:8px;">'
            '🔍&nbsp;&nbsp;Detecting objects in the scene…</div>'
        )
        self._vision_worker = VisionWorker(bgr)
        self._vision_worker.done.connect(self._on_vision_done)
        self._vision_worker.boxes.connect(self.boxes_ready.emit)
        self._vision_worker.error.connect(self._on_error)
        self._vision_worker.start()

    # ── vision output formatter ───────────────────────────────────────────────
    @staticmethod
    def _format_vision_html(obj_list: str) -> str:
        SIZE_COLOR  = {'small': '#6b7280', 'medium': '#2563eb', 'large': '#7c3aed'}
        cards = []
        for line in obj_list.strip().splitlines():
            line = line.strip()
            if not line.startswith('OBJECT:'):
                continue
            def _field(key):
                m = re.search(rf'{key}:\s*(.+?)(?=\s+[A-Z_]+:|$)', line)
                return m.group(1).strip() if m else ''
            name       = _field('OBJECT').replace('_', ' ').title()
            raw_name   = _field('OBJECT')
            center     = _field('CENTER')
            touches    = _field('TOUCHES')
            color      = _field('COLOR')
            size       = _field('SIZE').lower()
            desc       = _field('DESC')
            aka        = _field('ALSO_KNOWN_AS')
            size_clr   = SIZE_COLOR.get(size, '#64748b')
            aka_html   = ''
            if aka:
                tags = ''.join(
                    f'<span style="background:#f1f5f9;color:#475569;'
                    f'border:1px solid #cbd5e1;border-radius:3px;'
                    f'padding:1px 5px;margin-right:4px;font-size:9px;">'
                    f'{t.strip()}</span>'
                    for t in aka.split(',') if t.strip()
                )
                aka_html = f'<div style="margin-top:4px;">{tags}</div>'
            cards.append(
                f'<div style="background:#ffffff;border:1px solid #e2e8f0;'
                f'border-left:3px solid #3b82f6;border-radius:6px;'
                f'padding:8px 10px;margin-bottom:6px;">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                f'<span style="color:#1e293b;font-weight:700;font-size:11px;'
                f'font-family:\'Segoe UI\';">{name}</span>'
                f'<span style="color:#64748b;font-size:9px;font-family:Consolas;">'
                f'{raw_name}</span>'
                f'</div>'
                f'<div style="margin-top:3px;">'
                f'<span style="background:#dbeafe;color:#1d4ed8;border-radius:3px;'
                f'padding:1px 6px;font-size:9px;font-family:Consolas;margin-right:6px;">'
                f'&#127919; {center}</span>'
                f'<span style="background:#fef3c7;color:#92400e;border-radius:3px;'
                f'padding:1px 6px;font-size:9px;font-family:Consolas;margin-right:6px;">'
                f'&#9632; {color}</span>'
                f'<span style="background:#f3f4f6;color:{size_clr};border-radius:3px;'
                f'padding:1px 6px;font-size:9px;font-family:Consolas;">'
                f'{size}</span>'
                f'</div>'
                + (f'<div style="color:#64748b;font-size:9px;font-family:Consolas;'
                   f'margin-top:3px;">&#128205; touches: {touches}</div>' if touches else '')
                + (f'<div style="color:#6b7280;font-size:9px;font-family:\'Segoe UI\';'
                   f'margin-top:4px;line-height:1.4;">{desc}</div>' if desc else '')
                + aka_html
                + '</div>'
            )
        if not cards:
            return (
                '<div style="color:#6b7280;font-family:\'Segoe UI\';font-size:10px;'
                'padding:10px;">No objects detected.</div>'
            )
        count = len(cards)
        header = (
            f'<div style="color:#2563eb;font-family:\'Segoe UI\';font-size:9px;'
            f'letter-spacing:0.05em;margin-bottom:8px;">'
            f'{count} OBJECT{"S" if count != 1 else ""} DETECTED  ·  cells computed in Python</div>'
        )
        return header + ''.join(cards)

    def _on_vision_done(self, obj_list: str):
        self._object_list = obj_list
        self._scene_box.setHtml(self._format_vision_html(obj_list))
        self._run_btn.setEnabled(True)
        self._lock(False)
        self._set_stage("✅  Objects detected — enter task and click ⚡")

    # ── generate commands ─────────────────────────────────────────────────────
    def _on_run(self):
        task = self._task_input.toPlainText().strip()
        if not task:
            self._set_stage("⚠️  Please describe a task first"); return
        if not self._object_list:
            self._set_stage("⚠️  Import and analyse an image first"); return
        self._lock(True)
        self._play_btn.setEnabled(False)
        self._cmd_box.clear()
        self._set_stage("⚡  Step 2/2  ·  Generating command sequence…")
        self._command_worker = CommandWorker(self._object_list, task)
        self._command_worker.chunk.connect(self._on_cmd_chunk)
        self._command_worker.done.connect(self._on_cmd_done)
        self._command_worker.error.connect(self._on_error)
        self._command_worker.start()

    def _on_cmd_chunk(self, delta: str):
        self._cmd_box.moveCursor(QTextCursor.End)
        self._cmd_box.insertPlainText(delta)
        self._cmd_box.moveCursor(QTextCursor.End)

    def _on_cmd_done(self, _full: str):
        self._lock(False)
        self._play_btn.setEnabled(True)
        self._set_stage("✅  Commands ready — press ▶ PLAY to animate on grid")

    def _on_error(self, err: str):
        self._lock(False)
        self._set_stage("⚠️  Error")
        self._scene_box.setHtml(
            f'<div style="color:#dc2626;font-family:\'Segoe UI\';font-size:10px;padding:8px;">'
            f'⚠️&nbsp;&nbsp;{err}</div>'
        )

    # ── play / stop ───────────────────────────────────────────────────────────
    def _on_play(self):
        text = self._cmd_box.toPlainText().strip()
        if not text:
            return
        self._play_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._step_lbl.setText("Starting…")
        self._set_stage("▶  Playing commands on grid…")
        self.play_commands.emit(text)

    def _on_stop(self):
        self.stop_commands.emit()
        self._play_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._step_lbl.setText("")
        self._set_stage("■  Stopped")

    # ── called by MainWindow when runner finishes ─────────────────────────────
    def on_runner_finished(self):
        self._play_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._set_stage("✅  Playback complete")
        self._step_lbl.setText("")

    def on_runner_step(self, current: int, total: int, cmd: str):
        # Extract coordinate from goto_coordinate commands for prominent display
        m = re.match(r'goto_coordinate\s*=\s*([A-Ta-t])\s*,\s*(\d+)', cmd.strip())
        coord = f"  →  {m.group(1).upper()}{m.group(2)}" if m else ""
        self._step_lbl.setText(f"Step {current} / {total}  ·  {cmd}{coord}")


# ─────────────────────────────────────────────────────────────────────────────
#  Image panel  (loads a static image from disk)
# ─────────────────────────────────────────────────────────────────────────────
class CameraPanel(QWidget):
    runner_finished = Signal()   # forwarded to sidebar

    def __init__(self, sidebar: AISidebar, parent=None):
        super().__init__(parent)
        self._sidebar   = sidebar
        self._raw_image = None          # BGR numpy array of the loaded image
        self.setStyleSheet("background:#f5f7fa;")
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)

        # ── Top bar ───────────────────────────────────────────────────────────
        bar = QWidget(); bar.setFixedHeight(38)
        bar.setStyleSheet("background:#e8eaf0;border-bottom:1px solid #d0d4de;")
        bl = QHBoxLayout(bar); bl.setContentsMargins(12,0,12,0); bl.setSpacing(10)

        brand = QLabel("A2 Physical Simulator HOS")
        brand.setFont(QFont("Segoe UI Semibold", 10))
        brand.setStyleSheet("color:#1A2a2e;")

        # Import button lives in the top bar
        self._import_btn = QPushButton("📁  Import Image")
        self._import_btn.setFixedHeight(26)
        self._import_btn.setCursor(Qt.PointingHandCursor)
        self._import_btn.setStyleSheet("""
            QPushButton{background:#dbeafe;color:#1d4ed8;
                        border:1px solid #93c5fd;border-radius:6px;
                        font-family:'Segoe UI';font-weight:700;font-size:10px;padding:0 10px;}
            QPushButton:hover{background:#2563eb;color:#fff;}
            QPushButton:pressed{background:#1e3a8a;}
        """)
        self._import_btn.clicked.connect(self._import_image)

        self._status = QLabel("● No image loaded")
        self._status.setFont(QFont("Segoe UI", 9))
        self._status.setStyleSheet("color:#9ca3af;")

        bl.addWidget(brand)
        bl.addStretch()
        bl.addWidget(self._import_btn)
        bl.addWidget(self._status)
        lay.addWidget(bar)

        # ── Image display area ────────────────────────────────────────────────
        self._overlay = GridOverlay()
        self._video   = VideoLabel()
        self._video.setAlignment(Qt.AlignCenter)
        self._video.setStyleSheet("background:#f5f7fa;")
        self._video.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._video.attach_overlay(self._overlay)
        lay.addWidget(self._video, 1)

        # Placeholder text; grid shows full-panel until an image is loaded
        self._video.setText(
            "📁   Click  Import Image  to load a photo\n\n"
            "Supports  JPG · PNG · BMP · TIFF · WEBP")
        self._video.setFont(QFont("Segoe UI", 13))
        self._video.setStyleSheet("background:#f5f7fa; color:#c0c4d0;")
        # No image yet — overlay grid covers full panel as placeholder
        self._overlay.set_image_rect(None)

        # ── Command runner ────────────────────────────────────────────────────
        self._runner = CommandRunner()
        self._runner.move_to.connect(self._overlay.set_target)
        self._runner.state_changed.connect(self._overlay.set_state)
        self._runner.show_dot.connect(self._overlay.show_dot)
        self._runner.hide_dot.connect(self._overlay.hide_dot)
        self._runner.finished.connect(self.runner_finished.emit)

        # ── Sidebar signals ───────────────────────────────────────────────────
        sidebar.request_frame.connect(self._deliver_frame)
        sidebar.request_unfreeze.connect(self._on_unfreeze)   # no-op for static image
        sidebar.play_commands.connect(self.run_commands)
        sidebar.stop_commands.connect(self.stop_commands)
        sidebar.boxes_ready.connect(self._overlay.set_bboxes)

    # ── image import ──────────────────────────────────────────────────────────
    def _import_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Image",
            "",
            "Images (*.jpg *.jpeg *.png *.bmp *.tiff *.tif *.webp);;All Files (*)",
        )
        if not path:
            return   # user cancelled

        bgr = cv2.imread(path)
        if bgr is None:
            self._status.setText("⚠️  Could not read file")
            self._status.setStyleSheet("color:#f87171;")
            return

        self._raw_image = bgr
        self._overlay.set_bboxes([])   # stale boxes from a previous image are wrong
        self._show_image(bgr)

        import os
        fname = os.path.basename(path)
        self._status.setText(f"● {fname}")
        self._status.setStyleSheet("color:#22cc55;")

    def _show_image(self, bgr):
        """Display image with KeepAspectRatio. Tell the overlay the exact letterbox rect
        so its grid cells map 1-to-1 with the normalized bbox space used by the VLM."""
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        qi   = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888).copy()
        lw, lh = self._video.width() or 1280, self._video.height() or 720
        pix  = QPixmap.fromImage(qi).scaled(
            lw, lh, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        # Compute where the pixmap sits inside the label (centred)
        ox = (lw - pix.width())  / 2.0
        oy = (lh - pix.height()) / 2.0
        self._overlay.set_image_rect(QRectF(ox, oy, pix.width(), pix.height()))
        self._video.setText("")
        self._video.setStyleSheet("background:#f5f7fa;")
        self._video.setPixmap(pix)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._raw_image is not None:
            self._show_image(self._raw_image)

    # ── sidebar handshake ─────────────────────────────────────────────────────
    def _deliver_frame(self):
        self._sidebar.feed_frame(self._raw_image)

    def _on_unfreeze(self):
        pass   # nothing to unfreeze for a static image

    # ── command playback ──────────────────────────────────────────────────────
    def run_commands(self, text: str):
        self._runner.load(text)
        self._runner.start()

    def stop_commands(self):
        self._runner.stop()
        self._overlay.hide_dot()

    def closeEvent(self, event):
        super().closeEvent(event)

# ─────────────────────────────────────────────────────────────────────────────
#  Main window
# ─────────────────────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Humanoid Operating System – A2 Physical Simulator")
        self.resize(1440, 840)
        self.setMinimumSize(960, 600)
        pal = QPalette()
        pal.setColor(QPalette.Window, QColor("#f0f2f7"))
        self.setPalette(pal)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet("QSplitter::handle{background:#d0d4de;}")

        self._sidebar   = AISidebar()
        self._cam_panel = CameraPanel(self._sidebar)

        # Runner → sidebar feedback
        self._cam_panel.runner_finished.connect(self._sidebar.on_runner_finished)
        self._cam_panel._runner.step_info.connect(self._sidebar.on_runner_step)

        splitter.addWidget(self._cam_panel)
        splitter.addWidget(self._sidebar)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)

    def closeEvent(self, event):
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

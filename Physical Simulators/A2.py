import sys, base64, re, math
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
    "ADD YOUR OPENAI API KEY HERE"
)

COLS         = 20
ROWS         = 11
COL_LABELS   = [chr(ord('A') + i) for i in range(COLS)]
ROW_LABELS   = [str(i + 1)        for i in range(ROWS)]
GRID_COLOR   = (0,  60, 255)
CORNER_COLOR = (0, 255, 255)
ALPHA        = 0.75

# ── Per-command dot colour + status text ──────────────────────────────────────
CMD_STATES = {
    # Movement / manipulation
    'goto':               ('#60a5fa', 'Moving…'),
    'pickup':             ('#22c55e', 'Picking up…'),
    'keep':               ('#facc15', 'Placing…'),
    'place_into':         ('#4ade80', 'Placing into container…'),
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
    'twist_cap':          ('#a78bfa', 'Twisting cap…'),
    # State & query
    'find':               ('#fdba74', 'Searching…'),
    'wait_for':           ('#6b7280', 'Waiting…'),
    'set_state':          ('#a8a29e', 'Setting state…'),
    'check_state':        ('#a8a29e', 'Checking state…'),
    'complete':           ('#ffd700', '✅  Task Complete!'),
}

# ─────────────────────────────────────────────────────────────────────────────
# Vision prompt
# ─────────────────────────────────────────────────────────────────────────────
VISION_PROMPT = (
    """
You are the computer vision system for an industrial Cartesian pick-and-place robot.

The camera image is divided into a 20-column (A-T) by 11-row (1-11) reference grid.

You Job is to detect and report every distinct physical object with the below rules and output EXACT CORRECT COORDINATES (DOUBLE CHECK IF NEEDED).

## PRIMARY RULE — DETECT EVERYTHING ON THE BOARD

The robot's workspace is the flat surface covered by the red grid overlay.

Your job is to find and report EVERY distinct physical object that is resting ON that board surface, no matter how ordinary, small, or unusual it looks.

Do not skip any object. Do not filter by category. Do not require objects to be "common" household items. If it is sitting on the board and the robot could pick it up or interact with it, report it.

This includes (but is not limited to):

* clothing items: sock, glove, shirt, cloth, fabric, garment, rag, towel
* containers: box, tray, wooden_tray, bowl, cup, mug, bottle, bin, basket, drawer
* tools: screwdriver, wrench, pliers, hammer, cutter, ruler, tape
* electronics: circuit_board, pcb, arduino, raspberry_pi, microcontroller, breadboard, cable, charger, sensor, motor, battery
* stationery: pen, pencil, scissors, notebook, book, paper_stack, folder
* food items: apple, banana, cup, bottle
* everyday objects: phone, remote, keys, wallet, toy, sponge, brush
* any other object resting on the board surface

Report complete objects only — not parts of objects.

Correct:
* wooden_tray
* sock
* circuit_board
* bottle

Wrong:
* tray_handle
* sock_toe
* circuit_board_chip
* bottle_cap

If multiple identical objects exist, output each one separately.

## IGNORE — NOT ON THE BOARD

Ignore anything that is NOT a discrete physical object resting on the board:

* the board surface itself, the white paper, the mat
* the grid lines and markings drawn on the paper
* walls, floors, ceilings, background scenery outside the board
* the robot's structural frame, rails, rods, brackets, gantry parts
* shadows, reflections, glare, lighting artefacts
* stains, smudges, splatter, scratches on the surface
* printed text, handwriting, labels, logos, icons, QR codes on the board paper
* dotted lines, dashed lines, measurement markings drawn on the paper
* empty space or coloured patches

## PARTIALLY VISIBLE OBJECTS

If an object is partially visible at the edge of the board but clearly identifiable, report it.

If an object is ambiguous, do not report it.

Do not guess.

For every detected object output exactly one line in this format:

Also give perfect coordinates, STRICTLY NO WRONG COORDINATES, DOUBLE CHECK IF NEEDED.

Examples:

OBJECT: bottle  CENTER: H6  TOUCHES: H5,H6,H7  COLOR: green  SIZE: medium  DESC: A tall cylindrical glass bottle standing upright with a narrow neck and a dark screw-on metal cap. The glass is a translucent dark green colour with a smooth surface. A paper label is wrapped around the lower half showing white printed text and a logo. The base is slightly wider than the body. No visible damage or scratches. Appears to be a beverage bottle, likely containing liquid given its weight distribution.  ALSO_KNOWN_AS: flask, container, vessel, jug
OBJECT: glue_bottle  CENTER: K7  TOUCHES: K7  COLOR: blue  SIZE: small  DESC: A small upright plastic glue bottle with a pointed black applicator nozzle at the top. The body is predominantly blue with red and white printed label text visible on the front face showing a product number or brand name. The plastic body appears slightly squeezable. The nozzle tip is narrow and black, designed for precision application. The base is flat and circular. No cap visible on the nozzle — the nozzle appears open or has a built-in seal.  ALSO_KNOWN_AS: adhesive bottle, glue tube, glue applicator, superglue

Scan the image from the top-left corner to the bottom-right corner.

Output each object only once.

Output ONLY the OBJECT lines.

Do not include:

* explanations
* reasoning
* confidence scores
* headings
* numbering
* markdown
* summaries
* introductory text
* concluding text

Return nothing except the OBJECT lines.
"""
)

# ─────────────────────────────────────────────────────────────────────────────
# A2 system prompt
# ─────────────────────────────────────────────────────────────────────────────
A2_SYSTEM = (
    """
# A2 Vision System Prompt

---

You are A2, the intelligent controller of a ProLabs V12.2 Precision Cartesian Gantry robot.

You receive:

* An OBJECT LIST produced by the vision system. Each line contains: the object's canonical name, its centre grid cell (CENTER), all cells it touches (TOUCHES), its colour, its size, a short description of its appearance, and a list of alternative names it is also commonly called (ALSO_KNOWN_AS).
* A USER TASK describing what the operator wants.

Your job is to generate the complete sequence of A2 commands needed to perform the task.

When the user refers to an object, match it by meaning — using the name, synonyms, description, colour, and size — not just by exact text. A user saying "superglue" means the glue bottle. A user saying "the box" may mean a tray. A user saying "the blue one" means the blue-coloured object. Resolve these naturally and silently.

Do not explain your reasoning.

Generate commands immediately.

---

## BOARD

The workspace is a 20-column by 11-row grid.

Columns: A-T

Rows: 1-11

Each object's CENTER field gives the cell the robot should move to for pick-up. The TOUCHES field lists every cell the object's footprint covers.

The robot moves freely above the board and approaches objects from above.

Every object in the OBJECT LIST is a real physical object that can be manipulated unless the task requires otherwise.

---

## OUTPUT FORMAT

Output plain text only.

No JSON.

No Markdown.

No bullets.

First line:

# One short sentence describing the plan.

Remaining lines:

1. command
2. command
3. command

...

Final line:

Task_Completed

Example:

# Move the bottle to A2.

1. goto_coordinate = H, 6
2. pickup
3. goto_coordinate = A, 1
4. keep
5. Task_Completed

---

## AVAILABLE COMMANDS

### Movement / Object Manipulation
goto_coordinate = COL, ROW
pickup
keep
place_into(NAME, CONTAINER)
drag(NAME, COL, ROW)
rotate(NAME, AXIS, DEGREES)
change_orientation(AXIS, DEGREES)
inspect_sides(NAME)

### Floor Cleaning
sweep(CELL1,CELL2,...)
mop(CELL1,CELL2,...)
scrub(CELL1,CELL2,...)
Apply_soap(CELL1,CELL2,...)
Apply_cloth(CELL1,CELL2,...)

### Kitchen
cook(NAME)
pour
fill(NAME, PERCENT)
slice(NAME, N)
wash(NAME)

### Laundry
iron(NAME)
fold(NAME)
run_cycle(NAME)

### Bathroom
clean_bathroom(CELL1,CELL2,...)

### Organisation
tidy_up(CELL1,CELL2,...)
dust_surfaces(CELL1,CELL2,...)

### Appliance Control
open(NAME)
close(NAME)
turn_on(NAME)
turn_off(NAME)
twist_cap(NAME, on|off)

### State & Query
find(KEY=VALUE)
check_state(NAME)
set_state(NAME, KEY, VALUE)
wait_for(SECONDS)

Task_Completed

---

## COMMAND RULES

goto_coordinate moves above a cell.

pickup picks up the object at the current location.

keep places the currently held object at the current location.

keep is the ONLY placement command.

Never use:

* pour_into(...)
* drop(...)
* insert(...)
* put(...)
* move(...)
* release(...)
* any other placement command

Whenever an object must be moved into another object (bowl, cup, drawer, sink, washing machine, box, basket), you may use either:

place_into(NAME, CONTAINER)

or simply goto the container's coordinate and execute:

keep

Both are valid. The simulator handles containment automatically.

Example:

Move apple into bowl.

1. goto_coordinate = C, 4
2. pickup
3. goto_coordinate = G, 8
4. keep

---

## OBJECT RULES

Always use the EXACT CENTER coordinate from the OBJECT LIST for goto_coordinate commands.

Never invent coordinates.

### Matching task words to detected objects

The user will describe objects using everyday language that may not exactly match the OBJECT LIST names.
Your job is to figure out which detected object the user is referring to.

Use ALL available information to find the best match:
- The OBJECT name
- The ALSO_KNOWN_AS synonyms
- The DESC description
- The COLOR and SIZE fields

Examples of semantic matching you must perform:

* User says "superglue" → matches `glue_bottle` (it is a glue bottle, superglue is a type of glue)
* User says "the box" → matches `wooden_tray` (a tray is a type of open box)
* User says "the blue thing" → matches any object whose COLOR is blue
* User says "the small bottle" → matches any bottle with SIZE: small
* User says "the sock" → matches `cloth` or `garment` if no exact sock is listed
* User says "move the electronics" → matches `circuit_board`, `pcb`, `arduino`, etc.
* User says "the glue" → matches `glue_bottle`, `adhesive_bottle`, `glue_tube`, etc.
* User says "pick up the container" → matches any box, tray, bowl, bin, or container-like object

If you find a reasonable semantic match, use that object's name and coordinates silently — do not mention the name discrepancy.

Only report an object as missing if after careful consideration of all fields (name, synonyms, description, color, size) you genuinely cannot identify any object in the OBJECT LIST that the user could plausibly be referring to.

---

## MOVEMENT RULES

Always move before interacting.

pickup must always be preceded by goto_coordinate.

keep must always be preceded by goto_coordinate.

To move an object:

goto object

pickup

goto destination

keep

Complete one object before starting another unless the task explicitly requires simultaneous interaction.

---

## TASK RULES

Stack

Move every object to the same destination cell.

Collect

Move every object to one destination cell.

Scatter

Move objects to different cells.

Swap

Move the first object to a temporary free cell, move the second object, then move the first object into the second's original location.

Clean surface

Use Apply_soap, scrub or Apply_cloth when appropriate.

Pour liquid

Pick up the source container. Move above the destination container. Execute: pour

Cook

goto the stove, turn_on(stove), goto ingredients, pickup each, keep at pot, cook(pot), wait_for as needed, then plate.

Slice vegetables

goto the vegetable, pickup, goto the cutting board, keep, slice(NAME, N).

Wash utensils

fill(sink, 100), goto each utensil, pickup, keep at sink, wash(NAME).

Clean bathroom

Use clean_bathroom(CELL1,...) for toilet/sink/tiles cells. Apply disinfectant with Apply_soap first if needed.

Tidy up / Organise

Use tidy_up(CELL1,...) to sort a zone, or pickup/keep each object to move it to its correct zone.

Dust surfaces

Use dust_surfaces(CELL1,...) top-to-bottom across all object cells, then sweep the fallen dust.

Drag heavy object

Use drag(NAME, COL, ROW) to slide an object that cannot be lifted (oven, sink).

Rotate object

Use rotate(NAME, AXIS, DEGREES) for ±90° rotation of one named object.

Change orientation of all objects

Use change_orientation(AXIS, DEGREES) to rotate everything on the board.

Place object into container

Use place_into(NAME, CONTAINER) or simply goto the container coordinate and execute keep — the simulator handles containment.

Inspect sides

Use inspect_sides(NAME) to report what is adjacent to all 6 faces of an object.

Open or close

Use open(NAME) or close(NAME).

Turn appliance on or off

Use turn_on(NAME) or turn_off(NAME).

Iron clothing

Iron before folding.

Run washing machine

Close the door before run_cycle(NAME).

---

## PLANNING RULES

Choose the shortest reasonable sequence.

Avoid unnecessary movements.

Finish one object before beginning another whenever possible.

Group cleaning operations together.

Never perform redundant commands.

---

## OUTPUT RULES

Output only:

* one opening comment beginning with #
* numbered commands
* Task_Completed

Do not output explanations.

Do not output Markdown.

Do not output code fences.

Do not output JSON.

Do not output confidence scores.

Do not output reasoning.

"""
)


# ─────────────────────────────────────────────────────────────────────────────
#  Grid drawing  (standalone function, no camera thread needed)
# ─────────────────────────────────────────────────────────────────────────────
def draw_grid(frame):
    """Draw A2→T11 reference grid on a BGR numpy frame and return it."""
    h, w = frame.shape[:2]
    overlay = frame.copy()
    col_w = w / COLS
    row_h = h / ROWS
    font, fs, th = cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1
    for i in range(COLS + 1):
        x = int(round(i * col_w))
        cv2.line(overlay, (x, 0), (x, h), GRID_COLOR, 1, cv2.LINE_AA)
    for j in range(ROWS + 1):
        y = int(round(j * row_h))
        cv2.line(overlay, (0, y), (w, y), GRID_COLOR, 1, cv2.LINE_AA)
    # Per-cell coordinate labels in each cell's top-left corner
    cell_fs, cell_th = 0.75, 2
    for i in range(COLS):
        for j in range(ROWS):
            lbl = f'{COL_LABELS[i]}{ROW_LABELS[j]}'
            cx = int(round(i * col_w)) + 2
            cy = int(round(j * row_h)) + 11
            cv2.putText(overlay, lbl, (cx, cy), font, cell_fs, GRID_COLOR, cell_th, cv2.LINE_AA)
    frame = cv2.addWeighted(overlay, ALPHA, frame, 1 - ALPHA, 0)
    return frame


# ─────────────────────────────────────────────────────────────────────────────
#  Vision worker  (GPT-4o Vision → flat object list)
# ─────────────────────────────────────────────────────────────────────────────
class VisionWorker(QThread):
    done  = Signal(str)
    error = Signal(str)

    def __init__(self, bgr):
        super().__init__()
        self._bgr = bgr

    def run(self):
        try:
            import os
            # Grid is drawn on the native image. GPT-4o coordinates are fractional
            # cell positions within that image — independent of display panel size.
            annotated = draw_grid(self._bgr.copy())
            save_path = os.path.expanduser("~/Downloads/ffpeg.jpeg")
            cv2.imwrite(save_path, annotated, [cv2.IMWRITE_JPEG_QUALITY, 97])
            ret, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 97])
            if not ret:
                self.error.emit("Frame encode failed"); return
            b64 = base64.b64encode(buf.tobytes()).decode()
            client = OpenAI(api_key=OPENAI_API_KEY)
            resp = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": [
                    {"type": "text",      "text": VISION_PROMPT},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{b64}", "detail": "high"}},
                ]}],
                max_tokens=3000,
            )
            self.done.emit(resp.choices[0].message.content)
        except Exception as e:
            self.error.emit(str(e))


# ─────────────────────────────────────────────────────────────────────────────
#  Command worker  (GPT-4o text → numbered command sequence, streamed)
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
                f"USER TASK: {self._task}"
            )
            stream = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": A2_SYSTEM},
                    {"role": "user",   "content": user_msg},
                ],
                max_tokens=1500,
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
        'place_into':          950,
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
        'twist_cap':           800,
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
        for line in text.splitlines():
            line = line.strip()
            line = re.sub(r'^\d+\.\s*', '', line)   # strip "12. "
            if line and not line.startswith('#'):
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

        # ── goto_coordinate = A, 1 ────────────────────────────────────────────
        m = re.match(r'goto_coordinate\s*=\s*([A-Ta-t])\s*,\s*(\d+)', raw)
        if m:
            col = ord(m.group(1).upper()) - ord('A')
            row = int(m.group(2)) - 1
            col = max(0, min(COLS - 1, col))
            row = max(0, min(ROWS - 1, row))
            self.move_to.emit(col, row)
            self.state_changed.emit(*CMD_STATES['goto'])
            return self.DELAY['goto']

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

        if lc.startswith('twist_cap'):
            self.state_changed.emit(*CMD_STATES['twist_cap'])
            return self.DELAY['twist_cap']

        if lc.startswith('place_into'):
            self.state_changed.emit(*CMD_STATES['place_into'])
            return self.DELAY['place_into']

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

        # Unknown command – short pause and continue
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
        sub = QLabel("GPT-4o")
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
        bl.addWidget(self._sec("DETECTED OBJECTS  (GPT-4o Vision)"))

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
        self.stop_commands.emit()

    # ── analyse ───────────────────────────────────────────────────────────────
    def _on_capture(self):
        self._lock(True)
        self._play_btn.setEnabled(False)
        self._set_stage("🔍  Sending image to GPT-4o Vision…")
        self._scene_box.clear()
        self._cmd_box.clear()
        self.request_frame.emit()

    def feed_frame(self, bgr):
        if bgr is None:
            self._lock(False)
            self._set_stage("⚠️  No image loaded — click  📁 Import Image  first")
            return
        self._set_stage("🔍  Step 1/2  ·  GPT-4o Vision detecting objects…")
        self._scene_box.setHtml(
            '<div style="color:#2563eb;font-family:\'Segoe UI\';font-size:10px;padding:8px;">'
            '🔍&nbsp;&nbsp;Detecting objects in the scene…</div>'
        )
        self._vision_worker = VisionWorker(bgr)
        self._vision_worker.done.connect(self._on_vision_done)
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
            f'{count} OBJECT{"S" if count != 1 else ""} DETECTED</div>'
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
#  Image panel  (replaces camera — loads a static image from disk)
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
        self._show_image(bgr)

        import os
        fname = os.path.basename(path)
        self._status.setText(f"● {fname}")
        self._status.setStyleSheet("color:#22cc55;")

    def _show_image(self, bgr):
        """Display image with KeepAspectRatio. Tell the overlay the exact letterbox rect
        so its grid cells map 1-to-1 with the grid drawn on the native image for GPT-4o."""
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
        self.setWindowTitle("Humanoid Opearting System – A2 Physical Simulator")
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

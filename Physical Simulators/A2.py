import sys, os, base64, re, math, json
import cv2
import numpy as np
from openai import OpenAI

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QScrollArea, QSizePolicy,
    QSplitter, QPlainTextEdit, QTextEdit, QFrame, QFileDialog,
    QComboBox, QLineEdit, QMessageBox, QMenu, QSlider, QListWidget,
    QListWidgetItem, QGridLayout, QInputDialog,
)
from PySide6.QtCore  import Qt, Signal, QTimer, QObject, QPointF, QRectF, QThread
from PySide6.QtGui   import (QImage, QPixmap, QFont, QColor, QPalette,
                              QTextCursor, QPainter, QPen, QBrush, QRadialGradient,
                              QKeySequence, QShortcut, QLinearGradient, QPolygonF)

# ─────────────────────────────────────────────────────────────────────────────
OPENAI_API_KEY = (
    "sk-proj-vFVeJD0s4A4mfZGLCBUDPCOaQcNj7vQLPcNvHvhQXuWfFoR6OiW1X5gf9jyX"
    "yyJet33N-dsL_QT3BlbkFJ_hbcfH-O03UxhkANXi4VPepseIX2SkNSYQyX3sGZAn7vax"
    "8HYBseymYc-ExEV_nnNk0ZiCgXsA"
)

INSTRUCTIONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai_instructions.json")

# ─────────────────────────────────────────────────────────────────────────────
#  Cross-platform fonts  (Segoe UI / Consolas are Windows-only — on macOS they
#  force Qt to scan all font aliases at startup and then fall back arbitrarily)
# ─────────────────────────────────────────────────────────────────────────────
if sys.platform == "darwin":
    UI_FONT   = "SF Pro Text"
    UI_FONT_B = "SF Pro Text"
    MONO_FONT = "SF Mono"
elif sys.platform.startswith("win"):
    UI_FONT   = "Segoe UI"
    UI_FONT_B = "Segoe UI Semibold"
    MONO_FONT = "Consolas"
else:
    UI_FONT   = "Ubuntu"
    UI_FONT_B = "Ubuntu"
    MONO_FONT = "Ubuntu Mono"


def ui_font(size=9, bold=False):
    f = QFont(UI_FONT, size)
    if bold:
        f.setBold(True)
    return f


def mono_font(size=9, bold=False):
    f = QFont(MONO_FONT, size)
    if bold:
        f.setBold(True)
    return f


COLS         = 20
ROWS         = 11
COL_LABELS   = [chr(ord('A') + i) for i in range(COLS)]
ROW_LABELS   = [str(i + 1)        for i in range(ROWS)]

# ── Cell coverage tuning ─────────────────────────────────────────────────────
# OLD BUG: a hard 0.80 area threshold meant any object smaller than one grid
# cell touched ZERO cells, and only survived via the centroid fallback — so
# apply_soap / apply_cloth only ever swept a single cell. Now:
#   • a cell counts if the bbox covers >= TOUCH_THRESHOLD of it, OR
#   • if nothing clears that bar, we keep every cell whose overlap is at least
#     REL_FALLBACK of the best-covered cell (so small objects still span the
#     cells they visually sit on).
TOUCH_THRESHOLD = 0.30
REL_FALLBACK    = 0.45
MAX_TOUCH_CELLS = 24

# ── Theme ─────────────────────────────────────────────────────────────────────
C_BG        = "#0f1424"
C_PANEL     = "#161c31"
C_PANEL_2   = "#1d2540"
C_BORDER    = "#2c3757"
C_TEXT      = "#e8ecf8"
C_TEXT_DIM  = "#8b97b8"
C_CYAN      = "#22d3ee"
C_BLUE      = "#3b82f6"
C_VIOLET    = "#a855f7"
C_PINK      = "#ec4899"
C_GREEN     = "#22c55e"
C_AMBER     = "#f59e0b"
C_RED       = "#ef4444"

# ── Per-command dot colour + status text ──────────────────────────────────────
CMD_STATES = {
    'goto':               ('#60a5fa', 'Moving…'),
    'pickup':             ('#22c55e', 'Picking up…'),
    'keep':               ('#facc15', 'Placing…'),
    'drag':               ('#d97706', 'Dragging heavy object…'),
    'rotate':             ('#06b6d4', 'Rotating object…'),
    'change_orientation': ('#6366f1', 'Changing orientation…'),
    'inspect_sides':      ('#fbbf24', 'Inspecting sides…'),
    'sweep':              ('#fb923c', 'Sweeping…'),
    'mop':                ('#7dd3fc', 'Mopping…'),
    'scrub':              ('#f97316', 'Scrubbing…'),
    'apply_soap':         ('#e2e8f0', 'Applying soap…'),
    'apply_cloth':        ('#d4b483', 'Applying cloth…'),
    'cook':               ('#ff6b35', 'Cooking…'),
    'pour':               ('#22d3ee', 'Pouring…'),
    'slice':              ('#f43f5e', 'Slicing…'),
    'fill':               ('#38bdf8', 'Filling…'),
    'wash':               ('#38bdf8', 'Washing…'),
    'iron':               ('#f87171', 'Ironing…'),
    'fold':               ('#c084fc', 'Folding…'),
    'run_cycle':          ('#818cf8', 'Running cycle…'),
    'clean_bathroom':     ('#2dd4bf', 'Cleaning bathroom…'),
    'tidy_up':            ('#a78bfa', 'Tidying up…'),
    'dust_surfaces':      ('#d1d5db', 'Dusting surfaces…'),
    'open':               ('#2dd4bf', 'Opening…'),
    'close':              ('#2dd4bf', 'Closing…'),
    'turn_on':            ('#fde68a', 'Turning on…'),
    'turn_off':           ('#9ca3af', 'Turning off…'),
    'find':               ('#fdba74', 'Searching…'),
    'wait_for':           ('#6b7280', 'Waiting…'),
    'set_state':          ('#a8a29e', 'Setting state…'),
    'check_state':        ('#a8a29e', 'Checking state…'),
    'complete':           ('#ffd700', '✅  Task Complete!'),
}

# ─────────────────────────────────────────────────────────────────────────────
# Vision prompt  (BBOX version — model returns boxes, Python computes cells)
# FIX: surfaces the robot must ACT ON (table, counter, sink basin, tub) are now
# explicitly reportable objects. Previously "do not report the table surface"
# meant "wipe the table" had no coordinate to resolve to.
# ─────────────────────────────────────────────────────────────────────────────
VISION_PROMPT = (
    """
You are the vision system for a robot. Identify every physical object in this image.

Report EVERY physical thing the robot could touch, move, open, operate, or clean:
- small objects (bottles, clothes, tools, food, sponges, plates, cutlery, toys)
- large 3D items: appliances (washing machine, dryer, oven, stove), furniture,
  shelves, bins, baskets
- WORK SURFACES AND CONTAINERS the robot may need to act on directly:
  tables, stools, desks, countertops, sink basins, tubs, buckets, basins, trays.
  These ARE objects — a task like "wipe the table" or "wash the dishes in the
  sink" needs the table/sink to have its own coordinates. Always report them.

Do NOT report: the floor, walls, ceiling, shadows, reflections, or flat printed
markings. Everything else — when unsure, REPORT it.

For each object, give a tight OUTLINE POLYGON in NORMALIZED coordinates: the
image is 1000 units wide and 1000 units tall. (0,0) is top-left, (1000,1000)
is bottom-right.
- The polygon must hug the object's actual visible silhouette — for long thin
  or diagonally-angled objects (brooms, mops, cables, tools, rulers), follow
  the angle of the object with multiple points instead of drawing a big
  rectangle around it. Do NOT include empty background inside the polygon.
- Use 4 points for compact/rectangular objects, up to 8-10 points for
  irregular, thin, or angled ones.
- For tall objects (appliances, furniture), outline the BASE region where it
  meets the floor, not the full height.
- For flat work surfaces (table top, counter, sink basin), outline the FULL
  usable surface area, because the robot will sweep/wipe across all of it.

Output STRICT JSON only — no markdown, no code fences, no commentary:

{"objects": [
  {"name": "washing machine",
   "polygon": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
   "color": "white",
   "size": "large",
   "surface": false,
   "desc": "Front-loading washing machine with a round door.",
   "aka": ["washer", "laundry machine", "appliance"]}
]}

Rules:
- polygon values are integers 0-1000. At least 3 points, listed in order
  (clockwise or counter-clockwise) tracing the object's outline. No
  self-intersecting polygons.
- surface: true for tables/counters/sinks/tubs/trays the robot wipes or works on;
  false for everything else.
- One physical object = exactly one entry. Two similar items in different
  places are two entries.
- name: lowercase, short. desc: one sentence. aka: 2-3 synonyms.
"""
)

# ─────────────────────────────────────────────────────────────────────────────
# BBox → cell math  (deterministic)
# ─────────────────────────────────────────────────────────────────────────────
def bbox_to_cells(box, thr=TOUCH_THRESHOLD):
    """Return (center_cell, touches_list) from a normalized [x0,y0,x1,y1] box.

    Two-stage rule so that objects smaller than one grid cell still register the
    cells they actually sit on instead of collapsing to a single centroid cell.
    """
    try:
        x0, y0, x1, y1 = [max(0.0, min(1000.0, float(v))) for v in box]
    except (TypeError, ValueError):
        return None, []
    if x1 <= x0 or y1 <= y0:
        return None, []

    cell_w = 1000.0 / COLS
    cell_h = 1000.0 / ROWS
    cell_a = cell_w * cell_h

    scored = []   # (fraction_of_cell_covered, (ci, ri))
    for ci in range(COLS):
        cx0 = ci * cell_w
        if cx0 >= x1 or cx0 + cell_w <= x0:
            continue
        for ri in range(ROWS):
            cy0 = ri * cell_h
            if cy0 >= y1 or cy0 + cell_h <= y0:
                continue
            ow = max(0.0, min(x1, cx0 + cell_w) - max(x0, cx0))
            oh = max(0.0, min(y1, cy0 + cell_h) - max(y0, cy0))
            frac = (ow * oh) / cell_a
            if frac > 0.0:
                scored.append((frac, (ci, ri)))

    touches = [c for f, c in scored if f >= thr]

    if not touches and scored:
        # Object is smaller than a cell / straddles boundaries: keep every cell
        # whose overlap is a meaningful share of the best-covered cell.
        best = max(f for f, _ in scored)
        cut  = best * REL_FALLBACK
        touches = [c for f, c in scored if f >= cut]

    if len(touches) > MAX_TOUCH_CELLS:
        ranked  = sorted(scored, key=lambda s: -s[0])
        keep    = {c for _, c in ranked[:MAX_TOUCH_CELLS]}
        touches = [c for c in touches if c in keep]

    # CENTER = cell containing the bbox centroid; always part of TOUCHES.
    mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    cc = min(COLS - 1, int(mx / cell_w))
    cr = min(ROWS - 1, int(my / cell_h))
    if (cc, cr) not in touches:
        touches.append((cc, cr))
    touches.sort(key=lambda t: (t[1], t[0]))
    return (cc, cr), touches


def _poly_bbox(polygon):
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return [min(xs), min(ys), max(xs), max(ys)]


def _point_in_poly(x, y, polygon):
    """Standard ray-casting point-in-polygon test."""
    inside = False
    n = len(polygon)
    x0, y0 = polygon[-1]
    for i in range(n):
        x1, y1 = polygon[i]
        if ((y1 > y) != (y0 > y)) and \
           (x < (x0 - x1) * (y - y1) / ((y0 - y1) or 1e-9) + x1):
            inside = not inside
        x0, y0 = x1, y1
    return inside


# Sub-samples per cell edge when measuring how much of a cell a polygon
# covers — cheap approximation that avoids pulling in a geometry library
# while still hugging thin/angled objects instead of their bounding box.
POLY_SAMPLES = 5


def polygon_to_cells(polygon, thr=TOUCH_THRESHOLD):
    """Return (center_cell, touches_list) for a normalized polygon
    [[x,y], ...]. Mirrors bbox_to_cells but scores cell coverage by sampling
    points inside each candidate cell against the polygon, so a diagonal or
    thin object only claims the cells it actually occupies."""
    try:
        poly = [(max(0.0, min(1000.0, float(x))), max(0.0, min(1000.0, float(y))))
                for x, y in polygon]
    except (TypeError, ValueError):
        return None, []
    if len(poly) < 3:
        return None, []

    x0, y0, x1, y1 = _poly_bbox(poly)
    if x1 <= x0 or y1 <= y0:
        return None, []

    cell_w = 1000.0 / COLS
    cell_h = 1000.0 / ROWS

    scored = []   # (fraction_of_cell_covered, (ci, ri))
    ci_lo = max(0, int(x0 / cell_w))
    ci_hi = min(COLS - 1, int(x1 / cell_w))
    ri_lo = max(0, int(y0 / cell_h))
    ri_hi = min(ROWS - 1, int(y1 / cell_h))

    for ci in range(ci_lo, ci_hi + 1):
        cx0 = ci * cell_w
        for ri in range(ri_lo, ri_hi + 1):
            cy0 = ri * cell_h
            hits = 0
            for si in range(POLY_SAMPLES):
                sx = cx0 + (si + 0.5) * cell_w / POLY_SAMPLES
                for sj in range(POLY_SAMPLES):
                    sy = cy0 + (sj + 0.5) * cell_h / POLY_SAMPLES
                    if _point_in_poly(sx, sy, poly):
                        hits += 1
            frac = hits / (POLY_SAMPLES * POLY_SAMPLES)
            if frac > 0.0:
                scored.append((frac, (ci, ri)))

    touches = [c for f, c in scored if f >= thr]

    if not touches and scored:
        best = max(f for f, _ in scored)
        cut  = best * REL_FALLBACK
        touches = [c for f, c in scored if f >= cut]

    if len(touches) > MAX_TOUCH_CELLS:
        ranked  = sorted(scored, key=lambda s: -s[0])
        keep    = {c for _, c in ranked[:MAX_TOUCH_CELLS]}
        touches = [c for c in touches if c in keep]

    mx = sum(p[0] for p in poly) / len(poly)
    my = sum(p[1] for p in poly) / len(poly)
    cc = min(COLS - 1, max(0, int(mx / cell_w)))
    cr = min(ROWS - 1, max(0, int(my / cell_h)))
    if (cc, cr) not in touches:
        touches.append((cc, cr))
    touches.sort(key=lambda t: (t[1], t[0]))
    return (cc, cr), touches


def cell_name(c):
    return f"{COL_LABELS[c[0]]}{c[1] + 1}"


CELL_RE = re.compile(r'^([A-Ta-t])(1[01]|[1-9])$')


def parse_cell(txt):
    """'F6' → (5, 5) or None."""
    m = CELL_RE.match(txt.strip())
    if not m:
        return None
    return (ord(m.group(1).upper()) - ord('A'), int(m.group(2)) - 1)


def cells_to_bbox(cells):
    """Synthesise a normalized 0-1000 bbox that encloses a list of (col,row) cells.
    Lets manually-typed objects draw on the image just like detected ones."""
    if not cells:
        return None
    cw = 1000.0 / COLS
    ch = 1000.0 / ROWS
    x0 = min(c[0] for c in cells) * cw
    x1 = (max(c[0] for c in cells) + 1) * cw
    y0 = min(c[1] for c in cells) * ch
    y1 = (max(c[1] for c in cells) + 1) * ch
    return [round(x0), round(y0), round(x1), round(y1)]


def obj_to_line(o):
    """Dict → the OBJECT: line format the planner consumes."""
    aka = o.get('aka', [])
    aka = ", ".join(aka) if isinstance(aka, list) else str(aka)
    return (
        f"OBJECT: {o.get('name','object')}  "
        f"CENTER: {o.get('center','')}  "
        f"TOUCHES: {o.get('touches','')}  "
        f"COLOR: {o.get('color','?')}  "
        f"SIZE: {o.get('size','?')}  "
        f"DESC: {o.get('desc','')}  "
        f"ALSO_KNOWN_AS: {aka}"
    )


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

**Surface-work coverage** — for sweep / mop / apply_soap / apply_cloth, pass the object's FULL TOUCHES list, not just its CENTER. Cleaning one cell of a multi-cell object is a failure. If the task is to clean an object (a plate, a table, a counter), use every cell in that object's TOUCHES field.

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

## 3. Clean a Surface / Countertop / Table (wipe)

The table/counter/desk is itself an object in the OBJECT LIST. Use ITS full TOUCHES
list — every cell of the surface — not just its CENTER.

goto_coordinate = CLOTH_COL, CLOTH_ROW
pickup
apply_cloth(SURFACE_TOUCHES_CELLS...)   # ALL cells the surface touches
goto_coordinate = CLOTH_COL, CLOTH_ROW
keep

If a spray bottle / cleaner object exists, spray first:

goto_coordinate = SPRAY_COL, SPRAY_ROW
pickup
apply_soap(SURFACE_TOUCHES_CELLS...)
goto_coordinate = SPRAY_COL, SPRAY_ROW
keep
# then pick up the cloth and apply_cloth over the same cells

## 3b. Wash Dishes (sink)

Soap goes on the DISHES, using each dish's own TOUCHES cells — a plate that
touches 4 cells needs all 4 soaped, not just its centre.

goto_coordinate = SPONGE_COL, SPONGE_ROW      # or dish soap bottle
pickup
apply_soap(DISH1_TOUCHES...)                  # every cell of dish 1
apply_soap(DISH2_TOUCHES...)                  # every cell of dish 2
...repeat per dish/pan/utensil in the sink
apply_cloth(DISH1_TOUCHES...)                 # scrub/rinse pass, same cells
apply_cloth(DISH2_TOUCHES...)
...
goto_coordinate = SPONGE_COL, SPONGE_ROW
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

Group same-category items together using pickup/keep only. Move objects into the zone one at a time, finishing each object's move before starting the next, then finish with a surface wipe. Do not move appliances or work surfaces during this step — only loose objects.

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

## WORKED EXAMPLE — full-surface wipe

OBJECT LIST contains:
  table   CENTER H6   TOUCHES F4,G4,H4,F5,G5,H5,F6,G6,H6
  cloth   CENTER C9   TOUCHES C9

Task: "Wipe the table."

PLAN:
- wipe table: cloth, table | after: holding nothing

# wipe the whole table surface
1. goto_coordinate = C, 9
2. pickup
3. apply_cloth(F4,G4,H4,F5,G5,H5,F6,G6,H6)
4. goto_coordinate = C, 9
5. keep
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

Then the commands. The FIRST numbered command of every task must be
invoke(Alpha_2D_unstacker) — a fixed initialization step, always written exactly
like that, before any goto_coordinate/pickup/etc:

# brief task description
1. invoke(Alpha_2D_unstacker)
2. command
3. command
...
Task_Completed

Strict: numbered lines contain ONLY commands. No Markdown, no JSON, no explanations, no confidence scores. Task_Completed is always the final line.
"""
)


# ─────────────────────────────────────────────────────────────────────────────
#  Vision worker
# ─────────────────────────────────────────────────────────────────────────────
class VisionWorker(QThread):
    done  = Signal(list)    # list of object dicts (name/center/touches/box/…)
    error = Signal(str)

    def __init__(self, bgr):
        super().__init__()
        self._bgr = bgr

    def run(self):
        try:
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

            objs = []
            for obj in data.get("objects", []):
                polygon = obj.get("polygon")
                if isinstance(polygon, list) and len(polygon) >= 3:
                    center, touches = polygon_to_cells(polygon)
                    box = _poly_bbox(polygon)
                else:
                    # Fallback for older-style bbox-only responses.
                    box = obj.get("box")
                    center, touches = bbox_to_cells(box)
                if center is None:
                    continue
                objs.append({
                    'name':    str(obj.get('name', 'object')).lower(),
                    'center':  cell_name(center),
                    'touches': ",".join(cell_name(t) for t in touches),
                    'color':   obj.get('color', '?'),
                    'size':    obj.get('size', '?'),
                    'desc':    obj.get('desc', ''),
                    'aka':     obj.get('aka', []),
                    'box':     box,
                    'polygon': polygon if isinstance(polygon, list) else None,
                    'surface': bool(obj.get('surface', False)),
                    'source':  'vision',
                })
            if not objs:
                self.error.emit("Vision returned no usable objects.")
                return
            self.done.emit(objs)
        except Exception as e:
            self.error.emit(str(e))


# ─────────────────────────────────────────────────────────────────────────────
#  Command worker
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
            user_msg = f"OBJECT LIST:\n{self._objects}\n\nTask: {self._task}"
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
#  GridOverlay
# ─────────────────────────────────────────────────────────────────────────────
class GridOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._img_rect: 'QRectF | None' = None
        self._bboxes  : list = []

        self._cur_col: float = 0.0
        self._cur_row: float = 0.0
        self._tgt_col: float = 0.0
        self._tgt_row: float = 0.0
        self._speed   : float = 1.0
        self._trail   : list = []

        self._dot_color  = QColor('#60a5fa')
        self._status_txt = ''
        self._cell_lbl   = 'A1'
        self._visible    = False
        self._pulse      = 0.0

        self._anim = QTimer(self)
        self._anim.setInterval(16)
        self._anim.timeout.connect(self._tick)
        self._anim.start()

    def set_speed(self, mult: float):
        self._speed = max(0.25, min(6.0, float(mult)))

    def set_image_rect(self, rect: 'QRectF | None'):
        self._img_rect = rect
        self.update()

    def set_bboxes(self, objects: list):
        self._bboxes = objects or []
        self.update()

    # ── public API ────────────────────────────────────────────────────────────
    def show_dot(self, col: int = 0, row: int = 0):
        self._cur_col = self._tgt_col = float(col)
        self._cur_row = self._tgt_row = float(row)
        self._cell_lbl = f'{chr(ord("A") + col)}{row + 1}'
        self._visible  = True
        self._trail    = []
        self.update()

    def hide_dot(self):
        self._visible    = False
        self._status_txt = ''
        self._trail      = []
        self.update()

    def set_target(self, col: int, row: int):
        self._tgt_col  = float(max(0, min(COLS - 1, col)))
        self._tgt_row  = float(max(0, min(ROWS - 1, row)))
        self._cell_lbl = f'{chr(ord("A") + col)}{row + 1}'

    def set_state(self, color_hex: str, text: str):
        self._dot_color  = QColor(color_hex)
        self._status_txt = text
        self.update()

    # ── animation tick ────────────────────────────────────────────────────────
    def _tick(self):
        if self._visible:
            # Dot glide speed tracks the playback multiplier so fast playback
            # doesn't leave the dot lagging behind its command.
            speed = min(0.9, 0.10 * self._speed)
            dc = self._tgt_col - self._cur_col
            dr = self._tgt_row - self._cur_row
            if abs(dc) > 0.005 or abs(dr) > 0.005:
                self._cur_col += dc * speed
                self._cur_row += dr * speed
                self._trail.append((self._cur_col, self._cur_row))
                if len(self._trail) > 26:
                    self._trail.pop(0)
            else:
                self._cur_col = self._tgt_col
                self._cur_row = self._tgt_row
                if self._trail:
                    self._trail.pop(0)
            self._pulse = (self._pulse + 0.09) % (2 * math.pi)
        self.update()

    # ── coordinate helpers ────────────────────────────────────────────────────
    def _grid_area(self) -> QRectF:
        if self._img_rect is not None:
            return self._img_rect
        return QRectF(0, 0, float(self.width()), float(self.height()))

    def _px(self, col: float, row: float):
        a = self._grid_area()
        return (a.x() + (col + 0.5) * a.width() / COLS,
                a.y() + (row + 0.5) * a.height() / ROWS)

    # ── painting ──────────────────────────────────────────────────────────────
    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        self._paint_grid(p)
        if self._bboxes:
            p.setRenderHint(QPainter.Antialiasing, True)
            self._paint_bboxes(p)
            p.setRenderHint(QPainter.Antialiasing, False)
        if self._visible:
            p.setRenderHint(QPainter.Antialiasing, True)
            self._paint_trail(p)
            self._paint_highlight(p)
            if self._status_txt:
                self._draw_status_pill(p)

    def _paint_grid(self, painter: QPainter):
        area = self._grid_area()
        gx, gy, gw, gh = area.x(), area.y(), area.width(), area.height()
        if gw == 0 or gh == 0:
            return

        LINE = QColor(0, 229, 255, 90)
        painter.setPen(QPen(LINE, 1))
        for i in range(COLS + 1):
            x = round(gx + i * gw / COLS)
            painter.drawLine(x, round(gy), x, round(gy + gh))
        for j in range(ROWS + 1):
            y = round(gy + j * gh / ROWS)
            painter.drawLine(round(gx), y, round(gx + gw), y)

        # Border
        painter.setPen(QPen(QColor(0, 229, 255, 190), 2))
        painter.drawRect(QRectF(gx, gy, gw, gh))

        cw = gw / COLS
        rh = gh / ROWS
        painter.setFont(QFont(UI_FONT, 8, QFont.Bold))
        fm = painter.fontMetrics()
        painter.setPen(QColor(0, 229, 255, 130))
        for i in range(COLS):
            for j in range(ROWS):
                lbl = f'{COL_LABELS[i]}{ROW_LABELS[j]}'
                painter.drawText(round(gx + i * cw + 3),
                                 round(gy + j * rh + fm.ascent() + 2), lbl)

    BBOX_COLORS = [
        QColor(34, 211, 238),  QColor(168, 85, 247), QColor(236, 72, 153),
        QColor(34, 197, 94),   QColor(245, 158, 11), QColor(59, 130, 246),
        QColor(249, 115, 22),  QColor(20, 184, 166),
    ]

    def _paint_bboxes(self, painter: QPainter):
        area = self._grid_area()
        gx, gy, gw, gh = area.x(), area.y(), area.width(), area.height()
        if gw == 0 or gh == 0:
            return
        painter.setFont(QFont(UI_FONT, 9, QFont.Bold))
        fm = painter.fontMetrics()

        for idx, obj in enumerate(self._bboxes):
            polygon = obj.get('polygon')
            box     = obj.get('box')
            if isinstance(polygon, (list, tuple)) and len(polygon) >= 3:
                try:
                    pts = [(max(0.0, min(1000.0, float(x))), max(0.0, min(1000.0, float(y))))
                           for x, y in polygon]
                except (TypeError, ValueError):
                    continue
                xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
                x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
                qpoly = [QPointF(gx + px / 1000.0 * gw, gy + py / 1000.0 * gh) for px, py in pts]
            elif isinstance(box, (list, tuple)) and len(box) == 4:
                try:
                    x0, y0, x1, y1 = [max(0.0, min(1000.0, float(v))) for v in box]
                except (TypeError, ValueError):
                    continue
                if x1 <= x0 or y1 <= y0:
                    continue
                qpoly = None
            else:
                continue

            manual = obj.get('source') == 'manual'
            color  = QColor('#facc15') if manual else self.BBOX_COLORS[idx % len(self.BBOX_COLORS)]

            fill = QColor(color); fill.setAlpha(34)
            painter.setBrush(QBrush(fill))
            pen = QPen(color, 2)
            if manual:
                pen.setStyle(Qt.DashLine)
            painter.setPen(pen)
            if qpoly is not None:
                painter.drawPolygon(QPolygonF(qpoly))
            else:
                rect = QRectF(gx + x0 / 1000.0 * gw, gy + y0 / 1000.0 * gh,
                              (x1 - x0) / 1000.0 * gw, (y1 - y0) / 1000.0 * gh)
                painter.drawRect(rect)

            lbl = obj.get('name', 'object')
            if obj.get('center'):
                lbl += f"  @ {obj['center']}"
            if manual:
                lbl = "✎ " + lbl
            tw = fm.horizontalAdvance(lbl)
            th = fm.height()
            lx = gx + x0 / 1000.0 * gw
            ly = max(gy, gy + y0 / 1000.0 * gh - th - 5)
            painter.setBrush(QBrush(QColor(10, 14, 30, 235)))
            painter.setPen(QPen(color, 1))
            painter.drawRoundedRect(QRectF(lx, ly, tw + 12, th + 4), 5, 5)
            painter.setPen(color)
            painter.drawText(QPointF(lx + 6, ly + 2 + fm.ascent()), lbl)

    def _paint_trail(self, painter: QPainter):
        if len(self._trail) < 2:
            return
        n = len(self._trail)
        for i in range(n - 1):
            x1, y1 = self._px(*self._trail[i])
            x2, y2 = self._px(*self._trail[i + 1])
            a = int(150 * (i / n))
            c = QColor(self._dot_color); c.setAlpha(a)
            painter.setPen(QPen(c, 3, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def _paint_highlight(self, painter: QPainter):
        area = self._grid_area()
        px, py = self._px(self._cur_col, self._cur_row)
        cell_w = area.width()  / COLS
        cell_h = area.height() / ROWS
        r      = min(cell_w, cell_h) * 0.42

        color = self._dot_color
        pulse = math.sin(self._pulse)

        # Cell highlight square under the dot
        ci, ri = int(round(self._cur_col)), int(round(self._cur_row))
        hx = area.x() + ci * cell_w
        hy = area.y() + ri * cell_h
        hc = QColor(color); hc.setAlpha(int(38 + 18 * pulse))
        painter.setBrush(QBrush(hc))
        painter.setPen(QPen(color, 1.4))
        painter.drawRect(QRectF(hx, hy, cell_w, cell_h))

        # Outer glow ring
        glow_r = r * (1.9 + 0.25 * pulse)
        grad   = QRadialGradient(px, py, glow_r)
        gc     = QColor(color); gc.setAlpha(int(70 + 30 * pulse))
        grad.setColorAt(0.0, gc)
        grad.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 0))
        painter.setBrush(QBrush(grad)); painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(px, py), glow_r, glow_r)

        # Main dot
        dc = QColor(color); dc.setAlpha(235)
        painter.setBrush(QBrush(dc)); painter.setPen(QPen(QColor(255, 255, 255, 200), 1.5))
        painter.drawEllipse(QPointF(px, py), r, r)

        # Centre highlight
        hi_r = r * 0.38
        painter.setBrush(QBrush(QColor(255, 255, 255, int(170 + 60 * pulse))))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(px - r * 0.18, py - r * 0.18), hi_r, hi_r)

        # Cell label below dot
        if self._cell_lbl:
            painter.setFont(QFont(UI_FONT, 10, QFont.Bold))
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(self._cell_lbl)
            tx = px - tw / 2
            ty = py + r + fm.ascent() + 3
            painter.setPen(QColor(0, 0, 0, 190))
            painter.drawText(QPointF(tx + 1, ty + 1), self._cell_lbl)
            painter.setPen(QColor(255, 255, 255, 235))
            painter.drawText(QPointF(tx, ty), self._cell_lbl)

    def _draw_status_pill(self, painter: QPainter):
        w, h = self.width(), self.height()
        txt  = self._status_txt
        if self._speed != 1.0:
            txt += f"   ·   {self._speed:g}×"
        painter.setFont(QFont(UI_FONT_B, 12))
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(txt)
        pad_x, pad_y = 20, 8
        bar_w = tw + pad_x * 2
        bar_h = fm.height() + pad_y * 2
        bx    = (w - bar_w) / 2.0
        by    = h - bar_h - 22.0
        rect  = QRectF(bx, by, bar_w, bar_h)

        grad = QLinearGradient(bx, by, bx + bar_w, by)
        grad.setColorAt(0.0, QColor(12, 16, 34, 245))
        grad.setColorAt(1.0, QColor(26, 32, 60, 245))
        painter.setBrush(QBrush(grad))
        bc = QColor(self._dot_color); bc.setAlpha(230)
        painter.setPen(QPen(bc, 2))
        painter.drawRoundedRect(rect, bar_h / 2, bar_h / 2)

        painter.setPen(self._dot_color)
        painter.drawText(QPointF(bx + pad_x, by + pad_y + fm.ascent()), txt)


# ─────────────────────────────────────────────────────────────────────────────
#  CommandRunner  (now speed-aware)
# ─────────────────────────────────────────────────────────────────────────────
class CommandRunner(QObject):
    move_to       = Signal(int, int)
    state_changed = Signal(str, str)
    show_dot      = Signal(int, int)
    hide_dot      = Signal()
    step_info     = Signal(int, int, str)
    finished      = Signal()
    popup_show    = Signal(str)
    popup_hide    = Signal()

    DELAY = {
        'goto': 1300, 'pickup': 950, 'keep': 950, 'drag': 1800, 'rotate': 900,
        'change_orientation': 1100, 'inspect_sides': 1200, 'pour': 1300,
        'sweep': 1500, 'mop': 1500, 'scrub': 1300, 'apply_soap': 900,
        'apply_cloth': 900, 'cook': 2000, 'wash': 1300, 'iron': 1300,
        'fold': 1100, 'open': 800, 'close': 800, 'turn_on': 800,
        'turn_off': 800, 'run_cycle': 1600, 'slice': 1100, 'fill': 1300,
        'clean_bathroom': 2200, 'tidy_up': 1500, 'dust_surfaces': 1200,
        'find': 1000, 'set_state': 600, 'check_state': 600, 'default': 700,
    }
    CELL_STEP = 420   # base ms per cell inside sweep/mop/apply_* lists

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cmds    : list = []
        self._idx     : int  = 0
        self._running : bool = False
        self._speed   : float = 1.0
        self._timer   = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._step)

    # ── speed ─────────────────────────────────────────────────────────────────
    def set_speed(self, mult: float):
        """1.0 = normal. 2.0 = twice as fast. Applies live, mid-playback."""
        self._speed = max(0.25, min(6.0, float(mult)))

    def _scaled(self, ms: int) -> int:
        return max(40, int(ms / self._speed))

    # ── public API ────────────────────────────────────────────────────────────
    def load(self, text: str):
        self._cmds    = self._parse(text)
        self._idx     = 0
        self._running = False

    def start(self):
        if not self._cmds:
            return
        self._running = True
        self._idx     = 0
        self.show_dot.emit(0, 0)
        QTimer.singleShot(self._scaled(250), self._step)

    def stop(self):
        self._running = False
        self._timer.stop()

    # ── cell-list visitor ─────────────────────────────────────────────────────
    def _visit_cells(self, cells: list):
        if not cells or not self._running:
            if self._running:
                self._step()
            return
        col, row = cells[0]
        self.move_to.emit(col, row)
        rest = cells[1:]
        QTimer.singleShot(
            self._scaled(self.CELL_STEP),
            lambda: self._visit_cells(rest) if self._running else None,
        )

    @staticmethod
    def _parse_cells(raw: str) -> list:
        m = re.search(r'\(([^)]+)\)', raw)
        if not m:
            return []
        cells = []
        for token in m.group(1).split(','):
            cm = re.match(r'\s*([A-Ta-t])\s*(\d+)\s*$', token.strip())
            if cm:
                col = max(0, min(COLS - 1, ord(cm.group(1).upper()) - ord('A')))
                row = max(0, min(ROWS - 1, int(cm.group(2)) - 1))
                cells.append((col, row))
        return cells

    @staticmethod
    def _parse(text: str) -> list:
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
                    continue
            if line.startswith('#') or line.upper().startswith('MISSING:'):
                continue
            line = re.sub(r'^\d+\.\s*', '', line)
            if line:
                cmds.append(line)
        return cmds

    # ── execution loop ────────────────────────────────────────────────────────
    def _step(self):
        if not self._running or self._idx >= len(self._cmds):
            return
        cmd = self._cmds[self._idx]
        self._idx += 1
        self.step_info.emit(self._idx, len(self._cmds), cmd)
        delay = self._dispatch(cmd)
        if self._running and delay > 0:
            self._timer.start(self._scaled(delay))

    # ── invoke(...) — cosmetic no-op popup sequence ──────────────────────────
    def _invoke_sequence(self):
        if not self._running:
            return
        self.popup_show.emit('Invoking Alpha 2D unstacker')
        QTimer.singleShot(self._scaled(1000), self._invoke_stage2)

    def _invoke_stage2(self):
        if not self._running:
            return
        self.popup_show.emit('Alpha 2D stacker is unstacking')
        QTimer.singleShot(self._scaled(1000), self._invoke_stage3)

    def _invoke_stage3(self):
        if not self._running:
            return
        self.popup_show.emit('Unstaking is done...')
        QTimer.singleShot(self._scaled(1000), self._invoke_finish)

    def _invoke_finish(self):
        self.popup_hide.emit()
        if self._running:
            self._step()

    def _cells_cmd(self, key: str, raw: str) -> int:
        self.state_changed.emit(*CMD_STATES[key])
        cells = self._parse_cells(raw)
        if cells:
            self._visit_cells(cells)
            return 0
        return self.DELAY[key]

    def _dispatch(self, cmd: str) -> int:
        raw = cmd.strip()

        m = re.match(r'goto_coordinate\s*[:=]?\s*([A-Ta-t])\s*,?\s*(\d{1,2})\b',
                     raw, re.IGNORECASE)
        if m:
            col = max(0, min(COLS - 1, ord(m.group(1).upper()) - ord('A')))
            row = max(0, min(ROWS - 1, int(m.group(2)) - 1))
            self.move_to.emit(col, row)
            self.state_changed.emit(*CMD_STATES['goto'])
            return self.DELAY['goto']
        if raw.lower().startswith('goto_coordinate'):
            print(f"[CommandRunner] Unparsed goto_coordinate: {raw!r}")

        lc = raw.lower().split('(')[0].strip()

        if lc.startswith('invoke'):
            self._invoke_sequence()
            return 0

        if lc in ('pickup', 'keep', 'pour'):
            self.state_changed.emit(*CMD_STATES[lc])
            return self.DELAY[lc]

        if lc in ('sweep', 'mop', 'scrub', 'apply_soap', 'apply_cloth'):
            return self._cells_cmd(lc, raw)

        if lc in ('tidy_up', 'dust_surfaces', 'clean_bathroom'):
            self.state_changed.emit(*CMD_STATES[lc])
            cells = self._parse_cells(raw)
            if cells:
                self._visit_cells(cells)
                return 0
            return self.DELAY[lc]

        for key in ('wash', 'iron', 'fold', 'open', 'close', 'turn_on', 'turn_off',
                    'run_cycle', 'slice', 'fill', 'rotate', 'change_orientation',
                    'inspect_sides', 'cook', 'find', 'set_state', 'check_state'):
            if lc.startswith(key):
                self.state_changed.emit(*CMD_STATES[key])
                return self.DELAY[key]

        if lc.startswith('drag'):
            self.state_changed.emit(*CMD_STATES['drag'])
            m2 = re.search(r'drag\s*\(\s*[^,]+,\s*([A-Ta-t])\s*,\s*(\d+)\s*\)',
                           raw, re.IGNORECASE)
            if m2:
                col = max(0, min(COLS - 1, ord(m2.group(1).upper()) - ord('A')))
                row = max(0, min(ROWS - 1, int(m2.group(2)) - 1))
                self.move_to.emit(col, row)
            return self.DELAY['drag']

        if lc.startswith('wait_for'):
            m2   = re.search(r'(\d+(?:\.\d+)?)', raw)
            secs = float(m2.group(1)) if m2 else 2.0
            self.state_changed.emit(*CMD_STATES['wait_for'])
            return int(secs * 1000)

        if lc == 'task_completed':
            self.state_changed.emit(*CMD_STATES['complete'])
            self._running = False
            hold = self._scaled(2500)
            QTimer.singleShot(hold, lambda: self.hide_dot.emit())
            QTimer.singleShot(hold, lambda: self.finished.emit())
            return 0

        print(f"[CommandRunner] Unparsed command (no handler matched): {raw!r}")
        return self.DELAY['default']


# ─────────────────────────────────────────────────────────────────────────────
#  VideoLabel
# ─────────────────────────────────────────────────────────────────────────────
class VideoLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._overlay = None

    def attach_overlay(self, overlay: GridOverlay):
        self._overlay = overlay
        overlay.setParent(self)
        overlay.resize(self.size())
        overlay.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._overlay:
            self._overlay.resize(self.size())
            self._overlay.raise_()


# ─────────────────────────────────────────────────────────────────────────────
#  UI helpers
# ─────────────────────────────────────────────────────────────────────────────
def _divider():
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFixedHeight(1)
    line.setStyleSheet(f"background:{C_BORDER};border:none;")
    return line


def _field_css(accent=C_BLUE):
    return f"""
        QLineEdit, QPlainTextEdit, QComboBox {{
            background:{C_PANEL_2}; color:{C_TEXT};
            border:1px solid {C_BORDER}; border-radius:9px; padding:5px 9px;
            selection-background-color:{accent};
        }}
        QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{
            border:1px solid {accent};
        }}
        QComboBox::drop-down {{ border:none; width:18px; }}
        QComboBox QAbstractItemView {{
            background:{C_PANEL_2}; color:{C_TEXT};
            selection-background-color:{accent}; border:1px solid {C_BORDER};
        }}
    """


def _grad_btn(text, c1, c2, h=44, fs=12):
    b = QPushButton(text)
    b.setFixedHeight(h)
    b.setCursor(Qt.PointingHandCursor)
    b.setStyleSheet(f"""
        QPushButton {{
            background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {c1}, stop:1 {c2});
            color:#fff; border:none; border-radius:11px;
            font-family:'{UI_FONT}'; font-weight:800; font-size:{fs}px;
            letter-spacing:0.04em;
        }}
        QPushButton:hover {{
            background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {c2}, stop:1 {c1});
        }}
        QPushButton:pressed {{ background:{c2}; }}
        QPushButton:disabled {{ background:#232a44; color:#5b6485; }}
    """)
    return b


def _ghost_btn(text, accent, h=32, fs=10):
    b = QPushButton(text)
    b.setFixedHeight(h)
    b.setCursor(Qt.PointingHandCursor)
    b.setStyleSheet(f"""
        QPushButton {{
            background: rgba(255,255,255,0.04); color:{accent};
            border:1px solid {accent}; border-radius:9px;
            font-family:'{UI_FONT}'; font-weight:700; font-size:{fs}px;
        }}
        QPushButton:hover {{ background:{accent}; color:#0b0f1c; }}
        QPushButton:disabled {{ background:#1b2137; color:#4d5678; border-color:#2c3757; }}
    """)
    return b


class VScrollArea(QScrollArea):
    """Vertical-only scroll area. The inner widget is hard-clamped to the
    viewport width, so nothing can ever push the sidebar into horizontal scroll."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        w = self.widget()
        if w is not None:
            w.setMaximumWidth(self.viewport().width())


class SectionCard(QFrame):
    """A colour-accented container for a block of controls."""
    def __init__(self, title, accent, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background:{C_PANEL};
                border:1px solid {C_BORDER};
                border-left:3px solid {accent};
                border-radius:12px;
            }}
        """)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(10, 8, 10, 10)
        self.body.setSpacing(6)

        t = QLabel(title)
        t.setFont(QFont(UI_FONT, 8, QFont.Bold))
        t.setStyleSheet(f"color:{accent}; letter-spacing:0.14em; border:none; background:transparent;")
        self.body.addWidget(t)

    def add(self, w):
        if isinstance(w, (QHBoxLayout, QVBoxLayout, QGridLayout)):
            self.body.addLayout(w)
        else:
            self.body.addWidget(w)


# ─────────────────────────────────────────────────────────────────────────────
#  AI Sidebar
# ─────────────────────────────────────────────────────────────────────────────
class AISidebar(QWidget):
    request_frame = Signal()
    play_commands = Signal(str)
    stop_commands = Signal()
    boxes_ready   = Signal(list)
    speed_changed = Signal(float)

    SPEEDS = [0.5, 1.0, 1.5, 2.0, 3.0, 4.0]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._vision_objs : list = []
        self._vision_worker  = None
        self._command_worker = None
        self.setMinimumWidth(340)
        self.setMaximumWidth(400)
        self.setStyleSheet(f"background:{C_BG};")
        self._build_ui()
        self._refresh_objects()

    # ── object list ──────────────────────────────────────────────────────────
    @property
    def _all_objs(self):
        return self._vision_objs

    @property
    def _object_list(self) -> str:
        return "\n".join(obj_to_line(o) for o in self._all_objs)

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        hdr = QWidget(); hdr.setFixedHeight(54)
        hdr.setStyleSheet(f"""
            background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #1e1b4b, stop:0.45 #4c1d95, stop:1 #0e7490);
            border-bottom:1px solid {C_BORDER};
        """)
        hl = QHBoxLayout(hdr); hl.setContentsMargins(16, 0, 16, 0); hl.setSpacing(10)
        ico = QLabel("🤖"); ico.setFont(QFont(UI_FONT, 20))
        ico.setStyleSheet("background:transparent;")
        tw = QVBoxLayout(); tw.setSpacing(0)
        ttl = QLabel("ProLabs · Vision A2")
        ttl.setFont(QFont(UI_FONT_B, 12))
        ttl.setStyleSheet("color:#ffffff;background:transparent;")
        sub = QLabel("BBox Vision  +  Manual Entry")
        sub.setFont(QFont(UI_FONT, 8))
        sub.setStyleSheet("color:#a5f3fc;background:transparent;letter-spacing:0.08em;")
        tw.addWidget(ttl); tw.addWidget(sub)
        hl.addWidget(ico); hl.addLayout(tw); hl.addStretch()
        root.addWidget(hdr)

        scroll = VScrollArea()
        scroll.setStyleSheet(f"""
            QScrollArea{{border:none;background:transparent;}}
            QScrollBar:vertical{{background:{C_PANEL};width:8px;margin:0;border-radius:4px;}}
            QScrollBar::handle:vertical{{
                background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 {C_CYAN}, stop:1 {C_VIOLET});
                border-radius:4px;min-height:30px;}}
            QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{height:0;}}
        """)
        body = QWidget(); body.setStyleSheet("background:transparent;")
        bl = QVBoxLayout(body); bl.setContentsMargins(9, 10, 9, 14); bl.setSpacing(9)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # ── AI Instructions ───────────────────────────────────────────────────
        c_instr = SectionCard("AI INSTRUCTIONS · ADD ANYTIME", C_VIOLET)
        row = QHBoxLayout(); row.setSpacing(6)
        self._instr_input = QLineEdit()
        self._instr_input.setPlaceholderText("Type an instruction for the AI…")
        self._instr_input.setFixedHeight(32)
        self._instr_input.setStyleSheet(_field_css(C_VIOLET))
        self._instr_input.returnPressed.connect(self._on_add_instruction)
        add_btn = _ghost_btn("➕ Add", C_VIOLET)
        add_btn.clicked.connect(self._on_add_instruction)
        row.addWidget(self._instr_input, 1); row.addWidget(add_btn)
        c_instr.add(row)

        self._instr_combo = QComboBox()
        self._instr_combo.setFixedHeight(30)
        self._instr_combo.setStyleSheet(_field_css(C_VIOLET))
        # Never let a long instruction string widen the whole sidebar.
        self._instr_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self._instr_combo.setMinimumContentsLength(8)
        self._instr_combo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self._instr_combo.setContextMenuPolicy(Qt.CustomContextMenu)
        self._instr_combo.customContextMenuRequested.connect(self._on_instr_context_menu)
        c_instr.add(self._instr_combo)
        hint = QLabel("right-click an instruction to edit or delete it")
        hint.setWordWrap(True)
        hint.setFont(QFont(UI_FONT, 8))
        hint.setStyleSheet(f"color:{C_TEXT_DIM};background:transparent;border:none;")
        c_instr.add(hint)
        self._instructions = self._load_instructions()
        self._refresh_instr_combo()
        bl.addWidget(c_instr)

        # ── STEP 1 · Vision ───────────────────────────────────────────────────
        c_vis = SectionCard("STEP 1 · VISION ANALYSER", C_CYAN)
        self._capture_btn = _grad_btn("🔍   ANALYSE IMAGE  (VISION AI)", "#0891b2", "#22d3ee", h=38, fs=11)
        self._capture_btn.clicked.connect(self._on_capture)
        c_vis.add(self._capture_btn)
        note = QLabel("Detects every object in the image automatically.")
        note.setWordWrap(True)
        note.setFont(QFont(UI_FONT, 8))
        note.setStyleSheet(f"color:{C_TEXT_DIM};background:transparent;border:none;")
        c_vis.add(note)
        bl.addWidget(c_vis)

        # ── STEP 2 · Task ─────────────────────────────────────────────────────
        c_task = SectionCard("STEP 2 · DESCRIBE YOUR TASK", C_GREEN)
        self._task_input = QPlainTextEdit()
        self._task_input.setPlaceholderText(
            "Examples:\n"
            "  Wash all the dishes in the sink\n"
            "  Wipe down the whole table with the cloth\n"
            "  Collect all toys and stack them at T11")
        self._task_input.setFont(QFont(UI_FONT, 9))
        self._task_input.setFixedHeight(74)
        self._task_input.setStyleSheet(_field_css(C_GREEN))
        c_task.add(self._task_input)

        self._run_btn = _grad_btn("⚡   GENERATE A2 COMMANDS", "#15803d", "#22c55e", h=38, fs=11)
        self._run_btn.setEnabled(False)
        self._run_btn.clicked.connect(self._on_run)
        c_task.add(self._run_btn)

        self._stage_lbl = QLabel("")
        self._stage_lbl.setAlignment(Qt.AlignCenter)
        self._stage_lbl.setWordWrap(True)
        self._stage_lbl.setFont(QFont(UI_FONT, 9))
        self._stage_lbl.setStyleSheet(f"color:{C_CYAN};background:transparent;border:none;padding:2px;")
        c_task.add(self._stage_lbl)
        bl.addWidget(c_task)

        # ── Detected objects ──────────────────────────────────────────────────
        c_obj = SectionCard("OBJECT LIST  ·  VISION + MANUAL", C_BLUE)
        self._scene_box = QTextEdit()
        self._scene_box.setReadOnly(True)
        self._scene_box.setFixedHeight(260)
        self._scene_box.setLineWrapMode(QTextEdit.WidgetWidth)
        self._scene_box.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scene_box.setStyleSheet(f"""
            QTextEdit{{background:{C_PANEL_2};color:{C_TEXT};
                border:1px solid {C_BORDER};border-radius:9px;padding:6px;}}
            QScrollBar:vertical{{background:{C_PANEL};width:7px;border-radius:3px;}}
            QScrollBar::handle:vertical{{background:{C_BLUE};border-radius:3px;}}
        """)
        c_obj.add(self._scene_box)
        bl.addWidget(c_obj)

        # ── Commands ──────────────────────────────────────────────────────────
        c_cmd = SectionCard("A2 EXECUTION COMMANDS", C_PINK)
        self._cmd_box = QPlainTextEdit()
        self._cmd_box.setReadOnly(True)
        self._cmd_box.setFont(QFont(MONO_FONT, 9))
        self._cmd_box.setFixedHeight(180)
        self._cmd_box.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self._cmd_box.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._cmd_box.setStyleSheet(f"""
            QPlainTextEdit{{background:#12172b;color:#86efac;
                border:1px solid #2c3757;border-radius:9px;padding:6px;}}
            QScrollBar:vertical{{background:{C_PANEL};width:7px;border-radius:3px;}}
            QScrollBar::handle:vertical{{background:{C_PINK};border-radius:3px;}}
        """)
        self._cmd_box.setPlaceholderText("Numbered command sequence will stream here…")
        c_cmd.add(self._cmd_box)

        crow = QHBoxLayout(); crow.setSpacing(6)
        copy_btn  = _ghost_btn("📋  Copy",  C_GREEN, h=29)
        clear_btn = _ghost_btn("🗑  Clear all", C_RED, h=29)
        copy_btn.clicked.connect(
            lambda: QApplication.clipboard().setText(self._cmd_box.toPlainText()))
        clear_btn.clicked.connect(self._clear_all)
        crow.addWidget(copy_btn, 1); crow.addWidget(clear_btn, 1)
        c_cmd.add(crow)
        bl.addWidget(c_cmd)

        # ── STEP 3 · Playback + speed ─────────────────────────────────────────
        c_play = SectionCard("STEP 3 · PHYSICAL SIMULATION", C_CYAN)

        prow = QHBoxLayout(); prow.setSpacing(8)
        self._play_btn = _grad_btn("▶   PLAY", "#1d4ed8", "#3b82f6", h=36, fs=11)
        self._play_btn.setEnabled(False)
        self._play_btn.clicked.connect(self._on_play)
        self._stop_btn = _grad_btn("■  STOP", "#991b1b", "#ef4444", h=36, fs=11)
        self._stop_btn.setFixedWidth(82)
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._on_stop)
        prow.addWidget(self._play_btn, 1); prow.addWidget(self._stop_btn)
        c_play.add(prow)

        # Speed control
        srow = QHBoxLayout(); srow.setSpacing(8)
        slbl = QLabel("SPEED")
        slbl.setFont(QFont(UI_FONT, 8, QFont.Bold))
        slbl.setStyleSheet(f"color:{C_TEXT_DIM};background:transparent;border:none;letter-spacing:0.12em;")
        self._speed_slider = QSlider(Qt.Horizontal)
        self._speed_slider.setMinimum(0)
        self._speed_slider.setMaximum(len(self.SPEEDS) - 1)
        self._speed_slider.setValue(self.SPEEDS.index(1.0))
        self._speed_slider.setPageStep(1)
        self._speed_slider.setCursor(Qt.PointingHandCursor)
        self._speed_slider.setStyleSheet(f"""
            QSlider::groove:horizontal{{
                height:6px;border-radius:3px;
                background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {C_BLUE}, stop:0.5 {C_VIOLET}, stop:1 {C_PINK});}}
            QSlider::handle:horizontal{{
                background:#ffffff;border:2px solid {C_CYAN};
                width:16px;height:16px;margin:-6px 0;border-radius:9px;}}
            QSlider::handle:horizontal:hover{{border-color:{C_PINK};}}
        """)
        self._speed_slider.valueChanged.connect(self._on_speed_change)
        self._speed_lbl = QLabel("1×")
        self._speed_lbl.setFixedWidth(42)
        self._speed_lbl.setAlignment(Qt.AlignCenter)
        self._speed_lbl.setFont(QFont(MONO_FONT, 11, QFont.Bold))
        self._speed_lbl.setStyleSheet(
            f"color:{C_CYAN};background:{C_PANEL_2};border:1px solid {C_BORDER};"
            f"border-radius:7px;padding:3px;")
        srow.addWidget(slbl); srow.addWidget(self._speed_slider, 1); srow.addWidget(self._speed_lbl)
        c_play.add(srow)

        shint = QLabel("Speed applies live — drag it mid-playback. 0.5× … 4×")
        shint.setWordWrap(True)
        shint.setFont(QFont(UI_FONT, 8))
        shint.setStyleSheet(f"color:{C_TEXT_DIM};background:transparent;border:none;")
        c_play.add(shint)

        self._step_lbl = QLabel("")
        self._step_lbl.setAlignment(Qt.AlignCenter)
        self._step_lbl.setWordWrap(True)
        self._step_lbl.setFont(QFont(MONO_FONT, 9))
        self._step_lbl.setStyleSheet(f"color:{C_TEXT_DIM};background:transparent;border:none;padding:2px;")
        c_play.add(self._step_lbl)
        bl.addWidget(c_play)

        # ── Legend ────────────────────────────────────────────────────────────
        c_leg = SectionCard("HIGHLIGHT COLOUR LEGEND", C_TEXT_DIM)
        c_leg.add(self._legend())
        bl.addWidget(c_leg)

        bl.addStretch()

    @staticmethod
    def _legend():
        w = QWidget(); w.setStyleSheet("background:transparent;border:none;")
        g = QGridLayout(w); g.setContentsMargins(0, 2, 0, 2)
        g.setHorizontalSpacing(10); g.setVerticalSpacing(4)
        entries = [
            ('#60a5fa', 'goto — moving'),      ('#22c55e', 'pickup — grasp'),
            ('#facc15', 'keep — place'),       ('#22d3ee', 'pour — pouring'),
            ('#e2e8f0', 'apply_soap'),         ('#d4b483', 'apply_cloth'),
            ('#fb923c', 'sweep'),              ('#7dd3fc', 'mop'),
            ('#c084fc', 'fold'),               ('#ffd700', 'Task_Completed'),
        ]
        for i, (hexc, label) in enumerate(entries):
            row = QHBoxLayout(); row.setSpacing(6)
            dot = QLabel(); dot.setFixedSize(10, 10)
            dot.setStyleSheet(f"background:{hexc};border-radius:5px;border:none;")
            txt = QLabel(label)
            txt.setFont(QFont(MONO_FONT, 8))
            txt.setStyleSheet(f"color:{C_TEXT_DIM};background:transparent;border:none;")
            row.addWidget(dot); row.addWidget(txt); row.addStretch()
            holder = QWidget(); holder.setStyleSheet("background:transparent;border:none;")
            holder.setLayout(row)
            g.addWidget(holder, i // 2, i % 2)
        return w

    # ── state helpers ─────────────────────────────────────────────────────────
    def _lock(self, locked: bool):
        self._capture_btn.setEnabled(not locked)
        self._run_btn.setEnabled(not locked and bool(self._all_objs))

    def _set_stage(self, text: str, color=C_CYAN):
        self._stage_lbl.setText(text)
        self._stage_lbl.setStyleSheet(
            f"color:{color};background:transparent;border:none;padding:2px;")

    def _clear_all(self):
        self._vision_objs = []
        self._cmd_box.clear()
        self._play_btn.setEnabled(False)
        self._stop_btn.setEnabled(False)
        self._step_lbl.setText("")
        self._set_stage("")
        self._refresh_objects()
        self.stop_commands.emit()

    # ── speed ─────────────────────────────────────────────────────────────────
    def _on_speed_change(self, idx: int):
        mult = self.SPEEDS[idx]
        self._speed_lbl.setText(f"{mult:g}×")
        self.speed_changed.emit(mult)

    # ── instructions ──────────────────────────────────────────────────────────
    @staticmethod
    def _load_instructions() -> list:
        try:
            with open(INSTRUCTIONS_FILE, "r") as f:
                data = json.load(f)
            return [s for s in data if isinstance(s, str)]
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return []

    def _save_instructions(self):
        try:
            with open(INSTRUCTIONS_FILE, "w") as f:
                json.dump(self._instructions, f, indent=2)
        except OSError:
            pass

    def _refresh_instr_combo(self):
        self._instr_combo.clear()
        if not self._instructions:
            self._instr_combo.addItem("No instructions added yet")
            self._instr_combo.setEnabled(False)
        else:
            self._instr_combo.setEnabled(True)
            for s in self._instructions:
                self._instr_combo.addItem(s)
            self._instr_combo.setCurrentIndex(len(self._instructions) - 1)

    def _on_add_instruction(self):
        text = self._instr_input.text().strip()
        if not text:
            return
        self._instructions.append(text)
        self._save_instructions()
        self._refresh_instr_combo()
        self._instr_input.clear()

    def _on_instr_context_menu(self, pos):
        if not self._instructions:
            return
        idx = self._instr_combo.currentIndex()
        if idx < 0 or idx >= len(self._instructions):
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu{{background:{C_PANEL_2};color:{C_TEXT};border:1px solid {C_BORDER};}}"
            f"QMenu::item:selected{{background:{C_RED};}}")
        edit_act = menu.addAction("✏️  Edit")
        del_act  = menu.addAction("🗑  Delete")
        chosen = menu.exec(self._instr_combo.mapToGlobal(pos))
        if chosen == del_act:
            self._confirm_delete_instruction(idx)
        elif chosen == edit_act:
            self._edit_instruction(idx)

    def _edit_instruction(self, idx: int):
        current = self._instructions[idx]
        new_text, ok = QInputDialog.getText(
            self, "Edit Instruction", "Instruction:", text=current)
        if not ok:
            return
        new_text = new_text.strip()
        if not new_text:
            return
        self._instructions[idx] = new_text
        self._save_instructions()
        self._refresh_instr_combo()
        self._instr_combo.setCurrentIndex(idx)

    def _confirm_delete_instruction(self, idx: int):
        text = self._instructions[idx]
        if QMessageBox.question(
            self, "Delete Instruction", f'Delete this instruction?\n\n"{text}"',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) == QMessageBox.Yes:
            del self._instructions[idx]
            self._save_instructions()
            self._refresh_instr_combo()

    # ── unified object refresh ────────────────────────────────────────────────
    def _refresh_objects(self):
        self._scene_box.setHtml(self._format_objects_html(self._all_objs))
        self._run_btn.setEnabled(bool(self._all_objs))
        self.boxes_ready.emit([o for o in self._all_objs if o.get('box')])

    @staticmethod
    def _format_objects_html(objs: list) -> str:
        if not objs:
            return (f'<div style="color:{C_TEXT_DIM};font-family:\'{UI_FONT}\';font-size:10px;'
                    f'padding:10px;">No objects yet — run the vision analyser.</div>')
        SIZE_COLOR = {'small': '#94a3b8', 'medium': '#60a5fa', 'large': '#c084fc'}
        cards = []
        for o in objs:
            manual   = o.get('source') == 'manual'
            accent   = '#facc15' if manual else '#38bdf8'
            badge    = '✎ MANUAL' if manual else '👁 VISION'
            size     = str(o.get('size', '?')).lower()
            size_clr = SIZE_COLOR.get(size, '#94a3b8')
            aka      = o.get('aka', [])
            aka      = aka if isinstance(aka, list) else [aka]
            aka_html = ''
            if aka:
                tags = ''.join(
                    f'<span style="background:#243050;color:#94a3b8;'
                    f'border:1px solid #33406b;border-radius:3px;padding:1px 5px;'
                    f'margin-right:4px;font-size:9px;">{str(t).strip()}</span>'
                    for t in aka if str(t).strip())
                aka_html = f'<div style="margin-top:4px;">{tags}</div>'
            touches = o.get('touches', '')
            ncells  = len(touches.split(',')) if touches else 0
            cards.append(
                f'<div style="background:#1d2540;border:1px solid #2c3757;'
                f'border-left:3px solid {accent};border-radius:7px;'
                f'padding:8px 10px;margin-bottom:6px;">'
                f'<div><span style="color:#e8ecf8;font-weight:700;font-size:11px;'
                f'font-family:\'{UI_FONT}\';">{str(o.get("name","object")).title()}</span>'
                f'<span style="color:{accent};font-size:8px;font-family:{MONO_FONT};'
                f'float:right;">{badge}</span></div>'
                f'<div style="margin-top:4px;">'
                f'<span style="background:#0e7490;color:#cffafe;border-radius:3px;'
                f'padding:1px 6px;font-size:9px;font-family:{MONO_FONT};margin-right:5px;">'
                f'&#127919; {o.get("center","?")}</span>'
                f'<span style="background:#3b2f0b;color:#fcd34d;border-radius:3px;'
                f'padding:1px 6px;font-size:9px;font-family:{MONO_FONT};margin-right:5px;">'
                f'&#9632; {o.get("color","?")}</span>'
                f'<span style="background:#243050;color:{size_clr};border-radius:3px;'
                f'padding:1px 6px;font-size:9px;font-family:{MONO_FONT};">{size}</span>'
                f'</div>'
                + (f'<div style="color:#8b97b8;font-size:9px;font-family:{MONO_FONT};'
                   f'margin-top:4px;">&#128205; {ncells} cells: {touches}</div>'
                   if touches else '')
                + (f'<div style="color:#94a3b8;font-size:9px;font-family:\'{UI_FONT}\';'
                   f'margin-top:4px;line-height:1.4;">{o.get("desc","")}</div>'
                   if o.get('desc') else '')
                + aka_html + '</div>'
            )
        nv = sum(1 for o in objs if o.get('source') != 'manual')
        nm = len(objs) - nv
        header = (f'<div style="color:#38bdf8;font-family:\'{UI_FONT}\';font-size:9px;'
                  f'letter-spacing:0.05em;margin-bottom:8px;">'
                  f'{len(objs)} OBJECTS  ·  {nv} vision  ·  {nm} manual</div>')
        return header + ''.join(cards)

    # ── vision flow ───────────────────────────────────────────────────────────
    def _on_capture(self):
        self._lock(True)
        self._play_btn.setEnabled(False)
        self._set_stage("🔍  Sending image for bbox detection…")
        self._cmd_box.clear()
        self.request_frame.emit()

    def feed_frame(self, bgr):
        if bgr is None:
            self._lock(False)
            self._set_stage("⚠️  No image loaded — click  📁 Import Image  first", C_RED)
            return
        self._set_stage("🔍  Detecting objects (bbox)…")
        self._vision_worker = VisionWorker(bgr)
        self._vision_worker.done.connect(self._on_vision_done)
        self._vision_worker.error.connect(self._on_error)
        self._vision_worker.start()

    def _on_vision_done(self, objs: list):
        self._vision_objs = objs
        self._refresh_objects()
        self._lock(False)
        self._set_stage(f"✅  {len(objs)} objects detected — enter a task and hit ⚡", C_GREEN)

    # ── generate commands ─────────────────────────────────────────────────────
    def _on_run(self):
        task = self._task_input.toPlainText().strip()
        if not task:
            self._set_stage("⚠️  Please describe a task first", C_RED); return
        if not self._all_objs:
            self._set_stage("⚠️  Add objects first (vision or manual)", C_RED); return
        self._lock(True)
        self._play_btn.setEnabled(False)
        self._cmd_box.clear()
        self._set_stage("⚡  Generating command sequence…")
        if self._instructions:
            notes = "\n".join(f"- {s}" for s in self._instructions)
            task  = f"{task}\n\nADDITIONAL AI INSTRUCTIONS (apply throughout):\n{notes}"
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
        self._set_stage("✅  Commands ready — press ▶ PLAY", C_GREEN)

    def _on_error(self, err: str):
        self._lock(False)
        self._set_stage(f"⚠️  {err[:140]}", C_RED)

    # ── play / stop ───────────────────────────────────────────────────────────
    def _on_play(self):
        text = self._cmd_box.toPlainText().strip()
        if not text:
            return
        self._play_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._step_lbl.setText("Starting…")
        self._set_stage("▶  Simulating on grid…")
        self.play_commands.emit(text)

    def _on_stop(self):
        self.stop_commands.emit()
        self._play_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._step_lbl.setText("")
        self._set_stage("■  Stopped", C_TEXT_DIM)

    def on_runner_finished(self):
        self._play_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._set_stage("✅  Playback complete", C_GREEN)
        self._step_lbl.setText("")

    def on_runner_step(self, current: int, total: int, cmd: str):
        m = re.match(r'goto_coordinate\s*=\s*([A-Ta-t])\s*,\s*(\d+)', cmd.strip())
        coord = f"  →  {m.group(1).upper()}{m.group(2)}" if m else ""
        short = cmd if len(cmd) <= 58 else cmd[:55] + "…"
        self._step_lbl.setText(f"Step {current}/{total}  ·  {short}{coord}")


# ─────────────────────────────────────────────────────────────────────────────
#  Image panel
# ─────────────────────────────────────────────────────────────────────────────
class CameraPanel(QWidget):
    runner_finished = Signal()

    def __init__(self, sidebar: AISidebar, parent=None):
        super().__init__(parent)
        self._sidebar   = sidebar
        self._raw_image = None
        self.setStyleSheet(f"background:{C_BG};")
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)

        # ── Top bar ───────────────────────────────────────────────────────────
        bar = QWidget(); bar.setFixedHeight(48)
        bar.setStyleSheet(f"""
            background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #0e7490, stop:0.5 #4c1d95, stop:1 #1e1b4b);
            border-bottom:1px solid {C_BORDER};
        """)
        bl = QHBoxLayout(bar); bl.setContentsMargins(16, 0, 16, 0); bl.setSpacing(12)

        brand = QLabel("A2  PHYSICAL SIMULATOR  ·  HOS")
        brand.setFont(QFont(UI_FONT_B, 11))
        brand.setStyleSheet("color:#ffffff;background:transparent;letter-spacing:0.1em;")

        self._import_btn = QPushButton("📁  Import Image")
        self._import_btn.setFixedHeight(30)
        self._import_btn.setCursor(Qt.PointingHandCursor)
        self._import_btn.setStyleSheet(f"""
            QPushButton{{background:rgba(255,255,255,0.14);color:#ffffff;
                border:1px solid rgba(255,255,255,0.35);border-radius:8px;
                font-family:'{UI_FONT}';font-weight:700;font-size:10px;padding:0 14px;}}
            QPushButton:hover{{background:#ffffff;color:#1e1b4b;}}
        """)
        self._import_btn.clicked.connect(self._import_image)

        self._status = QLabel("● No image loaded")
        self._status.setFont(QFont(UI_FONT, 9))
        self._status.setStyleSheet("color:#c7d2fe;background:transparent;")

        hint = QLabel("F11 fullscreen  ·  Esc exit")
        hint.setFont(QFont(UI_FONT, 8))
        hint.setStyleSheet("color:rgba(255,255,255,0.55);background:transparent;")

        bl.addWidget(brand); bl.addStretch()
        bl.addWidget(hint); bl.addWidget(self._import_btn); bl.addWidget(self._status)
        lay.addWidget(bar)

        # ── Image display ─────────────────────────────────────────────────────
        self._overlay = GridOverlay()
        self._video   = VideoLabel()
        self._video.setAlignment(Qt.AlignCenter)
        self._video.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._video.attach_overlay(self._overlay)
        lay.addWidget(self._video, 1)

        self._video.setText(
            "📁   Click  Import Image  to load a photo\n\n"
            "JPG · PNG · BMP · TIFF · WEBP")
        self._video.setFont(QFont(UI_FONT, 14))
        self._video.setStyleSheet(f"background:{C_BG};color:#44507a;")
        self._overlay.set_image_rect(None)

        # ── Big invoke popup (floats over the video area) ───────────────────────
        self._popup = QLabel(self)
        self._popup.setAlignment(Qt.AlignCenter)
        self._popup.setWordWrap(True)
        self._popup.setFont(QFont(UI_FONT_B, 18))
        self._popup.setStyleSheet(f"""
            QLabel {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 #2e1065, stop:1 #4c1d95);
                color:#f5f3ff;
                border: 2px solid {C_VIOLET};
                border-radius: 18px;
                padding: 26px 40px;
            }}
        """)
        self._popup.hide()
        self._popup.raise_()

        # ── Runner ────────────────────────────────────────────────────────────
        self._runner = CommandRunner()
        self._runner.move_to.connect(self._overlay.set_target)
        self._runner.state_changed.connect(self._overlay.set_state)
        self._runner.show_dot.connect(self._overlay.show_dot)
        self._runner.hide_dot.connect(self._overlay.hide_dot)
        self._runner.finished.connect(self.runner_finished.emit)
        self._runner.popup_show.connect(self._show_popup)
        self._runner.popup_hide.connect(self._popup.hide)

        # ── Sidebar wiring ────────────────────────────────────────────────────
        sidebar.request_frame.connect(self._deliver_frame)
        sidebar.play_commands.connect(self.run_commands)
        sidebar.stop_commands.connect(self.stop_commands)
        sidebar.boxes_ready.connect(self._overlay.set_bboxes)
        sidebar.speed_changed.connect(self._on_speed)

    def _on_speed(self, mult: float):
        self._runner.set_speed(mult)
        self._overlay.set_speed(mult)

    # ── image import ──────────────────────────────────────────────────────────
    def _import_image(self):
        downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        start_dir = downloads if os.path.isdir(downloads) else os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Image", start_dir,
            "Images (*.jpg *.jpeg *.png *.bmp *.tiff *.tif *.webp);;All Files (*)")
        if not path:
            return
        bgr = cv2.imread(path)
        if bgr is None:
            self._status.setText("⚠️  Could not read file")
            self._status.setStyleSheet("color:#fca5a5;background:transparent;")
            return
        self._raw_image = bgr
        self._show_image(bgr)
        self._status.setText(f"● {os.path.basename(path)}")
        self._status.setStyleSheet("color:#86efac;background:transparent;")

    def _show_image(self, bgr):
        rgb  = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        qi   = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888).copy()
        lw   = self._video.width()  or 1280
        lh   = self._video.height() or 720
        pix  = QPixmap.fromImage(qi).scaled(lw, lh, Qt.KeepAspectRatio,
                                            Qt.SmoothTransformation)
        ox = (lw - pix.width())  / 2.0
        oy = (lh - pix.height()) / 2.0
        self._overlay.set_image_rect(QRectF(ox, oy, pix.width(), pix.height()))
        self._video.setText("")
        self._video.setPixmap(pix)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._raw_image is not None:
            self._show_image(self._raw_image)
        if self._popup.isVisible():
            self._center_popup()

    def _show_popup(self, text: str):
        self._popup.setText(text)
        self._popup.adjustSize()
        self._center_popup()
        self._popup.show()
        self._popup.raise_()

    def _center_popup(self):
        w = max(self._popup.width(),  int(self.width()  * 0.4))
        h = max(self._popup.height(), 90)
        self._popup.resize(w, h)
        self._popup.move((self.width() - w) // 2, (self.height() - h) // 2)

    def _deliver_frame(self):
        self._sidebar.feed_frame(self._raw_image)

    def run_commands(self, text: str):
        self._runner.load(text)
        self._runner.start()

    def stop_commands(self):
        self._runner.stop()
        self._overlay.hide_dot()


# ─────────────────────────────────────────────────────────────────────────────
#  Main window
# ─────────────────────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Humanoid Operating System – A2 Physical Simulator")
        self.setMinimumSize(1100, 680)
        pal = QPalette()
        pal.setColor(QPalette.Window, QColor(C_BG))
        pal.setColor(QPalette.WindowText, QColor(C_TEXT))
        self.setPalette(pal)
        self.setStyleSheet(f"QMainWindow{{background:{C_BG};}}")

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet(f"""
            QSplitter::handle{{
                background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 {C_CYAN}, stop:0.5 {C_VIOLET}, stop:1 {C_PINK});}}
        """)

        self._sidebar   = AISidebar()
        self._cam_panel = CameraPanel(self._sidebar)

        self._cam_panel.runner_finished.connect(self._sidebar.on_runner_finished)
        self._cam_panel._runner.step_info.connect(self._sidebar.on_runner_step)

        splitter.addWidget(self._cam_panel)
        splitter.addWidget(self._sidebar)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)

        # Fullscreen by default, with F11 toggle and Esc to leave.
        QShortcut(QKeySequence("F11"), self, activated=self._toggle_fullscreen)
        QShortcut(QKeySequence("Esc"), self, activated=self._leave_fullscreen)

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showMaximized()
        else:
            self.showFullScreen()

    def _leave_fullscreen(self):
        if self.isFullScreen():
            self.showMaximized()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    dark = QPalette()
    dark.setColor(QPalette.Window,        QColor(C_BG))
    dark.setColor(QPalette.WindowText,    QColor(C_TEXT))
    dark.setColor(QPalette.Base,          QColor(C_PANEL_2))
    dark.setColor(QPalette.AlternateBase, QColor(C_PANEL))
    dark.setColor(QPalette.Text,          QColor(C_TEXT))
    dark.setColor(QPalette.Button,        QColor(C_PANEL))
    dark.setColor(QPalette.ButtonText,    QColor(C_TEXT))
    dark.setColor(QPalette.Highlight,     QColor(C_BLUE))
    dark.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    dark.setColor(QPalette.ToolTipBase,   QColor(C_PANEL_2))
    dark.setColor(QPalette.ToolTipText,   QColor(C_TEXT))
    app.setPalette(dark)

    win = MainWindow()
    win.showFullScreen()          # ← opens fullscreen by default
    sys.exit(app.exec())

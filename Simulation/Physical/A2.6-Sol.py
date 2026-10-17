import sys, os, base64, re, math, json, html, io, wave, time, shutil, hashlib
import cv2
import numpy as np
from openai import OpenAI

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QScrollArea, QSizePolicy,
    QSplitter, QPlainTextEdit, QTextEdit, QFrame, QFileDialog,
    QComboBox, QLineEdit, QMessageBox, QMenu, QSlider, QListWidget,
    QListWidgetItem, QGridLayout, QInputDialog, QCheckBox, QDialog,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
)
from PySide6.QtCore  import (Qt, Signal, QTimer, QObject, QPointF, QRectF, QThread,
                              QSize, QPropertyAnimation, QEasingCurve, QEvent, QUrl,
                              QEventLoop)
from PySide6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices
# Imported up here, before any QApplication exists, because QtWebEngine has to
# claim its shared OpenGL context first or it refuses to start later.
try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
    WEBVIEW_IMPORT_ERROR = ""
except Exception as _web_err:
    QWebEngineView = QWebEnginePage = QWebEngineProfile = None
    WEBVIEW_IMPORT_ERROR = str(_web_err)
import PySide6                       # version is named in mic diagnostics
from PySide6.QtGui   import (QImage, QPixmap, QFont, QColor, QPalette,
                              QTextCursor, QPainter, QPen, QBrush, QRadialGradient,
                              QKeySequence, QShortcut, QLinearGradient, QPolygonF,
                              QPainterPath, QFontMetrics, QIcon, QAction,
                              QDesktopServices)

# ─────────────────────────────────────────────────────────────────────────────
OPENAI_API_KEY = (
    "ADD YOUR OPENAI API KEY HERE"
)

VISION_MODEL    = "gpt-5.4"
DEXTERITY_MODEL = "gpt-5.4-mini"
PLANNER_MODEL   = "gpt-5.6-terra"
VOICE_TIDY_MODEL = "gpt-5.4-nano"
SPEECH_MODEL     = "gpt-4o-transcribe"

# Custom instructions live in this file rather than a sidecar JSON: the app
# rewrites the block below in place when you edit them in the UI. Keep the
# assignment on its own line with the closing bracket in column 0 — the
# rewrite finds it by shape. Editing it by hand is fine; that is the point.
AI_INSTRUCTIONS = [
    "If you have more than one plate in the frame where you have to apply soap, apply soap one by one to each.",
    "while boiling, always add water before the thing which has to get boiled",
]

# Matches the block above and nothing else: anchored at column 0, and the
# escaped bracket keeps this very line from matching itself.
INSTRUCTIONS_RE = re.compile(r"^AI_INSTRUCTIONS = \[.*?^\]\n", re.S | re.M)

# ─────────────────────────────────────────────────────────────────────────────
#  Cross-platform fonts
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
TOUCH_THRESHOLD = 0.30
REL_FALLBACK    = 0.45
PADDING_KEEP_MIN = 0.55   # polygon area that must lie inside the real photo
MAX_TOUCH_CELLS = 48          # ceiling on cells any one object may claim
POLY_SAMPLES    = 5           # sub-samples per cell edge when scoring coverage

# ── Vision pre-processing ────────────────────────────────────────────────────
IMG_MAX_SIDE = 1536           # longest side sent to the API (post-letterbox)
RULER_FRAC   = 0.075          # ruler margin as a fraction of the content square

# ── CV localisation (OPTIONAL) ───────────────────────────────────────────────
# Segmentation-based snapping is available but DEFAULT OFF, because it only
# works when objects contrast cleanly with what they rest on. On real photos —
# soft shadows welded to an object's base, a white plate on a white counter,
# gradient lighting, textured worktops — a border-sampled background estimate
# either misses objects entirely or swallows their shadows, and a confidently
# wrong contour is worse than an approximate one. The model's own outlines,
# measured against the ruler canvas, are the default source of position.
#
# Turn snapping on per-import from the sidebar when the scene suits it: clean,
# well-separated objects on a plain contrasting background.
#
# Background REJECTION is separate and always on: it needs no segmentation,
# only the observation that an object covering most of the frame is the scene
# rather than a thing in it.
SNAP_DEFAULT_ON   = False   # CV snapping is OPT-IN — see note below
SEG_BORDER_FRAC   = 0.045   # border ring sampled to estimate the background
SEG_MIN_AREA_FRAC = 0.0016  # blobs smaller than this fraction of frame → noise
SEG_MAX_AREA_FRAC = 0.55    # blobs bigger than this are background, not objects
SEG_CLOSE_FRAC    = 0.012   # morphological kernel as a fraction of the frame
SNAP_MIN_SCORE    = 0.07    # below this the model polygon is kept unsnapped
SNAP_AMBIG_RATIO  = 0.80    # 2nd-best this close to best → too ambiguous to snap
SNAP_MAX_TRAVEL   = 0.42    # a snap may not move a centroid further than this
BG_REJECT_FRAC    = 0.55    # model polygons bigger than this are background
BG_FOREGROUND_MIN = 0.10    # ...or that contain almost no foreground pixels
# Span alone cannot separate a countertop from a bed — photographed head-on
# they are the same shape. What separates them is the NAME the model chose:
# the prompt already forbids reporting surfaces, so a large entry that comes
# back named "bed" or "sofa" is a deliberate identification of the subject,
# not a backdrop leaking through. Rejecting those on span alone left "make the
# bed" and "wash the car" with no object to act on at all.
#
# So the span rule below is unchanged for every name; it is only waived for
# this list, and even then only when the outline is self-contained (does not
# run off BG_EDGE_MIN_TOUCH sides of the frame, the way a real backdrop does).
BG_EDGE_TOL       = 0.02    # within 2% of a frame edge counts as touching it
BG_EDGE_MIN_TOUCH = 3       # sides a waived object still may not exceed
BG_ABSOLUTE_MAX   = 0.92    # nothing this large is ever a manipulable object
LARGE_SUBJECTS    = (
    "bed", "mattress", "bunk", "crib", "cot", "sofa", "couch", "loveseat",
    "futon", "armchair", "recliner", "car", "vehicle", "truck", "van",
    "bicycle", "motorcycle", "wheelchair", "stroller", "pram", "mower",
    "piano", "wardrobe", "bookcase", "bookshelf", "dresser", "refrigerator",
    "fridge", "freezer", "washing machine", "washer", "dryer", "dishwasher",
    "oven", "stove", "range", "treadmill", "sunbed", "hammock", "tent",
)
VERIFY_MAX_TRAVEL = 0.25    # pass-2 may not move a centroid further than this
UNKNOWN_MIN_AREA  = 0.006   # unmatched blob must be this big to be reported

# ── Theme ─────────────────────────────────────────────────────────────────────
# A calm, light glass surface.  Qt widgets cannot use backdrop-filter, but
# translucent whites, fine borders and soft shadows create the same hierarchy
# without sacrificing legibility on platforms that do not composite blur.
C_BG        = "#eef4ff"
C_PANEL     = "rgba(255,255,255,0.78)"
C_PANEL_2   = "#f8fbff"
C_BORDER    = "#d8e3f2"
C_TEXT      = "#172033"
C_TEXT_DIM  = "#66738a"
C_CYAN      = "#0891b2"
C_BLUE      = "#2563eb"
C_VIOLET    = "#7c3aed"
C_PINK      = "#db2777"
C_GREEN     = "#059669"
C_AMBER     = "#d97706"
C_RED       = "#dc2626"

# ── Per-command dot colour + status text ──────────────────────────────────────
CMD_STATES = {
    'goto':     ('#60a5fa', 'Moving…'),
    'contact':  ('#fb923c', 'Working surface…'),
    'pickup':   ('#22c55e', 'Picking up…'),
    'keep':     ('#facc15', 'Placing…'),
    'pour':     ('#22d3ee', 'Pouring…'),
    'slice':    ('#f43f5e', 'Slicing…'),
    'press':    ('#f97316', 'Pressing…'),
    'release':  ('#a78bfa', 'Releasing…'),
    'wait':     ('#6b7280', 'Waiting…'),
    'complete': ('#ffd700', '✅  Task Complete!'),
}

# A wait is real time the operator watches tick by. A wash cycle written as
# wait_X(2400) would freeze playback for forty minutes, so the requested time is
# reported in full but the simulation only holds for this long.
WAIT_MAX_PLAYBACK = 5.0       # seconds


# ═════════════════════════════════════════════════════════════════════════════
#  IMAGE INTAKE  —  works with any resolution, aspect ratio, depth or channel
#  layout the user throws at it.
# ═════════════════════════════════════════════════════════════════════════════
def imread_any(path):
    """Robust replacement for cv2.imread().

    Handles: unicode / non-ASCII paths (cv2.imread silently fails on Windows),
    RGBA PNGs (composited onto white instead of losing the alpha), greyscale,
    and 16-bit / float TIFFs. Always returns uint8 BGR or None.
    """
    try:
        buf = np.fromfile(path, dtype=np.uint8)
        img = cv2.imdecode(buf, cv2.IMREAD_UNCHANGED)
    except Exception:
        img = None
    if img is None:
        img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None:
        return None

    # Normalise bit depth ────────────────────────────────────────────────────
    if img.dtype != np.uint8:
        try:
            dmax = float(np.iinfo(img.dtype).max)
        except ValueError:
            dmax = 1.0                       # float images are 0..1 by convention
        img = img.astype(np.float32)
        lo, hi = float(np.nanmin(img)), float(np.nanmax(img))
        if hi > lo:
            img = (img - lo) * (255.0 / (hi - lo))
        else:
            # Flat image: stretching is undefined, so scale by the dtype range
            # instead of collapsing the whole frame to black.
            img = img * (255.0 / dmax)
        img = np.clip(np.nan_to_num(img), 0, 255).astype(np.uint8)

    # Normalise channels ─────────────────────────────────────────────────────
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.shape[2] == 4:
        a   = img[:, :, 3:4].astype(np.float32) / 255.0
        rgb = img[:, :, :3].astype(np.float32)
        img = np.clip(rgb * a + 255.0 * (1.0 - a), 0, 255).astype(np.uint8)
    elif img.shape[2] != 3:
        img = cv2.cvtColor(img[:, :, 0], cv2.COLOR_GRAY2BGR)
    return np.ascontiguousarray(img)


def build_measured_canvas(bgr):
    """Letterbox to a SQUARE and burn a 0-1000 ruler into the margins.

    Root fix for the localisation bias. The old prompt told the model the image
    was "1000 wide and 1000 tall" while handing it a 16:9 photo — so the model
    regressed positions against the real proportions and everything landed high
    and short. Here the canvas genuinely IS square, and the ruler gives the
    model something to measure against instead of estimating blind.

    Returns (canvas_bgr, mapping). `mapping` unmaps ruler-space coordinates
    back to the original image's own normalised 0-1000 space, which is what the
    20x11 grid overlay is drawn in.
    """
    h, w = bgr.shape[:2]
    longest = max(w, h)
    scale   = min(1.0, float(IMG_MAX_SIDE) / float(longest)) if longest else 1.0
    dw = max(1, int(round(w * scale)))
    dh = max(1, int(round(h * scale)))
    if (dw, dh) != (w, h):
        interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
        img = cv2.resize(bgr, (dw, dh), interpolation=interp)
    else:
        img = bgr

    S  = max(dw, dh)                      # content square side, in pixels
    ox = (S - dw) // 2                    # letterbox offsets inside that square
    oy = (S - dh) // 2
    M  = max(30, int(round(S * RULER_FRAC)))

    canvas = np.full((S + 2 * M, S + 2 * M, 3), 16, np.uint8)
    canvas[M:M + S, M:M + S] = (64, 64, 64)          # neutral letterbox bars
    canvas[M + oy:M + oy + dh, M + ox:M + ox + dw] = img

    _draw_ruler(canvas, S, M)

    mapping = {'S': S, 'ox': ox, 'oy': oy, 'dw': dw, 'dh': dh, 'M': M}
    return canvas, mapping


def _draw_ruler(canvas, S, M):
    """Faint internal gridlines + labelled ticks in the margin bands."""
    overlay = canvas.copy()

    # Internal reference lines every 100 units, stronger at the quarters.
    for u in range(0, 1001, 50):
        p = M + int(round(u / 1000.0 * S))
        if u % 250 == 0:
            col, th = (120, 220, 255), 2
        elif u % 100 == 0:
            col, th = (90, 170, 200), 1
        else:
            continue
        cv2.line(overlay, (p, M), (p, M + S), col, th, cv2.LINE_AA)
        cv2.line(overlay, (M, p), (M + S, p), col, th, cv2.LINE_AA)
    cv2.addWeighted(overlay, 0.22, canvas, 0.78, 0, canvas)

    # Ticks + numerals in the margins (full opacity, they sit off the photo).
    fs = max(0.34, M / 90.0)
    ft = max(1, int(round(M / 26.0)))
    for u in range(0, 1001, 50):
        p     = M + int(round(u / 1000.0 * S))
        major = (u % 100 == 0)
        ln    = int(M * (0.42 if major else 0.22))
        col   = (255, 255, 255) if major else (170, 190, 210)
        cv2.line(canvas, (p, M - ln), (p, M), col, 1 + major, cv2.LINE_AA)
        cv2.line(canvas, (p, M + S), (p, M + S + ln), col, 1 + major, cv2.LINE_AA)
        cv2.line(canvas, (M - ln, p), (M, p), col, 1 + major, cv2.LINE_AA)
        cv2.line(canvas, (M + S, p), (M + S + ln, p), col, 1 + major, cv2.LINE_AA)
        if major and u % 200 == 0:
            txt = str(u)
            (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, fs, ft)
            cv2.putText(canvas, txt, (p - tw // 2, max(th + 2, M - int(M * 0.48))),
                        cv2.FONT_HERSHEY_SIMPLEX, fs, (255, 255, 255), ft, cv2.LINE_AA)
            cv2.putText(canvas, txt, (max(2, M - int(M * 0.50) - tw), p + th // 2),
                        cv2.FONT_HERSHEY_SIMPLEX, fs, (255, 255, 255), ft, cv2.LINE_AA)

    cv2.rectangle(canvas, (M, M), (M + S, M + S), (0, 229, 255), 2, cv2.LINE_AA)
    cv2.putText(canvas, "X ->", (M + 4, M - 4), cv2.FONT_HERSHEY_SIMPLEX,
                fs * 0.8, (0, 229, 255), ft, cv2.LINE_AA)
    cv2.putText(canvas, "Y v", (4, M + int(S * 0.5)), cv2.FONT_HERSHEY_SIMPLEX,
                fs * 0.8, (0, 229, 255), ft, cv2.LINE_AA)


def content_rect(m):
    """Where the photo actually lives inside the 0-1000 ruler space.

    For a 310x416 portrait the square canvas is 416 wide, so the photo only
    occupies x = 127..873 — a third of the ruler width is letterbox bar. The
    model was never told this, so it happily outlined into the padding.
    """
    return (m['ox'] / m['S'] * 1000.0,
            m['oy'] / m['S'] * 1000.0,
            (m['ox'] + m['dw']) / m['S'] * 1000.0,
            (m['oy'] + m['dh']) / m['S'] * 1000.0)


def build_content_note(m):
    """Tell the model, in numbers, where the photograph actually is.

    The prompt used to say only that grey bars 'may' exist. For a 310x416
    portrait the photo occupies just x = 127..873 of the ruler — a third of the
    width is bar — and with no numbers the model outlined straight into the
    padding. Those points unmapped outside the frame and the object smeared to
    full width. Stating the rectangle removes the guesswork.
    """
    x0, y0, x1, y1 = content_rect(m)
    pad_x = x0 > 1.0 or x1 < 999.0
    pad_y = y0 > 1.0 or y1 < 999.0
    if not (pad_x or pad_y):
        return ("- The photograph fills the whole cyan box: every coordinate from 0 to\n"
                "  1000 on both axes is real picture. There are no padding bars.")
    where = "left and right" if pad_x else "top and bottom"
    return (
        f"- IMPORTANT — the photograph does NOT fill the cyan box. Plain grey\n"
        f"  padding bars run along the {where}. The real picture occupies only:\n"
        f"        x from {x0:.0f} to {x1:.0f}\n"
        f"        y from {y0:.0f} to {y1:.0f}\n"
        f"  Nothing exists outside that rectangle — it is flat grey filler. Every\n"
        f"  point of every polygon you output MUST fall inside it. A polygon\n"
        f"  reaching into the grey is wrong and will be discarded. Do NOT stretch\n"
        f"  an object to the edges of the cyan box; stop at the picture's edge.\n"
        f"  Still read coordinates against the ruler, which spans the full box\n"
        f"  including the bars."
    )


def unmap_point(x_sq, y_sq, m, clamp=True):
    """Ruler-space (0-1000 on the square canvas) → original-image 0-1000.

    clamp=False is the important one. Clamping was the bug behind the
    full-frame surfaces: a polygon that strayed a little into the letterbox bar
    unmapped to a negative x, got pinned to 0, and the object silently grew to
    the full width of the photo. The taller the aspect ratio the worse it got,
    which is why portrait shots blew up and landscape ones looked fine. Callers
    now unmap raw and clip the polygon properly instead.
    """
    px = x_sq / 1000.0 * m['S'] - m['ox']
    py = y_sq / 1000.0 * m['S'] - m['oy']
    x  = px / float(m['dw']) * 1000.0
    y  = py / float(m['dh']) * 1000.0
    if clamp:
        return (max(0.0, min(1000.0, x)), max(0.0, min(1000.0, y)))
    return (x, y)


def _clip_edge(poly, keep, intersect):
    """One Sutherland-Hodgman pass against a single half-plane."""
    if not poly:
        return []
    out = []
    prev = poly[-1]
    prev_in = keep(prev)
    for cur in poly:
        cur_in = keep(cur)
        if cur_in:
            if not prev_in:
                out.append(intersect(prev, cur))
            out.append(cur)
        elif prev_in:
            out.append(intersect(prev, cur))
        prev, prev_in = cur, cur_in
    return out


def clip_to_frame(poly):
    """Sutherland-Hodgman clip of a polygon to the 0-1000 frame.

    Returns (clipped_poly, kept_fraction). kept_fraction is the share of the
    original polygon area still inside the frame — anything mostly outside was
    the model outlining the letterbox bar, and gets dropped by the caller
    rather than smeared across the image.
    """
    def area(p):
        if len(p) < 3:
            return 0.0
        s = 0.0
        for i in range(len(p)):
            x0, y0 = p[i]
            x1, y1 = p[(i + 1) % len(p)]
            s += x0 * y1 - x1 * y0
        return abs(s) * 0.5

    a0 = area(poly)
    p  = [tuple(pt) for pt in poly]

    def lerp(a, b, t):
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)

    p = _clip_edge(p, lambda q: q[0] >= 0.0,
                   lambda a, b: lerp(a, b, (0.0 - a[0]) / ((b[0] - a[0]) or 1e-9)))
    p = _clip_edge(p, lambda q: q[0] <= 1000.0,
                   lambda a, b: lerp(a, b, (1000.0 - a[0]) / ((b[0] - a[0]) or 1e-9)))
    p = _clip_edge(p, lambda q: q[1] >= 0.0,
                   lambda a, b: lerp(a, b, (0.0 - a[1]) / ((b[1] - a[1]) or 1e-9)))
    p = _clip_edge(p, lambda q: q[1] <= 1000.0,
                   lambda a, b: lerp(a, b, (1000.0 - a[1]) / ((b[1] - a[1]) or 1e-9)))

    if len(p) < 3:
        return [], 0.0
    p = [(max(0.0, min(1000.0, x)), max(0.0, min(1000.0, y))) for x, y in p]
    frac = (area(p) / a0) if a0 > 1e-9 else 0.0
    return p, min(1.0, frac)


def encode_jpeg_b64(bgr, quality=92):
    ret, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ret:
        return None
    return base64.b64encode(buf.tobytes()).decode()


# ═════════════════════════════════════════════════════════════════════════════
#  POLYGON GEOMETRY
# ═════════════════════════════════════════════════════════════════════════════
def _poly_bbox(polygon):
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return [min(xs), min(ys), max(xs), max(ys)]


def poly_centroid(poly):
    """True area centroid (shoelace).

    The old code averaged the vertices, so a polygon with more points clustered
    on one side pulled CENTER toward that side — exactly what happened to the
    10-point plate outline. Area centroid is invariant to how the vertices are
    distributed. Degenerate/zero-area polygons fall back to the vertex mean.
    """
    n = len(poly)
    if n < 3:
        return (sum(p[0] for p in poly) / n, sum(p[1] for p in poly) / n)
    a = cx = cy = 0.0
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        cross = x0 * y1 - x1 * y0
        a  += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    a *= 0.5
    if abs(a) < 1e-9:
        return (sum(p[0] for p in poly) / n, sum(p[1] for p in poly) / n)
    return (cx / (6.0 * a), cy / (6.0 * a))


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


# ═════════════════════════════════════════════════════════════════════════════
#  CV LOCALISATION  —  the model names, OpenCV measures
#
#  Everything here works in ORIGINAL-frame pixels and returns ORIGINAL-frame
#  normalised 0-1000 polygons, so it plugs straight into polygon_to_cells.
# ═════════════════════════════════════════════════════════════════════════════
def _bg_reference(bgr):
    """Median Lab colour of a ring around the frame border.

    Backgrounds in these scenes (countertop, table, cloth, seamless sweep) touch
    the border almost by definition; the objects of interest rarely do. Sampling
    the ring is a cheap, assumption-light estimate of 'what is not an object'.
    """
    h, w = bgr.shape[:2]
    b = max(2, int(round(min(h, w) * SEG_BORDER_FRAC)))
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    ring = np.concatenate([
        lab[:b, :, :].reshape(-1, 3),
        lab[-b:, :, :].reshape(-1, 3),
        lab[:, :b, :].reshape(-1, 3),
        lab[:, -b:, :].reshape(-1, 3),
    ], axis=0)
    return lab, np.median(ring.astype(np.float32), axis=0)


def foreground_mask(bgr):
    """Binary mask of 'things that are not the background'."""
    h, w = bgr.shape[:2]
    lab, ref = _bg_reference(bgr)
    dist = np.linalg.norm(lab.astype(np.float32) - ref[None, None, :], axis=2)
    dist = cv2.GaussianBlur(dist, (0, 0), max(1.0, min(h, w) / 300.0))

    d8 = np.clip(dist / max(1e-6, dist.max()) * 255.0, 0, 255).astype(np.uint8)
    thr, mask = cv2.threshold(d8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Otsu on a near-empty frame picks up sensor noise. If the mask swallows
    # most of the frame the background estimate was wrong (busy/dark scene) and
    # a flat mask is more honest than a confidently wrong one.
    if mask.mean() > 255 * 0.80:
        return np.zeros((h, w), np.uint8)

    k = max(3, int(round(min(h, w) * SEG_CLOSE_FRAC)) | 1)
    kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kern)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kern)
    return mask


def segment_blobs(bgr):
    """Foreground mask → list of candidate object blobs.

    Each blob carries its contour as a normalised 0-1000 polygon plus the pixel
    geometry the matcher needs. Blobs that are too small (noise) or too large
    (the background itself leaking through) are discarded here so no later stage
    has to think about them.
    """
    h, w = bgr.shape[:2]
    frame_area = float(h * w)
    mask = foreground_mask(bgr)
    if not mask.any():
        return [], mask

    n, labels, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
    blobs = []
    for i in range(1, n):
        area = float(stats[i, cv2.CC_STAT_AREA])
        frac = area / frame_area
        if frac < SEG_MIN_AREA_FRAC or frac > SEG_MAX_AREA_FRAC:
            continue
        comp = (labels == i).astype(np.uint8)
        cnts, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cnts:
            continue
        cnt = max(cnts, key=cv2.contourArea)
        eps = 0.006 * cv2.arcLength(cnt, True)
        appr = cv2.approxPolyDP(cnt, eps, True).reshape(-1, 2)
        if len(appr) < 3:
            continue
        if len(appr) > 14:                      # keep the planner list readable
            step = len(appr) / 14.0
            appr = np.array([appr[int(j * step)] for j in range(14)])
        poly = [[float(x) / w * 1000.0, float(y) / h * 1000.0] for x, y in appr]
        x0, y0 = stats[i, cv2.CC_STAT_LEFT], stats[i, cv2.CC_STAT_TOP]
        blobs.append({
            'poly':     poly,
            'mask':     comp,
            'area_px':  area,
            'area_frac': frac,
            'centroid': (float(cents[i][0]) / w * 1000.0,
                         float(cents[i][1]) / h * 1000.0),
            'bbox':     [float(x0) / w * 1000.0,
                         float(y0) / h * 1000.0,
                         float(x0 + stats[i, cv2.CC_STAT_WIDTH])  / w * 1000.0,
                         float(y0 + stats[i, cv2.CC_STAT_HEIGHT]) / h * 1000.0],
            'used':     False,
        })
    blobs.sort(key=lambda b: -b['area_px'])
    return blobs, mask


def _poly_mask(poly, h, w):
    """Rasterise a normalised polygon into an original-frame pixel mask."""
    pts = np.array([[int(round(x / 1000.0 * w)), int(round(y / 1000.0 * h))]
                    for x, y in poly], np.int32)
    m = np.zeros((h, w), np.uint8)
    cv2.fillPoly(m, [pts], 1)
    return m


def _blob_from_mask(comp, shape_hw):
    """Build a blob record from a binary component mask."""
    h, w = shape_hw
    area = float(np.count_nonzero(comp))
    if area <= 0.0:
        return None
    cnts, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    cnt = max(cnts, key=cv2.contourArea)
    eps = 0.006 * cv2.arcLength(cnt, True)
    appr = cv2.approxPolyDP(cnt, eps, True).reshape(-1, 2)
    if len(appr) < 3:
        return None
    if len(appr) > 14:
        step = len(appr) / 14.0
        appr = np.array([appr[int(j * step)] for j in range(14)])
    ys, xs = np.nonzero(comp)
    return {
        'poly':      [[float(x) / w * 1000.0, float(y) / h * 1000.0] for x, y in appr],
        'mask':      comp,
        'area_px':   area,
        'area_frac': area / float(h * w),
        'centroid':  (float(xs.mean()) / w * 1000.0, float(ys.mean()) / h * 1000.0),
        'bbox':      [float(xs.min()) / w * 1000.0, float(ys.min()) / h * 1000.0,
                      float(xs.max()) / w * 1000.0, float(ys.max()) / h * 1000.0],
        'used':      False,
    }


def split_touching_blobs(objs, bgr, blobs):
    """Separate one blob that several objects are pointing at.

    Objects that physically touch in the photo — a plate against a slice of
    bread, two stacked cloths — merge into a single connected component, and one
    component can only be snapped to one object. Where two or more model
    outlines land on the same blob, watershed it using those outlines as seeds
    so each object gets its own contour back.
    """
    h, w = bgr.shape[:2]
    out, split_count = [], 0

    for blob in blobs:
        bm = blob['mask']
        claim = []
        for oi, o in enumerate(objs):
            pm = _poly_mask(o['polygon'], h, w)
            inter = float(np.count_nonzero(pm & bm))
            if inter <= 0.0:
                continue
            # The outline must be substantially about THIS blob, otherwise a
            # neighbour's slight overhang would trigger a pointless split.
            if inter / max(1.0, float(np.count_nonzero(pm))) > 0.25:
                claim.append((oi, pm))

        if len(claim) < 2:
            out.append(blob)
            continue

        markers = np.zeros((h, w), np.int32)
        markers[bm == 0] = 1                       # everything outside is background
        kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        seeded = 0
        for k, (oi, pm) in enumerate(claim):
            seed = cv2.erode((pm & bm).astype(np.uint8), kern, iterations=2)
            if not seed.any():
                seed = (pm & bm).astype(np.uint8)
            if not seed.any():
                continue
            markers[seed > 0] = 2 + k
            seeded += 1
        if seeded < 2:
            out.append(blob)
            continue

        cv2.watershed(bgr, markers)

        parts = []
        for k in range(len(claim)):
            comp = ((markers == 2 + k) & (bm > 0)).astype(np.uint8)
            if np.count_nonzero(comp) < max(24, blob['area_px'] * 0.04):
                continue
            nb = _blob_from_mask(comp, (h, w))
            if nb:
                parts.append(nb)
        if len(parts) >= 2:
            out.extend(parts)
            split_count += 1
            print(f"[cv] blob split into {len(parts)} by "
                  f"{[objs[oi]['name'] for oi, _ in claim]}")
        else:
            out.append(blob)

    if split_count:
        out.sort(key=lambda b: -b['area_px'])
    return out


def _match_score(poly, blob, shape):
    """How strongly a proposed outline corresponds to a blob.

    Deliberately not plain IoU. The model's outline is systematically offset and
    often the wrong size, so IoU alone rejects correct identifications — the
    observed misses reach a third of the frame. Overlapping candidates are
    scored on shape agreement; non-overlapping ones fall back to proximity
    alone, scaled so that a miss at the travel limit scores zero. Correctness is
    then protected by the travel limit and the ambiguity guard in snap_to_blobs
    rather than by a high threshold here.
    """
    h, w = shape
    pcx, pcy = poly_centroid(poly)
    bcx, bcy = blob['centroid']
    d = math.hypot(pcx - bcx, pcy - bcy) / 1000.0
    prox = max(0.0, 1.0 - d / SNAP_MAX_TRAVEL)

    pm = _poly_mask(poly, h, w)
    bm = blob['mask']
    inter = float(np.count_nonzero(pm & bm))
    if inter <= 0.0:
        return 0.45 * prox, d

    union  = float(np.count_nonzero(pm | bm))
    iou    = inter / union if union else 0.0
    recall = inter / blob['area_px'] if blob['area_px'] else 0.0
    return 0.45 * iou + 0.35 * recall + 0.20 * prox, d


def snap_to_blobs(objs, bgr, blobs):
    """Replace each model polygon with the contour of the blob it refers to.

    Objects are matched greedily by descending score so the confident ones claim
    their blob first. An object whose best blob is weak, or whose blob sits more
    than SNAP_MAX_TRAVEL away, keeps its original outline and is flagged
    unsnapped rather than being dragged somewhere wrong.
    """
    if not blobs:
        for o in objs:
            o['snapped'] = False
        return 0

    blobs[:] = split_touching_blobs(objs, bgr, blobs)
    shape = bgr.shape[:2]
    pairs = []
    for oi, o in enumerate(objs):
        for bi, b in enumerate(blobs):
            s, d = _match_score(o['polygon'], b, shape)
            if s > 0.0:
                pairs.append((s, d, oi, bi))
    pairs.sort(key=lambda p: -p[0])

    # Best and runner-up per object, so a near-tie can be refused rather than
    # guessed. Snapping an object onto its neighbour is worse than not snapping.
    best = {}
    for s, d, oi, bi in pairs:
        cur = best.setdefault(oi, [])
        cur.append(s)
    ambiguous = set()
    for oi, scores in best.items():
        scores.sort(reverse=True)
        if len(scores) > 1 and scores[0] > 0 and scores[1] / scores[0] >= SNAP_AMBIG_RATIO:
            ambiguous.add(oi)

    taken_o, taken_b, snapped = set(), set(), 0
    for s, d, oi, bi in pairs:
        if oi in taken_o or bi in taken_b:
            continue
        if s < SNAP_MIN_SCORE or d > SNAP_MAX_TRAVEL:
            continue
        if oi in ambiguous:
            print(f"[cv] {objs[oi]['name']}: two blobs score alike — not snapped")
            taken_o.add(oi)
            continue
        objs[oi]['polygon'] = list(blobs[bi]['poly'])
        objs[oi]['snapped'] = True
        objs[oi]['snap_score'] = round(s, 3)
        blobs[bi]['used'] = True
        taken_o.add(oi); taken_b.add(bi)
        snapped += 1

    for oi, o in enumerate(objs):
        if oi not in taken_o:
            o['snapped'] = False
    return snapped


def _edges_touched(x0, y0, x1, y1):
    """(count, spans_opposite_pair) for the frame edges a bbox reaches.

    The pair matters as much as the count: something running off BOTH the left
    and right (or both top and bottom) continues past the picture on an entire
    axis, which is what a surface does and what a self-contained object does
    not — whatever the model chose to call it.
    """
    t = BG_EDGE_TOL * 1000.0
    l, u = x0 <= t, y0 <= t
    r, d = x1 >= 1000.0 - t, y1 >= 1000.0 - t
    return sum((l, u, r, d)), ((l and r) or (u and d))


def is_large_subject(name):
    """True when a name denotes something big that is still a real object.

    The vision prompt already bans reporting surfaces, so an entry coming back
    named 'bed' or 'car' is the model identifying the subject of the photo, not
    a backdrop slipping through. Matched on the HEAD noun rather than on any
    word present: 'double bed' is a bed, but 'bedside table' is a table and
    'car key' is a key — neither inherits the waiver for merely containing it.
    """
    low = re.sub(r'[^a-z0-9 ]+', ' ', str(name or '').lower()).strip()
    if not low:
        return False
    if low in LARGE_SUBJECTS:               # exact, incl. 'washing machine'
        return True
    words = low.split()
    return bool(words) and words[-1] in LARGE_SUBJECTS


def is_background_polygon(poly, bgr=None, mask=None, name=None):
    """True when a proposed object is really the backdrop.

    The primary test needs no segmentation: anything spanning most of the frame
    is the scene, not a thing sitting in it. That alone catches every observed
    case — the 162-cell 'countertop' and the 134-cell 'wooden board' were 74%
    and 61% of the board.

    The one exception is a named large subject (bed, sofa, car — see
    LARGE_SUBJECTS). Those legitimately fill the frame, and rejecting them left
    "make the bed" with no object at all. They are waived from the span rule
    only while their outline stays self-contained; one that runs off three
    sides of the frame is a backdrop whatever it was called.

    The foreground test is a secondary check and only runs when a trustworthy
    mask is supplied, because on a low-contrast photo it would happily reject a
    real object for sitting on a similarly-coloured surface.
    """
    x0, y0, x1, y1 = _poly_bbox(poly)
    span = (x1 - x0) * (y1 - y0) / 1e6
    if span >= BG_REJECT_FRAC:
        edges, opposite = _edges_touched(x0, y0, x1, y1)
        waived = (span < BG_ABSOLUTE_MAX
                  and edges < BG_EDGE_MIN_TOUCH
                  and not opposite
                  and is_large_subject(name))
        if not waived:
            return True, f"spans {span * 100:.0f}% of the frame"
        print(f"[vision] '{name}' kept at {span * 100:.0f}% of frame "
              f"({edges} edge(s) touched) — large subject, not a backdrop")
    if span <= 0.0:
        return True, "degenerate"
    if mask is None or bgr is None or not mask.any():
        return False, ""
    h, w = bgr.shape[:2]
    pm = _poly_mask(poly, h, w)
    n  = float(np.count_nonzero(pm))
    if n < 1.0:
        return True, "degenerate"
    if float(np.count_nonzero(pm & (mask > 0))) / n < BG_FOREGROUND_MIN:
        return True, "no foreground inside"
    return False, ""


def unknown_from_blobs(blobs, existing):
    """Blobs the model never named, surfaced so nothing on the board is invisible.

    These are reported to the user and drawn on the grid, but the planner is told
    not to act on them unless the operator names one explicitly — an unidentified
    shape is not something a robot should be picking up on its own initiative.
    """
    out = []
    n = 0
    for b in blobs:
        if b['used'] or b['area_frac'] < UNKNOWN_MIN_AREA:
            continue
        n += 1
        out.append({
            'name':    f"unknown_{n}",
            'polygon': list(b['poly']),
            'color':   '?',
            'size':    'medium' if b['area_frac'] < 0.10 else 'large',
            'desc':    'Unidentified shape found by image segmentation; '
                       'the vision model did not name it.',
            'aka':     [],
            'unknown': True,
            'snapped': True,
        })
    return out


def polygon_to_cells(polygon, thr=TOUCH_THRESHOLD):
    """Normalised polygon → (center_cell, touches_list, coverage_dict).

    Coverage is measured by sampling points inside each candidate cell, so thin
    or diagonal objects only claim the cells they genuinely occupy. Surfaces are
    never capped: sweep/wipe has to span the whole thing.
    """
    try:
        poly = [(max(0.0, min(1000.0, float(x))), max(0.0, min(1000.0, float(y))))
                for x, y in polygon]
    except (TypeError, ValueError):
        return None, [], {}
    if len(poly) < 3:
        return None, [], {}

    x0, y0, x1, y1 = _poly_bbox(poly)
    if x1 <= x0 or y1 <= y0:
        return None, [], {}

    cell_w = 1000.0 / COLS
    cell_h = 1000.0 / ROWS

    cov = {}
    ci_lo = max(0, int(x0 / cell_w));            ci_hi = min(COLS - 1, int(x1 / cell_w))
    ri_lo = max(0, int(y0 / cell_h));            ri_hi = min(ROWS - 1, int(y1 / cell_h))

    for ci in range(ci_lo, ci_hi + 1):
        cx0 = ci * cell_w
        for ri in range(ri_lo, ri_hi + 1):
            cy0  = ri * cell_h
            hits = 0
            for si in range(POLY_SAMPLES):
                sx = cx0 + (si + 0.5) * cell_w / POLY_SAMPLES
                for sj in range(POLY_SAMPLES):
                    sy = cy0 + (sj + 0.5) * cell_h / POLY_SAMPLES
                    if _point_in_poly(sx, sy, poly):
                        hits += 1
            if hits:
                cov[(ci, ri)] = hits / float(POLY_SAMPLES * POLY_SAMPLES)

    touches = [c for c, f in cov.items() if f >= thr]
    if not touches and cov:
        best = max(cov.values())
        cut  = best * REL_FALLBACK
        touches = [c for c, f in cov.items() if f >= cut]

    if len(touches) > MAX_TOUCH_CELLS:
        ranked  = sorted(cov.items(), key=lambda kv: -kv[1])
        keep    = {c for c, _ in ranked[:MAX_TOUCH_CELLS]}
        touches = [c for c in touches if c in keep]

    # CENTER — area centroid, but only if it actually lands on the object.
    mx, my = poly_centroid(poly)
    if _point_in_poly(mx, my, poly):
        cc = min(COLS - 1, max(0, int(mx / cell_w)))
        cr = min(ROWS - 1, max(0, int(my / cell_h)))
    elif cov:
        cc, cr = max(cov.items(), key=lambda kv: kv[1])[0]
    else:
        cc = min(COLS - 1, max(0, int(mx / cell_w)))
        cr = min(ROWS - 1, max(0, int(my / cell_h)))

    if (cc, cr) not in touches:
        touches.append((cc, cr))
        cov.setdefault((cc, cr), 0.01)
    touches.sort(key=lambda t: (t[1], t[0]))
    return (cc, cr), touches, cov


def bbox_to_cells(box, thr=TOUCH_THRESHOLD):
    """Fallback for responses that only carry a bbox. Same contract as above."""
    try:
        x0, y0, x1, y1 = [max(0.0, min(1000.0, float(v))) for v in box]
    except (TypeError, ValueError):
        return None, [], {}
    if x1 <= x0 or y1 <= y0:
        return None, [], {}
    return polygon_to_cells([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], thr)


def resolve_overlaps(objs):
    """A cell can only belong to one physical object.

    In the failing run the plate polygon reached across the bread and both
    claimed L5/M5, so a wipe or slice aimed at one silently ran over the other.
    Contested cells go to whichever object covers more of them, so two objects
    can never both claim the same square. An object never loses its CENTER cell.
    """
    owner = {}
    for i, o in enumerate(objs):
        for c in o['_cells']:
            f = o['_cov'].get(c, 0.0)
            if c not in owner or f > owner[c][0]:
                owner[c] = (f, i)

    for i, o in enumerate(objs):
        kept = [c for c in o['_cells'] if owner.get(c, (0.0, i))[1] == i]
        ctr  = o['_center']
        if ctr not in kept:
            kept.append(ctr)
        o['_cells'] = sorted(set(kept), key=lambda t: (t[1], t[0]))
    return objs


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
    """Synthesise a normalised 0-1000 bbox enclosing a list of (col,row) cells."""
    if not cells:
        return None
    cw = 1000.0 / COLS
    ch = 1000.0 / ROWS
    x0 = min(c[0] for c in cells) * cw
    x1 = (max(c[0] for c in cells) + 1) * cw
    y0 = min(c[1] for c in cells) * ch
    y1 = (max(c[1] for c in cells) + 1) * ch
    return [round(x0), round(y0), round(x1), round(y1)]


def compact_cells(cells):
    """(col,row) list → run-length cell spec, e.g. 'D2-Q2,D3-Q3,D4-F4,H4-Q4'.

    A 134-cell surface spelled out in full was ~700 characters, and two of them
    made the OBJECT LIST longer than the rest of the planner prompt combined.
    Contiguous runs within a row collapse to 'START-END'; the runner expands
    them back to individual cells at playback.
    """
    by_row = {}
    for ci, ri in cells:
        by_row.setdefault(ri, set()).add(ci)
    out = []
    for ri in sorted(by_row):
        cols = sorted(by_row[ri])
        start = prev = cols[0]
        for c in cols[1:] + [None]:
            if c is not None and c == prev + 1:
                prev = c
                continue
            if start == prev:
                out.append(f"{COL_LABELS[start]}{ri + 1}")
            else:
                out.append(f"{COL_LABELS[start]}{ri + 1}-{COL_LABELS[prev]}{ri + 1}")
            if c is not None:
                start = prev = c
    return ",".join(out)


def expand_cell_spec(spec):
    """Inverse of compact_cells. Accepts 'D2', 'D2-Q2', and rectangles
    like 'D2-Q10'. Unknown tokens are skipped rather than aborting."""
    cells = []
    for token in str(spec).split(','):
        token = token.strip()
        if not token:
            continue
        m = re.match(r'^([A-Ta-t])\s*(\d{1,2})\s*-\s*([A-Ta-t])\s*(\d{1,2})$', token)
        if m:
            c0 = ord(m.group(1).upper()) - ord('A')
            r0 = int(m.group(2)) - 1
            c1 = ord(m.group(3).upper()) - ord('A')
            r1 = int(m.group(4)) - 1
            for rr in range(min(r0, r1), max(r0, r1) + 1):
                for cc in range(min(c0, c1), max(c0, c1) + 1):
                    if 0 <= cc < COLS and 0 <= rr < ROWS:
                        cells.append((cc, rr))
            continue
        one = parse_cell(token)
        if one:
            cells.append(one)
    seen, out = set(), []
    for c in cells:
        if c not in seen:
            seen.add(c); out.append(c)
    return out


def obj_to_line(o):
    """Dict → the OBJECT: line format the planner consumes."""
    aka = o.get('aka', [])
    aka = ", ".join(str(a) for a in aka) if isinstance(aka, list) else str(aka)
    cells = o.get('_cells')
    touches = compact_cells(cells) if cells else o.get('touches', '')
    return (
        f"OBJECT: {o.get('name','object')}  "
        f"CENTER: {o.get('center','')}  "
        f"TOUCHES: {touches}  "
        f"COLOR: {o.get('color','?')}  "
        f"SIZE: {o.get('size','?')}  "
        f"{'UNIDENTIFIED: yes  ' if o.get('unknown') else ''}"
        f"DESC: {o.get('desc','')}  "
        f"ALSO_KNOWN_AS: {aka}"
    )


# ═════════════════════════════════════════════════════════════════════════════
#  TRUNCATION-TOLERANT JSON PARSING
# ═════════════════════════════════════════════════════════════════════════════
def parse_vision_json(raw):
    """Return a list of object dicts from a model response.

    Hitting the token ceiling used to surface as a hard 'invalid JSON' error
    that threw away a whole response's worth of good detections. Now: strict
    parse first, then a brace-walking salvage that recovers every complete
    object entry and discards only the half-written tail.
    """
    txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip())
    try:
        data = json.loads(txt)
        if isinstance(data, dict) and isinstance(data.get("objects"), list):
            return data["objects"], False
        if isinstance(data, list):
            return data, False
    except json.JSONDecodeError:
        pass

    # Object entries live nested inside {"objects":[ ... ]}, so a truncated
    # response never closes the outer brace. Collect balanced blocks at EVERY
    # depth, then keep only the innermost ones that look like object entries.
    spans, stack, in_str, esc = [], [], False, False
    for i, ch in enumerate(txt):
        if in_str:
            if esc:            esc = False
            elif ch == '\\':   esc = True
            elif ch == '"':    in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == '{':
            stack.append(i)
        elif ch == '}' and stack:
            spans.append((stack.pop(), i + 1))

    salvaged, taken = [], []
    for s, e in sorted(spans, key=lambda sp: sp[1] - sp[0]):
        if any(s <= ts and te <= e for ts, te in taken):
            continue                      # a wrapper around an entry we already have
        chunk = txt[s:e]
        if '"polygon"' not in chunk and '"box"' not in chunk:
            continue
        try:
            d = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        if isinstance(d, dict) and ('polygon' in d or 'box' in d):
            salvaged.append((s, d))
            taken.append((s, e))
    salvaged.sort(key=lambda p: p[0])     # preserve the model's original order
    return [d for _, d in salvaged], True


# ═════════════════════════════════════════════════════════════════════════════
#  VISION PROMPT
#  Written against the measured square canvas — the ruler makes the coordinate
#  claim true, and the anchor rules stop the model from clipping objects short.
# ═════════════════════════════════════════════════════════════════════════════
VISION_PROMPT = (
    """
You are the vision system for a robot. Identify every physical object in this image.

## COORDINATE SPACE — READ THIS FIRST

The image has a RULER burned into its four margins, numbered 0 to 1000 on both
axes. That ruler defines the coordinate space:
- X runs left to right, 0 at the left edge of the cyan box, 1000 at the right.
- Y runs TOP to BOTTOM, 0 at the top edge of the cyan box, 1000 at the bottom.
- Faint lines cross the picture every 100 units, with brighter ones at 250,
  500 and 750. USE THEM. For every point you output, find the nearest faint
  line and count from it. Do not estimate a position without checking it
  against a ruler line first.
- The cyan box is the coordinate area. Anything outside it is ruler margin,
  not part of the scene.
{CONTENT_RECT_NOTE}

## WHAT TO REPORT

Report every DISCRETE PHYSICAL OBJECT resting in the scene — the things a robot
could pick up, move, open, operate or clean:
small objects (bottles, cups, clothes, tools, food, sponges, plates, cutlery,
toys), and large items (appliances, furniture, bins, baskets).

## WHAT TO IGNORE — STRICT

Do NOT report the background or any surface. Specifically, never output an entry
for: the table, tabletop, countertop, worktop, board, tray, desk, floor, ground,
wall, backsplash, tiling, curtain, sky, or the plain sweep/backdrop the objects
are photographed against. Do not report shadows, reflections, printed markings,
or the grey padding bars.

Apply this test to every candidate: "is this a thing sitting IN the scene, or is
it the scene?" A slice of bread sitting on a counter is an object. The counter
is not. If your entry would cover most of the picture, it is background — drop
it. A scene of three items on a table has exactly THREE objects.

Size is not the test — running off the frame is. A bed, sofa, car or appliance
photographed as the SUBJECT of the picture is a discrete object even though it
fills most of the frame: it has a closed outline with visible space beside it.
A backdrop has no such outline; it continues off every side of the picture.
Report the large subject, still skipping the surface it rests on.
{FURNITURE_EXCEPTION}

## OUTLINE RULES

Give each object a polygon in the ruler coordinate space above. Your outline is
a starting point that gets refined automatically against the image pixels, so
aim for a correct, well-centred shape rather than an exhaustive one:

1. The polygon's centre must land ON the object, not on adjacent background.
   This matters more than the exact edges — a well-centred rough outline is far
   more useful than a precise outline in the wrong place.
2. BOTTOM ANCHOR — the lowest point should be where the object MEETS whatever it
   rests on, at the base shadow. Do not stop at a colour or texture change
   partway down (a bread crust, a label, a shadowed base).
3. TOP ANCHOR — the highest point is the object's topmost visible pixel,
   including handles, spouts, lids and stems.
4. Between them, follow the visible silhouette. For long, thin or diagonal
   objects (brooms, cables, tools) follow the angle with several points rather
   than boxing them in.
5. Use 4 points for compact objects, up to 10 for irregular or round ones,
   spaced EVENLY around the outline — never clustered on one side.
6. For openable appliances the polygon must cover the opening (drum mouth, door,
   lid), because the robot loads at the polygon's centre.
7. NO OVERLAP between two objects' polygons. They may touch; they may not cross.

## OUTPUT

STRICT JSON only — no markdown, no code fences, no commentary:

{"objects": [
  {"name": "washing machine",
   "polygon": [[x0, y0], [x1, y1], [x2, y2], [x3, y3]],
   "color": "white",
   "size": "large",
   "desc": "Front-loading washing machine with a round door.",
   "aka": ["washer", "laundry machine", "appliance"]}
]}

Rules:
- polygon values are integers 0-1000. At least 3 points, in order (clockwise or
  counter-clockwise) tracing the outline. No self-intersecting polygons.
- One physical object = exactly one entry. Two similar items in different
  places are two entries.
- name: lowercase, short. desc: one sentence. aka: 2-3 synonyms.
"""
)

# ─────────────────────────────────────────────────────────────────────────────
#  Verification prompt — the model is shown its own outlines drawn back onto
#  the measured canvas. Checking a drawing is a far easier visual task than
#  regressing coordinates from scratch, so this pass catches the residual drift.
# ─────────────────────────────────────────────────────────────────────────────
# Furniture that is normally a SURFACE (so normally ignored), but becomes a
# legitimate target the moment the operator asks for it to be moved. Reporting
# a table unconditionally is what made every scene's tabletop an "object"; not
# reporting it ever is what made "push the desk to the office" unplannable.
MOVABLE_SURFACES = (
    "table", "tabletop", "desk", "counter", "countertop", "worktop", "board",
    "tray", "shelf", "bench", "workbench", "stand", "cart", "trolley",
    "nightstand", "dresser", "cabinet", "sideboard", "stool", "chair", "sofa",
    "couch", "ottoman", "bed", "rug", "mat", "doormat", "carpet",
)
MOVE_VERBS = (
    "move", "push", "pull", "slide", "drag", "shift", "reposition", "carry",
    "bring", "take", "put", "place", "relocate", "shove", "swap", "return",
)


def build_furniture_note(task_text=None):
    """Conditionally un-ban furniture the operator explicitly wants moved.

    The ignore list exists so a scene's tabletop is not reported as an object.
    But the same rule made any task whose real target IS that furniture
    impossible — vision would never emit it, so the planner had no coordinate
    and wrote MISSING for something plainly in the photo. When the instruction
    both names one of those items and asks for it to be moved, the exclusion is
    lifted for that item only; everything else on the list stays banned.
    """
    if not task_text:
        return ""
    low = str(task_text).lower()
    if not any(v in low for v in MOVE_VERBS):
        return ""
    named = sorted({s for s in MOVABLE_SURFACES if s in low})
    if not named:
        return ""
    items = ", ".join(named)
    return (
        f"\nEXCEPTION for this image — the operator's task refers to: {items}.\n"
        f"Those specific items are the TARGET of the task, so for this request\n"
        f"they ARE objects: outline and report them normally, even though the\n"
        f"list above would usually exclude them. Outline only the item itself\n"
        f"(its own silhouette), not the whole surface it continues into, and\n"
        f"keep ignoring every other surface, the floor, the walls and the\n"
        f"backdrop as usual."
    )


def build_vision_prompt(m, base=None, task_text=None):
    return ((base or VISION_PROMPT)
            .replace("{CONTENT_RECT_NOTE}", build_content_note(m))
            .replace("{FURNITURE_EXCEPTION}", build_furniture_note(task_text)))


VERIFY_PROMPT = (
    """
This is the same image, now with the outlines YOU produced drawn on top. Each
outline is numbered with a coloured tag. The ruler in the margins is unchanged:
0-1000 on both axes, X left to right, Y top to bottom, faint lines every 100.

{CONTENT_RECT_NOTE}

Check every numbered outline against the object it is supposed to cover:

1. POSITION — is the outline sitting on the object, or shifted off it? Shifted
   up is the most common error: check whether the outline's bottom edge reaches
   the object's contact point with whatever it rests on.
2. EXTENT — does it cover the whole object, top to bottom and side to side? An
   outline that stops partway down (at a colour or texture change rather than at
   the object's base) must be extended.
3. TIGHTNESS — does it swallow large areas of background? Pull it in.
4. OVERLAP — do two outlines cross? Separate them at the true boundary.
5. MISSING — is there a discrete physical object with no outline? Add it.
6. BACKGROUND — is any outline covering the table, counter, floor, wall or
   backdrop rather than an object resting in the scene? DELETE that entry
   entirely. Surfaces and backgrounds are never reported.
   Two things are NOT background and must be kept: a large item photographed as
   the subject (a bed, sofa, car, appliance) that has its own closed outline
   with space visible beside it, and anything covered by the exception below.
{FURNITURE_EXCEPTION}

Output the corrected FULL object list — every object, not just the changed ones
— in exactly the same JSON schema as before:

{"objects": [
  {"name": "...", "polygon": [[x,y], ...], "color": "...", "size": "...",
   "desc": "...", "aka": ["...", "..."]}
]}

Integers 0-1000. STRICT JSON only — no markdown, no code fences, no commentary.
Keep an outline unchanged if it is already correct; be decisive about moving the
ones that are not.
"""
)

# ─────────────────────────────────────────────────────────────────────────────
# Dexterity classifier prompt — silent pre-check before planning.
# ─────────────────────────────────────────────────────────────────────────────
DEXTERITY_SYSTEM = (
    """
You are a Dexterity Classifier for robotic manipulation tasks. The user will give you a task description. Your job is to decide whether the task is dexterous or non-dexterous for a general-purpose robot with a simple parallel gripper.

CRITICAL RULE: Even a slightly dexterous task is classified as dexterous. When in doubt, classify as dexterous. There is no borderline category.

A task is DEXTEROUS if it requires ANY of the following:
1. Fine fingertip precision — manipulating small, thin, or flexible objects (buttons, coins, paper sheets, threads, cables, pills).
2. Precise alignment or insertion — fitting one object into a tight tolerance (keys into locks, USB/plug into port, threading, peg-in-hole with small clearance).
3. Rotational manipulation using fingers/wrist against resistance or with precision — turning keys, unscrewing lids or caps, twisting knobs that need controlled torque.
4. In-hand reorientation or regrasping — adjusting the object's pose within the gripper mid-task.
5. Separating or singulating — picking one item from many (one sheet from a stack, one card from a deck), or peeling/detaching thin layers.
6. Bimanual coordination with fine control — two hands doing precise complementary actions (buttoning, tying, zipping).
7. Delicate force control — the object breaks, tears, or deforms if grip force is slightly wrong (eggs, chips, fabric manipulation).

A task is NON-DEXTEROUS only if ALL of the following hold:
- It can be done with a single whole-hand power grasp or open-palm contact.
- Placement/movement tolerance is loose (centimeter-scale, not millimeter-scale).
- No fine finger articulation, no tight insertion, no controlled twisting, no thin/small object handling.

Reference examples (calibrated ground truth — follow these exactly):
NON-DEXTEROUS: picking up a mug by its handle; pushing a box across a table with a flat palm; pouring water from a bottle into a glass; placing a book onto a shelf; wiping a table with a cloth; sweeping; mopping; stacking objects; loading a washing machine; slicing with a robot-mounted blade; folding laundry with the robot's fold mechanism.
DEXTEROUS: buttoning a shirt; turning a key in a lock; picking up a single sheet of paper from a flat table; unscrewing a jar lid; plugging a USB cable into a port.

If the task contains multiple sub-steps and ANY single sub-step is dexterous, the entire task is dexterous.

OUTPUT FORMAT — you must output EXACTLY one of the following two strings and nothing else:
{dexterous}
{non-dexterous}

No explanation, no reasoning, no punctuation, no extra words. Only the single token above, including the curly braces.
"""
)


# ─────────────────────────────────────────────────────────────────────────────
# A2 system prompt  (planner — unchanged behaviour)
# ─────────────────────────────────────────────────────────────────────────────
A2_SYSTEM = (
    """
You are A2, the controller of a ProLabs V12.2 Precision Cartesian Gantry robot.

You receive an OBJECT LIST (name, CENTER cell, TOUCHES cells, color, size, description, ALSO_KNOWN_AS) and a Task. Output the shortest correct command sequence.

---

## BOARD

20 columns (A-T) x 11 rows (1-11). CENTER is the cell to move above for pick-up. The robot approaches all objects from above.

---

## COMMANDS

There are exactly EIGHT commands. Nothing else exists. Any word outside this list is a critical error. (`pour` and `pour(FRACTION)` are the same command written two ways, not two commands.)

goto_coordinate = COL, ROW    move above a cell
pickup                        pick up the object at the current cell
keep                          place the held object at the current cell
press                         engage the tool / actuate whatever is at the current cell
release                       disengage - ends the engagement started by press
pour                          pour from the held source object into the container at the current cell
pour(FRACTION)                pour only part of it - FRACTION is 0.1 to 1.0 of the source's contents
slice(NAME, N)                slice object N times; robot must be above the object first
wait_X(SECONDS)               hold position and do nothing for SECONDS

Plus two non-action lines: `invoke(Alpha_2D_unstacker)` (fixed first step) and `Task_Completed` (fixed last line).

---

## press / release - THE KEY IDEA

`press` and `release` replace every appliance, cleaning and manipulation verb the robot used to have. There are two ways to use them.

**1. Momentary press - actuate something once.**
Hold nothing, move above the object, press, release. This is how you open a door, close a lid, flip a switch on or off, fold a garment, or start a cycle.

goto_coordinate = APPLIANCE_COL, APPLIANCE_ROW
press                    # open the door
release

**2. Contact pass - drag a held tool across cells.**
Pick up a tool (broom, mop, cloth, sponge, spray), move above the FIRST cell, `press` to put the tool in contact with the surface, then issue one `goto_coordinate` per cell. The tool stays in contact and works every cell it crosses. `release` lifts it at the end.

goto_coordinate = A, 6
press                    # cloth down
goto_coordinate = B, 6
goto_coordinate = C, 6
goto_coordinate = D, 6   # ...one line per cell
release                  # cloth up

This is the ONLY way to sweep, mop, scrub, soap or wipe. There is no sweep(), mop(), apply_soap() or apply_cloth() command - writing one is a critical error.

**3. Slide / drag an object - press on it, then goto the destination.**
Hold nothing, move above the object's CENTER, `press` to hold it down against the surface, then issue one `goto_coordinate` per cell along the path to its destination. The object slides with the gantry. `release` lets go at the end.

goto_coordinate = BOX_COL, BOX_ROW
press                    # hold the box down
goto_coordinate = DEST_COL, DEST_ROW
release                  # let go of the box

There is no drag() command - writing one is a critical error. Sliding is always press -> goto -> release.

**Rules for press/release**
- Every `press` must have exactly one matching `release`. Never press twice without releasing.
- The robot cannot `pickup` or `keep` while pressed. Release first.
- One contact pass per surface run. Do not press and release at every single cell - press once, cross the cells, release once.
- State your intent in a `#` comment on its own line, since the commands themselves are generic:
  `# turn the stove on`, `# wipe the countertop`, `# fold the shirt`.

---

## pour - HOW MUCH COMES OUT

Bare `pour` empties the held source completely into whatever is at the current cell. That is the right choice whenever the task is simply "pour the juice into the glass" and nothing is meant to be left over.

When the operator asks for only part of it, write the amount as a fraction of the source's contents:

goto_coordinate = BOTTLE_COL, BOTTLE_ROW
pickup
goto_coordinate = GLASS_COL, GLASS_ROW
pour(0.5)                # half the milk, the rest stays in the carton
goto_coordinate = BOTTLE_COL, BOTTLE_ROW
keep                     # return the carton, still half full

**Rules for pour**
- FRACTION is a decimal from 0.1 to 1.0. `pour(1.0)` and bare `pour` mean the same thing - prefer the bare form when emptying it.
- Never a percentage, never a volume, never a unit: `pour(0.25)`, not `pour(25%)` or `pour(250ml)`. A2 tracks proportion of the source, not millilitres.
- Map the operator's words to a fraction: "half" -> 0.5, "a third" -> 0.33, "a splash"/"a little"/"a drizzle" -> 0.1, "most of it" -> 0.75, "top it up" -> 0.25.
- Splitting one source between several containers is one `pour(FRACTION)` per container, moving between them while still holding the source: pour(0.5) at the first glass, goto the second, pour(1.0) to empty the rest.
- The source is still held after a partial pour, so it still needs its `keep` to be returned before the task ends.

---

## wait_X - PAUSING

`wait_X(SECONDS)` holds the gantry exactly where it is and does nothing for that many seconds. Use it when the task depends on something the robot does not control finishing: a cycle running, a kettle boiling, food cooking, a wiped surface drying, a liquid draining.

goto_coordinate = KETTLE_COL, KETTLE_ROW
press                    # switch the kettle on
release
wait_X(90)               # wait for it to boil

**MACHINES THAT RUN - wait_X is MANDATORY**
Whenever you switch an appliance ON and the task is about what that appliance DOES - washing, drying, cooking, heating, boiling, brewing - you must wait_X between turning it on and turning it off. Turning a washing machine on and straight back off does not wash anything; the plan is wrong without the wait. Use the operator's own figure if they gave one, otherwise a sensible stand-in for the cycle:

press                    # start the wash cycle
release
wait_X(300)              # let the cycle run
press                    # turn the washing machine off
release

**Rules for wait_X**
- SECONDS is a plain positive number, 1 to 600. Never a range, never a unit suffix, never a word.
- Say what is being waited for in a `#` comment, exactly as for press.
- Anything held stays held and anything pressed stays pressed across a wait. It is not a way to put something down.
- Outside the machine case above, a wait is only correct when a LATER step genuinely depends on it. Do not pad a plan with waits, and never make one the final command before Task_Completed.

---

## RULES

**Coordinates** - always use the exact CENTER from the OBJECT LIST. Never invent a coordinate.

**Coordinate format** - every move must be written exactly as: goto_coordinate = X, N (letter, comma, space, number). Never fuse the coordinate (H6), never omit the "=". No other spelling is valid.

**Surface coverage** - when cleaning an OBJECT, the contact pass must cross every cell in that object's TOUCHES list, not just its CENTER. Cleaning one cell of a multi-cell object is a failure.

**No surfaces in the list** - vision reports only discrete objects. Tables, counters, floors, walls and backdrops are never present, by design. Never invent a coordinate for one. To clean an area rather than an object, run the contact pass over explicit board cells (playbook 3).

**UNIDENTIFIED objects** - an entry marked UNIDENTIFIED: yes was found by image segmentation but never named, so something physical is there but nothing is known about it. Do NOT pick it up, move it, or include it in "collect everything" / "tidy up" style tasks. Act on it only if the operator names it explicitly. Otherwise treat its cells as occupied when choosing a temporary or destination cell.

**Placement** - `keep` is the only way to place a held object. Never use drop, put, insert, release, or move. (`release` ends a press; it does NOT put an object down.)

**Order** - always goto before pickup, keep, press or pour. Finish one object's full sequence before starting another.

**Held-object rule** - the robot holds at most ONE object. Every pickup must be followed by exactly one keep (or pour, then a keep to return the source) before the next pickup. Before writing Task_Completed, check: is anything still held? Is anything still pressed? If yes, release and/or goto its home cell and keep it FIRST.

**Efficiency** - choose the shortest sequence. No redundant moves.

**Object matching** - match user words to objects using name, ALSO_KNOWN_AS, description, color, and size. Resolve silently. Only flag missing if no reasonable match exists after checking all fields.

**Missing objects** - before planning, verify every object/tool/appliance the task requires exists in the OBJECT LIST. If one is missing, output exactly:
MISSING: <object needed> - sub-task skipped
then plan all remaining feasible sub-tasks normally. NEVER invent a coordinate. NEVER assume an object exists. Using any coordinate not present in the OBJECT LIST is a critical error.

**Gaps longer than a wait** - `wait_X` maxes out at 600 seconds, so it can only stand in for something that finishes within the session: a cycle, a boil, a soak, a surface drying. When a task's later half depends on an outside event that takes hours or days - a bin being emptied by a collection truck, laundry drying overnight, paint curing, a delivery arriving - do NOT stretch a wait to cover it and do NOT plan the second half blind. Plan the first half completely, end with Task_Completed, and state the boundary in a `#` comment:

# bring the bin back in once it has been emptied - separate task
Task_Completed

The operator re-runs the second half later, when the world has actually changed and vision can see the new state.

---

## TASK PATTERNS

**Move / Stack / Collect**
goto object -> pickup -> goto destination -> keep

**Swap A <-> B**
Move A to a free temp cell -> move B to A's original cell -> move A from temp to B's original cell

**Pour liquid**
goto source -> pickup -> goto destination -> pour -> goto source home -> keep

**Slice**
goto object -> slice(NAME, N)

**Slide / Drag (no lift)**
goto object -> press -> goto destination -> release - use when sliding is more appropriate than lifting (heavy or flat objects)

**Actuate (open / close / on / off / fold)**
goto object -> press -> release

**Wait for something to finish**
wait_X(SECONDS) - only when a later step depends on the delay

**Clean any surface or object**
goto tool -> pickup -> goto first cell -> press -> goto each remaining cell -> release -> goto tool home -> keep

**Sweep debris to ONE collection point** (see playbook 1b)
goto broom -> pickup -> per row: goto far edge -> press -> drag through the row ending AT the target cell -> release -> ...repeat per row, every pass ending at the same target -> goto broom home -> keep

**Store / unload items in a plain container** (see playbook 12)
goto container -> press -> release (open) -> per item: goto item -> pickup -> goto container -> keep -> ...repeat -> goto container -> press -> release (close)

**Tilt-pour a bag/box/can of loose contents** (see playbook 13)
goto source -> pickup -> goto destination -> pour -> goto source home -> keep

**Push a heavy/wheeled object** (see playbook 14)
goto object -> press -> goto destination (via waypoints if needed) -> release

**Replace a consumable** (see playbook 15)
goto holder -> pickup (old) -> goto disposal/temp -> keep -> goto new item -> pickup -> goto holder -> keep

**Fill a container at a tap** (see playbook 17)
goto container -> pickup -> goto tap -> keep -> press -> wait_X -> release -> pickup -> goto destination -> keep or pour

**Pour only part of a source** (see playbook "pour - HOW MUCH COMES OUT")
goto source -> pickup -> goto destination -> pour(FRACTION) -> goto source home -> keep

---

# A2 Task Playbooks

Substitute real CENTER/TOUCHES coordinates from the OBJECT LIST wherever COL/ROW/NAME placeholders appear below.

---

## 1. Sweep a Room

Requires a broom-type object (match via ALSO_KNOWN_AS/description if not literally named "broom"). If no broom-type object exists, output the MISSING line and skip.

goto_coordinate = BROOM_COL, BROOM_ROW
pickup
goto_coordinate = A, 1
press                      # broom down
goto_coordinate = B, 1
goto_coordinate = C, 1     # ...continue across the row, one line per cell
goto_coordinate = T, 1
goto_coordinate = A, 2     # step to the next row, still in contact
goto_coordinate = B, 2
...continue for every row that has debris or was specified by the user
release                    # broom up
goto_coordinate = BROOM_COL, BROOM_ROW
keep                       # return broom to its original cell

## 1b. Sweep Debris to ONE Collection Point

Use this instead of playbook 1 whenever the task says to gather, pile, collect
or push everything swept into a single cell/coordinate (e.g. "sweep the board
and collect all the dust onto one coordinate"). A single pass that crosses
every cell once does NOT converge anything - it just wipes past. To actually
converge, every row's contact pass must be dragged so that it ENDS at the
same target cell, the same way a person sweeps a room toward a dustpan: push
each row's debris toward the pile, don't just brush over it.

Pick the TARGET_COL, TARGET_ROW first (an empty cell on the object/board - the
operator's cell if named, otherwise a sensible corner or edge cell of the
object's TOUCHES list). Then, for every row that has debris, run a SEPARATE
press -> drag -> release pass that starts at the far edge of that row and
ends at TARGET_COL, TARGET_ROW - never the reverse direction, since dragging
away from the target would push debris off the pile instead of onto it.

goto_coordinate = BROOM_COL, BROOM_ROW
pickup
goto_coordinate = ROW1_FAR_COL, ROW1_ROW      # far edge of row 1, away from target
press                                          # broom down
goto_coordinate = ROW1_MID_COL, ROW1_ROW       # ...intermediate cells of row 1
goto_coordinate = TARGET_COL, TARGET_ROW       # drag row 1's debris onto the pile
release                                        # broom up, debris left at the pile
goto_coordinate = ROW2_FAR_COL, ROW2_ROW      # far edge of the next row
press
goto_coordinate = ROW2_MID_COL, ROW2_ROW
goto_coordinate = TARGET_COL, TARGET_ROW       # drag row 2's debris onto the same pile
release
...repeat once per row that has debris, every pass ending at TARGET_COL, TARGET_ROW
goto_coordinate = BROOM_COL, BROOM_ROW
keep                                           # return broom to its original cell

Every row gets its own press/release pair - do not chain rows together under
one press, since only the final destination of each individual contact pass
is where that row's debris ends up. State the target in a `#` comment on the
first press: `# sweep row toward the collection point`.

## 2. Mop a Floor (after sweeping)

Requires a mop object. If none exists, output the MISSING line and skip. A2 has no fill/bucket-solution tracking - mop directly. If the same task also asks for sweeping, list that step first and finish it completely (release + keep the broom) before picking up the mop.

goto_coordinate = MOP_COL, MOP_ROW
pickup
goto_coordinate = A, 1
press                      # mop down
goto_coordinate = B, 1
...one goto per cell, row by row
release
goto_coordinate = MOP_COL, MOP_ROW
keep

## 3. Clean a Surface / Countertop / Table (wipe)

Vision reports only discrete objects, never the table, counter or floor they
rest on, so there is no surface object to read TOUCHES from. Two cases:

(a) The user named the area to wipe in grid terms ("wipe C4 to H8", "wipe row
    6"). Expand that range yourself and wipe exactly those cells.
(b) The user said "wipe the table" with no area given. The board is 20x11 and
    the robot can reach all of it, so wipe the full board row by row.

goto_coordinate = CLOTH_COL, CLOTH_ROW
pickup
goto_coordinate = A, 6
press
goto_coordinate = B, 6
goto_coordinate = C, 6
...one goto per cell being cleaned
goto_coordinate = T, 6
release
goto_coordinate = CLOTH_COL, CLOTH_ROW
keep

If a spray bottle / cleaner object exists, spray the same cells first as a
separate contact pass, returning the spray before picking up the cloth:

goto_coordinate = SPRAY_COL, SPRAY_ROW
pickup
goto_coordinate = A, 6
press                      # spraying
goto_coordinate = B, 6
...same cells
release
goto_coordinate = SPRAY_COL, SPRAY_ROW
keep
# then pick up the cloth and run the wipe pass over the same cells

To clean a specific OBJECT (a plate, a tray, a chopping board), run the contact
pass over that object's own full TOUCHES list rather than a board region.

## 3b. Wash Dishes (sink)

Soap goes on the DISHES, using each dish's own TOUCHES cells - a plate that
touches 4 cells needs the pass to cross all 4, not just its centre. Keep the
sponge pressed while moving from one dish to the next; one pass covers them all.

goto_coordinate = SPONGE_COL, SPONGE_ROW      # or dish soap bottle
pickup
goto_coordinate = DISH1_TOUCH1_COL, DISH1_TOUCH1_ROW
press                                         # soaping
goto_coordinate = DISH1_TOUCH2_COL, DISH1_TOUCH2_ROW
...every cell of dish 1
goto_coordinate = DISH2_TOUCH1_COL, DISH2_TOUCH1_ROW
...every cell of dish 2, and so on per dish/pan/utensil in the sink
release
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

Folding is a momentary press with nothing held. The robot must be above the
garment first. Fold only garments that are not already folded (check DESC).

goto_coordinate = GARMENT1_COL, GARMENT1_ROW
press                       # fold the garment
release
goto_coordinate = GARMENT2_COL, GARMENT2_ROW
press
release
...repeat per garment
# optionally stack folded garments: pickup -> goto STACK_COL, STACK_ROW -> keep

## 6. Appliance -> Load -> Close -> Run

For any openable+switchable appliance (e.g. a washing machine, oven, box), every
open / close / on / off is the same momentary press. The `#` comment is what
tells the operator which one you meant.

goto_coordinate = APPLIANCE_COL, APPLIANCE_ROW
press                       # open the door
release
goto_coordinate = ITEM1_COL, ITEM1_ROW
pickup
goto_coordinate = APPLIANCE_COL, APPLIANCE_ROW
keep
...repeat per item to load
goto_coordinate = APPLIANCE_COL, APPLIANCE_ROW
press                       # close the door
release
press                       # turn the appliance on
release
wait_X(120)                 # let the cycle run
# always end the full task by turning appliances back off:
press                       # turn the appliance off
release

The `wait_X` is REQUIRED here and is a stand-in for the cycle, not a measurement of it - the robot cannot verify the operation actually finished. If the task names the appliance's job ("wash the clothes", "heat the mug", "run the dishwasher") then the cycle running IS the task, so on -> wait_X -> off is the whole point and a plan that presses on and straight back off is wrong. Use the operator's own figure whenever they give one ("run it for five minutes" -> wait_X(300)).

Washing machine + detergent: if a detergent object is present in the OBJECT LIST, add it after loading the laundry items and before the door is closed. Applies to washing machines only. If no detergent object is present, skip this step entirely - do not invent one.

goto_coordinate = DETERGENT_COL, DETERGENT_ROW
pickup
goto_coordinate = APPLIANCE_COL, APPLIANCE_ROW
pour            # or keep if the detergent is a pod/solid, not a liquid
goto_coordinate = DETERGENT_COL, DETERGENT_ROW
keep            # return the detergent bottle before continuing

## 7. Pour Liquid (bottle/jar -> container)

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

Group same-category items together using pickup/keep only. Move objects into the zone one at a time, finishing each object's move before starting the next, then finish with a wipe contact pass. Do not move appliances or UNIDENTIFIED entries during this step - only named loose objects.

goto_coordinate = OBJECT1_COL, OBJECT1_ROW
pickup
goto_coordinate = ZONE_COL, ZONE_ROW
keep
goto_coordinate = OBJECT2_COL, OBJECT2_ROW
pickup
goto_coordinate = ZONE_COL, ZONE_ROW
keep                                                # repeat per object
goto_coordinate = CLOTH_COL, CLOTH_ROW
pickup
goto_coordinate = ZONE_CELL1_COL, ZONE_CELL1_ROW
press                                               # final wipe-down
goto_coordinate = ZONE_CELL2_COL, ZONE_CELL2_ROW
...one goto per zone cell
release
goto_coordinate = CLOTH_COL, CLOTH_ROW
keep

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

Turn on the stove with a momentary press, move the pot onto it, load each solid ingredient into the pot with goto+keep, then pour in any liquid ingredient from a jar. Once cooking is done, plate the contents one item at a time only if a plate is present and plating was requested, then shut the stove off. There is no auto-eject - each item must be retrieved from the pot/pan individually.

goto_coordinate = STOVE_COL, STOVE_ROW
press                             # turn the stove on
release
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

Plating (only if a plate object is present in the OBJECT LIST and the user asked to plate/serve the food - otherwise skip this step entirely and go straight to shutdown):

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

goto_coordinate = STOVE_COL, STOVE_ROW
press                             # turn the stove off
release
goto_coordinate = POT_COL, POT_ROW
pickup
goto_coordinate = POT_HOME_COL, POT_HOME_ROW
keep                              # return pot to its original cell

## 12. Store / Unload Items in a Container (no power cycle)

For a plain container that just opens and closes - fridge, pantry, cabinet,
drawer, closet, dishwasher rack, bin - with no run/wash/cook cycle involved.
Difference from playbook 6: open once, move every item, close once. No press
for "on", no wait_X, unless the task separately asks the appliance to run.

Putting items IN:
goto_coordinate = CONTAINER_COL, CONTAINER_ROW
press                       # open the door/lid/drawer
release
goto_coordinate = ITEM1_COL, ITEM1_ROW
pickup
goto_coordinate = CONTAINER_COL, CONTAINER_ROW
keep
...repeat per item, finishing one item's move before starting the next
goto_coordinate = CONTAINER_COL, CONTAINER_ROW
press                       # close the door/lid/drawer
release

Taking items OUT (unload) is the same shape in reverse - open, then for each
item goto the container, pickup, goto the destination, keep - close only after
every item has been removed:
goto_coordinate = CONTAINER_COL, CONTAINER_ROW
press                       # open
release
goto_coordinate = CONTAINER_COL, CONTAINER_ROW
pickup                      # picks up whatever is in/on the container, last-placed first
goto_coordinate = DEST_COL, DEST_ROW
keep
...repeat per item
goto_coordinate = CONTAINER_COL, CONTAINER_ROW
press                       # close
release

If the task both empties one container and loads another (e.g. "move the
laundry basket to the washer"), treat them as two sub-tasks in order: first
move/empty the source, then load the target, per the PLAN header rules below.

## 13. Tilt-Pour a Bag/Box/Can into a Container

`pour` is not liquid-only - it is also how a bag, box or can of loose contents
(cereal, dry pet food, fertilizer granules, powdered detergent) empties into a
bowl, dish or planter. Same shape as playbook 7. Use `pickup`/`keep` instead
only when the item being moved is itself a single discrete object (a whole
fruit, a canned good, a jar) rather than something poured out of its
container.

goto_coordinate = SOURCE_COL, SOURCE_ROW    # bag, box, can, bottle
pickup
goto_coordinate = DEST_COL, DEST_ROW        # bowl, dish, pot, planter
pour
goto_coordinate = SOURCE_COL, SOURCE_ROW
keep                                         # return the source container

## 14. Push a Heavy or Wheeled Object to a Destination

Grills, bicycles, carts, office chairs, ottomans and other large/wheeled
items are pushed along the ground, never lifted with `pickup`. This is
playbook 3's "Slide / Drag" pattern applied to a destination move rather than
a cleaning pass: press to take hold, one goto per cell of the path, release at
the destination.

goto_coordinate = OBJECT_COL, OBJECT_ROW
press                       # take hold, do not pick up - this stays on the ground
goto_coordinate = WAYPOINT_COL, WAYPOINT_ROW   # optional intermediate cells along the path
goto_coordinate = DEST_COL, DEST_ROW
release                     # let go at the destination

## 15. Replace a Consumable (remove old, insert new)

Trash bags, light bulbs, toilet-paper rolls, batteries: the old one comes out
first and is disposed of or set aside, then a fresh one from the OBJECT LIST
goes into the same holder cell. Both the old and new item must be present in
the OBJECT LIST to plan this - if only one exists, do the half that's
possible and MISSING the other.

goto_coordinate = HOLDER_COL, HOLDER_ROW
pickup                      # take out the old/used one
goto_coordinate = DISPOSAL_COL, DISPOSAL_ROW    # bin, or a temp cell if no bin exists
keep
goto_coordinate = NEW_ITEM_COL, NEW_ITEM_ROW
pickup
goto_coordinate = HOLDER_COL, HOLDER_ROW
keep                        # fresh one now in the holder

## 16. Steps With No A2 Equivalent - Skip, Don't Invent

A2 is a fixed gantry over one board, not a mobile robot: there is no `walk`,
no separate rooms, and every object the robot could possibly reach is already
in the OBJECT LIST because vision already looked at the whole board. When a
task description talks in terms of walking to a room or carrying something up
or down stairs, that is narrative framing, not a step to plan:
- Ignore "walk to X" - the gantry is already positioned by `goto_coordinate`.
- Ignore "carry upstairs/downstairs" - there is one board, one surface.
- A tap/faucet/sink IS plannable whenever vision reports one, because it is a
  thing that gets actuated like any other - see playbook 17. Only skip the
  filling step when no such object appears in the OBJECT LIST at all, and then
  write the MISSING line rather than inventing a coordinate for it.
Only ever emit the eight real commands for physical manipulation that is
actually representable: moving, opening/closing (press/release), pouring,
slicing, waiting. If a task is ENTIRELY made of non-representable steps with
no manipulable object involved, treat it as nothing to plan rather than
inventing a coordinate.

## 17. Fill a Container from a Tap / Faucet / Sink

A tap is not a special case - it is an object that gets actuated, exactly like
a stove knob or a light switch. Turning it on IS a `press` on the tap's own
CENTER cell, and turning it off IS the matching `release`. Never write the
filling as a bare comment on some other command: the robot must actually be
at the tap's coordinate and actually press it.

Requires a tap-type object in the OBJECT LIST (match "tap", "faucet", "sink",
"spigot" via name/ALSO_KNOWN_AS/description). If none exists, output the
MISSING line and skip the filling sub-task.

The robot has ONE gripper, so it cannot hold the container and work the tap at
the same time. Put the container down at the tap's cell first, then actuate:

goto_coordinate = CONTAINER_COL, CONTAINER_ROW    # kettle, watering can, pot, bucket
pickup
goto_coordinate = TAP_COL, TAP_ROW
keep                        # stand the container under the tap
press                       # tap on - water is running
wait_X(20)                  # let the container fill
release                     # tap off
pickup                      # take the now-full container back
goto_coordinate = DEST_COL, DEST_ROW
keep

If the point of filling was to pour it somewhere (watering a plant, filling a
pot on the stove), finish with a pour instead of that last `keep`, then return
the container to where it came from:

goto_coordinate = PLANT_COL, PLANT_ROW
pour                        # water the plant
goto_coordinate = CONTAINER_HOME_COL, CONTAINER_HOME_ROW
keep                        # return the empty watering can

**Rules for playbook 17**
- The `press`/`release` pair belongs to the TAP's cell, not the container's.
  Do not press at the container's home cell and call it filling.
- `wait_X` is required between them - a tap pressed on and instantly off fills
  nothing. Use the operator's figure if given, otherwise 15-30 seconds.
- Rinsing something under the tap is the same shape with no pour at the end.
- Emptying/draining a container down the sink is just a `pour` at the sink's
  cell - no press needed, since nothing is being actuated.

---

## WORKED EXAMPLE - infeasible sub-task

OBJECT LIST contains only: sock (CENTER D7) and shirt (CENTER J3).
Task: "Sweep row 5, then stack all clothes at A10."

PLAN:
- sweep row 5: MISSING broom
- stack clothes: sock, shirt | after: holding nothing

DESTINATIONS:
- sock -> A10
- shirt -> A10

# stack clothes at A10 (sweep skipped)
MISSING: broom - sub-task skipped
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

## WORKED EXAMPLE - wipe every cell of an object

OBJECT LIST contains:
  plate   CENTER G5   TOUCHES F4,G4,H4,F5,G5,H5
  cloth   CENTER C9   TOUCHES C9

Task: "Wipe the plate."

PLAN:
- wipe plate: cloth, plate | after: holding nothing

# wipe every cell of the plate
1. goto_coordinate = C, 9
2. pickup
3. goto_coordinate = F, 4
4. press
5. goto_coordinate = G, 4
6. goto_coordinate = H, 4
7. goto_coordinate = F, 5
8. goto_coordinate = G, 5
9. goto_coordinate = H, 5
10. release
11. goto_coordinate = C, 9
12. keep
Task_Completed

---

## WORKED EXAMPLE - actuate an appliance

OBJECT LIST contains: microwave (CENTER M2), mug (CENTER D8).

Task: "Put the mug in the microwave and start it."

PLAN:
- heat mug: microwave, mug | after: holding nothing

DESTINATIONS:
- mug -> M2

# load the microwave and run it
1. goto_coordinate = M, 2
2. press                     # open the door
3. release
4. goto_coordinate = D, 8
5. pickup
6. goto_coordinate = M, 2
7. keep
8. press                     # close the door
9. release
10. press                    # start the microwave
11. release
12. wait_X(60)               # let it heat
13. press                    # turn the microwave off
14. release
Task_Completed

---

## WORKED EXAMPLE - bare momentary toggle, nothing held or loaded

Not every actuation involves loading an object first - a switch, doorbell,
lamp or knob-only appliance is just goto + press + release on its own.

OBJECT LIST contains: living room lamp (CENTER F2).
Task: "Turn on the living room lamp."

PLAN:
- turn on lamp: living room lamp | after: holding nothing

# turn on the living room lamp
1. goto_coordinate = F, 2
2. press                     # turn the lamp on
3. release
Task_Completed

---

## WORKED EXAMPLE - wait for a cycle with nothing to load

Brewing, steeping and similar cycles that need no items placed inside still
follow on -> wait_X -> off. Do not skip the wait just because nothing was
loaded first.

OBJECT LIST contains: coffee maker (CENTER H3).
Task: "Brew a pot of coffee."

PLAN:
- brew coffee: coffee maker | after: holding nothing

# run the coffee maker's brew cycle
1. goto_coordinate = H, 3
2. press                     # start brewing
3. release
4. wait_X(240)               # let it brew
5. press                     # turn the coffee maker off
6. release
Task_Completed

---

## WORKED EXAMPLE - store items in a container, no power cycle

OBJECT LIST contains: pantry (CENTER Q3), cereal box (CENTER D6), can (CENTER E6).
Task: "Put the cereal box and the can away in the pantry."

PLAN:
- store groceries: pantry, cereal box, can | after: holding nothing

DESTINATIONS:
- cereal box -> Q3
- can -> Q3

# put the cereal box and can into the pantry
1. goto_coordinate = Q, 3
2. press                     # open the pantry door
3. release
4. goto_coordinate = D, 6
5. pickup
6. goto_coordinate = Q, 3
7. keep
8. goto_coordinate = E, 6
9. pickup
10. goto_coordinate = Q, 3
11. keep
12. goto_coordinate = Q, 3
13. press                    # close the pantry door
14. release
Task_Completed

---

## WORKED EXAMPLE - rotation mapping

OBJECT LIST contains: red pen (CENTER B2), blue pen (CENTER B5).
Task: "Swap them: red goes where blue is, blue goes where red was."

PLAN:
- swap pens via temp cell | after: holding nothing

DESTINATIONS:
- red pen -> B5    (blue's current cell)
- blue pen -> B2   (red's current cell)

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

## WORKED EXAMPLE - sweep debris to ONE collection point (playbook 1b)

OBJECT LIST contains:
  broom          CENTER B9    TOUCHES B9
  cutting board  CENTER J4    TOUCHES G3,H3,I3,J3,K3,L3,M3,G4,H4,I4,J4,K4,L4,M4,N4,O4,G5,H5,I5,J5,K5,L5,M5,N5

Task: "Sweep the whole cutting board and collect all the dust at one coordinate."

The board spans rows 3-5. Pick an empty edge cell already in TOUCHES as the
pile - here N5, the board's own bottom-right-most touched cell - so the pile
sits on the object, not off it. Sweep each row toward N5, farthest cell first
so nothing is dragged past the pile.

PLAN:
- sweep cutting board, pile dust at N5: broom, cutting board | after: holding nothing

DESTINATIONS:
- (no object moves - this collects loose debris, not a physical object)

# sweep the cutting board, pile dust at N5
1. goto_coordinate = B, 9
2. pickup
3. goto_coordinate = G, 3               # far edge of row 3
4. press                                 # broom down
5. goto_coordinate = H, 3
6. goto_coordinate = I, 3
7. goto_coordinate = J, 3
8. goto_coordinate = K, 3
9. goto_coordinate = L, 3
10. goto_coordinate = M, 3
11. goto_coordinate = N, 5               # drag row 3's debris onto the pile
12. release
13. goto_coordinate = G, 4               # far edge of row 4
14. press
15. goto_coordinate = H, 4
16. goto_coordinate = I, 4
17. goto_coordinate = J, 4
18. goto_coordinate = K, 4
19. goto_coordinate = L, 4
20. goto_coordinate = M, 4
21. goto_coordinate = N, 4
22. goto_coordinate = O, 4
23. goto_coordinate = N, 5               # drag row 4's debris onto the same pile
24. release
25. goto_coordinate = G, 5               # far edge of row 5
26. press
27. goto_coordinate = H, 5
28. goto_coordinate = I, 5
29. goto_coordinate = J, 5
30. goto_coordinate = K, 5
31. goto_coordinate = L, 5
32. goto_coordinate = M, 5
33. goto_coordinate = N, 5               # already the pile - row 5 ends here
34. release
35. goto_coordinate = B, 9
36. keep
Task_Completed

---

## WORKED EXAMPLE - tilt-pour a bag into a bowl (playbook 13)

OBJECT LIST contains: cereal box (CENTER E6), bowl (CENTER K7).
Task: "Pour the cereal into the bowl."

PLAN:
- pour cereal: cereal box, bowl | after: holding nothing

# pour cereal into the bowl
1. goto_coordinate = E, 6
2. pickup
3. goto_coordinate = K, 7
4. pour
5. goto_coordinate = E, 6
6. keep
Task_Completed

---

## WORKED EXAMPLE - partial pour, source not emptied

OBJECT LIST contains: milk carton (CENTER D4), glass (CENTER J8).
Task: "Pour half the milk into the glass and put the rest back."

"Half" is a fraction of the source, so this is pour(0.5), not bare pour. The
carton is still held afterwards and still has to be returned with a keep.

PLAN:
- pour half the milk: milk carton, glass | after: holding nothing

# pour half the milk, return the carton
1. goto_coordinate = D, 4
2. pickup
3. goto_coordinate = J, 8
4. pour(0.5)                 # half into the glass, half stays in the carton
5. goto_coordinate = D, 4
6. keep                      # carton back home, still half full
Task_Completed

---

## WORKED EXAMPLE - fill from the tap, then water a plant (playbook 17)

OBJECT LIST contains:
  watering can  CENTER C7
  tap           CENTER P2    (ALSO_KNOWN_AS: faucet, sink)
  potted plant  CENTER G10

Task: "Fill the watering can and water the plant."

The tap is actuated at its OWN cell with a real press/release, not described
in a comment. One gripper means the can is set down under the tap before the
tap is touched.

PLAN:
- fill watering can: watering can, tap | after: holding watering can
- water plant: watering can, potted plant | after: holding nothing

# fill the watering can at the tap, then water the plant
1. goto_coordinate = C, 7
2. pickup
3. goto_coordinate = P, 2
4. keep                      # stand the can under the tap
5. press                     # tap on
6. wait_X(20)                # let the can fill
7. release                   # tap off
8. pickup                    # take the full can
9. goto_coordinate = G, 10
10. pour                     # water the plant
11. goto_coordinate = C, 7
12. keep                     # return the empty can
Task_Completed

---

## WORKED EXAMPLE - push a heavy object to a destination (playbook 14)

OBJECT LIST contains: grill (CENTER C10).
Task: "Move the grill to the patio at coordinate Q10."

PLAN:
- push grill to Q10: grill | after: holding nothing

DESTINATIONS:
- grill -> Q10

# push the grill to the patio
1. goto_coordinate = C, 10
2. press                    # take hold - grill stays on the ground, not lifted
3. goto_coordinate = J, 10  # waypoint along the path
4. goto_coordinate = Q, 10
5. release
Task_Completed

---

## WORKED EXAMPLE - replace a consumable (playbook 15)

OBJECT LIST contains:
  trash bin        CENTER R2
  full trash bag    CENTER R2    (inside/at the bin)
  new trash bag      CENTER S8

Task: "Take out the full trash bag and put in a new one."

PLAN:
- replace trash bag: trash bin, full trash bag, new trash bag | after: holding nothing

DESTINATIONS:
- full trash bag -> R2 stays the pickup point, moves out to disposal (no separate outdoor bin object exists here, so it is simply removed to a temp cell T11 - see RULES for temp-cell use)
- new trash bag -> R2

# swap the full trash bag for a new one
1. goto_coordinate = R, 2
2. pickup                   # take out the full bag
3. goto_coordinate = T, 11  # no outdoor bin object in the list - set aside at a free temp cell
4. keep
5. goto_coordinate = S, 8
6. pickup
7. goto_coordinate = R, 2
8. keep                     # new bag now in the bin
Task_Completed

---

## WORKED EXAMPLE - collect multiple objects at one cell (playbook 8)

OBJECT LIST contains: toy car (CENTER D3), toy block (CENTER F9), toy bin (CENTER T1).
Task: "Put all the toys in the bin."

PLAN:
- collect toys at bin: toy car, toy block, toy bin | after: holding nothing

DESTINATIONS:
- toy car -> T1
- toy block -> T1

# collect the toys into the bin
1. goto_coordinate = D, 3
2. pickup
3. goto_coordinate = T, 1
4. keep
5. goto_coordinate = F, 9
6. pickup
7. goto_coordinate = T, 1
8. keep
Task_Completed

---

## WORKED EXAMPLE - tidy a zone, finish with a wipe (playbook 9)

OBJECT LIST contains:
  book       CENTER C2
  remote     CENTER E5
  cloth      CENTER A11    TOUCHES A11
  shelf      CENTER R3     (the zone - a fixed cell, nothing is picked up from it)

Task: "Tidy the coffee table area onto the shelf at R3, then wipe it down."

PLAN:
- tidy zone at R3: book, remote, cloth | after: holding nothing

DESTINATIONS:
- book -> R3
- remote -> R3

# move loose items to the shelf, then wipe the shelf cell
1. goto_coordinate = C, 2
2. pickup
3. goto_coordinate = R, 3
4. keep
5. goto_coordinate = E, 5
6. pickup
7. goto_coordinate = R, 3
8. keep
9. goto_coordinate = A, 11
10. pickup
11. goto_coordinate = R, 3
12. press                   # final wipe-down of the zone cell
13. release
14. goto_coordinate = A, 11
15. keep
Task_Completed

---

## WORKED EXAMPLE - slice food (playbook 4)

OBJECT LIST contains: knife (CENTER B4), tomato (CENTER K6).
Task: "Slice the tomato into 4 pieces."

PLAN:
- slice tomato x4: knife, tomato | after: holding nothing

# slice the tomato
1. goto_coordinate = B, 4
2. pickup
3. goto_coordinate = K, 6
4. keep                      # knife now sits at the tomato's cell
5. slice(tomato, 4)
6. pickup                    # pick the knife back up
7. goto_coordinate = B, 4
8. keep                      # return knife to its original cell
Task_Completed

---

## WORKED EXAMPLE - mop the whole floor, no area named (playbook 2/3)

No mop-target object exists in vision - the floor is background, never
reported. "Mop the kitchen floor" with no area given means the whole
20x11 board, swept row by row, exactly as playbook 3(b) describes.

OBJECT LIST contains: mop (CENTER A1).
Task: "Mop the kitchen floor."

PLAN:
- mop whole board: mop | after: holding nothing

# mop the entire board, row by row
1. goto_coordinate = A, 1
2. pickup
3. goto_coordinate = A, 1
4. press                     # mop down
5. goto_coordinate = B, 1
6. goto_coordinate = C, 1      # (one goto per cell, continuing across row 1 to column T)
7. goto_coordinate = T, 1
8. goto_coordinate = A, 2      # step to row 2, still in contact
9. goto_coordinate = B, 2     # (continue across row 2 to column T, same as row 1)
10. goto_coordinate = T, 2
11. goto_coordinate = A, 3     # (repeat this row shape through row 11, then:)
12. goto_coordinate = T, 11
13. release                    # mop up after the last row
14. goto_coordinate = A, 1
15. keep
Task_Completed

---

## APPENDIX - household task category -> playbook

Every task type below reduces to a playbook above. Use this to route unfamiliar
phrasing instead of inventing new commands or steps.

- Floor cleaning (vacuum/sweep/mop/wipe a spill) -> 1, 1b, 2, 3
- Laundry (basket/washer/dryer load-unload, fold) -> 12 (load/unload), 5 (fold), 6 (run a cycle), 13 (pour detergent)
- Dishwashing (load/unload dishwasher, wash dishes, put dishes away) -> 12, 3b, 6 (run the dishwasher)
- Cooking (stovetop, oven, toaster, kettle, microwave) -> 11, 6, 12 (load food into an appliance)
- Food preparation (fridge/pantry to counter, pour cereal/milk, make a sandwich) -> 12, 13, "Move / Stack / Collect"
- Organizing / tidy a room (books, shoes, toys, remotes, mail to their place) -> 8, 9, "Move / Stack / Collect"
- Bathroom (towels, toiletries, toilet paper, trash) -> 12, 15 (replace roll), "Move / Stack / Collect"
- Bedroom / Living room (pillows, blankets, cushions, curtains) -> "Move / Stack / Collect", 14 (curtain pull is a slide)
- Gardening (watering can, pots, tools, weeds/leaves to bin) -> 13 (watering), 8/"Move / Stack / Collect", 14 (heavy pots)
- Pet care (food/water bowls, litter box, toys) -> 13 (fill bowl), 12, "Move / Stack / Collect"
- Grocery handling (bags to counter, unload into fridge/pantry) -> 14 (heavy bags), 12
- Trash / recycling (take out, replace bag) -> 12, 15
- Storage (boxes, bins, suitcases to/from a closet or shelf) -> 12, "Move / Stack / Collect", 14 (heavy boxes)
- Home office (papers, files, drawers, printer paper, chair) -> 12, "Move / Stack / Collect", 14 (chair)
- Outdoor (patio furniture, grill, bicycle, doormat, firewood) -> 14, "Move / Stack / Collect"
- Home maintenance (toolbox, batteries, light bulb, fire extinguisher) -> "Move / Stack / Collect", 15 (bulb/battery replace)

None of these categories need a new command. "Walk to the room" and door/lid
handling beyond press-release are already covered by playbook 16 - skip the
former, use press/release for the latter.

---

## APPENDIX B - two hundred non-move task titles, by command shape

None of these move an object to a new place - they are all press/release,
contact-pass, pour, slice or wait_X on a single object or the whole board.
Whatever the operator's exact wording, match it to the shape below and reuse
the matching worked example's structure with the real OBJECT LIST cells.

**Shape: momentary press -> release (see "bare momentary toggle" example)**
Turn On/Off: Washing Machine, Dishwasher, Oven, Microwave, Coffee Maker,
Space Heater, Air Purifier, Ceiling Fan, Living Room Lamp, Ceiling Light,
Bathroom Exhaust Fan. Open/Close: Refrigerator Door, Pantry Door, Oven Door,
Kitchen Drawer, Closet Door, Garage Door, Dishwasher Door, Window Blinds.
Press a Switch/Button: Doorbell, Blender Pulse/Power Button, Garbage
Disposal Switch, Toaster Lever, Stand Mixer Start Button, Vacuum Power
Button, Humidifier Power Button, Water Filter Reset Button, Smoke Detector
Test Button, Garage Door Opener Button, Electric Kettle Switch. Turn a
Dial/Adjust: Thermostat, Oven Temperature Dial, Stove Burner Level, Fan
Speed Dial, Humidifier Mist Level, Speaker Volume Knob, Dimmer Switch,
Water Heater Dial. Squeeze/Pump a Dispenser: Hand Soap, Hand Sanitizer,
Ketchup, Mustard, Lotion, Toothpaste, Dish Soap onto a Sponge, Whipped
Cream. Actuate a Lever: Recline a Chair, Raise/Lower a Footrest, Raise/
Lower an Adjustable Bed or Standing Desk, Tilt Blinds Open.

**Shape: press -> wait_X -> release, on/off pair (see "wait for a cycle" example)**
Run a Full Wash/Dry Cycle, Run the Dishwasher Cycle, Brew a Pot of Coffee,
Bake Cookies, Microwave Leftovers, Steep a Pot of Tea, Simmer a Pot of Soup,
Run the Rice Cooker Cycle, Charge a Robot Vacuum, Run an Air Fryer Cycle,
Toast Bread.

**Shape: pickup tool -> goto first cell -> press -> per-cell goto -> release -> return tool (see "wipe every cell of an object" / "mop the whole floor" examples)**
Wipe: Kitchen Countertop, Dining Table, Bathroom Sink Counter, Stovetop,
Refrigerator Door, Coffee Table, Kitchen Island, Microwave Interior,
Bathroom Mirror, TV Screen, Desk, Windowsill, Baseboards, Cabinet Fronts,
Bathtub Rim. Sweep: Kitchen Floor, Patio, Garage Floor, Front Porch, Around
the Dining Table, Hallway, Laundry Room Floor, Balcony, Under the Kitchen
Table, Entryway Tile, Workshop Floor, Basement Floor. Mop: Kitchen Floor,
Bathroom Floor, Hallway, Entryway Tile, Laundry Room Floor, Basement Floor,
Mudroom Floor, Around the Kitchen Island, Garage Floor, Sunroom Floor.
Scrub/Soap: Frying Pan, Dinner Plates, Casserole Dish, Baking Sheet, Coffee
Mugs, Cutting Board, Mixing Bowl, Cutlery, Grill Pan, Sink Basin, Bathtub,
Toilet Bowl. Wash: Living Room Window, Front Door Glass, Bathroom Mirror,
Car Interior Window, Patio Door Glass, Kitchen Window, Hallway Mirror,
Shower Glass Door, Sliding Glass Door, Vanity Mirror.

**Shape: pickup spray -> contact pass -> keep spray -> pickup cloth -> contact pass -> keep cloth (see playbook 3, "spray then wipe" note)**
Spray and Wipe: Kitchen Counter, Bathroom Mirror, Stovetop, Dining Table,
Shower Tiles, Refrigerator Shelves, Windows, Kitchen Sink, Toilet Exterior,
Countertop Backsplash.

**Shape: pickup source -> goto destination -> pour -> return source (see "tilt-pour a bag into a bowl" example, playbook 7/13)**
Pour Liquid: Water into a Glass, Orange Juice into a Cup, Milk into a
Cereal Bowl, Coffee into a Mug, Soup into a Bowl, Wine into a Glass, Olive
Oil into a Pan, Dish Soap into the Sink, Laundry Detergent or Fabric
Softener into the Washer, Pancake Batter onto a Griddle, Broth into a Pot,
Tea into a Cup, Vinegar into a Cleaning Bottle, Water into a Kettle.
Pour Solid/Granular: Cereal into a Bowl, Dry Pet Food into a Bowl, Rice
into a Pot, Sugar or Flour into a Mixing Bowl, Coffee Grounds into a
Filter, Salt into a Shaker, Birdseed into a Feeder, Ice Cubes into a
Cooler, Potting Soil into a Planter.

**Shape: pickup knife -> goto+keep at target -> slice(NAME, N) -> pickup -> return knife (see "slice food" example, playbook 4)**
Slice: a Loaf of Bread, a Tomato, a Cucumber, an Onion, a Block of Cheese,
a Cooked Chicken Breast, a Watermelon, a Lemon, a Bell Pepper, a Carrot, a
Cake, a Bagel.

**Shape: goto garment -> press -> release, no lift (see playbook 5)**
Fold: a Bath Towel, a T-Shirt, a Bedsheet, a Pair of Pants, a Dish Towel, a
Sweater, a Tablecloth, a Baby Blanket, a Beach Towel, a Pillowcase, a Cloth
Napkin, a Winter Scarf.

Every title above is handled by an existing playbook/example - none require
a new command or a new pattern. If an operator's phrasing doesn't obviously
match one of these shapes, fall back to the nearest playbook by what physical
action is being described (contact with a surface -> contact pass; a
container being filled -> pour; a discrete single actuation -> momentary
press), never by inventing a verb.

---

## OUTPUT FORMAT

First output a PLAN header, one line per sub-task, tracking held state:

PLAN:
- <sub-task>: <objects used> | after: holding nothing
(any missing required object -> write its MISSING line instead)

For ANY task that moves, swaps, rotates, or repositions objects, the PLAN must
also include a DESTINATIONS block - this is REQUIRED, do not write any command
without it:

DESTINATIONS:
- <object> -> <final cell>     (one line per moved object)

CHECK: "X goes where Y is" means X's final cell is Y's CURRENT cell (Y's CENTER
in the OBJECT LIST). It does NOT mean Y moves to X's cell. Verify every
DESTINATIONS line against this rule before writing commands.

Then the commands. Alpha 2D unstacking is invoked by the application itself
before every task. Do NOT output an invoke command:

# brief task description
1. command
2. command
...
Task_Completed

Strict: numbered lines contain ONLY the eight commands.
No Markdown, no JSON, no explanations, no confidence scores. A short `#` comment
may be appended to a command or written on its own line - everything after `#`
is ignored by the robot and exists only to say which real-world action a generic
press was meant to perform. Task_Completed is always the final line.
"""
)


# ═════════════════════════════════════════════════════════════════════════════
#  RESILIENT API LAYER
#
#  Every intermittent "it just stops" report traces back to this being absent.
#  A single transient 429, a dropped socket, or a response that spent its whole
#  budget before emitting content would kill the import outright — and with
#  second-pass verification enabled there are two calls per image, so the
#  exposure doubled.
# ═════════════════════════════════════════════════════════════════════════════
API_TIMEOUT_S   = 90.0
API_RETRIES     = 3
API_BACKOFF_S   = 1.6


class ModelError(RuntimeError):
    """Carries a message already phrased for the user."""


def resolve_openai_api_key() -> str:
    """Return the API key hardcoded in OPENAI_API_KEY above — nowhere else."""
    return (OPENAI_API_KEY or "").strip()


def make_client():
    return OpenAI(api_key=resolve_openai_api_key(),
                  timeout=API_TIMEOUT_S, max_retries=0)


def _describe_finish(resp):
    """Turn an empty completion into an explanation instead of silence."""
    try:
        choice = resp.choices[0]
    except (AttributeError, IndexError):
        return "the model returned no choices"
    reason = getattr(choice, "finish_reason", None)
    if reason == "length":
        return ("the model hit its token ceiling before writing any JSON "
                "(scene too busy — try again, or turn off second-pass)")
    if reason == "content_filter":
        return "the response was blocked by a content filter"
    if reason:
        return f"the model stopped early (finish_reason={reason})"
    return "the model returned an empty response"


def call_model(client, *, model, messages, max_tokens, stage="request",
               on_retry=None):
    """One chat completion with bounded retries and a real error message.

    Retries only on transport/rate faults. A content filter or a malformed
    request fails immediately — retrying those just wastes the user's time.
    """
    last = None
    for attempt in range(1, API_RETRIES + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                max_completion_tokens=max_tokens,
            )
            text = ""
            try:
                text = (resp.choices[0].message.content or "").strip()
            except (AttributeError, IndexError):
                text = ""
            if not text:
                raise ModelError(f"{stage}: {_describe_finish(resp)}")
            return text
        except ModelError:
            raise
        except Exception as e:                      # transport / rate / server
            last = e
            name = type(e).__name__
            if attempt < API_RETRIES:
                if on_retry:
                    on_retry(attempt, name)
                import time as _t
                _t.sleep(API_BACKOFF_S * attempt)
                continue
    raise ModelError(f"{stage} failed after {API_RETRIES} attempts "
                     f"({type(last).__name__}: {str(last)[:120]})")


# ═════════════════════════════════════════════════════════════════════════════
#  Vision worker  —  measured canvas → detect → (optional) verify → cells
# ═════════════════════════════════════════════════════════════════════════════
VERIFY_COLORS = [(255, 210, 60), (80, 240, 120), (255, 120, 220), (120, 200, 255),
                 (255, 150, 80), (200, 140, 255), (100, 255, 230), (255, 100, 120)]


class VisionWorker(QThread):
    done     = Signal(list)   # list of object dicts
    error    = Signal(str)
    progress = Signal(str)    # stage text for the sidebar

    def __init__(self, bgr, verify=True, snap=SNAP_DEFAULT_ON, task_text=None):
        super().__init__()
        self._bgr    = bgr
        self._verify = verify
        self._snap   = snap
        # Whatever is in the task box when detection runs. Used only to lift the
        # surface-exclusion for furniture the operator explicitly asked to move
        # (see build_furniture_note) — detection is otherwise task-independent.
        self._task   = task_text

    # ── API call ─────────────────────────────────────────────────────────────
    def _ask(self, client, canvas, prompt, stage="Vision"):
        b64 = encode_jpeg_b64(canvas)
        if b64 is None:
            raise ModelError("Frame encode failed")
        return call_model(
            client,
            model=VISION_MODEL,
            messages=[{"role": "user", "content": [
                {"type": "text",      "text": prompt},
                {"type": "image_url", "image_url": {
                    "url": f"data:image/jpeg;base64,{b64}", "detail": "high"}},
            ]}],
            max_tokens=12000,
            stage=stage,
            on_retry=lambda n, why: self.progress.emit(
                f"⟳  {stage} retry {n}/{API_RETRIES - 1} ({why})…"),
        )

    # ── raw model entries → polygons in original-frame space ────────────────
    @staticmethod
    def _convert(entries, mapping):
        """Model JSON → normalised polygons. No cells yet: position is still
        provisional at this stage and gets settled by the CV snap."""
        objs = []
        for obj in entries:
            if not isinstance(obj, dict):
                continue
            name    = str(obj.get('name', 'object')).lower().strip() or 'object'
            polygon = obj.get('polygon')

            if isinstance(polygon, list) and len(polygon) >= 3:
                try:
                    sq = [(max(0.0, min(1000.0, float(p[0]))),
                           max(0.0, min(1000.0, float(p[1])))) for p in polygon]
                except (TypeError, ValueError, IndexError):
                    continue
            else:
                box = obj.get('box')
                try:
                    bx0, by0, bx1, by1 = [float(v) for v in box]
                except (TypeError, ValueError):
                    continue
                sq = [(bx0, by0), (bx1, by0), (bx1, by1), (bx0, by1)]

            # Unmap RAW. Clamping here was the full-frame bug: a point that
            # strayed into a letterbox bar unmapped to a negative coordinate,
            # got pinned to the edge, and the object silently grew to the
            # photo's full width. Clip properly, discard what was mostly bar.
            poly = [unmap_point(x, y, mapping, clamp=False) for x, y in sq]
            poly, kept = clip_to_frame(poly)
            if len(poly) < 3 or kept < PADDING_KEEP_MIN:
                print(f"[clip] {name}: {100 * kept:.0f}% inside frame — discarded "
                      f"(outlined into the letterbox padding)")
                continue
            if kept < 0.995:
                print(f"[clip] {name}: trimmed to {100 * kept:.0f}% (padding overhang)")

            objs.append({
                'name':    name,
                'color':   obj.get('color', '?'),
                'size':    obj.get('size', '?'),
                'desc':    obj.get('desc', ''),
                'aka':     obj.get('aka', []),
                'polygon': poly,
                'source':  'vision',
                '_sq':     sq,
            })
        return objs

    # ── background rejection + CV snap + cell resolution ────────────────────
    def _localise(self, objs):
        """Turn provisional polygons into grid-locked objects.

        With snapping off (the default) this is background rejection plus cell
        resolution — the model's outlines, already measured against the ruler
        canvas, are the position. With snapping on, outlines are additionally
        locked to segmented contours where a confident match exists.
        """
        bgr   = self._bgr
        blobs, mask = [], None

        if self._snap:
            blobs, mask = segment_blobs(bgr)
            if not blobs:
                print("[cv] no usable blobs — keeping model outlines")

        live = []
        for o in objs:
            bg, why = is_background_polygon(o['polygon'], bgr, mask,
                                            name=o.get('name'))
            if bg:
                print(f"[bg] {o['name']}: rejected as background ({why})")
                continue
            o.setdefault('snapped', False)
            live.append(o)

        snapped = 0
        if self._snap and blobs:
            snapped = snap_to_blobs(live, bgr, blobs)
            extras = unknown_from_blobs(blobs, live)
            for e in extras:
                e['source'] = 'segment'
                print(f"[cv] {e['name']}: unmatched blob surfaced")
            live.extend(extras)

        for o in live:
            poly = o['polygon']
            center, touches, cov = polygon_to_cells(poly)
            if center is None:
                o['_cells'] = []
                continue
            o['polygon'] = [[round(x, 1), round(y, 1)] for x, y in poly]
            o['box']     = [round(v, 1) for v in _poly_bbox(poly)]
            o['_center'] = center
            o['_cells']  = touches
            o['_cov']    = cov

        live = [o for o in live if o.get('_cells')]
        resolve_overlaps(live)

        out = []
        for o in live:
            if not o['_cells']:
                continue
            o['center']  = cell_name(o['_center'])
            o['touches'] = ",".join(cell_name(c) for c in o['_cells'])
            out.append(o)
        return out, snapped

    # ── draw current detections back onto the canvas for the verify pass ────
    @staticmethod
    def _annotate(canvas, objs, mapping):
        out = canvas.copy()
        S, M = mapping['S'], mapping['M']

        def to_px(pt):
            return (M + int(round(pt[0] / 1000.0 * S)),
                    M + int(round(pt[1] / 1000.0 * S)))

        for i, o in enumerate(objs):
            col = VERIFY_COLORS[i % len(VERIFY_COLORS)]
            pts = np.array([to_px(p) for p in o['_sq']], np.int32)
            cv2.polylines(out, [pts], True, col, max(2, S // 500), cv2.LINE_AA)
            tag = f"{i + 1}"
            tx, ty = pts[:, 0].min(), max(M + 14, pts[:, 1].min() - 6)
            fs = max(0.45, S / 1400.0)
            ft = max(1, int(round(S / 700.0)))
            (tw, th), _ = cv2.getTextSize(tag, cv2.FONT_HERSHEY_SIMPLEX, fs, ft)
            cv2.rectangle(out, (tx - 2, ty - th - 4), (tx + tw + 4, ty + 3), (0, 0, 0), -1)
            cv2.putText(out, tag, (tx + 1, ty), cv2.FONT_HERSHEY_SIMPLEX,
                        fs, col, ft, cv2.LINE_AA)
        return out

    @staticmethod
    def _accept_verify(before, after):
        """Keep pass-2 only where it moved things a sane distance.

        Pass 2 has no more ground truth than pass 1 — it is the same model
        looking again. Left unchecked it can teleport a correct outline across
        the frame, which is worse than the drift it was meant to fix. Objects
        matched by name keep the new outline only if the move is small; the
        rest of pass 2 (genuinely new or dropped objects) is accepted as-is.
        """
        prev = {}
        for o in before:
            prev.setdefault(o['name'], poly_centroid(o['polygon']))
        rejected = 0
        for o in after:
            c = prev.get(o['name'])
            if not c:
                continue
            nx, ny = poly_centroid(o['polygon'])
            if math.hypot(nx - c[0], ny - c[1]) / 1000.0 > VERIFY_MAX_TRAVEL:
                rejected += 1
                o['_veto'] = True
        if rejected:
            print(f"[verify] {rejected} correction(s) moved too far — pass 1 kept")
        return rejected

    # ── thread body ─────────────────────────────────────────────────────────
    def run(self):
        try:
            canvas, mapping = build_measured_canvas(self._bgr)
            client = make_client()

            self.progress.emit("🔍  Pass 1 — identifying objects…")
            raw = self._ask(client, canvas,
                            build_vision_prompt(mapping, task_text=self._task),
                            stage="Vision pass 1")
            entries, salvaged = parse_vision_json(raw)
            if not entries:
                self.error.emit(
                    "Vision model returned no parsable objects.\n\nRaw output:\n" + raw[:700])
                return
            if salvaged:
                print("[vision] response was truncated — salvaged complete entries only")

            objs = self._convert(entries, mapping)
            if not objs:
                self.error.emit("Vision returned no usable objects.")
                return

            if self._verify:
                try:
                    self.progress.emit(f"🔎  Pass 2 — verifying {len(objs)} outlines…")
                    annotated = self._annotate(canvas, objs, mapping)
                    raw2 = self._ask(client, annotated,
                                     build_vision_prompt(mapping, VERIFY_PROMPT,
                                                         task_text=self._task),
                                     stage="Vision pass 2")
                    entries2, _ = parse_vision_json(raw2)
                    objs2 = self._convert(entries2, mapping) if entries2 else []
                    if objs2:
                        self._accept_verify(objs, objs2)
                        keep = {o['name'] for o in objs2 if o.get('_veto')}
                        merged = [o for o in objs2 if not o.get('_veto')]
                        merged += [o for o in objs if o['name'] in keep]
                        objs = merged or objs
                    else:
                        print("[vision] verification pass unusable — keeping pass 1")
                except Exception as e:
                    print(f"[vision] verification pass failed ({e}) — keeping pass 1")

            self.progress.emit("📐  Resolving grid cells…"
                               if not self._snap else
                               "📐  Locking outlines to image pixels…")
            objs, snapped = self._localise(objs)
            if not objs:
                self.error.emit(
                    "Every detection was rejected as background — the model "
                    "outlined the scene rather than the objects in it. Retry, "
                    "or use an image with clearly separated objects.")
                return

            if self._snap:
                n_unknown = sum(1 for o in objs if o.get('unknown'))
                print(f"[cv] {snapped}/{len(objs)} outline(s) snapped; "
                      f"{n_unknown} unidentified")

            for o in objs:
                o.pop('_sq', None); o.pop('_cov', None); o.pop('_veto', None)
            self.done.emit(objs)

        except Exception as e:
            self.error.emit(str(e))


# ─────────────────────────────────────────────────────────────────────────────
#  Dexterity worker — silent gate before the planner
# ─────────────────────────────────────────────────────────────────────────────
class DexterityWorker(QThread):
    verdict = Signal(str)   # 'dexterous' | 'non-dexterous'
    error   = Signal(str)

    def __init__(self, task: str):
        super().__init__()
        self._task = task

    def run(self):
        try:
            client = make_client()
            raw = call_model(
                client,
                model=DEXTERITY_MODEL,
                messages=[
                    {"role": "system", "content": DEXTERITY_SYSTEM},
                    {"role": "user",   "content": self._task},
                ],
                max_tokens=2000,
                stage="Dexterity check",
            ).lower()
            if "non-dexterous" in raw or "non_dexterous" in raw:
                self.verdict.emit("non-dexterous")
            else:
                self.verdict.emit("dexterous")
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
            client = make_client()
            user_msg = f"OBJECT LIST:\n{self._objects}\n\nTask: {self._task}"
            print("=== PLANNER INPUT ===")
            print(user_msg)
            print("=== END ===")

            # A stream can die mid-flight. Retry only while nothing has been
            # emitted yet — once text is on screen, restarting would duplicate it.
            full = ""
            last  = None
            for attempt in range(1, API_RETRIES + 1):
                try:
                    stream = client.chat.completions.create(
                        model=PLANNER_MODEL,
                        messages=[
                            {"role": "system", "content": A2_SYSTEM},
                            {"role": "user",   "content": user_msg},
                        ],
                        max_completion_tokens=6000,
                        stream=True,
                    )
                    for ch in stream:
                        try:
                            delta = ch.choices[0].delta.content or ""
                        except (AttributeError, IndexError):
                            continue
                        if delta:
                            full += delta
                            self.chunk.emit(delta)
                    break
                except Exception as e:
                    last = e
                    if full:
                        break                      # partial output kept
                    if attempt < API_RETRIES:
                        import time as _t
                        _t.sleep(API_BACKOFF_S * attempt)
                        continue
                    raise ModelError(
                        f"Planner failed after {API_RETRIES} attempts "
                        f"({type(last).__name__}: {str(last)[:120]})")
            if not full.strip():
                raise ModelError("Planner returned an empty response.")
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
        # The cyan lattice, its per-cell labels and the A-T / 1-11 headers were
        # presentation only — the grid the pipeline actually reasons about is
        # burned into the measured canvas by build_measured_canvas(). Cell
        # geometry still drives every position below via _grid_area().
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
                    pts = [(max(0.0, min(1000.0, float(p[0]))),
                            max(0.0, min(1000.0, float(p[1])))) for p in polygon]
                except (TypeError, ValueError, IndexError):
                    continue
                xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
                x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
                qpoly = [QPointF(gx + px / 1000.0 * gw, gy + py / 1000.0 * gh)
                         for px, py in pts]
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

            manual  = obj.get('source') == 'manual'
            unknown = bool(obj.get('unknown'))
            if manual:
                color = QColor('#facc15')
            elif unknown:
                color = QColor('#94a3b8')
            else:
                color = self.BBOX_COLORS[idx % len(self.BBOX_COLORS)]

            fill = QColor(color); fill.setAlpha(22 if unknown else 30)
            painter.setBrush(QBrush(fill))
            pen = QPen(color, 2)
            if manual or unknown:
                pen.setStyle(Qt.DashLine)
            painter.setPen(pen)
            if qpoly is not None:
                painter.drawPolygon(QPolygonF(qpoly))
            else:
                painter.drawRect(QRectF(gx + x0 / 1000.0 * gw, gy + y0 / 1000.0 * gh,
                                        (x1 - x0) / 1000.0 * gw,
                                        (y1 - y0) / 1000.0 * gh))

            lbl = obj.get('name', 'object')
            if obj.get('center'):
                lbl += f"  @ {obj['center']}"
            if manual:
                lbl = "✎ " + lbl
            if unknown:
                lbl = "? " + lbl
            elif obj.get('snapped'):
                lbl += "  ⧉"
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

        ci, ri = int(round(self._cur_col)), int(round(self._cur_row))
        hx = area.x() + ci * cell_w
        hy = area.y() + ri * cell_h
        hc = QColor(color); hc.setAlpha(int(38 + 18 * pulse))
        painter.setBrush(QBrush(hc))
        painter.setPen(QPen(color, 1.4))
        painter.drawRect(QRectF(hx, hy, cell_w, cell_h))

        glow_r = r * (1.9 + 0.25 * pulse)
        grad   = QRadialGradient(px, py, glow_r)
        gc     = QColor(color); gc.setAlpha(int(70 + 30 * pulse))
        grad.setColorAt(0.0, gc)
        grad.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 0))
        painter.setBrush(QBrush(grad)); painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(px, py), glow_r, glow_r)

        dc = QColor(color); dc.setAlpha(235)
        painter.setBrush(QBrush(dc)); painter.setPen(QPen(QColor(255, 255, 255, 200), 1.5))
        painter.drawEllipse(QPointF(px, py), r, r)

        hi_r = r * 0.38
        painter.setBrush(QBrush(QColor(255, 255, 255, int(170 + 60 * pulse))))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(px - r * 0.18, py - r * 0.18), hi_r, hi_r)

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
#  CommandRunner  (speed-aware)
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
        'goto': 1300, 'pickup': 950, 'keep': 950, 'pour': 1300,
        'slice': 1100, 'press': 800, 'release': 800, 'default': 700,
    }
    # A goto issued between press and release is one step of a contact pass
    # (sweeping, mopping, wiping) rather than a deliberate reposition, so it
    # runs at this shorter interval instead of DELAY['goto'].
    CELL_STEP = 420

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cmds    : list = []
        self._idx     : int  = 0
        self._running : bool = False
        self._speed   : float = 1.0
        self._pressed : bool = False
        self._timer   = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._step)

    def set_speed(self, mult: float):
        self._speed = max(0.25, min(6.0, float(mult)))

    def _scaled(self, ms: int) -> int:
        return max(40, int(ms / self._speed))

    def load(self, text: str):
        # Alpha 2D preparation is an application invariant, not a planner
        # decision. Strip a legacy/model-produced invoke if present, then add
        # exactly one hard-coded preparation step before every task.
        planned = [cmd for cmd in self._parse(text)
                   if not cmd.strip().lower().startswith('invoke')]
        self._cmds    = (["invoke(Alpha_2D_unstacker)"] + planned) if planned else []
        self._idx     = 0
        self._running = False
        self._pressed = False

    def start(self):
        if not self._cmds:
            return
        self._running = True
        self._idx     = 0
        self._pressed = False
        self.show_dot.emit(0, 0)
        QTimer.singleShot(self._scaled(250), self._step)

    def stop(self):
        self._running = False
        self._pressed = False
        self._timer.stop()

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
            # A trailing "# turn the stove on" annotates a generic press for the
            # operator; strip it so _dispatch only ever sees the bare command.
            line = line.split('#', 1)[0].strip()
            if line:
                cmds.append(line)
        return cmds

    def _step(self):
        if not self._running or self._idx >= len(self._cmds):
            return
        cmd = self._cmds[self._idx]
        self._idx += 1
        self.step_info.emit(self._idx, len(self._cmds), cmd)
        delay = self._dispatch(cmd)
        if self._running and delay > 0:
            self._timer.start(self._scaled(delay))

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

    def _dispatch(self, cmd: str) -> int:
        raw = cmd.strip()

        m = re.match(r'goto_coordinate\s*[:=]?\s*([A-Ta-t])\s*,?\s*(\d{1,2})\b',
                     raw, re.IGNORECASE)
        if m:
            col = max(0, min(COLS - 1, ord(m.group(1).upper()) - ord('A')))
            row = max(0, min(ROWS - 1, int(m.group(2)) - 1))
            self.move_to.emit(col, row)
            # Between press and release the gantry is holding something down
            # against the surface — a tool mid-sweep or an object being slid — so
            # a goto is one stroke of a contact pass, not a free move.
            key = 'contact' if self._pressed else 'goto'
            self.state_changed.emit(*CMD_STATES[key])
            return self.CELL_STEP if self._pressed else self.DELAY['goto']
        if raw.lower().startswith('goto_coordinate'):
            print(f"[CommandRunner] Unparsed goto_coordinate: {raw!r}")

        lc = raw.lower().split('(')[0].strip()

        if lc.startswith('invoke'):
            self._invoke_sequence()
            return 0

        if lc in ('pickup', 'keep', 'pour'):
            # pour may carry a fraction of the source — pour(0.5). Bare pour is
            # a full empty. Anything unparsable falls back to a full pour rather
            # than stalling the run.
            if lc == 'pour' and '(' in raw:
                mf = re.search(r'(\d*\.?\d+)', raw.split('(', 1)[1])
                frac = max(0.0, min(1.0, float(mf.group(1)))) if mf else 1.0
                if frac < 1.0:
                    self.state_changed.emit(CMD_STATES['pour'][0],
                                            f'Pouring {frac * 100:g}%…')
                    return self.DELAY['pour']
            self.state_changed.emit(*CMD_STATES[lc])
            return self.DELAY[lc]

        # press engages the tool / actuates whatever is at the current cell;
        # release ends it. Together they cover every appliance and cleaning
        # action the command set used to name individually.
        if lc in ('press', 'release'):
            self._pressed = (lc == 'press')
            self.state_changed.emit(*CMD_STATES[lc])
            return self.DELAY[lc]

        if lc.startswith('slice'):
            self.state_changed.emit(*CMD_STATES['slice'])
            return self.DELAY['slice']

        # wait_X(SECONDS) — hold position and do nothing while something outside
        # the robot's control happens: a cycle running, a kettle boiling, a
        # surface drying. Every wait_ spelling the planner produces lands here;
        # the duration is read from the argument, defaulting to 2s if it wrote
        # none. The gantry keeps whatever it is holding or pressing.
        if lc.startswith('wait'):
            arg = raw.split('(', 1)[1] if '(' in raw else raw
            m2  = re.search(r'(\d+(?:\.\d+)?)', arg) or \
                  re.search(r'(\d+(?:\.\d+)?)', raw)
            secs = max(0.0, float(m2.group(1))) if m2 else 2.0
            play = min(secs, WAIT_MAX_PLAYBACK)
            txt  = (f'Waiting {secs:g}s…' if play >= secs
                    else f'Waiting {secs:g}s (simulated as {play:g}s)…')
            self.state_changed.emit(CMD_STATES['wait'][0], txt)
            return int(play * 1000)

        if lc == 'task_completed':
            self.state_changed.emit(*CMD_STATES['complete'])
            self._running = False
            self._pressed = False
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
    """Vertical-only scroll area with the inner widget clamped to the viewport."""
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
# ─────────────────────────────────────────────────────────────────────────────
#  Conversation widgets
#
#  Qt's rich-text engine cannot align a bubble to one side, round only three of
#  its corners, or animate anything, so the transcript is built from real
#  widgets instead of appended HTML. Each message paints its own glass panel;
#  in-progress stages shimmer left-to-right until they resolve.
# ─────────────────────────────────────────────────────────────────────────────
class ShimmerLabel(QWidget):
    """One line of text with a soft highlight sweeping left → right."""

    PERIOD_MS = 30          # ~33 fps, enough for a smooth sweep
    SPEED     = 0.011       # phase advanced per tick (full sweep ≈ 2.7 s)
    BAND      = 0.22        # half-width of the bright band, in widget widths

    def __init__(self, text="", dim=C_TEXT_DIM, bright=C_TEXT, parent=None):
        super().__init__(parent)
        self._text   = text
        self._dim    = QColor(dim)
        self._bright = QColor(bright)
        self._phase  = -self.BAND
        self._active = True
        self.setFont(QFont(UI_FONT, 10))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(self.PERIOD_MS)

    def text(self):
        return self._text

    def set_text(self, text):
        self._text = text
        self._phase = -self.BAND
        self.updateGeometry()
        self.update()

    def set_active(self, active: bool):
        """Freeze the sweep once the stage it describes has finished."""
        self._active = active
        if active:
            if not self._timer.isActive():
                self._timer.start(self.PERIOD_MS)
        else:
            self._timer.stop()
        self.update()

    def _tick(self):
        self._phase += self.SPEED
        if self._phase > 1.0 + self.BAND:
            self._phase = -self.BAND
        self.update()

    def sizeHint(self):
        fm = QFontMetrics(self.font())
        return QSize(fm.horizontalAdvance(self._text) + 6, fm.height() + 4)

    def minimumSizeHint(self):
        return QSize(40, QFontMetrics(self.font()).height() + 4)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        fm = QFontMetrics(self.font())
        text = fm.elidedText(self._text, Qt.ElideRight, self.width())
        p.setFont(self.font())

        if not self._active:
            p.setPen(self._dim)
            p.drawText(self.rect(), Qt.AlignLeft | Qt.AlignVCenter, text)
            return

        # The band is a gradient across the label, not a moving overlay, so the
        # highlight bleeds into the surrounding letters instead of stepping.
        grad = QLinearGradient(0, 0, max(self.width(), 1), 0)
        base = QColor(self._dim); base.setAlpha(130)
        edge = QColor(self._bright); edge.setAlpha(190)
        peak = QColor(self._bright); peak.setAlpha(255)
        stops = [(0.0, base), (1.0, base)]
        for offset, colour in ((-self.BAND, base), (-self.BAND / 2, edge),
                               (0.0, peak), (self.BAND / 2, edge),
                               (self.BAND, base)):
            pos = self._phase + offset
            if 0.0 <= pos <= 1.0:
                stops.append((pos, colour))
        for pos, colour in sorted(stops, key=lambda s: s[0]):
            grad.setColorAt(min(max(pos, 0.0), 1.0), colour)
        p.setPen(QPen(QBrush(grad), 1))
        p.drawText(self.rect(), Qt.AlignLeft | Qt.AlignVCenter, text)


class DetailPane(QWidget):
    """A '›' toggle that slides a block of raw detail open underneath."""

    toggled = Signal()

    def __init__(self, on_dark=False, parent=None):
        super().__init__(parent)
        self._open  = False
        self._lines = []
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)

        arrow_c = "rgba(255,255,255,0.8)" if on_dark else C_TEXT_DIM
        hover_c = "#ffffff" if on_dark else C_BLUE
        self._btn = QPushButton("›  Details")
        self._btn.setCursor(Qt.PointingHandCursor)
        self._btn.setFlat(True)
        self._btn.setFixedHeight(18)
        self._btn.setFont(QFont(UI_FONT, 8, QFont.Bold))
        self._btn.setStyleSheet(
            f"QPushButton{{background:transparent;border:none;color:{arrow_c};"
            f"text-align:left;padding:0;letter-spacing:0.06em;}}"
            f"QPushButton:hover{{color:{hover_c};}}")
        self._btn.clicked.connect(self.toggle)

        self._copy_btn = QPushButton("Copy")
        self._copy_btn.setCursor(Qt.PointingHandCursor)
        self._copy_btn.setFlat(True)
        self._copy_btn.setFixedHeight(18)
        self._copy_btn.setFont(QFont(UI_FONT, 8, QFont.Bold))
        self._copy_btn.setStyleSheet(
            f"QPushButton{{background:transparent;border:none;color:{arrow_c};"
            f"text-align:left;padding:0 0 0 12px;letter-spacing:0.06em;}}"
            f"QPushButton:hover{{color:{hover_c};}}")
        self._copy_btn.clicked.connect(self._copy)
        self._copy_btn.setVisible(False)

        body_c = "rgba(255,255,255,0.72)" if on_dark else C_TEXT_DIM
        rule_c = "rgba(255,255,255,0.25)" if on_dark else C_BORDER
        self._body = QLabel("")
        self._body.setWordWrap(True)
        self._body.setFont(QFont(MONO_FONT, 8))
        self._body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._body.setStyleSheet(
            f"color:{body_c};background:transparent;border:none;"
            f"border-left:1px solid {rule_c};padding:2px 0 2px 8px;")
        self._body.setMaximumHeight(0)
        self._body.setVisible(False)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(0)
        head.addWidget(self._btn)
        head.addWidget(self._copy_btn)
        head.addStretch(1)
        v.addLayout(head)
        v.addWidget(self._body)

        self._anim = QPropertyAnimation(self._body, b"maximumHeight", self)
        self._anim.setDuration(190)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.finished.connect(self._unclamp)

    def add_line(self, text: str):
        if not text or (self._lines and self._lines[-1] == text):
            return
        self._lines.append(text)
        self._body.setText("\n".join(self._lines))
        if self._open:
            self._body.setMaximumHeight(16777215)

    def has_lines(self) -> bool:
        return bool(self._lines)

    def enable_copy(self):
        self._copy_btn.setVisible(True)

    def _copy(self):
        QApplication.clipboard().setText("\n".join(self._lines))
        self._copy_btn.setText("Copied")
        QTimer.singleShot(1400, lambda: self._copy_btn.setText("Copy"))

    def is_open(self) -> bool:
        return self._open

    def natural_width(self) -> int:
        fm = QFontMetrics(self._body.font())
        return max((fm.horizontalAdvance(l) for l in self._lines), default=0) + 12

    def toggle(self):
        self._open = not self._open
        self._btn.setText(("⌄  Details" if self._open else "›  Details"))
        self._anim.stop()
        if self._open:
            self._body.setVisible(True)
            target = self._body.sizeHint().height()
            self._anim.setStartValue(0)
            self._anim.setEndValue(max(target, 14))
        else:
            self._anim.setStartValue(self._body.height())
            self._anim.setEndValue(0)
        self._anim.start()
        self.toggled.emit()

    def _unclamp(self):
        # Once open, release the height clamp or lines added later get cut off.
        if self._open:
            self._body.setMaximumHeight(16777215)


class ComposeEdit(QPlainTextEdit):
    """Message box: Enter sends, ⇧⏎ is a new line, ⌘⏎ and ⌘⌫ drop a line."""

    submitted = Signal()

    def keyPressEvent(self, ev):
        enter = ev.key() in (Qt.Key_Return, Qt.Key_Enter)
        # ⌘ arrives as ControlModifier on macOS. Checked ahead of the send
        # rule, which only excludes Shift and would otherwise fire on ⌘⏎.
        if enter and (ev.modifiers() & Qt.ControlModifier):
            self._delete_line()
            ev.accept()
            return
        # Qt binds ⌘⌫ to "delete to start of line", which leaves everything
        # right of the cursor behind. Take the whole line instead.
        if (ev.key() in (Qt.Key_Backspace, Qt.Key_Delete)
                and (ev.modifiers() & Qt.ControlModifier)):
            self._delete_line()
            ev.accept()
            return
        if enter and not (ev.modifiers() & Qt.ShiftModifier):
            self.submitted.emit()
            ev.accept()
            return
        super().keyPressEvent(ev)

    def _delete_line(self):
        """Remove the line the cursor sits on, closing the gap behind it."""
        cur = self.textCursor()
        cur.beginEditBlock()
        cur.select(QTextCursor.BlockUnderCursor)
        cur.removeSelectedText()
        # BlockUnderCursor takes the newline *before* the line, so deleting the
        # first of several lines would otherwise leave an empty one behind.
        if cur.atBlockStart() and not cur.atEnd():
            cur.deleteChar()
        cur.endEditBlock()
        self.setTextCursor(cur)


# ── voice input ──────────────────────────────────────────────────────────────
# SpeechRecognition is optional: without it the microphone button simply says
# so instead of the app refusing to start.
try:
    import speech_recognition as speech_rec
    SPEECH_IMPORT_ERROR = ""
except Exception as _exc:
    speech_rec = None
    # Name the interpreter that came up short: installing into the wrong one
    # of several Pythons on a machine is the usual cause, and "not installed"
    # alone sends you round in circles.
    SPEECH_IMPORT_ERROR = f"{_exc}  —  running on {sys.executable}"

# Say these out loud and they arrive as punctuation. Longer phrases first so
# "question mark" is matched before "mark" can be eaten by a shorter rule.
SPOKEN_PUNCTUATION = [
    ("new paragraph", "\n\n"), ("full stop", "."), ("question mark", "?"),
    ("exclamation mark", "!"), ("exclamation point", "!"),
    ("open parenthesis", "("), ("close parenthesis", ")"),
    ("new line", "\n"), ("comma", ","), ("period", "."),
    ("colon", ":"), ("semicolon", ";"),
]


def mic_icon(colour: str, size: int = 22) -> QIcon:
    """The thin-line microphone: a capsule, a cradle arc, a short stem.

    Drawn rather than typed as an emoji so it inherits the button's colour and
    keeps the same hairline weight as the rest of the compose row.
    """
    dpr = 2
    pm  = QPixmap(size * dpr, size * dpr)
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)

    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(QColor(colour))
    pen.setWidthF(size / 14.0)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)

    u = size / 24.0                                   # work on a 24pt grid
    p.drawRoundedRect(QRectF(9 * u, 3 * u, 6 * u, 11 * u), 3 * u, 3 * u)
    p.drawArc(QRectF(6 * u, 9 * u, 12 * u, 10 * u), 180 * 16, 180 * 16)
    p.drawLine(QPointF(12 * u, 19 * u), QPointF(12 * u, 21 * u))
    p.end()
    return QIcon(pm)


class WaveMeter(QWidget):
    """Voice-note waveform: bars scroll in from the right as you speak.

    The bars are driven by a timer rather than by the audio callbacks, so the
    waveform crawls at one steady speed no matter how the device chunks its
    buffers; each frame draws the loudest level heard since the last one.
    """

    BAR, GAP, FPS = 3.0, 3.0, 24
    BAR_COLOUR    = "#8e97a8"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._levels  = []
        self._pending = 0.0
        self._hint    = ""
        self._timer   = QTimer(self)
        self._timer.setInterval(int(1000 / self.FPS))
        self._timer.timeout.connect(self._tick)

    def start(self, hint: str = ""):
        self._hint = hint
        self._levels.clear()
        self._pending = 0.0
        self._timer.start()
        self.update()

    def stop(self):
        self._timer.stop()

    def push(self, level: float):
        self._pending = max(self._pending, float(level))

    def _tick(self):
        self._levels.append(self._pending)
        # Decay rather than reset: a pause tapers the trace down to dots
        # instead of dropping it to a flat line between syllables.
        self._pending *= 0.4
        cap = max(8, int(self.width() / (self.BAR + self.GAP)) + 2)
        if len(self._levels) > cap:
            del self._levels[:-cap]
        self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        left = 4.0
        if self._hint:
            f = QFont(UI_FONT, 9)
            p.setFont(f)
            p.setPen(QColor(C_TEXT_DIM))
            p.drawText(QRectF(4, 0, self.width(), self.height()),
                       Qt.AlignVCenter | Qt.AlignLeft, self._hint)
            left = 4 + QFontMetrics(f).horizontalAdvance(self._hint) + 12

        p.setPen(Qt.NoPen)
        p.setBrush(QColor(self.BAR_COLOUR))
        mid  = self.height() / 2.0
        span = self.height() * 0.72
        x    = self.width() - self.BAR - 2
        for level in reversed(self._levels):
            if x < left:
                break
            # A gentle curve: quiet speech still shows, loud stays on-scale.
            amp = max(2.5, min(1.0, level) ** 0.6 * span)
            p.drawRoundedRect(QRectF(x, mid - amp / 2, self.BAR, amp),
                              self.BAR / 2, self.BAR / 2)
            x -= (self.BAR + self.GAP)


# Steers the recogniser towards this app's vocabulary. Without it, "stack the
# blue cube" comes back as "start the Bluetooth" — the words are only
# ambiguous in the absence of context.
SPEECH_PROMPT = (
    "Spoken commands for a robot arm working on a table. Vocabulary: pick up, "
    "put down, place, stack, move, rotate, push, slide, drop, grab, left, "
    "right, forward, back, up, down, centimetres, degrees, block, cube, "
    "brick, mug, cup, bottle, tray, bowl, plate, marker, plant, shelf, "
    "gripper, red, orange, yellow, green, blue, purple, pink, black, white."
)


def pcm_to_wav(pcm: bytes, rate: int, width: int) -> io.BytesIO:
    """Wrap raw PCM in a WAV container the transcription API will accept."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(pcm)
    buf.seek(0)
    buf.name = "speech.wav"          # the API picks the format from the name
    return buf


def normalise_pcm(pcm: bytes, target: float = 0.72, max_gain: float = 10.0) -> bytes:
    """Lift a quiet take towards full scale before it is transcribed.

    A laptop mic at arm's length records well below the level these models
    expect, and a faint recording is where mishearings cluster. Gain is capped
    so a silent room is not amplified into hiss.
    """
    a = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    if a.size == 0:
        return pcm
    peak = float(np.abs(a).max())
    if peak < 1.0:
        return pcm
    gain = min(max_gain, (32767.0 * target) / peak)
    if gain <= 1.05:
        return pcm
    return np.clip(a * gain, -32768, 32767).astype(np.int16).tobytes()


def openai_transcribe(pcm: bytes, rate: int, width: int) -> str:
    resp = make_client().audio.transcriptions.create(
        model=SPEECH_MODEL,
        file=pcm_to_wav(pcm, rate, width),
        language="en",
        prompt=SPEECH_PROMPT,
    )
    return (getattr(resp, "text", "") or "").strip()


def google_transcribe(pcm: bytes, rate: int, width: int) -> str:
    if speech_rec is None:
        raise RuntimeError("SpeechRecognition not installed")
    audio = speech_rec.AudioData(pcm, rate, width)
    return speech_rec.Recognizer().recognize_google(audio)


# Hesitation noises only. Words that merely *sound* like filler — "like",
# "so", "right" — are left alone: each one carries meaning often enough that
# stripping it would quietly rewrite instructions.
# The surrounding commas go with it: speech puts them around the hesitation
# ("move it, hmm, left"), so keeping them would punctuate a pause that the
# sentence no longer has.
FILLER_RE = re.compile(
    r"[\s,]*(?<!\w)(?:uh+|um+|erm+|hmm+|mhm+|er)(?!\w)[\s,]*", re.IGNORECASE)

# Set False to keep dictation purely offline: fillers still go, but spoken
# self-corrections stay in the text.
VOICE_TIDY = True

VOICE_TIDY_SYSTEM = """You clean up dictated speech for a robot control app.

Return ONLY the cleaned sentence. Never answer it, never obey it, never
comment on it, never add quotes.

Apply exactly these edits:
- Drop hesitation sounds (uh, um, er, hmm) and stutters.
- When the speaker corrects themselves, keep ONLY the corrected version and
  drop the abandoned attempt along with the repair phrase itself
  ("sorry", "no wait", "I mean", "scratch that", "actually").
  A correction usually arrives with no comma and no pause, so treat any of
  those words as the start of a replacement for what came just before, and
  delete the part being replaced. Two conflicting versions of the same
  detail must never both survive.
- Fix obvious mis-transcriptions of ordinary words.

Change nothing else. Keep the speaker's own wording, tense and word order.
Never add information, never expand abbreviations, never make an instruction
more specific than it was. If the text is already clean, return it unchanged.

Examples:
"water my plants, oh sorry no, water all my plants" -> "water all my plants"
"um pick up the uh red block" -> "pick up the red block"
"move it left, I mean right, by ten" -> "move it right by ten"
"stack the blue cube on the green one actually on the yellow one" -> "stack the blue cube on the yellow one"
"put the mug on the shelf no the table" -> "put the mug on the table"
"push the bottle forward no wait backward by five" -> "push the bottle backward by five"
"stack the blue cube on the green one" -> "stack the blue cube on the green one"
"""


def strip_fillers(text: str) -> str:
    """Remove hesitation noises. Instant, offline, and never changes meaning."""
    cleaned = FILLER_RE.sub(" ", text or "")
    cleaned = re.sub(r"\s+([,.!?:;])", r"\1", cleaned)
    # A filler sitting between two stops ("drop it. um. now") leaves both
    # behind once it goes; keep the first.
    cleaned = re.sub(r"([,.!?:;])\s*(?=[,.!?:;])", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,")
    return cleaned


def tidy_dictation(text: str) -> str:
    """Resolve spoken self-corrections with a small model.

    Regexes cannot do this part: "water my plants, oh sorry no, water all my
    plants" needs to know which half the speaker meant to keep. Any failure —
    offline, slow, or a suspiciously long answer — falls back to the input,
    so dictation never breaks just because the tidy step was unavailable.
    """
    words = text.split()
    if len(words) < 4:
        return text                       # nothing to repair in "stop" or "go"
    try:
        cleaned = call_model(
            make_client(),
            model=VOICE_TIDY_MODEL,
            messages=[{"role": "system", "content": VOICE_TIDY_SYSTEM},
                      {"role": "user",   "content": text}],
            max_tokens=400,
            stage="Dictation tidy",
        ).strip().strip('"')
    except Exception:
        return text
    # A tidy pass only ever shortens. Anything longer means the model answered
    # the instruction instead of cleaning it, so the original is safer.
    if not cleaned or len(cleaned.split()) > len(words) + 1:
        return text
    return cleaned


def speech_to_sentence(text: str) -> str:
    """Spoken punctuation words → real marks, plus a capitalised first letter."""
    text = (text or "").strip()
    if not text:
        return ""
    for word, symbol in SPOKEN_PUNCTUATION:
        text = re.sub(r"\b" + re.escape(word) + r"\b", symbol, text,
                      flags=re.IGNORECASE)
    text = re.sub(r"\s+([,.!?:;])", r"\1", text)      # "hello ," → "hello,"
    text = re.sub(r" {2,}", " ", text).strip()
    return (text[0].upper() + text[1:]) if text else ""


class VoiceRecorder(QObject):
    """Captures the default microphone until the speaker stops talking.

    PyAudio is deliberately not used — it needs PortAudio headers to compile,
    whereas QtMultimedia ships with the same PySide6 the rest of the UI runs
    on. SpeechRecognition only ever wanted raw PCM bytes, so the Qt capture is
    handed straight to it.
    """

    finished = Signal(bytes, bool)    # PCM, and whether the speaker ended it
    failed   = Signal(str)
    level    = Signal(float)          # 0..1, for the live meter

    RATE         = 16000
    SAMPLE_WIDTH = 2                  # Int16
    # Set just above the ambient floor measured on a laptop mic (~130 RMS),
    # not at conversational level: this only decides whether *anything* was
    # said, and the recogniser handles quiet speech far better than a gate
    # that throws the take away for being soft.
    SILENCE_RMS  = 190.0
    MAX_SECONDS  = 180.0              # runaway guard only — never sends
    DEAD_AIR     = 2.0                # no bytes at all by now = mic is blocked

    def __init__(self, parent=None):
        super().__init__(parent)
        self._quiet = 0.0
        self._src   = None
        self._io    = None
        self._buf   = bytearray()
        self._heard = False
        self._done  = False
        self._peak  = 0
        # macOS hands out an audio stream that simply never delivers a byte
        # when microphone access is refused — no error, no callback. Without a
        # timer of its own the recorder would sit there listening to nothing
        # forever, which is indistinguishable from a broken button.
        self._watchdog = QTimer(self)
        self._watchdog.setInterval(250)
        self._watchdog.timeout.connect(self._on_tick)
        self._elapsed = 0.0

    def is_active(self) -> bool:
        return self._src is not None

    def start(self) -> bool:
        device = QMediaDevices.defaultAudioInput()
        if device is None or device.isNull():
            self.failed.emit("No microphone found.")
            return False

        fmt = QAudioFormat()
        fmt.setSampleRate(self.RATE)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.Int16)

        self._buf = bytearray()
        self._heard, self._done = False, False
        self._peak, self._elapsed, self._quiet = 0, 0.0, 0.0
        self._src = QAudioSource(device, fmt, self)
        self._io  = self._src.start()
        if self._io is None:
            self._src = None
            self.failed.emit("Microphone could not be opened.")
            return False
        self._io.readyRead.connect(self._on_audio)
        self._watchdog.start()
        return True

    def _on_tick(self):
        """Wall-clock supervision, independent of whether audio is arriving."""
        self._elapsed += self._watchdog.interval() / 1000.0
        if not self._buf and self._elapsed >= self.DEAD_AIR:
            self.abort(
                "The microphone opened but delivered nothing. PySide6 "
                f"{PySide6.__version__} on {sys.executable} — 6.10.x captures "
                "no audio on macOS; upgrade with 'pip install -U PySide6'. "
                "Otherwise check Microphone access in System Settings.")
        elif self._elapsed >= self.MAX_SECONDS:
            self.stop(by_user=False)          # safety net, so it never sends

    def _on_audio(self):
        if self._src is None:
            return
        chunk = bytes(self._io.readAll())
        if not chunk:
            return
        self._buf += chunk

        samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
        rms     = float(np.sqrt(np.mean(samples ** 2))) if samples.size else 0.0
        if samples.size:
            self._peak = max(self._peak, int(np.abs(samples).max()))
        # Normalised against ordinary speaking volume, not the clipping point:
        # a loud passage pins the meter, which reads better than a trace that
        # never leaves the bottom third.
        self.level.emit(min(1.0, rms / 1400.0))

        # A pause never ends the take. Recording runs until the speaker says
        # it is over, so thinking mid-sentence cannot cut them off — and,
        # on the send-when-done path, cannot send half a thought.
        if rms >= self.SILENCE_RMS:
            self._heard = True
            self._quiet = 0.0

    def stop(self, by_user: bool = True):
        if self._done:
            return
        self._teardown()
        # A stream of pure digital zeros is what a muted or blocked input
        # sounds like; sending that to a recogniser only yields a confusing
        # "didn't catch that" for what is really a permissions problem.
        if self._peak < 8:
            self.failed.emit(
                "Only silence reached the microphone. Check it isn't muted, "
                "and that Microphone access is granted to "
                f"{sys.executable} in System Settings › Privacy & Security.")
            return
        if not self._heard:
            self.failed.emit("That was too quiet to make out — speak a little "
                             "louder or closer to the microphone.")
            return
        self.finished.emit(bytes(self._buf), by_user)

    def abort(self, message: str):
        if self._done:
            return
        self._teardown()
        self.failed.emit(message)

    def _teardown(self):
        self._done = True
        self._watchdog.stop()
        src, self._src, self._io = self._src, None, None
        if src is not None:
            try:
                src.stop()
            except Exception:
                pass
            src.deleteLater()


class TranscribeWorker(QThread):
    """PCM → text off the UI thread, then a disfluency clean-up pass.

    Both stages run here so the sidebar sees one finished sentence rather than
    text that visibly rewrites itself a second after it lands.
    """

    done   = Signal(str)
    failed = Signal(str)
    stage  = Signal(str)

    def __init__(self, pcm: bytes, rate: int, width: int, parent=None):
        super().__init__(parent)
        self._pcm, self._rate, self._width = pcm, rate, width

    def run(self):
        pcm = normalise_pcm(self._pcm)
        try:
            heard = openai_transcribe(pcm, self._rate, self._width)
        except Exception as first:
            # Google is a distant second — on this app's vocabulary it hears
            # "start the Bluetooth" for "stack the blue cube" — so it is a
            # fallback for an outage, not an equal alternative.
            try:
                heard = google_transcribe(pcm, self._rate, self._width)
            except Exception:
                self.failed.emit(f"Could not transcribe: {str(first)[:120]}")
                return
        if not heard.strip():
            self.failed.emit("Didn't catch that — try again.")
            return
        text = strip_fillers(heard)
        if VOICE_TIDY:
            self.stage.emit("Tidying…")
            text = tidy_dictation(text)
        self.done.emit(text)


try:
    import serial as pyserial
    from serial.tools import list_ports as serial_ports
    SERIAL_IMPORT_ERROR = ""
except Exception as _serial_err:          # pyserial is optional at import time
    pyserial, serial_ports = None, None
    SERIAL_IMPORT_ERROR = str(_serial_err)


def list_serial_devices():
    """(device, description) for every serial port the OS can see."""
    if serial_ports is None:
        return []
    out = []
    for p in serial_ports.comports():
        desc = (p.description or "").strip()
        out.append((p.device, desc if desc and desc != "n/a" else p.device))
    return out


class SerialLink(QObject):
    """The USB serial connection the planner's commands are written to.

    Two switches guard it, and both must be on before a byte leaves the app:
    the port has to be open, and Hardware Connect has to be enabled. That
    separation is deliberate — you can stay wired to the board while running
    simulation-only, and flip execution on without hunting for the port again.
    """

    status = Signal(str)              # human-readable state, for the dialog
    sent   = Signal(int, str)         # line count, port
    failed = Signal(str)

    BAUDS   = [9600, 19200, 38400, 57600, 115200, 250000]
    DEFAULT_BAUD = 115200

    def __init__(self, parent=None):
        super().__init__(parent)
        self._port = None
        self._name = ""
        self._baud = self.DEFAULT_BAUD
        self.enabled = False          # the Hardware Connect toggle

    # ── connection ────────────────────────────────────────────────────────────
    def is_open(self) -> bool:
        return self._port is not None and self._port.is_open

    def port_name(self) -> str:
        return self._name

    def baud(self) -> int:
        return self._baud

    def open(self, device: str, baud: int = None) -> bool:
        if pyserial is None:
            self.failed.emit(f"pyserial not installed: {SERIAL_IMPORT_ERROR}")
            return False
        self.close()
        baud = int(baud or self._baud)
        try:
            self._port = pyserial.Serial(device, baud, timeout=1, write_timeout=5)
        except Exception as err:
            self._port = None
            self.failed.emit(f"Could not open {device}: {err}")
            return False
        self._name, self._baud = device, baud
        self.status.emit(f"Connected to {device} @ {baud}")
        return True

    def close(self):
        if self._port is not None:
            try:
                self._port.close()
            except Exception:
                pass
        self._port = None
        self.status.emit("Not connected")

    # ── sending ───────────────────────────────────────────────────────────────
    @staticmethod
    def plan_lines(plan: str) -> list:
        """The commands to write out, taken straight from the runner's parser.

        Deliberately the same call the simulator makes, so the board receives
        byte-for-byte the commands the canvas is executing — step numbering,
        operator comments and MISSING notices are presentation, and only the
        bare command belongs on the wire.
        """
        return CommandRunner._parse(plan)

    def send_plan(self, plan: str) -> bool:
        """Write the generated sequence out. Called once, at generation time."""
        if not self.enabled:
            return False
        if not self.is_open():
            self.failed.emit("Hardware Connect is on but no USB device is connected.")
            return False
        lines = self.plan_lines(plan)
        if not lines:
            return False
        try:
            for line in lines:
                self._port.write((line + "\n").encode("utf-8"))
            self._port.flush()
        except Exception as err:
            self.failed.emit(f"Send failed on {self._name}: {err}")
            self.close()
            return False
        self.sent.emit(len(lines), self._name)
        return True


class ChatBubble(QFrame):
    """A frosted message panel, curved away from the side it is anchored to."""

    R_BIG, R_TAIL = 17, 6
    # Room inside the widget for the hand-painted shadow. A QGraphicsEffect
    # cannot be used here: ChatView fades each row in with an opacity effect,
    # and Qt refuses to render one effect inside another — the bubble simply
    # stops being painted, which read as messages vanishing on any relayout.
    SH_PAD, SH_DROP = 6, 3
    detail_toggled = Signal()

    def __init__(self, text="", user=False, kind="normal", parent=None):
        super().__init__(parent)
        self._user   = user
        self._kind   = kind          # normal | thinking | alert
        self._accent = None
        self._detail = None
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)

        self._lay = QVBoxLayout(self)
        p = self.SH_PAD
        self._lay.setContentsMargins(15 + p, 10 + p, 15 + p, 11 + p)
        self._lay.setSpacing(7)

        if kind == "thinking":
            self._content = ShimmerLabel(text)
        else:
            self._content = QLabel(text)
            self._content.setWordWrap(True)
            self._content.setFont(QFont(UI_FONT, 10))
            self._content.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self._content.setStyleSheet(
                f"color:{'#ffffff' if user else C_TEXT};background:transparent;"
                f"border:none;line-height:140%;")
        self._lay.addWidget(self._content)

    def sizeHint(self):
        # A word-wrapping QLabel asks for a narrow column, which would leave
        # every message wrapped to a third of the panel. Ask for the width the
        # text would take unwrapped instead, and let maximumWidth cap it.
        hint = super().sizeHint()
        m = self._lay.contentsMargins()
        want = 0
        if isinstance(self._content, QLabel):
            fm = QFontMetrics(self._content.font())
            want = max((fm.horizontalAdvance(line)
                        for line in self._content.text().splitlines()), default=0)
        if self._detail is not None and self._detail.is_open():
            want = max(want, self._detail.natural_width())
        if want:
            want += m.left() + m.right() + 2
            hint.setWidth(min(max(hint.width(), want), self.maximumWidth()))
        return hint

    # ── content ──────────────────────────────────────────────────────────────
    def set_text(self, text):
        if isinstance(self._content, ShimmerLabel):
            self._content.set_text(text)
        else:
            self._content.setText(text)
        self.updateGeometry()

    def set_accent(self, colour):
        self._accent = QColor(colour) if colour else None
        self.update()

    def add_detail(self, text: str):
        if self._detail is None:
            self._detail = DetailPane(on_dark=self._user)
            self._detail.toggled.connect(self.detail_toggled)
            self._detail.toggled.connect(self.updateGeometry)
            self._lay.addWidget(self._detail)
        self._detail.add_line(text)

    def enable_copy(self):
        if self._detail is not None:
            self._detail.enable_copy()

    def freeze(self, text=None):
        """Stop the shimmer — the stage this bubble narrates has resolved."""
        if isinstance(self._content, ShimmerLabel):
            self._content.set_active(False)
            if text:
                self._content.set_text(text)

    # ── painting ─────────────────────────────────────────────────────────────
    def _path(self, dx=0.0, dy=0.0) -> QPainterPath:
        p = self.SH_PAD
        r = QRectF(self.rect()).adjusted(p + 0.5, p + 0.5, -p - 0.5, -p - 0.5)
        r.translate(dx, dy)
        big, tail = self.R_BIG, self.R_TAIL
        tl, tr = big, big
        br, bl = (tail, big) if self._user else (big, tail)
        p = QPainterPath()
        p.moveTo(r.left() + tl, r.top())
        p.lineTo(r.right() - tr, r.top())
        p.quadTo(r.right(), r.top(), r.right(), r.top() + tr)
        p.lineTo(r.right(), r.bottom() - br)
        p.quadTo(r.right(), r.bottom(), r.right() - br, r.bottom())
        p.lineTo(r.left() + bl, r.bottom())
        p.quadTo(r.left(), r.bottom(), r.left(), r.bottom() - bl)
        p.lineTo(r.left(), r.top() + tl)
        p.quadTo(r.left(), r.top(), r.left() + tl, r.top())
        p.closeSubpath()
        return p

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # Soft drop shadow, approximated by widening strokes of falling alpha.
        shadow = self._path(0, self.SH_DROP)
        strength = 26 if self._kind != "thinking" else 12
        p.setBrush(Qt.NoBrush)
        for i in range(self.SH_PAD, 0, -1):
            alpha = int(strength * (1.0 - (i - 1) / float(self.SH_PAD)) ** 1.6)
            if alpha <= 0:
                continue
            p.setPen(QPen(QColor(23, 32, 51, alpha), i * 2))
            p.drawPath(shadow)

        path = self._path()
        if self._user:
            grad = QLinearGradient(0, 0, 0, self.height())
            grad.setColorAt(0.0, QColor(31, 41, 58, 250))
            grad.setColorAt(1.0, QColor(15, 22, 38, 250))
            p.fillPath(path, QBrush(grad))
            p.setPen(QPen(QColor(255, 255, 255, 46), 1))
        elif self._kind == "thinking":
            grad = QLinearGradient(0, 0, 0, self.height())
            grad.setColorAt(0.0, QColor(255, 255, 255, 140))
            grad.setColorAt(1.0, QColor(255, 255, 255, 96))
            p.fillPath(path, QBrush(grad))
            p.setPen(QPen(QColor(255, 255, 255, 190), 1))
        else:
            grad = QLinearGradient(0, 0, 0, self.height())
            grad.setColorAt(0.0, QColor(255, 255, 255, 226))
            grad.setColorAt(1.0, QColor(255, 255, 255, 178))
            p.fillPath(path, QBrush(grad))
            p.setPen(QPen(QColor(216, 227, 242, 235), 1))
        p.drawPath(path)

        # A hairline down the anchored edge tints the panel by outcome without
        # colouring the text itself.
        if self._accent is not None:
            p.save()
            p.setClipPath(path)
            box = path.boundingRect()
            bar = QRectF(box.left(), box.top(), 3.0, box.height())
            if self._user:
                bar.moveLeft(box.right() - 3.0)
            p.fillRect(bar, self._accent)
            p.restore()


class ChatView(QScrollArea):
    """Vertical transcript of bubbles, anchored to whichever side sent them."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet("""
            QScrollArea{background:transparent;border:none;}
            QScrollBar:vertical{width:7px;background:transparent;margin:6px 2px;}
            QScrollBar::handle:vertical{background:rgba(150,170,200,0.55);
                border-radius:3px;min-height:30px;}
            QScrollBar::handle:vertical:hover{background:rgba(120,145,185,0.8);}
            QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}
        """)
        self._body = QWidget()
        self._body.setStyleSheet("background:transparent;")
        self._lay = QVBoxLayout(self._body)
        self._lay.setContentsMargins(6, 8, 8, 10)
        self._lay.setSpacing(11)
        self._lay.addStretch(1)
        self.setWidget(self._body)
        self._bubbles = []
        self._anims   = []

    def _max_bubble_width(self) -> int:
        return max(int(self.viewport().width() * 0.82), 140)

    def add_bubble(self, bubble: ChatBubble, user=False) -> ChatBubble:
        row = QWidget()
        row.setStyleSheet("background:transparent;")
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        bubble.setMaximumWidth(self._max_bubble_width())
        bubble.detail_toggled.connect(self.scroll_to_end)
        if user:
            h.addStretch(1); h.addWidget(bubble, 0)
        else:
            h.addWidget(bubble, 0); h.addStretch(1)

        self._lay.insertWidget(self._lay.count() - 1, row)
        self._bubbles.append(bubble)

        # Fade the row in, then drop the effect again: an opacity effect left
        # in place would suppress any effect a child later acquires.
        fade = QGraphicsOpacityEffect(row)
        fade.setOpacity(0.0)
        row.setGraphicsEffect(fade)
        anim = QPropertyAnimation(fade, b"opacity", row)
        anim.setDuration(240)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.setStartValue(0.0); anim.setEndValue(1.0)
        anim.finished.connect(lambda r=row: r.setGraphicsEffect(None))
        anim.start()
        self._anims = [a for a in self._anims if a.state() == QPropertyAnimation.Running]
        self._anims.append(anim)

        self.scroll_to_end()
        return bubble

    def message(self, text, user=False, kind="normal", accent=None) -> ChatBubble:
        b = ChatBubble(text, user=user, kind=kind)
        if accent:
            b.set_accent(accent)
        return self.add_bubble(b, user=user)

    def scroll_to_end(self):
        QTimer.singleShot(0, self._to_end)
        QTimer.singleShot(60, self._to_end)

    def _to_end(self):
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        width = self._max_bubble_width()
        for b in self._bubbles:
            b.setMaximumWidth(width)
            b.updateGeometry()


class InstructionRow(QFrame):
    """One saved instruction: read-only until its pencil is clicked."""

    edited  = Signal(str)
    removed = Signal()

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"InstructionRow{{background:rgba(255,255,255,0.72);"
            f"border:1px solid {C_BORDER};border-radius:13px;}}")
        h = QHBoxLayout(self)
        h.setContentsMargins(12, 7, 8, 7)
        h.setSpacing(8)

        self._num = QLabel("1")
        self._num.setFixedWidth(14)
        self._num.setFont(QFont(MONO_FONT, 8))
        self._num.setStyleSheet(f"color:{C_TEXT_DIM};background:transparent;border:none;")

        self._edit = QLineEdit(text)
        self._edit.setReadOnly(True)
        self._edit.setFrame(False)
        self._edit.setFont(QFont(UI_FONT, 10))
        self._edit.setCursorPosition(0)
        self._edit.setStyleSheet(
            f"QLineEdit{{background:transparent;color:{C_TEXT};border:none;padding:0;"
            f"selection-background-color:#c7d2fe;}}"
            f"QLineEdit:!read-only{{background:rgba(255,255,255,0.9);"
            f"border:1px solid #c7d2fe;border-radius:8px;padding:2px 6px;}}")
        self._edit.returnPressed.connect(self._commit)
        self._edit.editingFinished.connect(self._commit)

        self._pencil = self._chip("✎", C_BLUE, "#e8f0ff")
        self._pencil.clicked.connect(self._begin_edit)
        trash = self._chip("✕", C_RED, "#fff1f2")
        trash.clicked.connect(self.removed)

        h.addWidget(self._num); h.addWidget(self._edit, 1)
        h.addWidget(self._pencil); h.addWidget(trash)

    @staticmethod
    def _chip(glyph, hover_fg, hover_bg):
        b = QPushButton(glyph)
        b.setCursor(Qt.PointingHandCursor)
        b.setFixedSize(22, 22)
        b.setStyleSheet(
            f"QPushButton{{background:transparent;color:{C_TEXT_DIM};border:none;"
            f"border-radius:11px;font-size:11px;}}"
            f"QPushButton:hover{{background:{hover_bg};color:{hover_fg};}}")
        return b

    def set_index(self, i: int):
        self._num.setText(str(i))

    def text(self) -> str:
        return self._edit.text().strip()

    def _begin_edit(self):
        self._edit.setReadOnly(False)
        self._edit.setFocus()
        self._edit.selectAll()

    def _commit(self):
        if self._edit.isReadOnly():
            return
        self._edit.setReadOnly(True)
        self._edit.setCursorPosition(0)
        self.edited.emit(self.text())


class InstructionsDialog(QDialog):
    """Frameless glass sheet for the planner's standing instructions.

    Instructions are kept as individual entries, added and saved one at a time
    rather than typed into a single blob — a wrapped line in a text box gave no
    way to tell where one instruction ended and the next began. Every add,
    edit and delete writes straight through to disk.
    """

    PAD, RADIUS = 20, 24
    changed = Signal(list)

    def __init__(self, items=None, parent=None):
        super().__init__(parent)
        self._items = list(items or [])
        self._rows  = []
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setModal(True)
        self.resize(520, 420)
        self._drag = None

        p = self.PAD
        root = QVBoxLayout(self)
        root.setContentsMargins(p + 24, p + 20, p + 24, p + 20)
        root.setSpacing(0)

        head = QHBoxLayout(); head.setSpacing(8)
        title = QLabel("Custom instructions")
        title.setFont(QFont(UI_FONT_B, 15))
        title.setStyleSheet(f"color:{C_TEXT};background:transparent;")
        close = QPushButton("✕")
        close.setCursor(Qt.PointingHandCursor)
        close.setFixedSize(26, 26)
        close.setStyleSheet(
            f"QPushButton{{background:rgba(255,255,255,0.6);color:{C_TEXT_DIM};"
            f"border:1px solid {C_BORDER};border-radius:13px;font-size:11px;}}"
            f"QPushButton:hover{{background:#fff1f2;color:{C_RED};border-color:#fecaca;}}")
        close.clicked.connect(self.reject)
        head.addWidget(title); head.addStretch(1); head.addWidget(close)
        root.addLayout(head)

        sub = QLabel("Added one at a time. A2 applies every one to each task you send.")
        sub.setFont(QFont(UI_FONT, 9))
        sub.setStyleSheet(f"color:{C_TEXT_DIM};background:transparent;")
        root.addWidget(sub)
        root.addSpacing(14)

        # ── add one ───────────────────────────────────────────────────────────
        entry = QFrame()
        entry.setStyleSheet(f"QFrame{{background:rgba(255,255,255,0.72);"
                            f"border:1px solid {C_BORDER};border-radius:17px;}}")
        el = QHBoxLayout(entry); el.setContentsMargins(14, 6, 6, 6); el.setSpacing(8)
        self._input = QLineEdit()
        self._input.setFrame(False)
        self._input.setFont(QFont(UI_FONT, 10))
        self._input.setPlaceholderText("Add an instruction…   e.g. Stack plates at T11 when done")
        self._input.setStyleSheet(
            f"QLineEdit{{background:transparent;color:{C_TEXT};border:none;padding:0;"
            f"selection-background-color:#c7d2fe;}}")
        self._input.returnPressed.connect(self._add)
        add = QPushButton("Add")
        add.setCursor(Qt.PointingHandCursor); add.setFixedHeight(30)
        add.setFont(QFont(UI_FONT, 10, QFont.Bold))
        add.setStyleSheet(
            "QPushButton{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #1f293a, stop:1 #0f1626);color:#ffffff;border:none;"
            "border-radius:15px;padding:0 18px;}"
            "QPushButton:hover{background:#172033;}")
        add.clicked.connect(self._add)
        el.addWidget(self._input, 1); el.addWidget(add)
        root.addWidget(entry)
        root.addSpacing(12)

        # ── saved list ────────────────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea{background:transparent;border:none;}
            QScrollBar:vertical{width:7px;background:transparent;margin:2px;}
            QScrollBar::handle:vertical{background:rgba(150,170,200,0.55);
                border-radius:3px;min-height:28px;}
            QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}
        """)
        holder = QWidget(); holder.setStyleSheet("background:transparent;")
        self._list = QVBoxLayout(holder)
        self._list.setContentsMargins(0, 0, 6, 0)
        self._list.setSpacing(7)
        self._empty = QLabel("No instructions yet — add your first above.")
        self._empty.setFont(QFont(UI_FONT, 9))
        self._empty.setStyleSheet(f"color:{C_TEXT_DIM};background:transparent;padding:14px 2px;")
        self._list.addWidget(self._empty)
        self._list.addStretch(1)
        scroll.setWidget(holder)
        root.addWidget(scroll, 1)
        root.addSpacing(12)

        foot = QHBoxLayout(); foot.setSpacing(9)
        self._hint = QLabel("")
        self._hint.setFont(QFont(UI_FONT, 8))
        self._hint.setStyleSheet(f"color:{C_TEXT_DIM};background:transparent;")
        done = QPushButton("Done")
        done.setCursor(Qt.PointingHandCursor); done.setFixedHeight(34)
        done.setFont(QFont(UI_FONT, 10, QFont.Bold))
        done.setStyleSheet(
            f"QPushButton{{background:rgba(255,255,255,0.8);color:{C_TEXT};"
            f"border:1px solid {C_BORDER};border-radius:17px;padding:0 24px;}}"
            f"QPushButton:hover{{background:#ffffff;border-color:#c7d2fe;}}")
        done.clicked.connect(self.accept)
        foot.addWidget(self._hint); foot.addStretch(1); foot.addWidget(done)
        root.addLayout(foot)

        self._rebuild()
        self._input.setFocus()

    # ── list management ──────────────────────────────────────────────────────
    def items(self) -> list:
        return list(self._items)

    def _add(self):
        text = self._input.text().strip()
        if not text:
            return
        self._items.append(text)
        self._input.clear()
        self._rebuild()
        self._commit()

    def _row_index(self, row) -> int:
        # A row can emit editingFinished while it is being torn down, so the
        # lookup has to tolerate a row that has already left the list.
        try:
            return self._rows.index(row)
        except ValueError:
            return -1

    def _remove(self, idx: int):
        if 0 <= idx < len(self._items):
            del self._items[idx]
            self._rebuild()
            self._commit()

    def _replace(self, idx: int, text: str):
        text = text.strip()
        if not (0 <= idx < len(self._items)) or text == self._items[idx]:
            return
        if not text:                       # emptied out — treat as a delete
            self._remove(idx)
            return
        self._items[idx] = text
        self._commit()

    def _commit(self):
        """Persist after every single change, not on the way out."""
        self.changed.emit(self.items())
        self._hint.setText("Saved")
        QTimer.singleShot(1600, self._reset_hint)

    def _reset_hint(self):
        self._hint.setText("⏎ to add · esc to close")

    def _rebuild(self):
        for row in self._rows:
            self._list.removeWidget(row)
            row.deleteLater()
        self._rows = []
        self._empty.setVisible(not self._items)
        for i, text in enumerate(self._items):
            row = InstructionRow(text)
            row.set_index(i + 1)
            row.removed.connect(lambda r=row: self._remove(self._row_index(r)))
            row.edited.connect(lambda t, r=row: self._replace(self._row_index(r), t))
            self._list.insertWidget(self._list.count() - 1, row)
            self._rows.append(row)

    # ── frameless window needs its own drag handling ─────────────────────────
    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._drag = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
            ev.accept()

    def mouseMoveEvent(self, ev):
        if self._drag is not None and ev.buttons() & Qt.LeftButton:
            self.move(ev.globalPosition().toPoint() - self._drag)
            ev.accept()

    def mouseReleaseEvent(self, _ev):
        self._drag = None

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pad = self.PAD
        panel = QRectF(self.rect()).adjusted(pad + 0.5, pad + 0.5, -pad - 0.5, -pad - 0.5)

        # Hand-painted rather than a QGraphicsEffect, so nothing here can
        # collide with an effect on a child widget. One hairline ring per step,
        # each stepped outwards: overlapping wide strokes stack their alpha and
        # turn the whole halo into a grey slab.
        p.setBrush(Qt.NoBrush)
        for i in range(1, pad):
            alpha = int(14 * (1.0 - i / float(pad)) ** 2.4)
            if alpha <= 0:
                continue
            p.setPen(QPen(QColor(23, 32, 51, alpha), 1))
            p.drawRoundedRect(panel.adjusted(-i, -i + 3, i, i + 3),
                              self.RADIUS + i, self.RADIUS + i)

        path = QPainterPath()
        path.addRoundedRect(panel, self.RADIUS, self.RADIUS)
        glass = QLinearGradient(panel.topLeft(), panel.bottomLeft())
        glass.setColorAt(0.0, QColor(255, 255, 255, 250))
        glass.setColorAt(1.0, QColor(236, 243, 255, 238))
        p.fillPath(path, QBrush(glass))

        # A brighter top edge sells the pane as glass catching the light.
        p.setPen(QPen(QColor(255, 255, 255, 235), 1))
        p.drawPath(path)
        p.setPen(QPen(QColor(216, 227, 242, 220), 1))
        p.drawRoundedRect(panel.adjusted(0.5, 0.5, -0.5, -0.5),
                          self.RADIUS - 1, self.RADIUS - 1)


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
        self._vision_worker    = None
        self._command_worker   = None
        self._dexterity_worker = None
        # Reassigning self._vision_worker used to drop the last reference to a
        # still-running QThread, so Qt destroyed it underneath itself and the
        # import silently never finished. Workers now live here until their
        # own finished signal fires.
        self._live_workers     = []
        self._last_frame       = None
        self._pending_task     = None
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
        # The old control-dense inspector remains below as reference code for
        # maintenance, but it is deliberately not built.  Operators interact
        # with A2 through one focused, ChatGPT-like conversation instead.
        self._build_chat_ui()
        return

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

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
        sub = QLabel("Measured Vision  +  Dexterity Gate")
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

        # ── STEP 1 · Task ─────────────────────────────────────────────────────
        c_task = SectionCard("STEP 1 · DESCRIBE YOUR TASK", C_GREEN)
        vnote = QLabel("Vision runs automatically when you import an image.")
        vnote.setWordWrap(True)
        vnote.setFont(QFont(UI_FONT, 8))
        vnote.setStyleSheet(f"color:{C_TEXT_DIM};background:transparent;border:none;")
        c_task.add(vnote)

        self._verify_chk = QCheckBox("Second-pass outline verification")
        self._verify_chk.setChecked(True)
        self._verify_chk.setCursor(Qt.PointingHandCursor)
        self._verify_chk.setFont(QFont(UI_FONT, 9))
        self._verify_chk.setStyleSheet(f"""
            QCheckBox {{ color:{C_TEXT}; background:transparent; border:none; spacing:7px; }}
            QCheckBox::indicator {{
                width:14px; height:14px; border-radius:4px;
                border:1px solid {C_BORDER}; background:{C_PANEL_2};
            }}
            QCheckBox::indicator:checked {{ background:{C_GREEN}; border:1px solid {C_GREEN}; }}
        """)
        c_task.add(self._verify_chk)

        self._snap_chk = QCheckBox("Snap outlines to pixels  (experimental)")
        self._snap_chk.setChecked(SNAP_DEFAULT_ON)
        self._snap_chk.setCursor(Qt.PointingHandCursor)
        self._snap_chk.setFont(QFont(UI_FONT, 9))
        self._snap_chk.setStyleSheet(f"""
            QCheckBox {{ color:{C_TEXT}; background:transparent; border:none; spacing:7px; }}
            QCheckBox::indicator {{
                width:14px; height:14px; border-radius:4px;
                border:1px solid {C_BORDER}; background:{C_PANEL_2};
            }}
            QCheckBox::indicator:checked {{ background:{C_AMBER}; border:1px solid {C_AMBER}; }}
        """)
        c_task.add(self._snap_chk)
        shint = QLabel("Off by default. Locks outlines to segmented contours — "
                       "only helps when objects contrast cleanly with what they "
                       "rest on. On busy or low-contrast scenes it makes "
                       "placement worse, so leave it off unless it visibly helps.")
        shint.setWordWrap(True)
        shint.setFont(QFont(UI_FONT, 8))
        shint.setStyleSheet(f"color:{C_TEXT_DIM};background:transparent;border:none;")
        c_task.add(shint)
        vhint = QLabel("Model re-checks its own outlines on the ruler image. "
                       "Much better placement, 2 API calls per import.")
        vhint.setWordWrap(True)
        vhint.setFont(QFont(UI_FONT, 8))
        vhint.setStyleSheet(f"color:{C_TEXT_DIM};background:transparent;border:none;")
        c_task.add(vhint)

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

        # Appears only after a failed detection. Re-runs on the frame already in
        # memory, so a transient API fault no longer costs a re-import.
        self._retry_btn = _ghost_btn("⟳  Retry vision", C_AMBER, h=29)
        self._retry_btn.setVisible(False)
        self._retry_btn.clicked.connect(self._on_retry_vision)
        c_task.add(self._retry_btn)
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

        # ── STEP 2 · Playback + speed ─────────────────────────────────────────
        c_play = SectionCard("STEP 2 · PHYSICAL SIMULATION", C_CYAN)

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

        c_leg = SectionCard("HIGHLIGHT COLOUR LEGEND", C_TEXT_DIM)
        c_leg.add(self._legend())
        bl.addWidget(c_leg)

        bl.addStretch()

    def _build_chat_ui(self):
        """Build the operator-facing command conversation.

        Scene perception and command planning remain internal pipeline stages;
        their raw prompts, object cards, command dump and colour legend are no
        longer part of the operating UI.
        """
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        self.setMinimumWidth(360)
        self.setMaximumWidth(460)
        self.setStyleSheet(f"background:{C_BG};")

        # Keep chrome deliberately quiet: the conversation itself is the UI.
        toolbar = QWidget()
        toolbar.setStyleSheet("background:transparent;border:none;")
        h = QHBoxLayout(toolbar); h.setContentsMargins(3, 0, 3, 0); h.setSpacing(8)
        self._instructions = self._load_instructions()
        self._instructions_btn = QPushButton()
        self._refresh_instruction_button()
        self._instructions_btn.setFixedHeight(30)
        self._instructions_btn.setCursor(Qt.PointingHandCursor)
        self._instructions_btn.clicked.connect(self._open_instructions)
        self._instructions_btn.setStyleSheet(f"QPushButton{{background:rgba(255,255,255,0.75);color:{C_TEXT_DIM};border:1px solid {C_BORDER};border-radius:10px;padding:0 11px;font-weight:600;}} QPushButton:hover{{background:#ffffff;color:{C_VIOLET};border-color:#c4b5fd;}}")
        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setFixedHeight(30); self._stop_btn.setEnabled(False)
        self._stop_btn.setCursor(Qt.PointingHandCursor); self._stop_btn.clicked.connect(self._on_stop)
        self._stop_btn.setStyleSheet(f"QPushButton{{background:#fff;color:{C_RED};border:1px solid #fecaca;border-radius:10px;padding:0 12px;font-weight:700;}} QPushButton:hover{{background:#fff1f2;}} QPushButton:disabled{{color:#b8c0ce;border-color:{C_BORDER};}}")
        h.addWidget(self._instructions_btn); h.addStretch(); h.addWidget(self._stop_btn)
        root.addWidget(toolbar)

        self._chat = ChatView()
        root.addWidget(self._chat, 1)

        compose = QFrame()
        compose.setStyleSheet(f"QFrame{{background:rgba(255,255,255,0.92);border:1px solid {C_BORDER};border-radius:22px;}}")
        glow = QGraphicsDropShadowEffect(compose)
        glow.setBlurRadius(26); glow.setOffset(0, 5)
        glow.setColor(QColor(23, 32, 51, 46))
        compose.setGraphicsEffect(glow)
        cl = QHBoxLayout(compose); cl.setContentsMargins(12, 9, 9, 9); cl.setSpacing(8)
        self._task_input = ComposeEdit()
        self._task_input.setPlaceholderText(
            "Message A2…   ⏎ send · ⇧⏎ new line · 🎙 or right ⌥ to speak")
        self._task_input.submitted.connect(self._on_submit)
        self._task_input.setFixedHeight(52)
        self._task_input.setFont(QFont(UI_FONT, 10))
        self._task_input.setStyleSheet(f"QPlainTextEdit{{background:transparent;color:{C_TEXT};border:none;padding:6px;}}")
        self._mic_btn = QPushButton()
        self._mic_btn.setIconSize(QSize(21, 21))
        self._mic_btn.setFixedSize(36, 36); self._mic_btn.setCursor(Qt.PointingHandCursor)
        self._mic_btn.setToolTip("Speak your message  ·  right ⌥ speaks and sends")
        self._mic_btn.clicked.connect(lambda: self.toggle_voice(auto_send=False))
        self._paint_mic(False)
        self._run_btn = QPushButton("↑")
        self._run_btn.setFixedSize(36, 36); self._run_btn.setCursor(Qt.PointingHandCursor)
        self._run_btn.setStyleSheet(f"QPushButton{{background:{C_TEXT};color:white;border:none;border-radius:18px;font-size:20px;font-weight:bold;}} QPushButton:hover{{background:{C_BLUE};}} QPushButton:disabled{{background:#cbd5e1;}}")
        self._run_btn.clicked.connect(self._on_run)
        # Takes the text box's place while recording, the way a voice note
        # replaces the message field rather than crowding in beside it.
        self._wave = WaveMeter()
        self._wave.setFixedHeight(52)
        self._wave.setVisible(False)
        cl.addWidget(self._task_input, 1); cl.addWidget(self._wave, 1)
        cl.addWidget(self._mic_btn, 0, Qt.AlignBottom)
        cl.addWidget(self._run_btn, 0, Qt.AlignBottom)

        # Voice state: one recorder at a time, and whether this take should be
        # sent automatically (right ⌥) or just dropped into the box (button).
        self._voice        = None
        self._voice_send   = False
        self._voice_tail   = ""
        self._voice_thread = None
        self._idle_hint    = self._task_input.placeholderText()
        self._serial       = None       # USB link, set by the main window
        self._send_when_ready = False   # armed by an example, fired by vision
        root.addWidget(compose)

        note = QLabel("Commands run automatically once prepared.")
        note.setWordWrap(True); note.setFont(QFont(UI_FONT, 8)); note.setStyleSheet(f"color:{C_TEXT_DIM};background:transparent;border:none;padding:0 4px;")
        root.addWidget(note)

        # Internal pipeline defaults. The chat UI deliberately shows none of
        # these; Settings is where they surface for anyone who wants them.
        self._verify_chk = QCheckBox(); self._verify_chk.setChecked(True)
        self._snap_chk = QCheckBox(); self._snap_chk.setChecked(SNAP_DEFAULT_ON)
        self._speed_mult = 1.0
        self._cmd_text = ""
        self._compact_stages = True
        self._thinking = None          # live ShimmerLabel bubble, if any
        self._chat_message("A2", "Import an image, then tell me what to do.")

    def _refresh_instruction_button(self):
        count = len(getattr(self, "_instructions", []))
        self._instructions_btn.setText(
            "Custom instructions" + (f" · {count}" if count else ""))

    def _open_instructions(self):
        """Edit persistent planner preferences without returning to a sidebar.

        Each add, edit or delete is written through immediately, so closing the
        sheet — by any route, including Esc — never discards a change.
        """
        dlg = InstructionsDialog(self._instructions, self)
        dlg.changed.connect(self._apply_instructions)
        dlg.exec()

    def _apply_instructions(self, items: list):
        self._instructions = [s.strip() for s in items if s.strip()]
        self._save_instructions()
        self._refresh_instruction_button()

    def _chat_message(self, speaker, message, user=False, accent=None):
        return self._chat.message(str(message), user=user, accent=accent)

    @staticmethod
    def _legend():
        w = QWidget(); w.setStyleSheet("background:transparent;border:none;")
        g = QGridLayout(w); g.setContentsMargins(0, 2, 0, 2)
        g.setHorizontalSpacing(10); g.setVerticalSpacing(4)
        entries = [
            ('#60a5fa', 'goto — moving'),      ('#22c55e', 'pickup — grasp'),
            ('#facc15', 'keep — place'),       ('#22d3ee', 'pour — pouring'),
            ('#f97316', 'press — engage'),     ('#a78bfa', 'release — disengage'),
            ('#fb923c', 'contact pass / slide'), ('#f43f5e', 'slice'),
            ('#6b7280', 'wait_X — paused'),    ('#ffd700', 'Task_Completed'),
            ('#4ade80', '⧉ pixel-locked'),     ('#94a3b8', '? unidentified'),
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
    # ── voice input ───────────────────────────────────────────────────────────
    def _paint_mic(self, live: bool):
        if live:
            css = (f"QPushButton{{background:{C_RED};border:none;"
                   "border-radius:18px;}}")
        else:
            css = (f"QPushButton{{background:rgba(255,255,255,0.85);"
                   f"border:1px solid {C_BORDER};border-radius:18px;}}"
                   "QPushButton:hover{background:#ffffff;border-color:#c4b5fd;}")
        self._mic_btn.setStyleSheet(css)
        # A stylesheet colour cannot reach a painted icon, so it is redrawn.
        self._mic_btn.setIcon(mic_icon("#ffffff" if live else C_TEXT_DIM))

    def shutdown(self):
        """Let go of the microphone before the window closes."""
        if self._voice is not None:
            self._voice.abort("Window closed.")
            self._voice = None

    def toggle_voice(self, auto_send: bool = False):
        """Start dictating, or stop the take that is already running.

        Nothing ends a take but you: tap to start, tap again to stop. auto_send
        is what separates the two entry points — the right ⌥ key sends the
        sentence once you stop, the button leaves it in the box to edit.
        """
        if self._voice_thread is not None and self._voice_thread.isRunning():
            return                                  # already transcribing
        if self._voice is not None:
            self._voice.stop(by_user=True)          # second tap = stop now
            return
        if speech_rec is None:
            self._set_stage(f"⚠️  Speech recognition unavailable: "
                            f"{SPEECH_IMPORT_ERROR}", C_RED)
            return

        rec = VoiceRecorder(self)
        rec.finished.connect(self._on_voice_audio)
        rec.failed.connect(self._on_voice_failed)
        rec.level.connect(self._wave.push)
        self._voice_send = auto_send
        if not rec.start():
            return
        self._voice = rec
        self._paint_mic(True)
        self._show_wave(True, "Listening…  ·  tap to stop"
                        + ("  &  send" if auto_send else ""))

    def _show_wave(self, on: bool, hint: str = ""):
        """Swap the text box for the waveform, or put it back."""
        if on:
            self._wave.start(hint)
        else:
            self._wave.stop()
        self._wave.setVisible(on)
        self._task_input.setVisible(not on)

    def _on_voice_audio(self, pcm: bytes, by_user: bool):
        self._voice = None
        self._paint_mic(False)
        self._show_wave(False)
        # The runaway guard also lands here. Text still arrives in the box,
        # but a take the speaker never closed is never sent.
        self._voice_send = self._voice_send and by_user
        if len(pcm) < VoiceRecorder.RATE * VoiceRecorder.SAMPLE_WIDTH // 4:
            self._task_input.setPlaceholderText(self._idle_hint)
            return                                  # under 0.25 s: a stray tap
        self._task_input.setPlaceholderText("Transcribing…")
        self._mic_btn.setEnabled(False)
        w = TranscribeWorker(pcm, VoiceRecorder.RATE,
                             VoiceRecorder.SAMPLE_WIDTH, self)
        w.done.connect(self._on_voice_text)
        w.failed.connect(self._on_voice_failed)
        w.stage.connect(self._task_input.setPlaceholderText)
        w.finished.connect(self._voice_thread_done)
        self._voice_thread = w
        w.start()

    def _voice_thread_done(self):
        self._voice_thread = None
        self._mic_btn.setEnabled(True)

    def _on_voice_text(self, text: str):
        self._task_input.setPlaceholderText(self._idle_hint)
        sentence = speech_to_sentence(text)
        if not sentence:
            return
        existing = self._task_input.toPlainText().rstrip()
        joined   = f"{existing} {sentence}" if existing else sentence
        self._task_input.setPlainText(joined)
        self._task_input.moveCursor(QTextCursor.End)
        self._task_input.setFocus()
        if self._voice_send:
            self._on_submit()

    def _on_voice_failed(self, message: str):
        self._voice = None
        self._paint_mic(False)
        self._show_wave(False)
        self._mic_btn.setEnabled(True)
        self._task_input.setPlaceholderText(self._idle_hint)
        self._set_stage(f"⚠️  {message}", C_RED)

    def _lock(self, locked: bool):
        self._run_btn.setEnabled(not locked and bool(self._all_objs))

    def _set_stage(self, text: str, color=C_CYAN):
        """Narrate a pipeline stage.

        Anything still in flight (the default cyan) drives one shimmering
        bubble that rewrites itself as the pipeline advances; the engineering
        checkpoints it passes through are folded into that bubble's Details
        toggle rather than flooding the transcript. A non-default colour means
        the stage resolved, so the shimmer freezes and the outcome lands as a
        normal message.
        """
        if not text or text == getattr(self, "_last_stage", None):
            self._last_stage = text
            return
        self._last_stage = text

        verbose = ("preparing measured", "pass 1", "pass 2", "resolving grid",
                   "locking outlines", "retry")
        is_verbose = any(part in text.lower() for part in verbose)
        working = (color == C_CYAN)

        if working:
            if self._thinking is None:
                self._thinking = self._chat.message("", kind="thinking")
            if is_verbose and getattr(self, "_compact_stages", True):
                # Keep the headline steady, tuck the checkpoint underneath.
                self._thinking.add_detail(text)
                if not self._thinking._content.text():
                    self._thinking.set_text("Working…")
            else:
                previous = self._thinking._content.text()
                if previous:
                    self._thinking.add_detail(previous)
                self._thinking.set_text(text)
            self._chat.scroll_to_end()
            return

        self._end_thinking()
        self._chat_message("A2", text, accent=color)

    def _chat_error(self, err, summary="Not able to complete task."):
        """Report a failure in one line, with the raw error a toggle away.

        The full text is kept intact rather than truncated: an API key or quota
        message is only useful if it can be read and copied in full.
        """
        self._end_thinking()
        bubble = self._chat.message(summary, accent=C_RED)
        for line in str(err).strip().splitlines() or [str(err)]:
            bubble.add_detail(line.rstrip())
        bubble.enable_copy()
        self._last_stage = summary
        self._chat.scroll_to_end()
        return bubble

    def _end_thinking(self, final_text=None):
        if self._thinking is not None:
            self._thinking.freeze(final_text)
            self._thinking = None

    def _clear_all(self):
        self._vision_objs = []
        self._cmd_text = ""
        self._stop_btn.setEnabled(False)
        self._end_thinking()
        self._set_stage("")
        self._refresh_objects()
        self.stop_commands.emit()

    def _on_speed_change(self, idx: int):
        mult = self.SPEEDS[idx]
        self._speed_lbl.setText(f"{mult:g}×")
        self.speed_changed.emit(mult)

    def set_task_text(self, text: str, send_when_ready: bool = False):
        """Put a task in the message box.

        send_when_ready is what makes an example one click: the task cannot be
        sent yet — there is nothing on the board until vision has finished —
        so it is armed here and fired from _on_vision_done.
        """
        self._task_input.setPlainText(text)
        self._task_input.moveCursor(QTextCursor.End)
        self._task_input.setFocus()
        self._send_when_ready = bool(send_when_ready)

    # ── playback speed ────────────────────────────────────────────────────────
    def speed_mult(self) -> float:
        return self._speed_mult

    def set_speed_mult(self, mult: float):
        """The one way playback speed changes now that Settings owns the control."""
        self._speed_mult = float(mult)
        self.speed_changed.emit(self._speed_mult)

    # ── instructions ──────────────────────────────────────────────────────────
    @staticmethod
    def _load_instructions() -> list:
        return [s for s in AI_INSTRUCTIONS if isinstance(s, str)]

    def _save_instructions(self):
        """Write the instructions back into this file's own block.

        The rewrite goes through a temporary copy swapped in with os.replace,
        so an interrupted save can never leave the app's source truncated.
        AI_INSTRUCTIONS is updated in memory as well, keeping the running app
        and the file in agreement without a restart.
        """
        global AI_INSTRUCTIONS
        AI_INSTRUCTIONS = list(self._instructions)
        block = ("AI_INSTRUCTIONS = [\n"
                 + "".join(f"    {json.dumps(s)},\n" for s in self._instructions)
                 + "]\n")
        path = os.path.abspath(__file__)
        try:
            with open(path, "r", encoding="utf-8") as f:
                src = f.read()
            new, count = INSTRUCTIONS_RE.subn(lambda _m: block, src, count=1)
            if count != 1:
                raise RuntimeError("the AI_INSTRUCTIONS block was not found")
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(new)
            os.replace(tmp, path)
        except Exception as exc:
            # It still applies this session, but say so — silently losing an
            # instruction the operator just wrote would be worse.
            self._set_stage("⚠️  Instructions apply now but could not be saved "
                            f"into {os.path.basename(path)}: {exc}", C_RED)

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
        # Object data is deliberately kept out of the sidebar UI. It remains
        # available to the planner and to the grid overlay.
        self._run_btn.setEnabled(bool(self._all_objs))
        self.boxes_ready.emit([o for o in self._all_objs if o.get('box')])

    @staticmethod
    def _format_objects_html(objs: list) -> str:
        """Qt's rich-text engine ignores margin/float on inline spans, which is
        why the badges ran together as 'brownsmall' and 'egghen eggbrown egg'.
        Spacing is done with non-breaking spaces instead."""
        if not objs:
            return (f'<div style="color:{C_TEXT_DIM};font-family:\'{UI_FONT}\';font-size:10px;'
                    f'padding:10px;">No objects yet — import an image to analyse it.</div>')
        SIZE_COLOR = {'small': '#94a3b8', 'medium': '#60a5fa', 'large': '#c084fc'}
        SEP  = '&nbsp;&nbsp;'
        cards = []
        for o in objs:
            manual   = o.get('source') == 'manual'
            accent   = '#facc15' if manual else '#38bdf8'
            badge    = '&#9998; MANUAL' if manual else '&#128065; VISION'
            size     = str(o.get('size', '?')).lower()
            size_clr = SIZE_COLOR.get(size, '#94a3b8')

            aka = o.get('aka', [])
            aka = aka if isinstance(aka, list) else [aka]
            aka_html = ''
            tags = SEP.join(
                f'<span style="background:#243050;color:#94a3b8;'
                f'border:1px solid #33406b;font-size:9px;">'
                f'&nbsp;{str(t).strip()}&nbsp;</span>'
                for t in aka if str(t).strip())
            if tags:
                aka_html = f'<div style="margin-top:5px;">{tags}</div>'

            if o.get('unknown'):
                surf = (' &nbsp;<span style="color:#94a3b8;font-size:9px;">'
                        'UNIDENTIFIED</span>')
            elif o.get('snapped'):
                surf = (' &nbsp;<span style="color:#4ade80;font-size:9px;">'
                        'PIXEL-LOCKED</span>')
            else:
                surf = ''      # the normal case: position came from the model
            touches = o.get('touches', '')
            ncells  = len(touches.split(',')) if touches else 0

            cards.append(
                f'<div style="background:#1d2540;border:1px solid #2c3757;'
                f'border-left:3px solid {accent};border-radius:7px;'
                f'padding:8px 10px;margin-bottom:7px;">'
                f'<div><span style="color:#e8ecf8;font-weight:700;font-size:11px;'
                f'font-family:\'{UI_FONT}\';">{str(o.get("name","object")).title()}</span>'
                f'{SEP}<span style="color:{accent};font-size:8px;'
                f'font-family:{MONO_FONT};">{badge}</span>{surf}</div>'
                f'<div style="margin-top:5px;">'
                f'<span style="background:#0e7490;color:#cffafe;'
                f'font-size:9px;font-family:{MONO_FONT};">'
                f'&nbsp;&#127919; {o.get("center","?")}&nbsp;</span>{SEP}'
                f'<span style="background:#3b2f0b;color:#fcd34d;'
                f'font-size:9px;font-family:{MONO_FONT};">'
                f'&nbsp;&#9632; {o.get("color","?")}&nbsp;</span>{SEP}'
                f'<span style="background:#243050;color:{size_clr};'
                f'font-size:9px;font-family:{MONO_FONT};">&nbsp;{size}&nbsp;</span>'
                f'</div>'
                + (f'<div style="color:#8b97b8;font-size:9px;font-family:{MONO_FONT};'
                   f'margin-top:5px;">&#128205; {ncells} cells: {touches}</div>'
                   if touches else '')
                + (f'<div style="color:#94a3b8;font-size:9px;font-family:\'{UI_FONT}\';'
                   f'margin-top:5px;line-height:1.4;">{o.get("desc","")}</div>'
                   if o.get('desc') else '')
                + aka_html + '</div>'
            )
        nv = sum(1 for o in objs if o.get('source') != 'manual')
        nm = len(objs) - nv
        header = (f'<div style="color:#38bdf8;font-family:\'{UI_FONT}\';font-size:9px;'
                  f'letter-spacing:0.05em;margin-bottom:8px;">'
                  f'{len(objs)} OBJECTS &nbsp;·&nbsp; {nv} vision &nbsp;·&nbsp; {nm} manual</div>')
        return header + ''.join(cards)

    # ── vision flow (auto-triggered on image import) ─────────────────────────
    def auto_analyse(self):
        """Called by CameraPanel right after a successful image import."""
        self._lock(True)
        self._stop_btn.setEnabled(False)
        self._cmd_text = ""
        self._set_stage("Analysing board…")
        self.request_frame.emit()

    # ── worker lifetime ──────────────────────────────────────────────────────
    def _track(self, worker):
        """Hold a reference until the thread reports finished, then release it."""
        self._live_workers.append(worker)
        worker.finished.connect(lambda w=worker: self._untrack(w))
        return worker

    def _untrack(self, worker):
        try:
            self._live_workers.remove(worker)
        except ValueError:
            pass
        worker.deleteLater()

    def _vision_busy(self) -> bool:
        return any(isinstance(w, VisionWorker) and w.isRunning()
                   for w in self._live_workers)

    def feed_frame(self, bgr):
        if bgr is None:
            self._lock(False)
            self._set_stage("⚠️  No image loaded — click  📁 Import Image  first", C_RED)
            return
        if self._vision_busy():
            self._set_stage("⏳  Vision is already running — wait for it to finish", C_AMBER)
            return
        self._last_frame = bgr
        self._set_stage("🔍  Preparing measured canvas…")
        # The task text, when the operator has already typed one, only lifts the
        # surface-exclusion for furniture they asked to move. Empty box → the
        # prompt is byte-for-byte what it always was.
        w = self._track(VisionWorker(bgr, verify=self._verify_chk.isChecked(),
                                     snap=self._snap_chk.isChecked(),
                                     task_text=self._task_input.toPlainText().strip()))
        self._vision_worker = w
        w.progress.connect(self._set_stage)
        w.done.connect(self._on_vision_done)
        w.error.connect(self._on_vision_error)
        w.start()

    def _on_retry_vision(self):
        """Re-run detection on the frame already in memory — no re-import."""
        if self._last_frame is None:
            self._set_stage("⚠️  Nothing to retry — import an image first", C_RED)
            return
        self._lock(True)
        self.feed_frame(self._last_frame)

    def _on_vision_error(self, err: str):
        self._lock(False)
        self._send_when_ready = False
        self._chat_error(err, "Not able to analyse the board.")

    def _on_vision_done(self, objs: list):
        self._vision_objs = objs
        self._refresh_objects()
        self._lock(False)
        if self._snap_chk.isChecked():
            locked  = sum(1 for o in objs if o.get('snapped'))
            unknown = sum(1 for o in objs if o.get('unknown'))
            bits = [f"{locked}/{len(objs)} pixel-locked"]
            if unknown:
                bits.append(f"{unknown} unidentified")
            tail = "  ·  " + "  ·  ".join(bits)
        else:
            tail = ""
        headline = (f"Board ready — {len(objs)} items mapped{tail}. "
                    f"What would you like me to do?")
        self._end_thinking()
        bubble = self._chat_message("A2", headline, accent=C_GREEN)
        for o in objs:
            bubble.add_detail(obj_to_line(o))
        self._last_stage = headline
        self._chat.scroll_to_end()

        # An example arrives as a scene and its task together, so once the board
        # is mapped the task goes out on its own. Only ever armed by loading an
        # example — a hand-typed task is still sent by hand.
        if self._send_when_ready:
            self._send_when_ready = False
            if self._task_input.toPlainText().strip():
                self._on_run()

    # ── generate commands (dexterity gate → planner) ──────────────────────────
    def _on_submit(self):
        # Enter is ignored while a task is in flight, matching the send button.
        if self._run_btn.isEnabled():
            self._on_run()

    def _on_run(self):
        task = self._task_input.toPlainText().strip()
        if not task:
            self._set_stage("⚠️  Please describe a task first", C_RED); return
        if not self._all_objs:
            self._set_stage("Please import an image first so I can analyse the board.", C_RED); return
        self._chat_message("You", task, user=True)
        self._task_input.clear()
        self._lock(True)
        self._stop_btn.setEnabled(False)
        self._cmd_text = ""
        self._set_stage("Thinking…")
        if self._instructions:
            notes = "\n".join(f"- {s}" for s in self._instructions)
            task  = f"{task}\n\nADDITIONAL AI INSTRUCTIONS (apply throughout):\n{notes}"
        # Do not hold the operator behind a second LLM classifier. The planner
        # already carries the A2 capability constraints and can start now.
        self._set_stage("Planning task…")
        w = self._track(CommandWorker(self._object_list, task))
        self._command_worker = w
        w.chunk.connect(self._on_cmd_chunk)
        w.done.connect(self._on_cmd_done)
        w.error.connect(self._on_error)
        w.start()

    def _on_dexterity_verdict(self, verdict: str):
        if verdict == "dexterous":
            self._pending_task = None
            self._lock(False)
            self._set_stage(
                "🖐  Task requires dexterous manipulation — A2 (parallel gripper) "
                "cannot perform it. Try rephrasing with non-dexterous actions.", C_RED)
            return
        task = self._pending_task
        self._pending_task = None
        self._set_stage("Planning the command sequence…")
        w = self._track(CommandWorker(self._object_list, task))
        self._command_worker = w
        w.chunk.connect(self._on_cmd_chunk)
        w.done.connect(self._on_cmd_done)
        w.error.connect(self._on_error)
        w.start()

    def _on_cmd_chunk(self, delta: str):
        self._cmd_text += delta

    @staticmethod
    def _missing_objects(plan: str) -> list:
        """Objects the planner declared absent from the board.

        The planner is told to emit `MISSING: <object> - sub-task skipped` and
        carry on planning whatever is still feasible, and CommandRunner._parse
        drops those lines — so a partially impossible plan used to execute with
        no mention of what was missing. Nothing runs on a partial plan now.
        """
        names = []
        for line in plan.splitlines():
            line = line.strip().lstrip('#').strip()
            if not line.upper().startswith("MISSING:"):
                continue
            name = line.split(":", 1)[1].strip()
            name = re.split(r'\s+[-–]\s+', name, maxsplit=1)[0].strip()
            if name and name not in names:
                names.append(name)
        return names

    def _on_cmd_done(self, _full: str):
        self._lock(False)
        self._end_thinking()

        missing = self._missing_objects(self._cmd_text)
        if missing:
            listed = ", ".join(missing)
            self._chat_error(
                self._cmd_text.strip(),
                f"Not able to complete task — {listed} not on the board.")
            return

        if not CommandRunner._parse(self._cmd_text):
            self._chat_error(self._cmd_text.strip() or "The planner returned no commands.",
                             "Not able to complete task — no runnable steps.")
            return

        bubble = self._chat_message(
            "A2", "Commands ready. Invoking Alpha 2D unstacker…", accent=C_GREEN)
        # The plan itself stays folded away — one arrow reveals every step.
        for line in self._cmd_text.strip().splitlines():
            if line.strip():
                bubble.add_detail(line.strip())
        bubble.enable_copy()
        self._last_stage = "Commands ready. Invoking Alpha 2D unstacker…"
        self._chat.scroll_to_end()
        # The wire gets the plan the moment it exists and is known good — once
        # per generation, not per simulated step, so the board and the canvas
        # are working from the same sequence rather than racing each other.
        self._send_to_hardware(self._cmd_text)
        # Running is intentional: the conversational UI has no separate
        # play/approval step once it has successfully prepared a task.
        self._on_play()

    # ── hardware ──────────────────────────────────────────────────────────────
    def set_serial(self, link):
        """Hand the sidebar the shared USB link owned by the main window."""
        self._serial = link
        link.failed.connect(lambda msg: self._set_stage(f"⚠️  {msg}", C_RED))
        link.sent.connect(
            lambda n, port: self._set_stage(
                f"🔌  Sent {n} command{'' if n == 1 else 's'} to {port}", C_VIOLET))

    def _send_to_hardware(self, plan: str):
        link = getattr(self, "_serial", None)
        if link is not None and link.enabled:
            link.send_plan(plan)      # reports its own success or failure

    def _on_error(self, err: str):
        self._lock(False)
        self._chat_error(err)

    # ── play / stop ───────────────────────────────────────────────────────────
    def _on_play(self):
        text = self._cmd_text.strip()
        if not text:
            return
        self._stop_btn.setEnabled(True)
        self._set_stage("Executing on the board…")
        self.play_commands.emit(text)

    def _on_stop(self):
        self.stop_commands.emit()
        self._stop_btn.setEnabled(False)
        self._set_stage("Stopped.", C_TEXT_DIM)

    def on_runner_finished(self):
        self._stop_btn.setEnabled(False)
        self._set_stage("Task complete.", C_GREEN)

    def on_runner_step(self, current: int, total: int, cmd: str):
        m = re.match(r'goto_coordinate\s*=\s*([A-Ta-t])\s*,\s*(\d+)', cmd.strip())
        coord = f"  →  {m.group(1).upper()}{m.group(2)}" if m else ""
        short = cmd if len(cmd) <= 58 else cmd[:55] + "…"
        # Keep progress lightweight: high-frequency robot steps belong on the
        # canvas, while the chat narrates only the meaningful lifecycle stages.


# ─────────────────────────────────────────────────────────────────────────────
#  Image panel
# ─────────────────────────────────────────────────────────────────────────────
def enumerate_cameras(max_probe: int = 6):
    """Every capture device the machine can see, as (index, name) pairs.

    Qt names the devices, which is the only way to tell a built-in FaceTime
    camera apart from the USB one you just plugged in. Its enumeration order is
    the same order OpenCV indexes them, so the position doubles as the cv2
    index. If Qt reports nothing we fall back to opening indices blind.
    """
    cams = []
    try:
        for i, dev in enumerate(QMediaDevices.videoInputs()):
            name = dev.description() or f"Camera {i}"
            cams.append((i, name))
    except Exception:
        pass
    if cams:
        return cams
    for i in range(max_probe):
        cap = cv2.VideoCapture(i)
        alive = cap.isOpened()
        cap.release()
        if alive:
            cams.append((i, f"Camera {i}"))
    return cams


class ToggleSwitch(QWidget):
    """iOS-style sliding switch. Emits toggled(bool) like a QCheckBox."""

    toggled = Signal(bool)

    def __init__(self, checked=False, parent=None):
        super().__init__(parent)
        self._on = bool(checked)
        self.setFixedSize(46, 26)
        self.setCursor(Qt.PointingHandCursor)

    def isChecked(self):
        return self._on

    def setChecked(self, on: bool):
        on = bool(on)
        if on != self._on:
            self._on = on
            self.update()
            self.toggled.emit(on)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.setChecked(not self._on)
        super().mousePressEvent(ev)

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(1, 1, -1, -1)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(C_GREEN if self._on else "#c9d5e6"))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d  = r.height() - 6
        cx = r.right() - 3 - d if self._on else r.left() + 3
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(cx, r.top() + 3, d, d)


class USBCameraDialog(QDialog):
    """Pick which connected camera feeds the main vision.

    The list is rebuilt from the OS every time it opens (and on Refresh), so a
    camera plugged in while the app was running shows up. Highlighting an entry
    opens it straight away for a live preview — that is the only reliable way
    to tell two identically named webcams apart before committing to one.
    """

    PREVIEW_W, PREVIEW_H = 384, 216

    def __init__(self, current_index=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connect USB Camera")
        self.setModal(True)
        self.setMinimumWidth(440)
        self.setStyleSheet(f"QDialog{{background:{C_BG};}}")

        self.chosen_index = None      # set on accept; None means "disconnect"
        self.chosen_name  = ""
        self._cap = None

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(10)

        title = QLabel("Connect USB Camera")
        title.setFont(QFont(UI_FONT_B, 14))
        title.setStyleSheet(f"color:{C_TEXT};background:transparent;")
        sub = QLabel("Detected capture devices. Select one to preview it, "
                     "then use it as the live feed for vision.")
        sub.setWordWrap(True)
        sub.setFont(QFont(UI_FONT, 9))
        sub.setStyleSheet(f"color:{C_TEXT_DIM};background:transparent;")
        root.addWidget(title); root.addWidget(sub)

        self._list = QListWidget()
        self._list.setFixedHeight(112)
        self._list.setFont(QFont(UI_FONT, 10))
        self._list.setStyleSheet(f"""
            QListWidget{{background:#ffffff;color:{C_TEXT};
                border:1px solid {C_BORDER};border-radius:10px;padding:4px;}}
            QListWidget::item{{padding:6px 8px;border-radius:6px;}}
            QListWidget::item:selected{{background:{C_BLUE};color:#ffffff;}}
        """)
        self._list.currentRowChanged.connect(self._on_row)
        root.addWidget(self._list)

        self._preview = QLabel()
        self._preview.setFixedSize(self.PREVIEW_W, self.PREVIEW_H)
        self._preview.setAlignment(Qt.AlignCenter)
        self._preview.setFont(QFont(UI_FONT, 10))
        self._preview.setStyleSheet(
            f"background:#0f172a;color:#94a3b8;border-radius:10px;")
        self._preview.setText("No preview")
        root.addWidget(self._preview, 0, Qt.AlignHCenter)

        self._status = QLabel("")
        self._status.setFont(QFont(UI_FONT, 9))
        self._status.setStyleSheet(f"color:{C_TEXT_DIM};background:transparent;")
        root.addWidget(self._status)

        btns = QHBoxLayout(); btns.setSpacing(8)
        refresh = QPushButton("⟳  Refresh")
        cancel  = QPushButton("Cancel")
        disconn = QPushButton("Disconnect")
        self._use = QPushButton("Use This Camera")
        for b in (refresh, cancel, disconn):
            b.setFixedHeight(30); b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(f"""
                QPushButton{{background:#ffffff;color:{C_TEXT};
                    border:1px solid {C_BORDER};border-radius:8px;
                    font-family:'{UI_FONT}';font-weight:700;font-size:10px;padding:0 14px;}}
                QPushButton:hover{{background:#e8f0ff;color:{C_BLUE};}}
            """)
        self._use.setFixedHeight(30); self._use.setCursor(Qt.PointingHandCursor)
        self._use.setStyleSheet(f"""
            QPushButton{{background:{C_BLUE};color:#ffffff;border:none;
                border-radius:8px;font-family:'{UI_FONT}';font-weight:700;
                font-size:10px;padding:0 18px;}}
            QPushButton:hover{{background:#1d4ed8;}}
            QPushButton:disabled{{background:#c9d5e6;color:#ffffff;}}
        """)
        refresh.clicked.connect(self._reload)
        cancel.clicked.connect(self.reject)
        disconn.clicked.connect(self._disconnect)
        self._use.clicked.connect(self._accept_current)
        btns.addWidget(refresh); btns.addStretch(1)
        btns.addWidget(disconn); btns.addWidget(cancel); btns.addWidget(self._use)
        root.addLayout(btns)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

        self._reload(select_index=current_index)

    # ── device list ───────────────────────────────────────────────────────────
    def _reload(self, *, select_index=None):
        if select_index is None:
            select_index = self._current_index()
        self._close_cap()
        self._list.blockSignals(True)
        self._list.clear()
        self._cams = enumerate_cameras()
        for idx, name in self._cams:
            QListWidgetItem(f"📷  {name}   ·   index {idx}", self._list)
        self._list.blockSignals(False)

        if not self._cams:
            self._status.setText("⚠️  No cameras detected. Plug one in and hit Refresh.")
            self._preview.setText("No camera detected")
            self._use.setEnabled(False)
            return

        self._use.setEnabled(True)
        row = next((r for r, (i, _) in enumerate(self._cams) if i == select_index), 0)
        self._list.setCurrentRow(row)
        self._status.setText(f"{len(self._cams)} device(s) detected")

    def _current_index(self):
        row = self._list.currentRow()
        if 0 <= row < len(getattr(self, "_cams", [])):
            return self._cams[row][0]
        return None

    # ── live preview ──────────────────────────────────────────────────────────
    def _on_row(self, row):
        self._close_cap()
        if not (0 <= row < len(self._cams)):
            return
        idx, name = self._cams[row]
        cap = cv2.VideoCapture(idx)
        if not cap.isOpened():
            cap.release()
            self._preview.setText("Could not open this camera")
            self._status.setText(f"⚠️  {name} is busy or unavailable")
            return
        self._cap = cap
        self._status.setText(f"Previewing {name}")
        self._timer.start(33)

    def _tick(self):
        if self._cap is None:
            return
        ok, frame = self._cap.read()
        if not ok or frame is None:
            return
        rgb  = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        qi   = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888).copy()
        self._preview.setPixmap(QPixmap.fromImage(qi).scaled(
            self.PREVIEW_W, self.PREVIEW_H, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _close_cap(self):
        self._timer.stop()
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    # ── outcomes ──────────────────────────────────────────────────────────────
    def _accept_current(self):
        row = self._list.currentRow()
        if not (0 <= row < len(self._cams)):
            return
        self.chosen_index, self.chosen_name = self._cams[row]
        self._close_cap()          # released here so the panel can claim it
        self.accept()

    def _disconnect(self):
        self.chosen_index, self.chosen_name = None, ""
        self._close_cap()
        self.accept()

    def reject(self):
        self._close_cap()
        super().reject()

    def closeEvent(self, ev):
        self._close_cap()
        super().closeEvent(ev)


# Captured before anything can edit them, so Restore Defaults means the values
# this file shipped with rather than whatever the last session left behind.
SETTINGS_DEFAULTS = {
    "VISION_MODEL": VISION_MODEL,
    "DEXTERITY_MODEL": DEXTERITY_MODEL,
    "PLANNER_MODEL": PLANNER_MODEL,
    "VOICE_TIDY_MODEL": VOICE_TIDY_MODEL,
    "SPEECH_MODEL": SPEECH_MODEL,
    "WAIT_MAX_PLAYBACK": WAIT_MAX_PLAYBACK,
    "VOICE_TIDY": VOICE_TIDY,
}


def set_setting(name: str, value):
    """Rebind a module-level knob. Every reader looks it up per call, so the
    change lands on the next request rather than needing a restart."""
    globals()[name] = value


class SettingsDialog(QDialog):
    """One window for the knobs that were previously constants in the source.

    Everything here is read at the point of use, so a change applies to the
    next vision pass, the next plan, the next wait — nothing is cached and
    nothing needs a restart. The legend is carried along because this is where
    people come looking for "what does that colour mean".
    """

    WAIT_CAPS = [2.0, 5.0, 10.0, 15.0, 30.0, 60.0]

    def __init__(self, sidebar, parent=None):
        super().__init__(parent)
        self._sidebar = sidebar
        self.setWindowTitle("Settings")
        self.setMinimumSize(520, 640)
        self.setStyleSheet(f"QDialog{{background:{C_BG};}}")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 14)
        outer.setSpacing(10)

        title = QLabel("Settings")
        title.setFont(QFont(UI_FONT_B, 15))
        title.setStyleSheet(f"color:{C_TEXT};background:transparent;")
        outer.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        holder = QWidget(); holder.setStyleSheet("background:transparent;")
        body = QVBoxLayout(holder)
        body.setContentsMargins(0, 0, 6, 0)
        body.setSpacing(10)
        scroll.setWidget(holder)
        outer.addWidget(scroll, 1)

        body.addWidget(self._simulation_card())
        body.addWidget(self._models_card())
        body.addWidget(self._voice_card())
        legend = SectionCard("HIGHLIGHT COLOUR LEGEND", C_TEXT_DIM)
        legend.add(AISidebar._legend())
        body.addWidget(legend)
        body.addStretch(1)

        row = QHBoxLayout(); row.setSpacing(8)
        restore = QPushButton("Restore defaults")
        restore.setFixedHeight(30); restore.setCursor(Qt.PointingHandCursor)
        restore.setStyleSheet(f"""
            QPushButton{{background:#ffffff;color:{C_TEXT};
                border:1px solid {C_BORDER};border-radius:8px;
                font-family:'{UI_FONT}';font-weight:700;font-size:10px;padding:0 14px;}}
            QPushButton:hover{{background:#fff1f2;color:{C_RED};border-color:#fecaca;}}
        """)
        restore.clicked.connect(self._restore)
        done = QPushButton("Done")
        done.setFixedHeight(30); done.setCursor(Qt.PointingHandCursor)
        done.setStyleSheet(f"""
            QPushButton{{background:{C_BLUE};color:#ffffff;border:none;
                border-radius:8px;font-family:'{UI_FONT}';font-weight:700;
                font-size:10px;padding:0 18px;}}
            QPushButton:hover{{background:#1d4ed8;}}
        """)
        done.clicked.connect(self.accept)
        row.addWidget(restore); row.addStretch(1); row.addWidget(done)
        outer.addLayout(row)

    # ── shared widget styling ─────────────────────────────────────────────────
    def _row(self, label: str, widget, hint: str = ""):
        wrap = QVBoxLayout(); wrap.setSpacing(2)
        line = QHBoxLayout(); line.setSpacing(10)
        lab = QLabel(label)
        lab.setFont(QFont(UI_FONT, 9))
        lab.setStyleSheet(f"color:{C_TEXT};background:transparent;border:none;")
        line.addWidget(lab); line.addStretch(1); line.addWidget(widget)
        wrap.addLayout(line)
        if hint:
            h = QLabel(hint)
            h.setWordWrap(True)
            h.setFont(QFont(UI_FONT, 8))
            h.setStyleSheet(f"color:{C_TEXT_DIM};background:transparent;border:none;")
            wrap.addWidget(h)
        return wrap

    def _field(self, text: str) -> QLineEdit:
        e = QLineEdit(text)
        e.setFixedWidth(210)
        e.setFixedHeight(26)
        e.setFont(QFont(MONO_FONT, 9))
        e.setStyleSheet(f"""
            QLineEdit{{background:#ffffff;color:{C_TEXT};
                border:1px solid {C_BORDER};border-radius:7px;padding:0 8px;}}
            QLineEdit:focus{{border-color:{C_BLUE};}}
        """)
        return e

    # ── cards ─────────────────────────────────────────────────────────────────
    def _simulation_card(self):
        card = SectionCard("SIMULATION", C_CYAN)

        speeds = AISidebar.SPEEDS
        current = self._sidebar.speed_mult()
        self._speed = QSlider(Qt.Horizontal)
        self._speed.setMinimum(0)
        self._speed.setMaximum(len(speeds) - 1)
        self._speed.setPageStep(1)
        self._speed.setValue(speeds.index(current) if current in speeds
                             else speeds.index(1.0))
        self._speed.setFixedWidth(190)
        self._speed.setCursor(Qt.PointingHandCursor)
        self._speed.setStyleSheet(f"""
            QSlider::groove:horizontal{{
                height:6px;border-radius:3px;
                background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {C_BLUE}, stop:0.5 {C_VIOLET}, stop:1 {C_PINK});}}
            QSlider::handle:horizontal{{
                background:#ffffff;border:2px solid {C_CYAN};
                width:16px;height:16px;margin:-6px 0;border-radius:9px;}}
            QSlider::handle:horizontal:hover{{border-color:{C_PINK};}}
        """)
        self._speed_lbl = QLabel(f"{AISidebar.SPEEDS[self._speed.value()]:g}×")
        self._speed_lbl.setFixedWidth(38)
        self._speed_lbl.setAlignment(Qt.AlignCenter)
        self._speed_lbl.setFont(QFont(MONO_FONT, 10, QFont.Bold))
        self._speed_lbl.setStyleSheet(f"color:{C_CYAN};background:transparent;border:none;")
        self._speed.valueChanged.connect(self._on_speed)
        srow = QHBoxLayout(); srow.setSpacing(6)
        srow.addWidget(self._speed); srow.addWidget(self._speed_lbl)
        holder = QWidget(); holder.setStyleSheet("background:transparent;border:none;")
        holder.setLayout(srow)
        card.add(self._row("Playback speed", holder,
                           "Applies live — drag it mid-playback. 0.5× … 4×"))

        self._wait = QComboBox()
        self._wait.setFixedWidth(120)
        self._wait.setFixedHeight(26)
        self._wait.setFont(QFont(UI_FONT, 9))
        self._wait.setStyleSheet(f"""
            QComboBox{{background:#ffffff;color:{C_TEXT};
                border:1px solid {C_BORDER};border-radius:7px;padding:0 8px;}}
        """)
        for cap in self.WAIT_CAPS:
            self._wait.addItem(f"{cap:g} s", cap)
        self._select_wait(WAIT_MAX_PLAYBACK)
        self._wait.currentIndexChanged.connect(
            lambda _i: set_setting("WAIT_MAX_PLAYBACK", self._wait.currentData()))
        card.add(self._row("Simulated wait cap", self._wait,
                           "A wait_X(300) still reports five minutes; playback "
                           "only holds for this long."))

        self._verify = QCheckBox()
        self._verify.setChecked(self._sidebar._verify_chk.isChecked())
        self._verify.setCursor(Qt.PointingHandCursor)
        self._verify.toggled.connect(self._sidebar._verify_chk.setChecked)
        card.add(self._row("Second-pass outline verification", self._verify))

        self._snap = QCheckBox()
        self._snap.setChecked(self._sidebar._snap_chk.isChecked())
        self._snap.setCursor(Qt.PointingHandCursor)
        self._snap.toggled.connect(self._sidebar._snap_chk.setChecked)
        card.add(self._row("Snap outlines to pixels (experimental)", self._snap))
        return card

    def _models_card(self):
        card = SectionCard("MODELS", C_VIOLET)
        self._model_fields = {}
        for name, label in (("VISION_MODEL", "Vision"),
                            ("DEXTERITY_MODEL", "Dexterity"),
                            ("PLANNER_MODEL", "Planner"),
                            ("VOICE_TIDY_MODEL", "Dictation tidy"),
                            ("SPEECH_MODEL", "Speech to text")):
            field = self._field(globals()[name])
            field.editingFinished.connect(
                lambda n=name, f=field: set_setting(n, f.text().strip()))
            self._model_fields[name] = field
            card.add(self._row(label, field))
        note = QLabel("Takes effect on the next request — nothing is cached.")
        note.setFont(QFont(UI_FONT, 8))
        note.setStyleSheet(f"color:{C_TEXT_DIM};background:transparent;border:none;")
        card.add(note)
        return card

    def _voice_card(self):
        card = SectionCard("VOICE", C_PINK)

        self._tidy = ToggleSwitch(VOICE_TIDY)
        self._tidy.toggled.connect(lambda on: set_setting("VOICE_TIDY", on))
        card.add(self._row("Clean up dictation", self._tidy,
                           "A second pass that strips hesitations from what you said."))

        note = QLabel("🎙 button dictates into the box; right ⌥ dictates and sends.")
        note.setWordWrap(True)
        note.setFont(QFont(UI_FONT, 8))
        note.setStyleSheet(f"color:{C_TEXT_DIM};background:transparent;border:none;")
        card.add(note)
        return card

    # ── behaviour ─────────────────────────────────────────────────────────────
    def _on_speed(self, idx: int):
        mult = AISidebar.SPEEDS[idx]
        self._speed_lbl.setText(f"{mult:g}×")
        # Through the sidebar rather than straight to the runner: it is what
        # both the runner and the grid overlay are already listening to.
        self._sidebar.set_speed_mult(mult)

    def _select_wait(self, value: float):
        i = self._wait.findData(value)
        if i < 0:
            self._wait.addItem(f"{value:g} s", value)
            i = self._wait.count() - 1
        self._wait.setCurrentIndex(i)

    def _restore(self):
        for name, value in SETTINGS_DEFAULTS.items():
            set_setting(name, value)
        for name, field in self._model_fields.items():
            field.setText(SETTINGS_DEFAULTS[name])
        self._select_wait(SETTINGS_DEFAULTS["WAIT_MAX_PLAYBACK"])
        self._tidy.setChecked(SETTINGS_DEFAULTS["VOICE_TIDY"])
        self._speed.setValue(AISidebar.SPEEDS.index(1.0))
        self._verify.setChecked(True)
        self._snap.setChecked(SNAP_DEFAULT_ON)


IMAGE_MODEL     = "gpt-image-1"
IMAGE_TIMEOUT_S = 240.0
IMAGE_QUALITY   = "low"        # always low — faster/cheaper view generation
IMAGE_MAX_SIDE  = 1536         # longest side uploaded as the reference photo
VIEWS_TITLE     = "Generate / View all 3 views"
VIEWS_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               ".views_cache")

# The three camera angles the panel can produce. Detection of the source
# viewpoint skips regenerating the angle the board already shows.
VIEW_KINDS = {
    "top": {
        "title": "Top view",
        "angle": ("a straight-down bird's-eye top view looking directly down "
                  "onto the scene from above"),
    },
    "side": {
        "title": "Side view",
        "angle": ("a true side elevation view looking horizontally at the "
                  "scene from one side"),
    },
    "isometric": {
        "title": "Isometric view",
        "angle": ("an isometric / three-quarter elevated view that shows the "
                  "depth and height of the scene"),
    },
}

# Menu order for Views ▸ Change View.
CHANGE_VIEW_ORDER = ("isometric", "top", "side")


def build_view_prompt(kind: str) -> str:
    """Identity-locked prompt: same objects, only the camera moves."""
    meta = VIEW_KINDS[kind]
    return (
        f"Using the reference photograph, generate {meta['angle']}.\n\n"
        "CRITICAL — identity lock (do not invent a new scene):\n"
        "- Reproduce the EXACT same objects, materials, colours, labels, "
        "relative positions, proportions, and background as the reference.\n"
        "- Do NOT invent, add, remove, restyle, swap, or replace any object.\n"
        "- Do NOT invent new furniture, tools, props, text, or decorations "
        "that are not already in the reference.\n"
        "- Only change the camera viewpoint; object identity must stay fixed.\n"
        "- Photorealistic single photograph — no collage, multi-panel grid, "
        "borders, captions, watermarks, or UI chrome."
    )


# ── disk cache for generated views ───────────────────────────────────────────
# Layout (images only — no sidecar JSON/TXT; index lives in this process):
#   .views_cache/<scene_id>/
#       original.png
#       side.png | top.png | isometric.png
#
# Fingerprints are kept in a module-level dict (rebuilt by scanning PNGs on
# first use). Original AND every generated angle are indexed so putting a
# generated view on the board still resolves back to the same scene.


# fingerprint → {"scene": scene_id, "role": role}; None until first load/scan.
_VIEWS_INDEX: dict | None = None

# PNG basenames (without .png) that belong in the fingerprint index.
_VIEWS_IMAGE_ROLES = ("original",) + tuple(VIEW_KINDS.keys())


def _views_cache_dir() -> str:
    os.makedirs(VIEWS_CACHE_DIR, exist_ok=True)
    return VIEWS_CACHE_DIR


def _strip_legacy_views_sidecars() -> None:
    """Remove old index.json / meta.json left by earlier versions (one-shot)."""
    root = VIEWS_CACHE_DIR
    if not os.path.isdir(root):
        return
    try:
        for name in ("index.json", "index.json.tmp"):
            path = os.path.join(root, name)
            if os.path.isfile(path):
                os.remove(path)
        for scene in os.listdir(root):
            folder = os.path.join(root, scene)
            if not os.path.isdir(folder):
                continue
            for junk in ("meta.json", "meta.json.tmp"):
                path = os.path.join(folder, junk)
                if os.path.isfile(path):
                    os.remove(path)
    except Exception:
        pass


def _rebuild_views_index() -> dict:
    """Scan .views_cache PNG folders and build fingerprint → scene/role."""
    index: dict = {}
    root = _views_cache_dir()
    try:
        scenes = os.listdir(root)
    except Exception:
        return index
    for scene in scenes:
        folder = os.path.join(root, scene)
        if not os.path.isdir(folder):
            continue
        for role in _VIEWS_IMAGE_ROLES:
            path = os.path.join(folder, f"{role}.png")
            if not os.path.isfile(path):
                continue
            try:
                img = cv2.imread(path)
            except Exception:
                img = None
            if img is None:
                continue
            fp = image_fingerprint(img)
            if fp:
                index[fp] = {"scene": scene, "role": role}
    return index


def _load_views_index() -> dict:
    """In-memory index only — never read/write a separate JSON file."""
    global _VIEWS_INDEX
    if _VIEWS_INDEX is None:
        _strip_legacy_views_sidecars()
        _VIEWS_INDEX = _rebuild_views_index()
    return _VIEWS_INDEX


def _register_view_fingerprint(fp: str, scene_id: str, role: str) -> None:
    if not fp or not scene_id or not role:
        return
    index = _load_views_index()
    index[fp] = {"scene": scene_id, "role": role}


def image_fingerprint(bgr) -> str:
    """Stable short hash of a board photo (downscaled JPEG bytes)."""
    if bgr is None:
        return ""
    h, w = bgr.shape[:2]
    m = max(h, w)
    if m > 256:
        scale = 256.0 / m
        small = cv2.resize(bgr, (max(1, int(w * scale)), max(1, int(h * scale))),
                           interpolation=cv2.INTER_AREA)
    else:
        small = bgr
    ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        # Fallback: raw shape + a few pixels — better than crashing.
        return hashlib.sha256(
            f"{bgr.shape}".encode() + bgr[:: max(1, h // 8),
                                          :: max(1, w // 8)].tobytes()
        ).hexdigest()[:16]
    return hashlib.sha256(buf.tobytes()).hexdigest()[:16]


def find_scene_id(bgr) -> str | None:
    """Return the scene id that owns this image (original or any saved view)."""
    fp = image_fingerprint(bgr)
    if not fp:
        return None
    entry = _load_views_index().get(fp)
    if not isinstance(entry, dict):
        return None
    scene = entry.get("scene")
    if not scene:
        return None
    folder = os.path.join(_views_cache_dir(), scene)
    return scene if os.path.isdir(folder) else None


def ensure_scene(bgr) -> str:
    """Find or create a scene for this board image; always saves original.png."""
    existing = find_scene_id(bgr)
    if existing:
        # Make sure original exists; if the hit was on a view file only, keep it.
        orig_path = os.path.join(_views_cache_dir(), existing, "original.png")
        if not os.path.isfile(orig_path):
            save_scene_image(existing, "original", bgr)
        return existing
    scene_id = image_fingerprint(bgr) or hashlib.sha256(
        str(time.time()).encode()).hexdigest()[:16]
    folder = os.path.join(_views_cache_dir(), scene_id)
    os.makedirs(folder, exist_ok=True)
    save_scene_image(scene_id, "original", bgr)
    return scene_id


def save_scene_image(scene_id: str, role: str, bgr) -> None:
    """Write original/side/top/isometric PNG and register its fingerprint in memory."""
    if bgr is None or not scene_id or not role:
        return
    folder = os.path.join(_views_cache_dir(), scene_id)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{role}.png")
    try:
        cv2.imwrite(path, bgr)
    except Exception:
        return
    fp = image_fingerprint(bgr)
    _register_view_fingerprint(fp, scene_id, role)


def load_scene_original(scene_id: str):
    path = os.path.join(_views_cache_dir(), scene_id, "original.png")
    if not os.path.isfile(path):
        return None
    return cv2.imread(path)


def load_scene_views(scene_id: str) -> dict:
    """Return {kind: bgr} for every angle already on disk for this scene."""
    out = {}
    if not scene_id:
        return out
    folder = os.path.join(_views_cache_dir(), scene_id)
    for kind in VIEW_KINDS:
        path = os.path.join(folder, f"{kind}.png")
        if not os.path.isfile(path):
            continue
        img = cv2.imread(path)
        if img is not None:
            out[kind] = img
    return out


def load_scene_view(scene_id: str, kind: str):
    views = load_scene_views(scene_id)
    return views.get(kind)


def _prepare_view_source(bgr, max_side=IMAGE_MAX_SIDE):
    """Shrink huge board photos so the image API accepts them quickly."""
    if bgr is None:
        raise RuntimeError("No board image to generate views from.")
    h, w = bgr.shape[:2]
    m = max(h, w)
    if m <= max_side:
        return bgr
    scale = max_side / float(m)
    return cv2.resize(bgr, (max(1, int(w * scale)), max(1, int(h * scale))),
                      interpolation=cv2.INTER_AREA)


def _bgr_to_png_bytes(bgr) -> bytes:
    ok, buf = cv2.imencode(".png", bgr)
    if not ok:
        raise RuntimeError("Could not encode the board image.")
    return buf.tobytes()


def _bgr_to_qpixmap(bgr, max_w=320, max_h=220) -> QPixmap:
    if bgr is None:
        return QPixmap()
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    qi = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888).copy()
    pix = QPixmap.fromImage(qi)
    return pix.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def _format_views_error(err) -> str:
    """Turn OpenAI / transport failures into something the operator can act on."""
    text = str(err) or err.__class__.__name__
    low = text.lower()
    if ("401" in text or "invalid_api_key" in low or "incorrect api key" in low
            or "authentication" in low):
        return ("OpenAI rejected the API key. Update the hardcoded "
                "OPENAI_API_KEY constant near the top of A2.6-Sol.py.")
    if "429" in text or "rate" in low:
        return "OpenAI rate limit hit — wait a moment and try Generate again."
    if "timeout" in low or "timed out" in low:
        return "ChatGPT Image timed out. Try again (views can take ~1 min each)."
    # Prefer the short API message when present.
    if len(text) > 320:
        text = text[:317] + "…"
    return text


class ViewsWorker(QThread):
    """Fill missing view angles via gpt-image-1 (skips anything already provided)."""

    progress    = Signal(str)
    view_ready  = Signal(str, object)   # kind, bgr ndarray
    view_failed = Signal(str, str)      # kind, short error
    finished_ok = Signal(str)           # detected source kind (or "other")
    failed      = Signal(str)

    def __init__(self, bgr, kinds=None, parent=None):
        super().__init__(parent)
        self._bgr = bgr
        # None → generate whatever is missing after detection; list → only those.
        self._kinds = list(kinds) if kinds is not None else None

    def run(self):
        try:
            if self._bgr is None:
                raise RuntimeError("No source image for view generation.")

            # Nothing left to do — caller already has every requested angle.
            if self._kinds is not None and not self._kinds:
                self.progress.emit("All requested views are already saved.")
                self.finished_ok.emit("other")
                return

            api_key = resolve_openai_api_key()
            if not api_key or not api_key.startswith("sk-"):
                raise RuntimeError(
                    "No OpenAI API key found. Set the hardcoded "
                    "OPENAI_API_KEY constant near the top of A2.6-Sol.py.")
            client = OpenAI(api_key=api_key, timeout=IMAGE_TIMEOUT_S,
                            max_retries=0)

            self.progress.emit("Detecting current viewpoint\u2026")
            detected = self._detect_view(client)

            if self._kinds is not None:
                needed = [k for k in self._kinds if k in VIEW_KINDS]
            elif detected in VIEW_KINDS:
                needed = [k for k in ("side", "isometric", "top")
                          if k != detected]
            else:
                needed = ["side", "isometric", "top"]

            # If the reference photo already IS one of the missing angles,
            # reuse it instead of spending an API call.
            if detected in needed:
                self.view_ready.emit(detected, self._bgr.copy())
                needed = [k for k in needed if k != detected]
                self.progress.emit(
                    f"Source looks like {VIEW_KINDS[detected]['title']} "
                    f"\u2014 saved without regenerating.")

            if not needed:
                self.progress.emit("Nothing left to generate.")
                self.finished_ok.emit(
                    detected if detected in VIEW_KINDS else "other")
                return

            self.progress.emit(
                f"Generating {len(needed)} missing view"
                f"{'s' if len(needed) != 1 else ''}\u2026")

            src = _prepare_view_source(self._bgr)
            png = _bgr_to_png_bytes(src)
            errors = []
            for i, kind in enumerate(needed, 1):
                title = VIEW_KINDS[kind]["title"]
                self.progress.emit(
                    f"Generating {title} ({i}/{len(needed)}) with "
                    f"ChatGPT Image \u2014 often 30\u201390s\u2026")
                try:
                    out = self._edit_view(client, png, kind)
                    self.view_ready.emit(kind, out)
                except Exception as one_err:
                    # Keep going so one failed angle does not wipe the rest.
                    why = _format_views_error(one_err)
                    errors.append(f"{title}: {why}")
                    self.view_failed.emit(kind, why)
                    self.progress.emit(f"{title} failed \u2014 continuing\u2026")

            if errors and len(errors) == len(needed):
                raise RuntimeError("All views failed.\n" + "\n".join(errors))
            if errors:
                self.progress.emit(
                    "Finished with some failures: " + " | ".join(errors))
            self.finished_ok.emit(
                detected if detected in VIEW_KINDS else "other")
        except Exception as err:
            self.failed.emit(_format_views_error(err))

    def _detect_view(self, client) -> str:
        """Classify the board image as top / side / isometric / other."""
        # Use a downscaled frame so detection stays fast and cheap.
        small = _prepare_view_source(self._bgr, max_side=768)
        b64 = encode_jpeg_b64(small, quality=80)
        if not b64:
            return "other"
        prompt = (
            "Classify the camera viewpoint of this scene photo. "
            "Reply with exactly one word from this list and nothing else:\n"
            "top\nside\nisometric\nother\n\n"
            "top = bird's-eye / straight-down looking at a surface from above\n"
            "side = horizontal side elevation of the scene\n"
            "isometric = 3/4 elevated angle showing depth and height\n"
            "other = anything else (front, angled, unclear)"
        )
        try:
            text = call_model(
                client,
                model=VISION_MODEL,
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{b64}",
                        "detail": "low"}},
                ]}],
                max_tokens=16,
                stage="View detect",
            )
        except Exception:
            return "other"
        word = (text or "").strip().lower().split()
        if not word:
            return "other"
        token = word[0].strip(".,:;!\"'")
        return token if token in VIEW_KINDS else "other"

    def _edit_view(self, client, png_bytes: bytes, kind: str):
        """Call ChatGPT Image (gpt-image-1) with the board photo as reference.

        The installed openai SDK rejects input_fidelity as a named kwarg, so
        high fidelity is requested through extra_body when the API supports it.
        The image is passed as a named multipart file tuple — a bare BytesIO
        without a filename is unreliable across SDK versions.
        """
        kwargs = dict(
            model=IMAGE_MODEL,
            image=("source.png", png_bytes, "image/png"),
            prompt=build_view_prompt(kind),
            size="1024x1024",
            quality=IMAGE_QUALITY,
        )
        try:
            result = client.images.edit(
                **kwargs, extra_body={"input_fidelity": "high"})
        except Exception as first:
            # Retry without extra_body if that field is what the server rejected.
            if "input_fidelity" in str(first).lower():
                result = client.images.edit(**kwargs)
            else:
                raise

        if not getattr(result, "data", None):
            raise RuntimeError(
                f"ChatGPT Image returned an empty response for "
                f"{VIEW_KINDS[kind]['title']}.")
        item = result.data[0]
        raw = None
        b64 = getattr(item, "b64_json", None)
        if b64 is None and isinstance(item, dict):
            b64 = item.get("b64_json")
        url = getattr(item, "url", None)
        if url is None and isinstance(item, dict):
            url = item.get("url")
        if b64:
            raw = base64.b64decode(b64)
        elif url:
            import urllib.request
            with urllib.request.urlopen(url, timeout=90) as resp:
                raw = resp.read()
        if not raw:
            raise RuntimeError(
                f"ChatGPT Image returned no pixels for "
                f"{VIEW_KINDS[kind]['title']}.")
        arr = np.frombuffer(raw, dtype=np.uint8)
        bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if bgr is None:
            raise RuntimeError(
                f"Could not decode the {VIEW_KINDS[kind]['title']} image.")
        return bgr


class ViewCard(QFrame):
    """One selectable thumbnail in the views panel."""

    clicked = Signal(str)   # key: "original" or a VIEW_KINDS key

    def __init__(self, key: str, title: str, parent=None):
        super().__init__(parent)
        self.key = key
        self._title = title
        self._bgr = None
        self._selected = False
        self._placeholder = "Not generated yet"
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(240)
        self._apply_style(False)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(6)

        self._lbl_title = QLabel(title)
        self._lbl_title.setFont(QFont(UI_FONT_B, 10))
        self._lbl_title.setStyleSheet(
            f"color:{C_TEXT};background:transparent;border:none;")
        self._lbl_title.setAlignment(Qt.AlignCenter)

        self._img = QLabel()
        self._img.setAlignment(Qt.AlignCenter)
        self._img.setMinimumHeight(160)
        self._img.setStyleSheet(
            f"background:#ffffff;border:1px solid {C_BORDER};border-radius:8px;"
            f"color:{C_TEXT_DIM};")
        self._img.setText(self._placeholder)

        self._hint = QLabel("")
        self._hint.setFont(QFont(UI_FONT, 8))
        self._hint.setAlignment(Qt.AlignCenter)
        self._hint.setStyleSheet(
            f"color:{C_TEXT_DIM};background:transparent;border:none;")

        lay.addWidget(self._lbl_title)
        lay.addWidget(self._img, 1)
        lay.addWidget(self._hint)

    def _apply_style(self, selected: bool):
        border = C_VIOLET if selected else C_BORDER
        bg = "#f3e8ff" if selected else "#ffffff"
        width = 2 if selected else 1
        self.setStyleSheet(f"""
            ViewCard{{
                background:{bg};
                border:{width}px solid {border};
                border-radius:12px;
            }}
        """)

    def set_selected(self, on: bool):
        self._selected = on
        self._apply_style(on)
        self._hint.setText("Selected \u2014 click Load to use on the board"
                           if on and self._bgr is not None else "")

    def set_image(self, bgr, note: str = ""):
        self._bgr = None if bgr is None else bgr.copy()
        if bgr is None:
            self._img.setPixmap(QPixmap())
            self._img.setText(self._placeholder)
        else:
            self._img.setText("")
            self._img.setPixmap(_bgr_to_qpixmap(bgr, 300, 170))
        if note:
            self._hint.setText(note)

    def set_busy(self, text: str = "Generating\u2026"):
        self._bgr = None
        self._img.setPixmap(QPixmap())
        self._img.setText(text)

    def set_error(self, text: str):
        self._bgr = None
        self._img.setPixmap(QPixmap())
        self._img.setText(text)

    def bgr(self):
        return None if self._bgr is None else self._bgr.copy()

    def has_image(self) -> bool:
        return self._bgr is not None

    def mousePressEvent(self, ev):
        if self._bgr is not None:
            self.clicked.emit(self.key)
        super().mousePressEvent(ev)


class ViewsPopup(QWidget):
    """Views \u25b8 Generate all 3 views \u2014 ChatGPT Image panel over the board.

    Child of the main window (not a separate window) so full-screen on macOS
    still shows it. Uses gpt-image-1 with the board photo as reference so the
    alternate angles keep the same objects.
    """

    INSET = 0.05

    def __init__(self, parent, cam_panel):
        super().__init__(parent)
        self._cam = cam_panel
        self._worker = None
        self._source_bgr = None
        self._scene_id = None
        self._selected_key = None
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_NoMousePropagation, True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setStyleSheet("background:rgba(15,23,42,0.42);")

        shell = QVBoxLayout(self)
        shell.setContentsMargins(0, 0, 0, 0)

        self._card = card = QFrame()
        card.setStyleSheet(f"""
            QFrame#viewsCard{{background:{C_BG};border:1px solid {C_BORDER};
                border-radius:16px;}}
        """)
        card.setObjectName("viewsCard")
        shell.addWidget(card)

        root = QVBoxLayout(card)
        root.setContentsMargins(16, 12, 16, 14)
        root.setSpacing(10)

        # ── title bar ────────────────────────────────────────────────────────
        bar = QHBoxLayout(); bar.setSpacing(8)
        title = QLabel(VIEWS_TITLE)
        title.setFont(QFont(UI_FONT_B, 12))
        title.setStyleSheet(
            f"color:{C_TEXT};background:transparent;border:none;")
        bar.addWidget(title); bar.addStretch(1)

        def flat(text, width=None, primary=False):
            b = QPushButton(text)
            b.setFixedHeight(30)
            if width:
                b.setFixedWidth(width)
            b.setCursor(Qt.PointingHandCursor)
            if primary:
                b.setStyleSheet(f"""
                    QPushButton{{background:{C_VIOLET};color:#ffffff;border:none;
                        border-radius:8px;font-family:'{UI_FONT}';font-weight:700;
                        font-size:11px;padding:0 14px;}}
                    QPushButton:hover{{background:#6d28d9;}}
                    QPushButton:disabled{{background:#c4b5fd;color:#f5f3ff;}}
                """)
            else:
                b.setStyleSheet(f"""
                    QPushButton{{background:#ffffff;color:{C_TEXT};
                        border:1px solid {C_BORDER};border-radius:8px;
                        font-family:'{UI_FONT}';font-weight:700;font-size:11px;
                        padding:0 12px;}}
                    QPushButton:hover{{background:#e8f0ff;color:{C_BLUE};}}
                    QPushButton:disabled{{color:{C_TEXT_DIM};background:#f8fafc;}}
                """)
            return b

        self._gen_btn = flat("Generate missing", primary=True)
        self._gen_btn.clicked.connect(self._start_generate)
        bar.addWidget(self._gen_btn)

        close = flat("\u2715", 30)
        close.clicked.connect(self.hide)
        bar.addWidget(close)
        root.addLayout(bar)

        sub = QLabel(
            "Saved views for this image load automatically. Generate only "
            "fills gaps (side / isometric / top) \u2014 same objects only. "
            "Click a view, then Load to put it on the board.")
        sub.setWordWrap(True)
        sub.setFont(QFont(UI_FONT, 9))
        sub.setStyleSheet(
            f"color:{C_TEXT_DIM};background:transparent;border:none;")
        root.addWidget(sub)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setFont(QFont(UI_FONT, 9))
        self._status.setStyleSheet(
            f"color:{C_TEXT_DIM};background:transparent;border:none;")
        root.addWidget(self._status)

        # ── cards grid ───────────────────────────────────────────────────────
        grid = QGridLayout(); grid.setSpacing(10)
        self._cards = {}
        specs = [
            ("original",  "Original",       0, 0),
            ("side",      "Side view",      0, 1),
            ("isometric", "Isometric view", 1, 0),
            ("top",       "Top view",       1, 1),
        ]
        for key, title, r, c in specs:
            card_w = ViewCard(key, title)
            card_w.clicked.connect(self._on_card_clicked)
            self._cards[key] = card_w
            grid.addWidget(card_w, r, c)
        root.addLayout(grid, 1)

        # ── footer ───────────────────────────────────────────────────────────
        foot = QHBoxLayout(); foot.setSpacing(8)
        self._sel_lbl = QLabel("No view selected")
        self._sel_lbl.setFont(QFont(UI_FONT, 9))
        self._sel_lbl.setStyleSheet(
            f"color:{C_TEXT_DIM};background:transparent;border:none;")
        foot.addWidget(self._sel_lbl, 1)

        self._load_btn = flat("Load selected view", primary=True)
        self._load_btn.setEnabled(False)
        self._load_btn.clicked.connect(self._load_selected)
        foot.addWidget(self._load_btn)
        root.addLayout(foot)

    # ── open / layout ────────────────────────────────────────────────────────
    def fit_to_parent(self):
        p = self.parentWidget()
        if p is None:
            return
        m = int(min(p.width(), p.height()) * self.INSET)
        self.setGeometry(p.rect())
        self.layout().setContentsMargins(m, m, m, m)

    def present(self):
        self.fit_to_parent()
        self._prime_source()
        self.show()
        self.raise_()
        self.setFocus(Qt.OtherFocusReason)

    def _missing_kinds(self):
        return [k for k in ("side", "isometric", "top")
                if not self._cards[k].has_image()]

    def _prime_source(self):
        """Pull the board image, resolve its scene, and load any saved views."""
        bgr = getattr(self._cam, "_raw_image", None)
        if bgr is None:
            self._source_bgr = None
            self._scene_id = None
            self._cards["original"].set_image(None)
            self._cards["original"].set_error("No image on the board")
            for key in ("side", "isometric", "top"):
                self._cards[key].set_image(None)
            self._selected_key = None
            self._load_btn.setEnabled(False)
            self._sel_lbl.setText("No view selected")
            self._gen_btn.setEnabled(False)
            self._status.setText(
                "Import or capture an image first, then generate views.")
            self._status.setStyleSheet(
                f"color:{C_AMBER};background:transparent;border:none;")
            return

        busy = self._worker is not None and self._worker.isRunning()

        # Resolve scene from the board photo (works for original OR a loaded view).
        scene_id = find_scene_id(bgr)
        if scene_id is None and not busy:
            # Brand-new image — treat current board as the scene original.
            scene_id = ensure_scene(bgr)

        self._scene_id = scene_id
        original = load_scene_original(scene_id) if scene_id else None
        if original is None:
            original = bgr
        self._source_bgr = original.copy()
        self._cards["original"].set_image(
            self._source_bgr, "Scene original (saved)")

        saved = load_scene_views(scene_id) if scene_id else {}
        if not busy:
            for key in ("side", "isometric", "top"):
                if key in saved:
                    self._cards[key].set_image(saved[key], "Saved \u2014 click to select")
                else:
                    self._cards[key].set_image(None)
            self._selected_key = None
            for c in self._cards.values():
                c.set_selected(False)
            self._load_btn.setEnabled(False)
            self._sel_lbl.setText("No view selected")

        missing = self._missing_kinds()
        self._gen_btn.setEnabled(not busy)
        n_saved = 3 - len(missing)
        if n_saved == 3:
            self._status.setText(
                "All 3 views are saved for this image \u2014 nothing to regenerate. "
                "Click a view and Load, or use Views \u25b8 Change View.")
            self._status.setStyleSheet(
                f"color:{C_GREEN};background:transparent;border:none;")
        elif n_saved > 0:
            self._status.setText(
                f"Loaded {n_saved} saved view{'s' if n_saved != 1 else ''}. "
                f"Generate missing will create only: "
                + ", ".join(VIEW_KINDS[k]["title"] for k in missing) + ".")
            self._status.setStyleSheet(
                f"color:{C_TEXT_DIM};background:transparent;border:none;")
        else:
            self._status.setText(
                "No saved views yet \u2014 click Generate missing to create "
                "side, isometric, and top.")
            self._status.setStyleSheet(
                f"color:{C_TEXT_DIM};background:transparent;border:none;")

    # ── generation ───────────────────────────────────────────────────────────
    def _start_generate(self):
        if self._source_bgr is None:
            self._prime_source()
        if self._source_bgr is None:
            return
        if self._worker is not None and self._worker.isRunning():
            return

        # Re-load disk state so we never regenerate what is already saved.
        if self._scene_id is None:
            self._scene_id = ensure_scene(self._source_bgr)
        saved = load_scene_views(self._scene_id)
        for key, img in saved.items():
            self._cards[key].set_image(img, "Saved \u2014 click to select")

        missing = self._missing_kinds()
        if not missing:
            self._status.setText(
                "All 3 views are already saved \u2014 nothing to generate.")
            self._status.setStyleSheet(
                f"color:{C_GREEN};background:transparent;border:none;")
            return

        for key in ("side", "isometric", "top"):
            self._cards[key].set_selected(False)
            if key in missing:
                self._cards[key].set_busy("Waiting\u2026")
        self._selected_key = None
        self._load_btn.setEnabled(False)
        self._sel_lbl.setText("No view selected")
        self._gen_btn.setEnabled(False)
        self._status.setText(
            "Generating only missing views: "
            + ", ".join(VIEW_KINDS[k]["title"] for k in missing) + "\u2026")
        self._status.setStyleSheet(
            f"color:{C_VIOLET};background:transparent;border:none;")

        self._worker = ViewsWorker(self._source_bgr, kinds=missing, parent=self)
        self._worker.progress.connect(self._on_progress)
        self._worker.view_ready.connect(self._on_view_ready)
        self._worker.view_failed.connect(self._on_view_failed)
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_progress(self, text: str):
        self._status.setText(text)
        self._status.setStyleSheet(
            f"color:{C_VIOLET};background:transparent;border:none;")
        # Mark the view currently cooking, if we can tell from the message.
        low = text.lower()
        for key, meta in VIEW_KINDS.items():
            if meta["title"].lower() in low and "generating" in low:
                if not self._cards[key].has_image():
                    self._cards[key].set_busy("Generating\u2026")

    def _on_view_ready(self, kind: str, bgr):
        card = self._cards.get(kind)
        if card is None:
            return
        # Persist so reopening the panel (or Change View) never re-pays the API.
        if self._scene_id and bgr is not None:
            save_scene_image(self._scene_id, kind, bgr)
        note = "Saved (from original)" if (
            self._source_bgr is not None
            and bgr is not None
            and bgr.shape == self._source_bgr.shape
            and np.array_equal(bgr, self._source_bgr)
        ) else "Saved \u2014 click to select"
        card.set_image(bgr, note)

    def _on_view_failed(self, kind: str, why: str):
        card = self._cards.get(kind)
        if card is None:
            return
        short = (why.splitlines()[0] if why else "Failed")[:48]
        card.set_error(f"Failed\n{short}")

    def _on_finished(self, detected: str):
        self._gen_btn.setEnabled(True)
        ready = sum(1 for k in ("side", "isometric", "top")
                    if self._cards[k].has_image())
        if ready == 0:
            self._status.setText("No views were generated. Try Generate again.")
            self._status.setStyleSheet(
                f"color:{C_RED};background:transparent;border:none;")
            return
        if detected in VIEW_KINDS:
            label = VIEW_KINDS[detected]["title"]
            self._status.setText(
                f"Done ({ready} view{'s' if ready != 1 else ''}) \u2014 "
                f"source was {label}. Pick a view and click Load.")
        else:
            self._status.setText(
                f"Done ({ready} view{'s' if ready != 1 else ''}) \u2014 "
                "pick one and click Load.")
        self._status.setStyleSheet(
            f"color:{C_GREEN};background:transparent;border:none;")

    def _on_failed(self, err: str):
        self._gen_btn.setEnabled(True)
        self._status.setText(f"Could not generate views: {err}")
        self._status.setStyleSheet(
            f"color:{C_RED};background:transparent;border:none;")
        for key in ("side", "isometric", "top"):
            if not self._cards[key].has_image():
                self._cards[key].set_error("Failed")

    # ── selection / load ─────────────────────────────────────────────────────
    def _on_card_clicked(self, key: str):
        card = self._cards.get(key)
        if card is None or not card.has_image():
            return
        self._selected_key = key
        for k, c in self._cards.items():
            c.set_selected(k == key)
        title = ("Original" if key == "original"
                 else VIEW_KINDS.get(key, {}).get("title", key))
        self._sel_lbl.setText(f"Selected: {title}")
        self._load_btn.setEnabled(True)

    def _load_selected(self):
        key = self._selected_key
        if not key:
            return
        card = self._cards.get(key)
        if card is None:
            return
        bgr = card.bgr()
        if bgr is None:
            return
        title = ("Original" if key == "original"
                 else VIEW_KINDS.get(key, {}).get("title", key))
        if hasattr(self._cam, "load_bgr"):
            self._cam.load_bgr(bgr, label=title)
        else:
            # Fallback: write a temp file and use the file loader.
            tmp = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                f".views_load_{key}.png")
            cv2.imwrite(tmp, bgr)
            self._cam.load_image_file(tmp)
        self._status.setText(f"Loaded {title} onto the board.")
        self._status.setStyleSheet(
            f"color:{C_GREEN};background:transparent;border:none;")
        self.hide()

    def mousePressEvent(self, ev):
        # Clicking the dimmed backdrop dismisses, the way a modal sheet does.
        if not self._card.geometry().contains(ev.position().toPoint()):
            if self._worker is None or not self._worker.isRunning():
                self.hide()
            return
        super().mousePressEvent(ev)

    def hideEvent(self, ev):
        # Leave a running worker alone so a re-open can still receive results;
        # only clear selection chrome.
        super().hideEvent(ev)

# ─────────────────────────────────────────────────────────────────────────────
#  Examples
# ─────────────────────────────────────────────────────────────────────────────
EXAMPLES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "examples")

# Scene and task travel together: an example is only useful if the words match
# what is actually on the board. The image file lives beside this script so the
# set can be extended by dropping in a photo and adding a line here.
EXAMPLES = [
    {
        "file":  "Example 1.jpeg",
        "title": "Laundry room",
        "task":  "wash my clothes",
        "note":  "Pile on the floor, washer and detergent on the counter — "
                 "load, start, and let the cycle run.",
    },
    {
        "file":  "Example 2.png",
        "title": "Plates and soap",
        "task":  "apply soap to all the plates using bottle",
        "note":  "Three plates in a row and a squeeze bottle: the same action "
                 "repeated across every plate.",
    },
]


def example_path(entry) -> str:
    return os.path.join(EXAMPLES_DIR, entry["file"])


class ExampleCard(QFrame):
    """One example: its photo, its task, and a button that loads both."""

    load_requested = Signal(dict)
    changed        = Signal()

    THUMB_W, THUMB_H = 168, 104

    def __init__(self, entry: dict, parent=None):
        super().__init__(parent)
        self._entry = entry
        self.setStyleSheet(f"""
            QFrame{{background:rgba(255,255,255,0.78);
                border:1px solid {C_BORDER};border-radius:12px;}}
        """)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 10, 12, 10)
        lay.setSpacing(12)

        self._thumb = QLabel()
        self._thumb.setFixedSize(self.THUMB_W, self.THUMB_H)
        self._thumb.setAlignment(Qt.AlignCenter)
        self._thumb.setFont(QFont(UI_FONT, 8))
        lay.addWidget(self._thumb)

        col = QVBoxLayout(); col.setSpacing(3)
        title = QLabel(entry["title"])
        title.setFont(QFont(UI_FONT_B, 11))
        title.setStyleSheet(f"color:{C_TEXT};background:transparent;border:none;")
        task = QLabel(f"“{entry['task']}”")
        task.setWordWrap(True)
        task.setFont(QFont(MONO_FONT, 9))
        task.setStyleSheet(f"color:{C_VIOLET};background:transparent;border:none;")
        note = QLabel(entry.get("note", ""))
        note.setWordWrap(True)
        note.setFont(QFont(UI_FONT, 8))
        note.setStyleSheet(f"color:{C_TEXT_DIM};background:transparent;border:none;")
        col.addWidget(title); col.addWidget(task); col.addWidget(note)
        col.addStretch(1)

        row = QHBoxLayout(); row.setSpacing(6)
        self._load = QPushButton("Load example")
        self._load.setFixedHeight(28)
        self._load.setCursor(Qt.PointingHandCursor)
        self._load.setStyleSheet(f"""
            QPushButton{{background:{C_BLUE};color:#ffffff;border:none;
                border-radius:8px;font-family:'{UI_FONT}';font-weight:700;
                font-size:10px;padding:0 14px;}}
            QPushButton:hover{{background:#1d4ed8;}}
            QPushButton:disabled{{background:#c9d5e6;}}
        """)
        self._load.clicked.connect(lambda: self.load_requested.emit(self._entry))
        self._locate = QPushButton("Locate image…")
        self._locate.setFixedHeight(28)
        self._locate.setCursor(Qt.PointingHandCursor)
        self._locate.setStyleSheet(f"""
            QPushButton{{background:#ffffff;color:{C_TEXT};
                border:1px solid {C_BORDER};border-radius:8px;
                font-family:'{UI_FONT}';font-weight:700;font-size:10px;padding:0 12px;}}
            QPushButton:hover{{background:#e8f0ff;color:{C_BLUE};}}
        """)
        self._locate.clicked.connect(self._pick_file)
        row.addWidget(self._load); row.addWidget(self._locate); row.addStretch(1)
        col.addLayout(row)
        lay.addLayout(col, 1)

        self.refresh()

    def refresh(self):
        path = example_path(self._entry)
        have = os.path.isfile(path)
        self._load.setEnabled(have)
        self._locate.setVisible(not have)
        if have:
            pix = QPixmap(path)
            if not pix.isNull():
                self._thumb.setPixmap(pix.scaled(self.THUMB_W, self.THUMB_H,
                                                 Qt.KeepAspectRatioByExpanding,
                                                 Qt.SmoothTransformation))
                self._thumb.setStyleSheet("border:none;border-radius:8px;")
                return
        self._thumb.setPixmap(QPixmap())
        self._thumb.setText("image not\nsaved yet")
        self._thumb.setStyleSheet(
            f"background:#e9eef7;color:{C_TEXT_DIM};"
            f"border:1px dashed {C_BORDER};border-radius:8px;")

    def _pick_file(self):
        """Adopt a photo into the examples folder under its canonical name.

        The tasks ship with the app but the photos cannot, so the first time an
        example is used its image is copied in and stays put from then on.
        """
        downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        start = downloads if os.path.isdir(downloads) else os.path.expanduser("~")
        src, _ = QFileDialog.getOpenFileName(
            self, f"Choose the image for “{self._entry['title']}”", start,
            "Images (*.jpg *.jpeg *.png *.bmp *.tiff *.tif *.webp);;All Files (*)")
        if not src:
            return
        try:
            os.makedirs(EXAMPLES_DIR, exist_ok=True)
            shutil.copyfile(src, example_path(self._entry))
        except Exception as err:
            QMessageBox.warning(self, "Examples", f"Could not save it: {err}")
            return
        self.refresh()
        self.changed.emit()


class ExamplesDialog(QDialog):
    """A shelf of ready-made scenes: load the photo and its task in one click."""

    def __init__(self, cam_panel, sidebar, parent=None):
        super().__init__(parent)
        self._cam, self._sidebar = cam_panel, sidebar
        self.setWindowTitle("Examples")
        self.setMinimumSize(560, 480)
        self.setStyleSheet(f"QDialog{{background:{C_BG};}}")

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(10)

        title = QLabel("Examples")
        title.setFont(QFont(UI_FONT_B, 15))
        title.setStyleSheet(f"color:{C_TEXT};background:transparent;")
        root.addWidget(title)

        sub = QLabel("Loading one puts the photo on the board and its task in "
                     "the message box, ready to send.")
        sub.setWordWrap(True)
        sub.setFont(QFont(UI_FONT, 9))
        sub.setStyleSheet(f"color:{C_TEXT_DIM};background:transparent;")
        root.addWidget(sub)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        holder = QWidget(); holder.setStyleSheet("background:transparent;")
        body = QVBoxLayout(holder)
        body.setContentsMargins(0, 0, 6, 0)
        body.setSpacing(8)
        for entry in EXAMPLES:
            card = ExampleCard(entry)
            card.load_requested.connect(self._load)
            body.addWidget(card)
        body.addStretch(1)
        scroll.setWidget(holder)
        root.addWidget(scroll, 1)

        self._folder = QLabel(f"Images live in {EXAMPLES_DIR}")
        self._folder.setWordWrap(True)
        self._folder.setFont(QFont(UI_FONT, 8))
        self._folder.setStyleSheet(f"color:{C_TEXT_DIM};background:transparent;")
        root.addWidget(self._folder)

        close = QPushButton("Close")
        close.setFixedHeight(30); close.setCursor(Qt.PointingHandCursor)
        close.setStyleSheet(f"""
            QPushButton{{background:{C_BLUE};color:#ffffff;border:none;
                border-radius:8px;font-family:'{UI_FONT}';font-weight:700;
                font-size:10px;padding:0 18px;}}
            QPushButton:hover{{background:#1d4ed8;}}
        """)
        close.clicked.connect(self.accept)
        row = QHBoxLayout(); row.addStretch(1); row.addWidget(close)
        root.addLayout(row)

    def _load(self, entry: dict):
        # Task first: loading the image starts vision immediately, and vision
        # reads the box to know which furniture the operator means to move.
        self._sidebar.set_task_text(entry["task"], send_when_ready=True)
        if not self._cam.load_image_file(example_path(entry)):
            self._sidebar.set_task_text("")
            QMessageBox.warning(self, "Examples",
                                "That image could not be read — pick it again.")
            return
        self.accept()


class HardwareConnectDialog(QDialog):
    """Extensions ▸ Hardware Connect: choose the USB port, arm the link.

    The switch and the port are separate on purpose. Connecting proves the
    cable works without committing to driving the arm; the switch is what
    decides whether a generated plan actually leaves the app.
    """

    def __init__(self, link: SerialLink, parent=None):
        super().__init__(parent)
        self._link = link
        self.setWindowTitle("Hardware Connect")
        self.setModal(True)
        self.setMinimumWidth(440)
        self.setStyleSheet(f"QDialog{{background:{C_BG};}}")

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(12)

        title = QLabel("Hardware Connect")
        title.setFont(QFont(UI_FONT_B, 14))
        title.setStyleSheet(f"color:{C_TEXT};background:transparent;")
        root.addWidget(title)

        row = QHBoxLayout(); row.setSpacing(10)
        lab = QLabel("Send generated commands over USB")
        lab.setFont(QFont(UI_FONT, 10))
        lab.setStyleSheet(f"color:{C_TEXT};background:transparent;")
        self.switch = ToggleSwitch(link.enabled)
        self.switch.toggled.connect(self._on_switch)
        row.addWidget(lab); row.addStretch(1); row.addWidget(self.switch)
        root.addLayout(row)

        # ── port picker ───────────────────────────────────────────────────────
        pick = QHBoxLayout(); pick.setSpacing(8)
        self._ports = QComboBox()
        self._ports.setFixedHeight(30)
        self._ports.setFont(QFont(UI_FONT, 9))
        self._ports.setStyleSheet(f"""
            QComboBox{{background:#ffffff;color:{C_TEXT};
                border:1px solid {C_BORDER};border-radius:8px;padding:0 10px;}}
        """)
        self._baud = QComboBox()
        self._baud.setFixedHeight(30)
        self._baud.setFont(QFont(UI_FONT, 9))
        self._baud.setStyleSheet(self._ports.styleSheet())
        for b in SerialLink.BAUDS:
            self._baud.addItem(str(b), b)
        self._baud.setCurrentText(str(link.baud()))

        refresh = QPushButton("⟳")
        refresh.setFixedSize(30, 30)
        for b in (refresh,):
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(f"""
                QPushButton{{background:#ffffff;color:{C_TEXT};
                    border:1px solid {C_BORDER};border-radius:8px;font-size:12px;}}
                QPushButton:hover{{background:#e8f0ff;color:{C_BLUE};}}
            """)
        refresh.clicked.connect(self._reload_ports)

        self._conn_btn = QPushButton("Connect")
        self._conn_btn.setFixedHeight(30)
        self._conn_btn.setCursor(Qt.PointingHandCursor)
        self._conn_btn.clicked.connect(self._on_connect)

        pick.addWidget(self._ports, 1)
        pick.addWidget(self._baud)
        pick.addWidget(refresh)
        pick.addWidget(self._conn_btn)
        root.addLayout(pick)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setFont(QFont(UI_FONT, 9))
        root.addWidget(self._status)

        note = QLabel("The full command sequence is written to the port once, "
                      "as soon as the planner finishes generating it — one line "
                      "per command, exactly as shown in the plan.")
        note.setWordWrap(True)
        note.setFont(QFont(UI_FONT, 9))
        note.setStyleSheet(f"color:{C_TEXT_DIM};background:transparent;")
        root.addWidget(note)

        done = QPushButton("Done")
        done.setFixedHeight(30); done.setCursor(Qt.PointingHandCursor)
        done.setStyleSheet(f"""
            QPushButton{{background:{C_BLUE};color:#ffffff;border:none;
                border-radius:8px;font-family:'{UI_FONT}';font-weight:700;
                font-size:10px;padding:0 18px;}}
            QPushButton:hover{{background:#1d4ed8;}}
        """)
        done.clicked.connect(self.accept)
        br = QHBoxLayout(); br.addStretch(1); br.addWidget(done)
        root.addLayout(br)

        self._link.failed.connect(self._show_error)
        self._reload_ports()
        self._refresh_state()

    # ── ports ─────────────────────────────────────────────────────────────────
    def _reload_ports(self):
        keep = self._ports.currentData() or self._link.port_name()
        self._ports.clear()
        devices = list_serial_devices()
        for dev, desc in devices:
            self._ports.addItem(f"{desc}  ·  {dev}" if desc != dev else dev, dev)
        if keep:
            i = self._ports.findData(keep)
            if i >= 0:
                self._ports.setCurrentIndex(i)
        if not devices:
            self._ports.addItem("No serial devices found", None)

    def _on_connect(self):
        if self._link.is_open():
            self._link.close()
        else:
            dev = self._ports.currentData()
            if not dev:
                self._show_error("No serial device selected.")
                return
            self._link.open(dev, self._baud.currentData())
        self._refresh_state()

    def _on_switch(self, on: bool):
        self._link.enabled = on
        if on and not self._link.is_open():
            self._show_error("Switch is on, but no device is connected yet — "
                             "connect a port or nothing will be sent.")
        else:
            self._refresh_state()

    def _refresh_state(self):
        open_now = self._link.is_open()
        self._conn_btn.setText("Disconnect" if open_now else "Connect")
        self._conn_btn.setStyleSheet(f"""
            QPushButton{{background:{'#ffffff' if open_now else C_BLUE};
                color:{C_RED if open_now else '#ffffff'};
                border:{'1px solid ' + C_BORDER if open_now else 'none'};
                border-radius:8px;font-family:'{UI_FONT}';font-weight:700;
                font-size:10px;padding:0 16px;}}
        """)
        self._ports.setEnabled(not open_now)
        self._baud.setEnabled(not open_now)

        if pyserial is None:
            self._set_status(f"⚠️  pyserial not installed — {SERIAL_IMPORT_ERROR}", C_RED)
        elif open_now and self._link.enabled:
            self._set_status(f"● Armed — plans go to {self._link.port_name()} "
                             f"@ {self._link.baud()}", C_GREEN)
        elif open_now:
            self._set_status(f"● Connected to {self._link.port_name()} "
                             "— switch off, nothing is sent", C_AMBER)
        else:
            self._set_status("○ Not connected", C_TEXT_DIM)

    def _set_status(self, text: str, color):
        self._status.setText(text)
        self._status.setStyleSheet(f"color:{color};background:transparent;")

    def _show_error(self, message: str):
        self._set_status(f"⚠️  {message}", C_RED)


class CameraPanel(QWidget):
    runner_finished = Signal()

    # Reserved gutters so the A-T / 1-11 headers drawn outside the image rect
    # are never clipped against the widget edge.
    PAD_L, PAD_T, PAD_R, PAD_B = 26, 20, 10, 10

    def __init__(self, sidebar: AISidebar, parent=None):
        super().__init__(parent)
        self._sidebar   = sidebar
        self._raw_image = None
        self._cap       = None      # live USB camera, when one is connected
        self._cam_index = None
        self._cam_name  = ""
        self._cam_first = False     # first frame of a session triggers analysis
        self.setStyleSheet(f"background:{C_BG};")
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)

        # ── Top bar ───────────────────────────────────────────────────────────
        bar = QWidget(); bar.setFixedHeight(48)
        bar.setStyleSheet(f"""
            background:rgba(255,255,255,0.86);
            border-bottom:1px solid {C_BORDER};
        """)
        bl = QHBoxLayout(bar); bl.setContentsMargins(16, 0, 16, 0); bl.setSpacing(12)

        brand = QLabel("A2  PHYSICAL SIMULATOR  ·  HOS")
        brand.setFont(QFont(UI_FONT_B, 11))
        brand.setStyleSheet(f"color:{C_TEXT};background:transparent;letter-spacing:0.1em;")

        self._import_btn = QPushButton("📁  Import Image")
        self._import_btn.setFixedHeight(30)
        self._import_btn.setCursor(Qt.PointingHandCursor)
        self._import_btn.setStyleSheet(f"""
            QPushButton{{background:#ffffff;color:{C_TEXT};
                border:1px solid {C_BORDER};border-radius:8px;
                font-family:'{UI_FONT}';font-weight:700;font-size:10px;padding:0 14px;}}
            QPushButton:hover{{background:#e8f0ff;color:{C_BLUE};}}
        """)
        self._import_btn.clicked.connect(self._import_image)

        self._status = QLabel("● No image loaded")
        self._status.setFont(QFont(UI_FONT, 9))
        self._status.setStyleSheet(f"color:{C_TEXT_DIM};background:transparent;")

        hint = QLabel("F11 fullscreen  ·  Esc exit")
        hint.setFont(QFont(UI_FONT, 8))
        hint.setStyleSheet(f"color:{C_TEXT_DIM};background:transparent;")

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
            "Vision analysis starts automatically\n\n"
            "Any resolution · JPG · PNG · BMP · TIFF · WEBP")
        self._video.setFont(QFont(UI_FONT, 14))
        self._video.setStyleSheet(f"background:{C_BG};color:{C_TEXT_DIM};")
        self._overlay.set_image_rect(None)

        # ── Big invoke popup ──────────────────────────────────────────────────
        self._popup = QLabel(self)
        self._popup.setAlignment(Qt.AlignCenter)
        self._popup.setWordWrap(True)
        self._popup.setFont(QFont(UI_FONT_B, 18))
        self._popup.setStyleSheet(f"""
            QLabel {{
                background:rgba(255,255,255,0.96);
                color:{C_TEXT};
                border: 2px solid #c4b5fd;
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

        # ── Live camera ───────────────────────────────────────────────────────
        self._cam_timer = QTimer(self)
        self._cam_timer.timeout.connect(self._grab_frame)

    def _on_speed(self, mult: float):
        self._runner.set_speed(mult)
        self._overlay.set_speed(mult)

    # ── USB camera ────────────────────────────────────────────────────────────
    def choose_camera(self):
        """File ▸ Connect USB Camera — pick the device that feeds main vision."""
        dlg = USBCameraDialog(self._cam_index, self)
        if dlg.exec() != QDialog.Accepted:
            return
        if dlg.chosen_index is None:
            self.stop_camera()
        else:
            self.start_camera(dlg.chosen_index, dlg.chosen_name)

    def start_camera(self, index: int, name: str = ""):
        self.stop_camera()
        cap = cv2.VideoCapture(index)
        if not cap.isOpened():
            cap.release()
            QMessageBox.warning(self, "Camera",
                                f"Could not open {name or f'camera {index}'}. "
                                "It may be in use by another app.")
            return
        self._cap       = cap
        self._cam_index = index
        self._cam_name  = name or f"Camera {index}"
        self._cam_first = True
        self._overlay.set_bboxes([])
        self._status.setText(f"● {self._cam_name}  (live)")
        self._status.setStyleSheet("color:#86efac;background:transparent;")
        self._cam_timer.start(33)

    def stop_camera(self):
        self._cam_timer.stop()
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            self._status.setText("● Camera disconnected")
            self._status.setStyleSheet(f"color:{C_TEXT_DIM};background:transparent;")
        self._cam_index = None
        self._cam_name  = ""

    def is_camera_live(self) -> bool:
        return self._cap is not None

    def _grab_frame(self):
        if self._cap is None:
            return
        ok, frame = self._cap.read()
        if not ok or frame is None:
            return
        self._raw_image = frame
        self._show_image(frame)
        if self._cam_first:
            # Analyse once the feed is actually delivering, not at open time —
            # the first read after opening is often a black frame.
            self._cam_first = False
            self._sidebar.auto_analyse()

    # ── image import ──────────────────────────────────────────────────────────
    def _import_image(self):
        downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        start_dir = downloads if os.path.isdir(downloads) else os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Image", start_dir,
            "Images (*.jpg *.jpeg *.png *.bmp *.tiff *.tif *.webp);;All Files (*)")
        if not path:
            return
        self.load_image_file(path)

    def load_image_file(self, path: str) -> bool:
        """Put a file on the board. Shared by Import Image and the examples."""
        self.stop_camera()          # a still image replaces the live feed
        bgr = imread_any(path)
        if bgr is None:
            self._status.setText("⚠️  Could not read file")
            self._status.setStyleSheet("color:#fca5a5;background:transparent;")
            return False
        return self.load_bgr(bgr, label=os.path.basename(path))

    def load_bgr(self, bgr, label: str = "image") -> bool:
        """Put a BGR frame on the board (import, examples, or a generated view)."""
        if bgr is None:
            return False
        self.stop_camera()
        self._raw_image = bgr
        self._overlay.set_bboxes([])
        self._show_image(bgr)
        h, w = bgr.shape[:2]
        self._status.setText(f"● {label}  ({w}×{h})")
        self._status.setStyleSheet("color:#86efac;background:transparent;")
        self._sidebar.auto_analyse()
        return True

    def _show_image(self, bgr):
        rgb  = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        qi   = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888).copy()
        lw   = self._video.width()  or 1280
        lh   = self._video.height() or 720
        aw   = max(50, lw - self.PAD_L - self.PAD_R)
        ah   = max(50, lh - self.PAD_T - self.PAD_B)
        pix  = QPixmap.fromImage(qi).scaled(aw, ah, Qt.KeepAspectRatio,
                                            Qt.SmoothTransformation)
        ox = self.PAD_L + (aw - pix.width())  / 2.0
        oy = self.PAD_T + (ah - pix.height()) / 2.0
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
                background:{C_BORDER};}}
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

        self._serial = SerialLink(self)
        self._sidebar.set_serial(self._serial)
        self._build_menus()

        QShortcut(QKeySequence("F11"), self, activated=self._toggle_fullscreen)
        QShortcut(QKeySequence("Esc"), self, activated=self._leave_fullscreen)

        # Right ⌥ dictates and sends. It is watched application-wide rather
        # than as a QShortcut because a lone modifier never forms a sequence,
        # and left/right can only be told apart by their macOS key code.
        # Watched on the compose box, NOT on the application. An application
        # filter written in Python is marshalled a wrapper for every object of
        # every event in the process, and creating a wrapper sets a property,
        # which sends an event, which re-enters the filter — with QtWebEngine's
        # object churn that recursion overflows the stack and the app dies with
        # SIGSEGV the moment the browser opens. A modifier-only key press is
        # ignored by the text box and propagates up to keyPressEvent anyway, so
        # one narrow filter plus that override covers both focus cases.
        self._sidebar._task_input.installEventFilter(self)

    # ── menu bar ──────────────────────────────────────────────────────────────
    def _build_menus(self):
        # On macOS this becomes the system menu bar at the top of the screen.
        bar = self.menuBar()
        bar.setNativeMenuBar(True)

        # Held on self: a menu the Python side stops referencing can be
        # collected out from under a native menu bar.
        self._file_menu = file_menu = QMenu("File", self)
        bar.addMenu(file_menu)

        act_cam = QAction("Connect USB Camera…", self)
        act_cam.setShortcut(QKeySequence("Ctrl+Shift+C"))
        act_cam.triggered.connect(self._cam_panel.choose_camera)
        file_menu.addAction(act_cam)

        act_disc = QAction("Disconnect Camera", self)
        act_disc.triggered.connect(self._cam_panel.stop_camera)
        file_menu.addAction(act_disc)

        file_menu.addSeparator()

        act_img = QAction("Import Image…", self)
        act_img.setShortcut(QKeySequence.Open)
        act_img.triggered.connect(self._cam_panel._import_image)
        file_menu.addAction(act_img)

        self._ext_menu = ext_menu = QMenu("Extensions", self)
        bar.addMenu(ext_menu)
        self._act_hw = QAction("Hardware Connect…", self)
        self._act_hw.setCheckable(True)      # ticked while armed and connected
        self._act_hw.triggered.connect(self._open_hardware_connect)
        ext_menu.addAction(self._act_hw)

        self._view_menu = view_menu = QMenu("Views", self)
        bar.addMenu(view_menu)
        act_views = QAction(f"{VIEWS_TITLE}…", self)
        act_views.triggered.connect(self._open_views)
        view_menu.addAction(act_views)

        change_menu = QMenu("Change View", self)
        view_menu.addMenu(change_menu)
        self._change_view_menu = change_menu
        self._change_view_actions = {}
        for kind in CHANGE_VIEW_ORDER:
            title = VIEW_KINDS[kind]["title"].replace(" view", "")
            # Menu labels: Isometric / Top / Side
            act = QAction(title, self)
            act.triggered.connect(
                lambda _checked=False, k=kind: self._change_view(k))
            change_menu.addAction(act)
            self._change_view_actions[kind] = act

        self._ex_menu = ex_menu = QMenu("Examples", self)
        bar.addMenu(ex_menu)
        act_examples = QAction("Browse Examples…", self)
        act_examples.setShortcut(QKeySequence("Ctrl+E"))
        act_examples.triggered.connect(self._open_examples)
        ex_menu.addAction(act_examples)

        self._set_menu = set_menu = QMenu("Settings", self)
        bar.addMenu(set_menu)
        act_settings = QAction("Open Settings…", self)
        act_settings.setShortcut(QKeySequence("Ctrl+,"))
        act_settings.triggered.connect(self._open_settings)
        set_menu.addAction(act_settings)

    def _open_views(self):
        # Kept on self so generated views survive between openings rather than
        # being rebuilt every time the menu is clicked.
        try:
            if getattr(self, "_views", None) is None:
                self._views = ViewsPopup(self, self._cam_panel)
            self._views.present()
        except Exception as err:
            # Never fail silently — a menu item that does nothing when clicked
            # is the hardest kind of bug to report.
            self._views = None
            QMessageBox.warning(self, VIEWS_TITLE,
                                f"The panel could not open:\n\n{err}")

    def _change_view(self, kind: str):
        """Views ▸ Change View ▸ {Isometric|Top|Side} — swap the board angle.

        Uses a saved view when one exists for this scene; otherwise generates
        only that missing angle from the scene original, saves it, then loads.
        """
        if kind not in VIEW_KINDS:
            return
        bgr = getattr(self._cam_panel, "_raw_image", None)
        if bgr is None:
            QMessageBox.information(
                self, "Change View",
                "Load an image on the board first, then pick a view.")
            return

        worker = getattr(self, "_change_worker", None)
        if worker is not None and worker.isRunning():
            QMessageBox.information(
                self, "Change View",
                "Already generating a view \u2014 wait for it to finish.")
            return

        title = VIEW_KINDS[kind]["title"]
        scene_id = find_scene_id(bgr)
        if scene_id is None:
            scene_id = ensure_scene(bgr)
        original = load_scene_original(scene_id)
        if original is None:
            original = bgr
            save_scene_image(scene_id, "original", bgr)

        cached = load_scene_view(scene_id, kind)
        if cached is not None:
            self._cam_panel.load_bgr(cached, label=title)
            return

        # Need a one-shot generation for this angle only.
        self._change_scene_id = scene_id
        self._change_kind = kind
        try:
            self._cam_panel._status.setText(
                f"\u25cf Generating {title}\u2026")
            self._cam_panel._status.setStyleSheet(
                f"color:{C_VIOLET};background:transparent;")
        except Exception:
            pass

        self._change_worker = ViewsWorker(original, kinds=[kind], parent=self)
        self._change_worker.view_ready.connect(self._on_change_view_ready)
        self._change_worker.view_failed.connect(self._on_change_view_failed)
        self._change_worker.failed.connect(self._on_change_view_failed_all)
        self._change_worker.finished_ok.connect(self._on_change_view_finished)
        self._change_worker.start()

    def _on_change_view_ready(self, kind: str, img):
        scene_id = getattr(self, "_change_scene_id", None)
        if scene_id and img is not None:
            save_scene_image(scene_id, kind, img)
        if kind == getattr(self, "_change_kind", None) and img is not None:
            title = VIEW_KINDS[kind]["title"]
            self._cam_panel.load_bgr(img, label=title)

    def _on_change_view_failed(self, kind: str, why: str):
        if kind != getattr(self, "_change_kind", None):
            return
        QMessageBox.warning(
            self, "Change View",
            f"Could not generate {VIEW_KINDS.get(kind, {}).get('title', kind)}:"
            f"\n\n{why}")

    def _on_change_view_failed_all(self, err: str):
        QMessageBox.warning(self, "Change View",
                            f"Could not change view:\n\n{err}")
        try:
            self._cam_panel._status.setText("\u25cf View generation failed")
            self._cam_panel._status.setStyleSheet(
                "color:#fca5a5;background:transparent;")
        except Exception:
            pass

    def _on_change_view_finished(self, _detected: str):
        # Status is updated by load_bgr on success; clear the generating hint
        # only if we never loaded (e.g. empty needed list edge case).
        kind = getattr(self, "_change_kind", None)
        scene_id = getattr(self, "_change_scene_id", None)
        if kind and scene_id and load_scene_view(scene_id, kind) is None:
            try:
                self._cam_panel._status.setText(
                    "\u25cf No view was produced")
                self._cam_panel._status.setStyleSheet(
                    f"color:{C_AMBER};background:transparent;")
            except Exception:
                pass

    def _open_examples(self):
        ExamplesDialog(self._cam_panel, self._sidebar, self).exec()

    def _open_settings(self):
        SettingsDialog(self._sidebar, self).exec()

    def _open_hardware_connect(self):
        dlg = HardwareConnectDialog(self._serial, self)
        dlg.exec()
        self._serial.enabled = dlg.switch.isChecked()
        # A tick beside the menu item is the only at-a-glance sign that plans
        # are leaving the app, once the sheet is closed.
        self._act_hw.setChecked(self._serial.enabled and self._serial.is_open())

    def closeEvent(self, ev):
        self._cam_panel.stop_camera()
        self._sidebar.shutdown()
        self._serial.close()
        # Parentless, so nothing else would take it down with the board. It is
        # closed here and the pending deletions are then flushed: Chromium's
        # teardown runs through deleteLater, and if the process exits before
        # the event loop gets back to it, the render process is torn down from
        # under itself and the app dies on quit instead of exiting.
        # The popup is a child widget, so it goes down with the window.
        super().closeEvent(ev)

    # macOS virtual key code for the right Option key (left Option is 0x3A).
    RIGHT_OPTION_VK = 0x3D

    def _is_right_option(self, ev) -> bool:
        return (sys.platform == "darwin"
                and ev.type() == QEvent.KeyPress
                and ev.key() == Qt.Key_Alt
                and not ev.isAutoRepeat()
                and ev.nativeVirtualKey() == self.RIGHT_OPTION_VK)

    def eventFilter(self, obj, ev):
        if self._is_right_option(ev):
            self._sidebar.toggle_voice(auto_send=True)
            return True
        return super().eventFilter(obj, ev)

    def keyPressEvent(self, ev):
        """Right ⌥ when focus is anywhere but the compose box."""
        if self._is_right_option(ev):
            self._sidebar.toggle_voice(auto_send=True)
            return
        super().keyPressEvent(ev)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        views = getattr(self, "_views", None)
        if views is not None and views.isVisible():
            views.fit_to_parent()

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

    light = QPalette()
    light.setColor(QPalette.Window,        QColor(C_BG))
    light.setColor(QPalette.WindowText,    QColor(C_TEXT))
    light.setColor(QPalette.Base,          QColor(C_PANEL_2))
    light.setColor(QPalette.AlternateBase, QColor("#ffffff"))
    light.setColor(QPalette.Text,          QColor(C_TEXT))
    light.setColor(QPalette.Button,        QColor("#ffffff"))
    light.setColor(QPalette.ButtonText,    QColor(C_TEXT))
    light.setColor(QPalette.Highlight,     QColor(C_BLUE))
    light.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    light.setColor(QPalette.ToolTipBase,   QColor("#ffffff"))
    light.setColor(QPalette.ToolTipText,   QColor(C_TEXT))
    app.setPalette(light)

    win = MainWindow()
    win.showFullScreen()
    sys.exit(app.exec())

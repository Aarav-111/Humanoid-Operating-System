import sys
import math
import base64
import re
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout,
    QVBoxLayout, QLineEdit, QTextEdit, QPushButton, QLabel, QColorDialog, QToolBar,
    QMenu, QInputDialog)
from PySide6.QtCore import QTimer, Qt, QThread, Signal, QBuffer, QIODevice, QPoint, QPointF
from PySide6.QtGui import QPainter, QColor, QFont, QPen, QPolygonF, QBrush, QIcon, QPixmap, QCursor
from openai import OpenAI


class ChatWorker(QThread):
    response_received = Signal(str)

    def __init__(self, api_key, history, image_base64=None):
        super().__init__()
        self.client = OpenAI(api_key=api_key)
        self.history = history
        self.image_base64 = image_base64

    def run(self):
        try:
            messages = list(self.history)

            if self.image_base64:
                last_msg = messages[-1]
                if last_msg["role"] == "user":
                    text_content = last_msg["content"]
                    messages[-1] = {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": text_content},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{self.image_base64}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }

            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                max_tokens=500,
                temperature=0
            )
            reply = response.choices[0].message.content
            self.response_received.emit(reply)
        except Exception as e:
            self.response_received.emit(f"OpenAI Error: {str(e)}")


# ──────────────────────────────────────────────────────────────
#  Drawing helpers
# ──────────────────────────────────────────────────────────────

def draw_tshirt(qp: QPainter, cx: float, cy: float, w: float, h: float, color: QColor):
    """Draw a simple filled T-shirt silhouette centred on (cx, cy)."""
    qp.save()
    qp.translate(cx, cy)

    # Scale factor so the design fits within w×h
    sx, sy = w / 60.0, h / 60.0

    # Body rectangle
    body = QPolygonF([
        QPointF(-18 * sx, -10 * sy),
        QPointF( 18 * sx, -10 * sy),
        QPointF( 18 * sx,  28 * sy),
        QPointF(-18 * sx,  28 * sy),
    ])

    # Left sleeve
    left_sleeve = QPolygonF([
        QPointF(-18 * sx, -10 * sy),
        QPointF(-30 * sx, -24 * sy),
        QPointF(-22 * sx, -28 * sy),
        QPointF(-12 * sx,  -4 * sy),
    ])

    # Right sleeve
    right_sleeve = QPolygonF([
        QPointF( 18 * sx, -10 * sy),
        QPointF( 30 * sx, -24 * sy),
        QPointF( 22 * sx, -28 * sy),
        QPointF( 12 * sx,  -4 * sy),
    ])

    # Collar (small trapezoid)
    collar = QPolygonF([
        QPointF(-10 * sx, -10 * sy),
        QPointF( 10 * sx, -10 * sy),
        QPointF(  6 * sx, -18 * sy),
        QPointF( -6 * sx, -18 * sy),
    ])

    qp.setPen(Qt.NoPen)
    qp.setBrush(QBrush(color))
    for poly in (body, left_sleeve, right_sleeve):
        qp.drawPolygon(poly)

    # Collar in slightly darker shade
    darker = QColor(max(0, color.red() - 30), max(0, color.green() - 30), max(0, color.blue() - 30))
    qp.setBrush(QBrush(darker))
    qp.drawPolygon(collar)

    # Outline
    qp.setPen(QPen(QColor(200, 200, 200, 80), 1))
    qp.setBrush(Qt.NoBrush)
    for poly in (body, left_sleeve, right_sleeve, collar):
        qp.drawPolygon(poly)

    qp.restore()


# ──────────────────────────────────────────────────────────────
#  Custom drawn objects (polygon / circle)
# ──────────────────────────────────────────────────────────────

class CustomPolygonObj:
    _counter = 0

    def __init__(self, points: list[QPointF], color: QColor):
        CustomPolygonObj._counter += 1
        self.name = f"Shape {CustomPolygonObj._counter}"
        self.points = points          # list of QPointF (absolute canvas coords)
        self.color = color
        self.type = "custom_polygon"
        # For compatibility with drag logic we expose a mutable pos (centroid)
        self._update_centroid()

    def _update_centroid(self):
        if self.points:
            cx = sum(p.x() for p in self.points) / len(self.points)
            cy = sum(p.y() for p in self.points) / len(self.points)
            self.pos = [cx, cy]
        else:
            self.pos = [0, 0]

    # Translate all points by (dx, dy)
    def translate(self, dx, dy):
        self.points = [QPointF(p.x() + dx, p.y() + dy) for p in self.points]
        self._update_centroid()

    # Approximate bounding half-size for click detection
    @property
    def w(self):
        if len(self.points) < 2:
            return 20
        xs = [p.x() for p in self.points]
        return (max(xs) - min(xs)) / 2 + 10

    @property
    def h(self):
        if len(self.points) < 2:
            return 20
        ys = [p.y() for p in self.points]
        return (max(ys) - min(ys)) / 2 + 10

    def hit_test(self, px, py) -> bool:
        """Point-in-polygon using ray-casting."""
        poly = self.points
        n = len(poly)
        inside = False
        j = n - 1
        for i in range(n):
            xi, yi = poly[i].x(), poly[i].y()
            xj, yj = poly[j].x(), poly[j].y()
            if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi + 1e-12) + xi):
                inside = not inside
            j = i
        return inside


class CustomCircleObj:
    _counter = 0

    def __init__(self, cx: float, cy: float, radius: float, color: QColor):
        CustomCircleObj._counter += 1
        self.name = f"Circle {CustomCircleObj._counter}"
        self.pos = [cx, cy]
        self.radius = radius
        self.color = color
        self.type = "custom_circle"
        self.w = radius
        self.h = radius

    def hit_test(self, px, py) -> bool:
        return math.hypot(px - self.pos[0], py - self.pos[1]) <= self.radius


# ──────────────────────────────────────────────────────────────
#  Toolbar widget (top-left overlay)
# ──────────────────────────────────────────────────────────────

TOOL_NONE    = "none"
TOOL_POLYGON = "polygon"
TOOL_CIRCLE  = "circle"


class DrawingToolbar(QWidget):
    """Floating toolbar placed at the top-left of RobotSim."""

    polygonToolSelected = Signal()
    circleToolSelected  = Signal()
    cancelTool          = Signal()
    colorChanged        = Signal(QColor)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(44)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background: rgba(20,20,35,200); border-radius: 8px; border: 1px solid #555;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        lbl = QLabel("Draw:")
        lbl.setStyleSheet("color: #aaa; font-size: 12px;")
        layout.addWidget(lbl)

        self.btn_poly = QPushButton("⬡ Polygon")
        self.btn_poly.setCheckable(True)
        self.btn_poly.setFixedHeight(30)
        self.btn_poly.setStyleSheet(self._btn_style())
        self.btn_poly.clicked.connect(self._on_poly)
        layout.addWidget(self.btn_poly)

        self.btn_circle = QPushButton("◯ Circle")
        self.btn_circle.setCheckable(True)
        self.btn_circle.setFixedHeight(30)
        self.btn_circle.setStyleSheet(self._btn_style())
        self.btn_circle.clicked.connect(self._on_circle)
        layout.addWidget(self.btn_circle)

        self.btn_cancel = QPushButton("✕ Cancel")
        self.btn_cancel.setFixedHeight(30)
        self.btn_cancel.setStyleSheet(
            "QPushButton{background:#8B0000;color:white;border-radius:5px;padding:0 8px;font-size:12px;}"
            "QPushButton:hover{background:#b00000;}"
        )
        self.btn_cancel.clicked.connect(self._on_cancel)
        self.btn_cancel.setVisible(False)
        layout.addWidget(self.btn_cancel)

        # Colour picker swatch
        self.draw_color = QColor(255, 165, 0)
        self.btn_color = QPushButton()
        self.btn_color.setFixedSize(30, 30)
        self.btn_color.setToolTip("Pick drawing colour")
        self._refresh_color_btn()
        self.btn_color.clicked.connect(self._pick_color)
        layout.addWidget(self.btn_color)

        hint_lbl = QLabel("Hint: click=add point · dbl-click=finish polygon · drag=resize circle")
        hint_lbl.setStyleSheet("color:#555; font-size:10px;")
        layout.addWidget(hint_lbl)

    # ── helpers ──────────────────────────────────────────────
    @staticmethod
    def _btn_style():
        return (
            "QPushButton{background:#1e3a5f;color:white;border-radius:5px;padding:0 10px;font-size:12px;}"
            "QPushButton:hover{background:#2a5080;}"
            "QPushButton:checked{background:#007acc;border:2px solid #4da6ff;}"
        )

    def _refresh_color_btn(self):
        px = QPixmap(28, 28)
        px.fill(self.draw_color)
        self.btn_color.setIcon(QIcon(px))
        self.btn_color.setIconSize(px.size())
        self.btn_color.setStyleSheet(
            "QPushButton{background:#333;border-radius:5px;border:1px solid #888;}"
        )

    def _pick_color(self):
        c = QColorDialog.getColor(self.draw_color, self, "Choose Drawing Colour")
        if c.isValid():
            self.draw_color = c
            self._refresh_color_btn()
            self.colorChanged.emit(c)

    def _on_poly(self):
        self.btn_circle.setChecked(False)
        if self.btn_poly.isChecked():
            self.btn_cancel.setVisible(True)
            self.polygonToolSelected.emit()
        else:
            self.btn_cancel.setVisible(False)
            self.cancelTool.emit()

    def _on_circle(self):
        self.btn_poly.setChecked(False)
        if self.btn_circle.isChecked():
            self.btn_cancel.setVisible(True)
            self.circleToolSelected.emit()
        else:
            self.btn_cancel.setVisible(False)
            self.cancelTool.emit()

    def _on_cancel(self):
        self.btn_poly.setChecked(False)
        self.btn_circle.setChecked(False)
        self.btn_cancel.setVisible(False)
        self.cancelTool.emit()

    def reset(self):
        self.btn_poly.setChecked(False)
        self.btn_circle.setChecked(False)
        self.btn_cancel.setVisible(False)


# ──────────────────────────────────────────────────────────────
#  Main simulation widget
# ──────────────────────────────────────────────────────────────

class RobotSim(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumWidth(800)
        self.setMouseTracking(True)
        self.setContextMenuPolicy(Qt.PreventContextMenu)
        self.CELL_SIZE = 80
        self.MARGIN_X, self.MARGIN_Y = 100, 150
        self.COL_LABELS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
        self.ROW_LABELS = ['1', '2', '3', '4', '5']

        self.arm_visible = True

        self.bot_pos    = [self.MARGIN_X + 40, self.MARGIN_Y + 40]
        self.bot_target = list(self.bot_pos)
        self.brick_pos  = [self.MARGIN_X + 120, self.MARGIN_Y + 40]

        # ── extra objects (standard + T-shirts) ──────────────
        self.extra_objects = [
            {
                "name": "Grey Box",
                "pos": [self.MARGIN_X + 120, self.MARGIN_Y - 80],
                "color": QColor(100, 100, 100),
                "type": "rect",
                "w": 40, "h": 40
            },
            {
                "name": "Water Bottle",
                "pos": [self.MARGIN_X + 200, self.MARGIN_Y - 80],
                "color": QColor(100, 150, 255),
                "type": "bottle",
                "w": 30, "h": 50
            },
            # ── 2 White T-shirts ──────────────────────────────
            {
                "name": "White T-Shirt 1",
                "pos": [self.MARGIN_X + 300, self.MARGIN_Y - 80],
                "color": QColor(240, 240, 240),
                "type": "tshirt",
                "w": 50, "h": 55
            },
            {
                "name": "White T-Shirt 2",
                "pos": [self.MARGIN_X + 370, self.MARGIN_Y - 80],
                "color": QColor(240, 240, 240),
                "type": "tshirt",
                "w": 50, "h": 55
            },
            # ── 2 Blue T-shirts ───────────────────────────────
            {
                "name": "Blue T-Shirt 1",
                "pos": [self.MARGIN_X + 440, self.MARGIN_Y - 80],
                "color": QColor(30, 100, 200),
                "type": "tshirt",
                "w": 50, "h": 55
            },
            {
                "name": "Blue T-Shirt 2",
                "pos": [self.MARGIN_X + 510, self.MARGIN_Y - 80],
                "color": QColor(30, 100, 200),
                "type": "tshirt",
                "w": 50, "h": 55
            },
        ]

        # ── custom drawn objects ──────────────────────────────
        self.custom_objects: list = []   # CustomPolygonObj | CustomCircleObj

        # ── robot state ───────────────────────────────────────
        self.holding    = False
        self.held_extra = None
        self.speed      = 15

        # ── drag state ────────────────────────────────────────
        self.dragging_obj  = None
        self.drag_offset   = QPoint(0, 0)

        # ── drawing state ─────────────────────────────────────
        self.draw_tool      = TOOL_NONE   # TOOL_NONE / TOOL_POLYGON / TOOL_CIRCLE
        self.draw_color     = QColor(255, 165, 0)
        self.poly_points: list[QPointF] = []   # in-progress polygon vertices
        self.mouse_pos      = QPointF(0, 0)    # live cursor (for preview)

        self.circle_center  = None   # QPointF when placing circle
        self.circle_radius  = 0.0
        self.circle_dragging = False

        # ── drawing toolbar ───────────────────────────────────
        self.toolbar = DrawingToolbar(self)
        self.toolbar.move(10, 10)
        self.toolbar.polygonToolSelected.connect(self._activate_polygon_tool)
        self.toolbar.circleToolSelected.connect(self._activate_circle_tool)
        self.toolbar.cancelTool.connect(self._cancel_tool)
        self.toolbar.colorChanged.connect(self._set_draw_color)

        # ── physics timer ─────────────────────────────────────
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_physics)
        self.timer.start(16)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Keep toolbar at top-left and sized to its sizeHint width
        self.toolbar.setFixedWidth(min(self.width() - 20, 700))
        self.toolbar.move(10, 10)

    # ── tool activation ──────────────────────────────────────

    def _activate_polygon_tool(self):
        self.draw_tool   = TOOL_POLYGON
        self.poly_points = []
        self.setCursor(Qt.CrossCursor)

    def _activate_circle_tool(self):
        self.draw_tool     = TOOL_CIRCLE
        self.circle_center = None
        self.circle_radius = 0.0
        self.setCursor(Qt.CrossCursor)

    def _cancel_tool(self):
        self.draw_tool      = TOOL_NONE
        self.poly_points    = []
        self.circle_center  = None
        self.circle_dragging = False
        self.toolbar.reset()
        self.setCursor(Qt.ArrowCursor)
        self.update()

    def _set_draw_color(self, color: QColor):
        self.draw_color = color

    # ── grid ─────────────────────────────────────────────────

    def get_coords(self, col, row):
        try:
            c_idx = self.COL_LABELS.index(col.strip().upper())
            r_idx = 5 - int(row.strip())
            return (self.MARGIN_X + c_idx * self.CELL_SIZE + 40,
                    self.MARGIN_Y + r_idx * self.CELL_SIZE + 40)
        except Exception:
            return None

    # ── physics ───────────────────────────────────────────────

    def update_physics(self):
        if self.dragging_obj:
            return

        dx = self.bot_target[0] - self.bot_pos[0]
        dy = self.bot_target[1] - self.bot_pos[1]
        dist = math.hypot(dx, dy)
        if dist > self.speed:
            self.bot_pos[0] += (dx / dist) * self.speed
            self.bot_pos[1] += (dy / dist) * self.speed
        else:
            self.bot_pos = list(self.bot_target)

        if self.holding:
            if self.held_extra == "brick":
                self.brick_pos = list(self.bot_pos)
            elif isinstance(self.held_extra, dict):
                self.held_extra["pos"] = list(self.bot_pos)
            elif isinstance(self.held_extra, (CustomPolygonObj, CustomCircleObj)):
                dx2 = self.bot_pos[0] - self.held_extra.pos[0]
                dy2 = self.bot_pos[1] - self.held_extra.pos[1]
                if isinstance(self.held_extra, CustomPolygonObj):
                    self.held_extra.translate(dx2, dy2)
                else:
                    self.held_extra.pos = list(self.bot_pos)
        self.update()

    def is_at_target(self):
        return math.hypot(self.bot_target[0] - self.bot_pos[0],
                          self.bot_target[1] - self.bot_pos[1]) < 2

    # ── mouse events ─────────────────────────────────────────

    def mousePressEvent(self, event):
        p = event.position()
        px, py = p.x(), p.y()

        # ── polygon tool ──────────────────────────────────────
        if self.draw_tool == TOOL_POLYGON:
            if event.button() == Qt.LeftButton:
                self.poly_points.append(QPointF(px, py))
                self.update()
            return

        # ── circle tool ───────────────────────────────────────
        if self.draw_tool == TOOL_CIRCLE:
            if event.button() == Qt.LeftButton:
                if self.circle_center is None:
                    self.circle_center  = QPointF(px, py)
                    self.circle_radius  = 0.0
                    self.circle_dragging = True
                else:
                    # Second click: commit circle
                    self._commit_circle()
            return

        # ── right-click context menu for custom objects ───────
        if event.button() == Qt.RightButton:
            ip = event.position().toPoint()
            for obj in self.custom_objects:
                hit = False
                if isinstance(obj, CustomPolygonObj):
                    hit = obj.hit_test(ip.x(), ip.y())
                elif isinstance(obj, CustomCircleObj):
                    hit = obj.hit_test(ip.x(), ip.y())
                if hit:
                    self._show_custom_obj_menu(obj, event.globalPosition().toPoint())
                    return

        # ── drag logic ────────────────────────────────────────
        ip = event.position().toPoint()
        if math.hypot(ip.x() - self.bot_pos[0], ip.y() - self.bot_pos[1]) < 40:
            self.dragging_obj = "bot"
            self.drag_offset  = QPoint(ip.x() - int(self.bot_pos[0]),
                                       ip.y() - int(self.bot_pos[1]))
            return

        if abs(ip.x() - self.brick_pos[0]) < 25 and abs(ip.y() - self.brick_pos[1]) < 25:
            self.dragging_obj = "brick"
            self.drag_offset  = QPoint(ip.x() - int(self.brick_pos[0]),
                                       ip.y() - int(self.brick_pos[1]))
            return

        for obj in self.extra_objects:
            if abs(ip.x() - obj["pos"][0]) < obj["w"] / 2 + 10 and \
               abs(ip.y() - obj["pos"][1]) < obj["h"] / 2 + 10:
                self.dragging_obj = obj
                self.drag_offset  = QPoint(ip.x() - int(obj["pos"][0]),
                                           ip.y() - int(obj["pos"][1]))
                return

        # Custom objects drag
        for obj in self.custom_objects:
            if isinstance(obj, CustomPolygonObj):
                if obj.hit_test(ip.x(), ip.y()):
                    self.dragging_obj = obj
                    self.drag_offset  = QPoint(ip.x() - int(obj.pos[0]),
                                               ip.y() - int(obj.pos[1]))
                    return
            elif isinstance(obj, CustomCircleObj):
                if obj.hit_test(ip.x(), ip.y()):
                    self.dragging_obj = obj
                    self.drag_offset  = QPoint(ip.x() - int(obj.pos[0]),
                                               ip.y() - int(obj.pos[1]))
                    return

    def mouseDoubleClickEvent(self, event):
        # Finish polygon on double-click (double-click also fires mousePressEvent
        # so we already have the last point added; remove duplicate)
        if self.draw_tool == TOOL_POLYGON and event.button() == Qt.LeftButton:
            if len(self.poly_points) > 1:
                # Remove the extra point added by the second click of the double-click
                self.poly_points = self.poly_points[:-1]
            if len(self.poly_points) >= 3:
                self._commit_polygon()
            else:
                self.poly_points = []
                self.update()
            return

        # Circle: double-click also commits
        if self.draw_tool == TOOL_CIRCLE and self.circle_center is not None:
            self._commit_circle()

    def mouseMoveEvent(self, event):
        p = event.position()
        self.mouse_pos = QPointF(p.x(), p.y())

        # ── circle radius dragging ────────────────────────────
        if self.draw_tool == TOOL_CIRCLE and self.circle_center is not None and self.circle_dragging:
            self.circle_radius = math.hypot(p.x() - self.circle_center.x(),
                                            p.y() - self.circle_center.y())
            self.update()
            return

        # ── preview polygon ───────────────────────────────────
        if self.draw_tool == TOOL_POLYGON:
            self.update()
            return

        # ── drag objects ──────────────────────────────────────
        if self.dragging_obj:
            ip = event.position().toPoint()
            nx = ip.x() - self.drag_offset.x()
            ny = ip.y() - self.drag_offset.y()
            if self.dragging_obj == "bot":
                self.bot_pos    = [nx, ny]
                self.bot_target = list(self.bot_pos)
            elif self.dragging_obj == "brick":
                self.brick_pos = [nx, ny]
            elif isinstance(self.dragging_obj, dict):
                self.dragging_obj["pos"] = [nx, ny]
            elif isinstance(self.dragging_obj, CustomPolygonObj):
                dx = nx - self.dragging_obj.pos[0]
                dy = ny - self.dragging_obj.pos[1]
                self.dragging_obj.translate(dx, dy)
            elif isinstance(self.dragging_obj, CustomCircleObj):
                self.dragging_obj.pos = [nx, ny]
            self.update()

    def mouseReleaseEvent(self, event):
        if self.draw_tool == TOOL_CIRCLE and self.circle_dragging:
            self.circle_dragging = False
            # Commit on release if radius is meaningful
            if self.circle_center is not None and self.circle_radius > 5:
                self._commit_circle()
            return

        self.dragging_obj = None

    # ── commit drawing ────────────────────────────────────────

    def _commit_polygon(self):
        obj = CustomPolygonObj(list(self.poly_points), QColor(self.draw_color))
        self.custom_objects.append(obj)
        self.poly_points = []
        self._cancel_tool()

    def _commit_circle(self):
        if self.circle_center and self.circle_radius > 5:
            obj = CustomCircleObj(
                self.circle_center.x(), self.circle_center.y(),
                self.circle_radius, QColor(self.draw_color)
            )
            self.custom_objects.append(obj)
        self.circle_center   = None
        self.circle_radius   = 0.0
        self.circle_dragging = False
        self._cancel_tool()

    # ── context menu for custom objects ──────────────────────

    def _show_custom_obj_menu(self, obj, global_pos):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1a1a2e;
                color: #e0e0e0;
                border: 1px solid #444;
                border-radius: 6px;
                padding: 4px;
                font-size: 13px;
            }
            QMenu::item {
                padding: 8px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #007acc;
                color: white;
            }
            QMenu::separator {
                height: 1px;
                background: #444;
                margin: 3px 8px;
            }
        """)

        title_action = menu.addAction(f"  {obj.name}")
        title_action.setEnabled(False)
        menu.addSeparator()

        rename_action = menu.addAction("✏️  Rename")
        delete_action = menu.addAction("🗑️  Delete")
        delete_action.setProperty("danger", True)

        action = menu.exec(global_pos)

        if action == rename_action:
            new_name, ok = QInputDialog.getText(
                self, "Rename Object", "Enter new name:",
                text=obj.name
            )
            if ok and new_name.strip():
                obj.name = new_name.strip()
                self.update()

        elif action == delete_action:
            if obj in self.custom_objects:
                self.custom_objects.remove(obj)
                self.update()

    # ── paint ─────────────────────────────────────────────────

    def paintEvent(self, event):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        qp.fillRect(self.rect(), QColor(10, 10, 20))

        # Staging area border
        qp.setPen(QColor(60, 60, 80))
        qp.drawRect(self.MARGIN_X, self.MARGIN_Y - 110, 540, 90)
        qp.setPen(QColor(150, 150, 150))
        qp.setFont(QFont("Arial", 10))
        qp.drawText(self.MARGIN_X + 10, self.MARGIN_Y - 90, "STAGING AREA / SHELF")

        # Grid
        for c in range(8):
            for r in range(5):
                x = self.MARGIN_X + c * self.CELL_SIZE
                y = self.MARGIN_Y + r * self.CELL_SIZE
                qp.setPen(QColor(40, 45, 60))
                qp.drawRect(x, y, self.CELL_SIZE, self.CELL_SIZE)
                qp.setPen(QColor(60, 60, 80))
                cell_label = f"{self.COL_LABELS[c]}{self.ROW_LABELS[4 - r]}"
                qp.drawText(x + 5, y + 20, cell_label)

        # Axis labels
        qp.setPen(QColor(0, 180, 255))
        qp.setFont(QFont("Courier New", 12, QFont.Bold))
        for i, lbl in enumerate(self.COL_LABELS):
            qp.drawText(self.MARGIN_X + i * self.CELL_SIZE + 35,
                        self.MARGIN_Y + 5 * self.CELL_SIZE + 25, lbl)
        for i, lbl in enumerate(reversed(self.ROW_LABELS)):
            qp.drawText(self.MARGIN_X - 25, self.MARGIN_Y + i * self.CELL_SIZE + 45, lbl)

        # ── draw standard extra objects ────────────────────────
        for obj in self.extra_objects:
            ox, oy = obj["pos"][0], obj["pos"][1]
            ow, oh = obj["w"], obj["h"]
            color  = obj["color"]
            otype  = obj["type"]

            if otype == "rect":
                qp.setBrush(color)
                qp.setPen(Qt.NoPen)
                qp.drawRect(int(ox - ow / 2), int(oy - oh / 2), ow, oh)

            elif otype == "bottle":
                qp.setBrush(color)
                qp.setPen(Qt.NoPen)
                qp.drawRoundedRect(int(ox - ow / 2), int(oy - oh / 2), ow, oh, 5, 5)
                qp.drawRect(int(ox - ow / 4), int(oy - oh / 2 - 5), int(ow / 2), 5)

            elif otype == "tshirt":
                draw_tshirt(qp, ox, oy, ow, oh, color)

            # Label
            qp.setPen(QColor(200, 200, 200))
            qp.setFont(QFont("Arial", 8))
            qp.drawText(int(ox - ow / 2), int(oy + oh / 2 + 14), obj["name"])

        # ── draw custom objects ────────────────────────────────
        for obj in self.custom_objects:
            if isinstance(obj, CustomPolygonObj):
                qp.setBrush(QBrush(QColor(obj.color.red(), obj.color.green(),
                                          obj.color.blue(), 160)))
                qp.setPen(QPen(obj.color.lighter(130), 2))
                qp.drawPolygon(QPolygonF(obj.points))
                qp.setPen(QColor(200, 200, 200))
                qp.setFont(QFont("Arial", 8))
                qp.drawText(int(obj.pos[0]), int(obj.pos[1]), obj.name)

            elif isinstance(obj, CustomCircleObj):
                qp.setBrush(QBrush(QColor(obj.color.red(), obj.color.green(),
                                          obj.color.blue(), 160)))
                qp.setPen(QPen(obj.color.lighter(130), 2))
                r = obj.radius
                qp.drawEllipse(QPointF(obj.pos[0], obj.pos[1]), r, r)
                qp.setPen(QColor(200, 200, 200))
                qp.setFont(QFont("Arial", 8))
                qp.drawText(int(obj.pos[0] - r / 2), int(obj.pos[1] + r + 14), obj.name)

        # ── in-progress polygon preview ────────────────────────
        if self.draw_tool == TOOL_POLYGON and self.poly_points:
            qp.setPen(QPen(self.draw_color, 2, Qt.DashLine))
            qp.setBrush(Qt.NoBrush)
            pts = self.poly_points + [self.mouse_pos]
            for i in range(len(pts) - 1):
                qp.drawLine(pts[i], pts[i + 1])
            # Close preview to first point
            if len(self.poly_points) >= 2:
                qp.drawLine(self.mouse_pos, self.poly_points[0])
            # Vertex dots
            qp.setBrush(self.draw_color)
            qp.setPen(Qt.NoPen)
            for pt in self.poly_points:
                qp.drawEllipse(pt, 4, 4)
            # Status hint
            qp.setPen(QColor(255, 255, 100))
            qp.setFont(QFont("Arial", 11))
            qp.drawText(10, self.height() - 10,
                        f"Polygon: {len(self.poly_points)} pts — click to add · dbl-click to finish")

        # ── in-progress circle preview ─────────────────────────
        if self.draw_tool == TOOL_CIRCLE and self.circle_center is not None:
            r = math.hypot(self.mouse_pos.x() - self.circle_center.x(),
                           self.mouse_pos.y() - self.circle_center.y()) if self.circle_dragging else self.circle_radius
            qp.setBrush(QBrush(QColor(self.draw_color.red(), self.draw_color.green(),
                                      self.draw_color.blue(), 80)))
            qp.setPen(QPen(self.draw_color, 2, Qt.DashLine))
            qp.drawEllipse(self.circle_center, r, r)
            # Centre dot
            qp.setBrush(self.draw_color)
            qp.setPen(Qt.NoPen)
            qp.drawEllipse(self.circle_center, 4, 4)
            qp.setPen(QColor(255, 255, 100))
            qp.setFont(QFont("Arial", 11))
            qp.drawText(10, self.height() - 10,
                        f"Circle: r={r:.0f}px — drag to resize · release/click to commit")
        elif self.draw_tool == TOOL_CIRCLE:
            qp.setPen(QColor(255, 255, 100))
            qp.setFont(QFont("Arial", 11))
            qp.drawText(10, self.height() - 10, "Circle: click & drag to place")

        # ── robotic arm ───────────────────────────────────────
        if self.arm_visible:
            grid_top    = self.MARGIN_Y
            grid_bottom = self.MARGIN_Y + 5 * self.CELL_SIZE
            grid_left   = self.MARGIN_X
            grid_right  = self.MARGIN_X + 8 * self.CELL_SIZE

            qp.setPen(QPen(QColor(50, 50, 60), 10))
            qp.drawLine(grid_left - 20, grid_top - 10,  grid_right + 20, grid_top - 10)
            qp.drawLine(grid_left - 20, grid_bottom + 10, grid_right + 20, grid_bottom + 10)

            rail_x = self.bot_pos[0]
            qp.setPen(QPen(QColor(40, 100, 140), 14))
            qp.drawLine(int(rail_x), int(grid_top - 10), int(rail_x), int(grid_bottom + 10))
            qp.setPen(QPen(QColor(100, 200, 255), 2))
            qp.drawLine(int(rail_x), int(grid_top - 10), int(rail_x), int(grid_bottom + 10))

            head_y = self.bot_pos[1]
            qp.setBrush(QColor(30, 30, 30))
            qp.setPen(QPen(QColor(255, 140, 0), 2))
            qp.drawRect(int(rail_x - 25), int(head_y - 25), 50, 50)
            qp.setBrush(QColor(255, 140, 0))
            qp.setPen(Qt.NoPen)
            qp.drawEllipse(int(rail_x - 8), int(head_y - 8), 16, 16)

            qp.setPen(QPen(QColor(200, 200, 200), 4))
            claw_offset = 10 if self.holding else 25
            qp.drawLine(int(rail_x - 15), int(head_y + 25), int(rail_x - 15), int(head_y + 40))
            qp.drawLine(int(rail_x - 15), int(head_y + 40), int(rail_x - claw_offset), int(head_y + 50))
            qp.drawLine(int(rail_x + 15), int(head_y + 25), int(rail_x + 15), int(head_y + 40))
            qp.drawLine(int(rail_x + 15), int(head_y + 40), int(rail_x + claw_offset), int(head_y + 50))

        qp.end()


# ──────────────────────────────────────────────────────────────
#  Main window
# ──────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Prolabs V12.2 - Precision Cartesian Gantry")
        self.showMaximized()

        self.api_key = "YOUR OPENAI API KEY HERE"

        system_prompt = """You are a Coordinate locator and planner where you plan locate and coordinates.

PHASE 1 INTERNAL IMAGE ANALYSIS

Whenever an image is provided which will be of a board:

You must internally determine:

The column and row of every object relevant to the task

The center coordinate of each object

The full horizontal and vertical span of objects if dragging is required

The orientation of objects if relevant for cutting or folding

You must NEVER output this internal reasoning.

Coordinates must always be treated as:

column, row

Example format:

E, 3

Always go to the center of the object.

Never go to edge or corner.

PHASE 2 COORDINATE ACTION PLANNER

After internal detection switch role to Coordinates going planner.

Valid functions you can output are strictly limited to:

{goto_coordinate = column, row}
{pickup}
{keep}
{Task_Completed}

No other outputs allowed.

No explanations

No comments

No punctuation outside required format.

Always include comma between column and row.

GENERAL MOVEMENT RULES

Always go to exact center of object.

Must goto before pickup.

Must pickup before keep.

Cannot hold more than one object.

Must keep object before picking another.

No teleportation.

No skipping steps.

Always place objects with stability.

Never drop objects outside containers.

OBJECT INTERACTION RULE

Objects may be:

ingredient
tool
container
surface
machine

Containers include:

bowl
plate
pot
pan
cup
tray
basket

Tools include:

knife
spoon
spatula
ladle
peeler
tongs

Machines include:

stove
sink
washing area
cutting board

COOKING TRAINING RULES

Cooking tasks must follow strict real world order.

Container Setup

Pot or pan must be picked and placed on stove before adding ingredients.

Never turn on stove before pot is placed.

Never add ingredient before pot is placed.

INGREDIENT TRANSFER RULE

If bowl contains ingredient:

pickup bowl

goto pot

keep bowl tilted into pot

then keep bowl away from stove

Never invent internal ingredients.

Treat bowl as container unless specified otherwise.

WATER RULE

Water source must not be picked unless shown as movable container.

If water must be added:

goto water source

simulate filling container by pickup if container is movable

goto pot

keep to transfer

Never pickup water if water is fixed tap unless shown as movable.

HEATING RULE

Pot must be on stove before heating.

After ingredients and water added:

goto stove control center

pickup stove knob if separate object

keep after activation if required

Heating must happen only after setup.

After sufficient logical steps:

goto stove control

deactivate

Do not deactivate before cooking is logically complete.

CUTTING RULE

When cutting is required:

Cutting must happen on cutting board.

Steps:

pickup ingredient

goto cutting board

keep ingredient on cutting board

pickup knife

move knife across ingredient horizontally

repeat motion across ingredient vertically

keep knife after cutting

If slices are required:

treat sliced pieces as same object location.

CHOPPING RULE

For chopping tasks:

pickup ingredient

goto cutting board

keep ingredient

pickup knife

perform repeated small horizontal cuts

perform repeated vertical cuts

keep knife after chopping finished

PEELING RULE

For peeling:

pickup ingredient

goto cutting board

keep ingredient

pickup peeler

drag peeler across full surface span

repeat until surface covered

keep peeler away after peeling.

MIXING RULE

If mixing ingredients in bowl or pot:

pickup spoon

goto container center

simulate circular motion by visiting multiple internal coordinates

continue until ingredients logically mixed

keep spoon away after mixing.

STIRRING RULE

If pot is cooking:

pickup spoon

goto pot center

move across multiple coordinates inside pot

simulate circular stirring motion

continue until ingredients evenly distributed

keep spoon away.

POURING RULE

If liquid container exists:

pickup container

goto target container

keep container tilted into target

then keep container upright away from target.

SORTING RULE

If sorting objects:

Identify object groups.

For each object:

goto object center

pickup object

goto correct container or region

keep object

Repeat until all objects sorted.

STACKING RULE

If stacking objects:

pickup first object

goto base location

keep

pickup second object

goto top of previous object

keep

Repeat until stack complete.

FOLDING RULE

If folding cloth or fabric:

pickup cloth center

drag across cloth horizontal span

keep

pickup cloth edge

drag toward opposite edge

keep

Repeat until cloth compact.

PLATE SERVING RULE

For serving food:

pickup cooked container

goto plate

keep contents onto plate

then keep container away.

WASHING RULE

If object must be washed:

goto sink center

pickup object

drag object across water span

pickup soap if required

apply soap rule

drag object again under water

keep object on drying area.

SOAP RULE STRICT

If asked to apply soap on an object:

goto soap center

pickup soap

drag across ALL coordinates occupied by the object

horizontally

vertically

do NOT keep during dragging

only keep soap AFTER fully covering

keep soap away from target object

do NOT move target object

Never keep mid application.

CLEANING SURFACE RULE

For cleaning table or board:

pickup cloth

drag across full horizontal span

drag across full vertical span

repeat until surface covered

keep cloth away from surface.

MULTI OBJECT RULE

If sorting or multiple object handling:

Repeat:

{goto_coordinate = column, row}

{pickup}

{goto_coordinate = column, row}

{keep}

Until task complete.

Then:

{Task_Completed}

TOOL SAFETY RULE

Sharp tools such as knife must always be kept away from ingredient after use.

Never leave knife on ingredient.

Always keep tool away after use.

LOGICAL COMPLETION RULE

Task is complete only when:

All ingredients processed

All tools placed away

Cooking stopped if started

Objects placed in final location

Then output:

{Task_Completed}

STRICT OUTPUT FORMAT

No explanations

No reasoning

No extra words

No punctuation

Only valid function calls

Always include comma between column and row.

Correct format example:

{goto_coordinate = E, 3}

{pickup}

{goto_coordinate = C, 5}

{keep}

{Task_Completed}

PRIORITY ORDER

Detect objects internally

Plan realistic sequence

Enforce cooking order

Enforce tool rules

Enforce soap rule if applicable

Enforce washing rules

Output only valid function calls

End with {Task_Completed}"""

        self.chat_history  = [{"role": "system", "content": system_prompt}]
        self.command_queue = []
        self.execution_timer = QTimer()
        self.execution_timer.timeout.connect(self.process_queue)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QHBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        left_side   = QWidget()
        left_layout = QVBoxLayout(left_side)
        self.sim    = RobotSim()
        left_layout.addWidget(self.sim)

        right_side = QWidget()
        right_side.setStyleSheet("background-color: #0e0e1a; border-left: 2px solid #333;")
        right_layout = QVBoxLayout(right_side)
        right_layout.setContentsMargins(20, 20, 20, 20)

        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setStyleSheet(
            "background: #0e0e1a; color: #e0e0e0; font-family: Segoe UI; font-size: 14px; border: none;"
        )
        self.chat_display.append("<b>Prolabs AI:</b> Cartesian System Ready. Describe a movement task.<br>")

        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Describe task (e.g., 'Place bottle at B2')...")
        self.chat_input.setStyleSheet(
            "background: #1e1e2e; color: white; padding: 12px; border-radius: 5px; font-size: 14px; border: 1px solid #444;"
        )
        self.chat_input.returnPressed.connect(self.send_chat)

        self.send_btn = QPushButton("Execute")
        self.send_btn.setStyleSheet(
            "QPushButton { background-color: #007acc; color: white; padding: 10px; border-radius: 5px; font-weight: bold; }"
            "QPushButton:hover { background-color: #005f9e; }"
        )
        self.send_btn.clicked.connect(self.send_chat)

        input_layout = QHBoxLayout()
        input_layout.addWidget(self.chat_input)
        input_layout.addWidget(self.send_btn)

        right_layout.addWidget(QLabel("<h2 style='color:white;'>Autonomous Planner</h2>"))
        right_layout.addWidget(self.chat_display)
        right_layout.addLayout(input_layout)

        layout.addWidget(left_side,  7)
        layout.addWidget(right_side, 3)

    # ── screenshot ────────────────────────────────────────────

    def capture_board(self):
        self.sim.arm_visible = False
        pixmap = self.sim.grab()
        self.sim.arm_visible = True

        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        pixmap.save(buffer, "PNG")
        return base64.b64encode(buffer.data().data()).decode("utf-8")

    # ── chat ──────────────────────────────────────────────────

    def send_chat(self):
        user_text = self.chat_input.text().strip()
        if not user_text or self.execution_timer.isActive():
            return

        image_data = self.capture_board()
        self.chat_display.append(f"<div style='color: #4da6ff;'><b>Task:</b> {user_text}</div>")
        self.chat_input.clear()
        self.chat_input.setDisabled(True)
        self.chat_history.append({"role": "user", "content": user_text})

        self.worker = ChatWorker(self.api_key, self.chat_history, image_data)
        self.worker.response_received.connect(self.handle_ai_response)
        self.worker.start()

    def handle_ai_response(self, response):
        self.chat_display.append(f"<br><div style='color: #00ff96;'>{response}</div><br>")
        self.chat_history.append({"role": "assistant", "content": response})

        commands = re.findall(r'\{(.*?)\}', response)
        self.command_queue = commands
        self.execution_timer.start(800)

    def process_queue(self):
        if not self.command_queue:
            self.execution_timer.stop()
            self.chat_input.setDisabled(False)
            self.chat_input.setFocus()
            return

        if not self.sim.is_at_target():
            return

        cmd = self.command_queue.pop(0).strip()

        if "goto_coordinate =" in cmd:
            parts = cmd.split('=')[1].split(',')
            if len(parts) == 2:
                coords = self.sim.get_coords(parts[0], parts[1])
                if coords:
                    self.sim.bot_target = list(coords)

        elif cmd == "pickup":
            all_objs = (
                [{"pos": self.sim.brick_pos, "ref": "brick"}]
                + [{"pos": o["pos"], "ref": o} for o in self.sim.extra_objects]
                + [{"pos": o.pos,             "ref": o} for o in self.sim.custom_objects]
            )
            for obj in all_objs:
                dist = math.hypot(self.sim.bot_pos[0] - obj["pos"][0],
                                  self.sim.bot_pos[1] - obj["pos"][1])
                if dist < 60:
                    self.sim.holding    = True
                    self.sim.held_extra = obj["ref"]
                    break

        elif cmd == "keep":
            self.sim.holding    = False
            self.sim.held_extra = None

        elif cmd == "Task_Completed":
            self.command_queue = []

        sb = self.chat_display.verticalScrollBar()
        sb.setValue(sb.maximum())


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

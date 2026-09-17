from __future__ import annotations

from typing import Dict, Optional

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup, QColorDialog, QDialog, QGridLayout, QHBoxLayout, QLabel,
    QPushButton, QToolButton, QVBoxLayout, QWidget,
)


class DrawingToolsDialog(QDialog):
    """Palette dessin verticale compacte, au format barre d'outils."""

    def __init__(self, tab: "CamTab", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.tab = tab
        self.current_color = QColor(*self.tab.active_drawing_viewer().drawing_color)
        self.setWindowTitle("Dessiner")
        self.setModal(False)
        self.setFixedSize(150, 338)
        self.setSizeGripEnabled(False)
        self.setStyleSheet(
            "QDialog { background-color: #232323; }"
            "QToolButton { background-color: #4a4a4a; border: 1px solid #5d5d5d; border-radius: 4px; }"
            "QToolButton:hover { background-color: #5a5a5a; }"
            "QToolButton:checked { background-color: #6a6a6a; border: 1px solid #8a8a8a; }"
            "QLabel { color: #f0f0f0; font-weight: bold; }"
            "QLabel#DrawingSizeValue { background-color: #2f2f2f; color: #ffffff; border: 1px solid #707070; border-radius: 4px; padding: 4px; }"
            "QPushButton#DrawingSizeButton { background-color: #454545; color: #ffffff; border: 1px solid #777777; border-radius: 4px; font-weight: bold; }"
            "QPushButton#DrawingSizeButton:hover { background-color: #5a5a5a; border-color: #ffffff; }"
            "QPushButton { background-color: #3a3a3a; color: white; border: 1px solid #4d4d4d; padding: 4px; }"
            "QPushButton:hover { background-color: #4a4a4a; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)
        tools_widget = QWidget()
        tools_grid = QGridLayout(tools_widget)
        tools_grid.setContentsMargins(0, 0, 0, 0)
        tools_grid.setHorizontalSpacing(8)
        tools_grid.setVerticalSpacing(6)
        self.tool_buttons: Dict[str, QToolButton] = {}

        tool_specs = [
            ("undo", "Dessin précédent", "undo"),
            ("redo", "Dessin suivant", "redo"),
            ("freehand", "Main levée", "freehand"),
            ("line", "Ligne droite", "line"),
            ("rect", "Rectangle", "rect"),
            ("ellipse", "Ellipse", "ellipse"),
            ("eraser", "Gomme", "eraser"),
            ("color", "Couleur du trait", "color"),
        ]

        for idx, (tool_key, tooltip, icon_kind) in enumerate(tool_specs):
            btn = QToolButton()
            btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
            btn.setIconSize(QSize(26, 26))
            btn.setMinimumSize(44, 40)
            btn.setMaximumSize(46, 42)
            btn.setToolTip(tooltip)

            if tool_key == "undo":
                btn.setIcon(self._make_tool_icon(icon_kind))
                btn.clicked.connect(self.undo_drawing)
            elif tool_key == "redo":
                btn.setIcon(self._make_tool_icon(icon_kind))
                btn.clicked.connect(self.redo_drawing)
            elif tool_key == "color":
                self.btn_color = btn
                btn.setIcon(self._make_color_icon(self.current_color))
                btn.clicked.connect(self.choose_color)
            else:
                btn.setCheckable(True)
                btn.setIcon(self._make_tool_icon(icon_kind))
                btn.clicked.connect(lambda checked=False, tk=tool_key: self.select_tool(tk))
                self.tool_group.addButton(btn)
                self.tool_buttons[tool_key] = btn

            tools_grid.addWidget(btn, idx // 2, idx % 2)

        layout.addWidget(tools_widget, 0, Qt.AlignHCenter)

        label_size = QLabel("Taille")
        label_size.setAlignment(Qt.AlignCenter)
        label_size.setStyleSheet("QLabel { color: #f0f0f0; font-size: 14px; font-weight: bold; }")
        layout.addWidget(label_size)

        self.current_width = max(1, min(80, int(self.tab.active_drawing_viewer().drawing_width)))
        size_row = QHBoxLayout()
        size_row.setContentsMargins(0, 0, 0, 0)
        size_row.setSpacing(5)
        self.btn_width_minus = QPushButton("-")
        self.btn_width_minus.setObjectName("DrawingSizeButton")
        self.btn_width_minus.setFixedSize(32, 26)
        self.btn_width_minus.setToolTip("Diminuer la taille")
        self.btn_width_minus.clicked.connect(lambda: self.change_width_delta(-1))
        self.width_value_label = QLabel(str(self.current_width))
        self.width_value_label.setObjectName("DrawingSizeValue")
        self.width_value_label.setAlignment(Qt.AlignCenter)
        self.width_value_label.setFixedSize(42, 26)
        self.width_value_label.setToolTip("Épaisseur du trait / taille de la gomme")
        self.btn_width_plus = QPushButton("+")
        self.btn_width_plus.setObjectName("DrawingSizeButton")
        self.btn_width_plus.setFixedSize(32, 26)
        self.btn_width_plus.setToolTip("Augmenter la taille")
        self.btn_width_plus.clicked.connect(lambda: self.change_width_delta(1))
        size_row.addWidget(self.btn_width_minus)
        size_row.addWidget(self.width_value_label)
        size_row.addWidget(self.btn_width_plus)
        layout.addLayout(size_row)

        # V2.77 : plus de grand stretch entre Taille et Effacer.
        layout.addSpacing(4)
        self.btn_clear = QPushButton("Effacer")
        self.btn_clear.setFixedHeight(24)
        self.btn_clear.setToolTip("Effacer tous les dessins de l'image active")
        self.btn_clear.clicked.connect(self.clear_current_drawings)
        # Bordure rouge légère uniquement pour signaler l'action destructive.
        self.btn_clear.setStyleSheet(
            "QPushButton { background-color: #3a3a3a; color: white; border: 1px solid #d64b4b; padding: 3px; }"
            "QPushButton:hover { background-color: #4a3030; }"
        )
        layout.addWidget(self.btn_clear)

        self.btn_close = QPushButton("Fermer")
        self.btn_close.setFixedHeight(24)
        self.btn_close.clicked.connect(self.close)
        layout.addWidget(self.btn_close)

        self.apply_color(self.current_color)
        self.apply_width(self.current_width)
        self.tab.set_drawing_enabled_for_all(True)
        self.select_tool(str(self.tab.active_drawing_viewer().drawing_tool or "freehand"))

    def _make_color_icon(self, color: QColor) -> QIcon:
        pixmap = QPixmap(28, 28)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setPen(QPen(QColor(65, 65, 65), 1))
            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(4, 4, 20, 20), 4, 4)
        finally:
            painter.end()
        return QIcon(pixmap)

    def _make_tool_icon(self, kind: str) -> QIcon:
        pixmap = QPixmap(28, 28)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)
            pen = QPen(QColor(238, 238, 238), 2)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            if kind == "undo":
                painter.drawLine(QPointF(11, 9), QPointF(6, 14))
                painter.drawLine(QPointF(6, 14), QPointF(11, 19))
                painter.drawLine(QPointF(7, 14), QPointF(18, 14))
                painter.drawLine(QPointF(18, 14), QPointF(18, 19))
            elif kind == "redo":
                painter.drawLine(QPointF(17, 9), QPointF(22, 14))
                painter.drawLine(QPointF(22, 14), QPointF(17, 19))
                painter.drawLine(QPointF(21, 14), QPointF(10, 14))
                painter.drawLine(QPointF(10, 14), QPointF(10, 19))
            elif kind == "freehand":
                pts = [QPointF(5, 19), QPointF(9, 11), QPointF(13, 16), QPointF(18, 8), QPointF(23, 13)]
                for a, b in zip(pts, pts[1:]):
                    painter.drawLine(a, b)
            elif kind == "line":
                painter.drawLine(QPointF(6, 22), QPointF(22, 6))
            elif kind == "rect":
                painter.drawRect(QRectF(6, 7, 16, 13))
            elif kind == "ellipse":
                painter.drawEllipse(QRectF(6, 7, 16, 13))
            elif kind == "eraser":
                painter.drawLine(QPointF(8, 18), QPointF(14, 9))
                painter.drawLine(QPointF(14, 9), QPointF(21, 14))
                painter.drawLine(QPointF(21, 14), QPointF(15, 23))
                painter.drawLine(QPointF(15, 23), QPointF(8, 18))
                painter.drawLine(QPointF(6, 23), QPointF(22, 23))
        finally:
            painter.end()
        return QIcon(pixmap)

    def select_tool(self, tool_key: str) -> None:
        tool_key = str(tool_key or "freehand")
        btn = self.tool_buttons.get(tool_key)
        if btn is not None:
            btn.setChecked(True)
        self.tab.set_drawing_tool_for_all(tool_key)

    def undo_drawing(self) -> None:
        self.tab.active_drawing_viewer().undo_drawing()

    def redo_drawing(self) -> None:
        self.tab.active_drawing_viewer().redo_drawing()

    def clear_current_drawings(self) -> None:
        self.tab.active_drawing_viewer().clear_current_drawings()

    def change_width_delta(self, delta: int) -> None:
        self.apply_width(self.current_width + int(delta))

    def apply_width(self, value: int) -> None:
        self.current_width = max(1, min(80, int(value)))
        if hasattr(self, "width_value_label"):
            self.width_value_label.setText(str(self.current_width))
        self.tab.set_drawing_width_for_all(self.current_width)

    def apply_color(self, color: QColor) -> None:
        self.tab.set_drawing_color_for_all(color)

    def choose_color(self) -> None:
        color = QColorDialog.getColor(self.current_color, self, "Couleur du trait")
        if not color.isValid():
            return
        self.current_color = color
        self.btn_color.setIcon(self._make_color_icon(color))
        self.apply_color(color)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.tab.set_drawing_enabled_for_all(False)
        super().closeEvent(event)

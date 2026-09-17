from __future__ import annotations

from typing import Optional, Tuple

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QToolButton, QWidget

from ..utils import format_rgb


class ColorButton(QToolButton):
    clicked_index = Signal(int)
    edit_requested = Signal(int)

    def __init__(self, index: int, color: Tuple[int, int, int], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.index = index
        self.rgb = color
        self.setText(f"Fond {index + 1}")
        self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.setMinimumWidth(95)
        self.setIconSize(QSize(18, 18))
        self.set_color(color)
        self.clicked.connect(lambda: self.clicked_index.emit(self.index))
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(lambda _pos: self.edit_requested.emit(self.index))

    def _make_color_icon(self, color: Tuple[int, int, int]) -> QIcon:
        pixmap = QPixmap(18, 18)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setPen(QPen(QColor(70, 70, 70), 1))
            painter.setBrush(QColor(*color))
            painter.drawRoundedRect(QRectF(1, 1, 16, 16), 3, 3)
        finally:
            painter.end()
        return QIcon(pixmap)

    def set_color(self, color: Tuple[int, int, int]) -> None:
        self.rgb = color
        self.setIcon(self._make_color_icon(color))
        self.setToolTip(
            f"Fond {self.index + 1} : {format_rgb(color)}\n"
            "Clic gauche = choisir ce fond | clic droit = modifier la couleur"
        )

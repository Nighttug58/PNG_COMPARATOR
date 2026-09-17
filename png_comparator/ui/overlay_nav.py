from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, Signal
from PySide6.QtWidgets import QGraphicsOpacityEffect, QPushButton, QWidget


class OverlayNavButton(QWidget):
    """Zone de navigation flottante avec bouton visuel animé.

    La zone sensible reste fixe et confortable dans le viewer. Seul le bouton
    visuel glisse légèrement vers le bord au repos puis revient au hover.
    """

    clicked = Signal()

    def __init__(self, text: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.side = "left" if "‹" in text or "◀" in text else "right"
        self.rest_pos = QPoint(0, 0)
        self.visual_rest_pos = QPoint(0, 0)
        self.visual_hover_pos = QPoint(0, 0)
        self.zone_width = 64
        self.zone_height = 58
        self.button_size = 44
        self.visible_strip = 10
        self.setFixedSize(self.zone_width, self.zone_height)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setToolTip("Image précédente" if self.side == "left" else "Image suivante")

        self.visual_button = QPushButton("◀" if self.side == "left" else "▶", self)
        self.visual_button.setFixedSize(self.button_size, self.button_size)
        self.visual_button.setCursor(Qt.PointingHandCursor)
        self.visual_button.setFocusPolicy(Qt.NoFocus)
        self.visual_button.clicked.connect(self.clicked.emit)
        self.visual_button.setStyleSheet(
            "QPushButton {"
            " background-color: rgba(38, 43, 50, 232);"
            " color: rgba(255,255,255,250);"
            " border: 1px solid rgba(255,255,255,190);"
            " border-radius: 7px;"
            " font-size: 21px;"
            " font-weight: bold;"
            " padding: 0px;"
            " margin: 0px;"
            " text-align: center;"
            "}"
            "QPushButton:hover {"
            " background-color: rgba(48, 54, 63, 248);"
            " border: 1px solid rgba(255,255,255,230);"
            "}"
            "QPushButton:disabled {"
            " color: rgba(255,255,255,110);"
            " background-color: rgba(30,34,40,130);"
            " border: 1px solid rgba(255,255,255,70);"
            "}"
        )

        self.opacity_effect = QGraphicsOpacityEffect(self.visual_button)
        self.visual_button.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(0.25)

        self.move_animation = QPropertyAnimation(self.visual_button, b"pos", self)
        self.move_animation.setDuration(145)
        self.move_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.opacity_animation = QPropertyAnimation(self.opacity_effect, b"opacity", self)
        self.opacity_animation.setDuration(130)
        self.opacity_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.raise_()

    def update_edge_positions(self, viewer: QWidget) -> None:
        y = max(8, (viewer.height() - self.height()) // 2)
        if self.side == "left":
            self.rest_pos = QPoint(0, y)
            self.visual_rest_pos = QPoint(-(self.button_size - self.visible_strip), (self.height() - self.button_size) // 2)
            self.visual_hover_pos = QPoint(8, (self.height() - self.button_size) // 2)
        else:
            self.rest_pos = QPoint(max(0, viewer.width() - self.width()), y)
            self.visual_rest_pos = QPoint(self.width() - self.visible_strip, (self.height() - self.button_size) // 2)
            self.visual_hover_pos = QPoint(max(0, self.width() - self.button_size - 8), (self.height() - self.button_size) // 2)
        self.move(self.rest_pos)
        if not self.underMouse():
            self.visual_button.move(self.visual_rest_pos)
            self.opacity_effect.setOpacity(0.25)
        else:
            self.visual_button.move(self.visual_hover_pos)
            self.opacity_effect.setOpacity(1.0)
        self.raise_()

    def animate_visual_to(self, pos: QPoint, opacity: float) -> None:
        self.move_animation.stop()
        self.move_animation.setStartValue(self.visual_button.pos())
        self.move_animation.setEndValue(pos)
        self.move_animation.start()
        self.opacity_animation.stop()
        self.opacity_animation.setStartValue(self.opacity_effect.opacity())
        self.opacity_animation.setEndValue(opacity)
        self.opacity_animation.start()

    def set_rest_opacity(self) -> None:
        """Remet l'état repos/hover sans déplacer la zone sensible."""
        if self.underMouse():
            self.visual_button.move(self.visual_hover_pos)
            self.opacity_effect.setOpacity(1.0)
        else:
            self.visual_button.move(self.visual_rest_pos)
            self.opacity_effect.setOpacity(0.25)
        self.raise_()

    def setEnabled(self, enabled: bool) -> None:  # type: ignore[override]
        super().setEnabled(enabled)
        self.visual_button.setEnabled(enabled)

    def enterEvent(self, event) -> None:  # type: ignore[override]
        self.animate_visual_to(self.visual_hover_pos, 1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        self.animate_visual_to(self.visual_rest_pos, 0.25)
        super().leaveEvent(event)

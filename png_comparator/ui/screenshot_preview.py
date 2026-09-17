from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QWidget


class ScreenshotPreviewCanvas(QWidget):
    """Viewer simple pour captures : molette = zoom, clic gauche = pan, sans scrollbars."""

    def __init__(self, owner: "ScreenshotLibraryDialog", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.owner = owner
        self.pixmap: Optional[QPixmap] = None
        self.zoom_factor = 1.0
        self.center_norm_x = 0.5
        self.center_norm_y = 0.5
        self._dragging = False
        self._last_mouse_pos = QPointF()
        self.setMinimumSize(360, 260)
        self.setMouseTracking(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.open_context_menu)

    def set_pixmap(self, pixmap: QPixmap) -> None:
        self.pixmap = pixmap
        self.fit_to_window()

    def has_pixmap(self) -> bool:
        return self.pixmap is not None and not self.pixmap.isNull()

    def fit_scale(self) -> float:
        if not self.has_pixmap():
            return 1.0
        return max(0.05, min(20.0, min(self.width() / max(1, self.pixmap.width()), self.height() / max(1, self.pixmap.height())) * 0.98))

    def fit_to_window(self) -> None:
        self.zoom_factor = self.fit_scale()
        self.center_norm_x = 0.5
        self.center_norm_y = 0.5
        self.update()

    def target_rect(self) -> Optional[QRectF]:
        if not self.has_pixmap():
            return None
        iw = self.pixmap.width()
        ih = self.pixmap.height()
        cx = self.center_norm_x * iw
        cy = self.center_norm_y * ih
        x = self.width() / 2.0 - cx * self.zoom_factor
        y = self.height() / 2.0 - cy * self.zoom_factor
        return QRectF(x, y, iw * self.zoom_factor, ih * self.zoom_factor)

    def zoom_at(self, pos: QPointF, factor: float) -> None:
        if not self.has_pixmap():
            return
        old_rect = self.target_rect()
        if old_rect is None:
            return
        iw = max(1, self.pixmap.width())
        ih = max(1, self.pixmap.height())
        img_x = (pos.x() - old_rect.x()) / max(0.0001, self.zoom_factor)
        img_y = (pos.y() - old_rect.y()) / max(0.0001, self.zoom_factor)
        new_zoom = max(0.05, min(20.0, self.zoom_factor * float(factor)))
        self.zoom_factor = new_zoom
        cx = img_x - (pos.x() - self.width() / 2.0) / max(0.0001, new_zoom)
        cy = img_y - (pos.y() - self.height() / 2.0) / max(0.0001, new_zoom)
        self.center_norm_x = cx / iw
        self.center_norm_y = cy / ih
        self.update()

    def wheelEvent(self, event) -> None:  # type: ignore[override]
        if event.angleDelta().y() == 0:
            event.ignore()
            return
        steps = event.angleDelta().y() / 120.0
        self.zoom_at(event.position(), 1.15 ** steps)
        event.accept()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton and self.has_pixmap():
            self._dragging = True
            self._last_mouse_pos = event.position()
            self._pan_last_mouse_pos = event.position()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._dragging and self.has_pixmap():
            delta = event.position() - self._last_mouse_pos
            self._last_mouse_pos = event.position()
            iw = max(1, self.pixmap.width())
            ih = max(1, self.pixmap.height())
            self.center_norm_x -= float(delta.x()) / max(0.0001, self.zoom_factor) / iw
            self.center_norm_y -= float(delta.y()) / max(0.0001, self.zoom_factor) / ih
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            self._pan_last_mouse_pos = event.position()
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton:
            self.fit_to_window()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def open_context_menu(self, pos: QPoint) -> None:
        self.owner.open_preview_context_menu(self.mapToGlobal(pos))

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        try:
            painter.fillRect(self.rect(), QColor(26, 29, 34))
            if not self.has_pixmap():
                painter.setPen(QColor(235, 235, 235))
                painter.drawText(self.rect(), Qt.AlignCenter, "Aucun screenshot sélectionné")
                return
            target = self.target_rect()
            if target is None:
                return
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.drawPixmap(target, self.pixmap, QRectF(self.pixmap.rect()))
            percent = self.zoom_factor * 100.0
            label = f"Zoom : {percent:.0f}%"
            fm = painter.fontMetrics()
            text_rect = fm.boundingRect(label).adjusted(-7, -4, 7, 4)
            text_rect.moveTopLeft(QPoint(8, 8))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, 150))
            painter.drawRoundedRect(QRectF(text_rect), 4, 4)
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(text_rect, Qt.AlignCenter, label)
        finally:
            painter.end()

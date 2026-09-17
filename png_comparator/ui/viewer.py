from __future__ import annotations

from typing import Optional, Tuple

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..models import ViewerState
from ..utils import image_border_color_for_background


class CompareImageCanvas(QWidget):
    """Canvas de visualisation pur : image, zoom/pan, comparaison et mini-map."""

    camera_changed = Signal(object)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(220, 180)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.bg_color = QColor(255, 255, 255)
        self.pixmap: Optional[QPixmap] = None
        self.overlay_pixmap: Optional[QPixmap] = None
        self.overlay_path: Optional[str] = None
        self.main_opacity = 1.0
        self.overlay_opacity = 0.0
        self.current_path: Optional[str] = None
        self.pending_path: Optional[str] = None
        self.original_image_width = 0
        self.original_image_height = 0

        self.camera_state = ViewerState(
            fit_mode=True,
            scale=1.0,
            center_norm_x=0.5,
            center_norm_y=0.5,
        )
        self._dragging = False
        self._minimap_dragging = False
        self._pan_last_mouse_pos = QPointF()
        self._suppress_camera_signal = False
        self._message = "Aucune image sélectionnée"
        self.show_minimap = True
        self.info_text = ""
        self.min_scale = 0.10
        self.max_scale = 40.0

    def has_image(self) -> bool:
        return self.pixmap is not None and not self.pixmap.isNull()

    def set_background(self, color: QColor) -> None:
        self.bg_color = QColor(color)
        self.update()

    def set_inspection_overlays(
        self,
        *,
        minimap: Optional[bool] = None,
        info_text: Optional[str] = None,
        **_ignored,
    ) -> None:
        if minimap is not None:
            self.show_minimap = bool(minimap)
        if info_text is not None:
            self.info_text = str(info_text)
        self.update()

    def set_loading(
        self,
        path: Optional[str],
        preserve_view: bool = True,
        state_override: Optional[ViewerState] = None,
    ) -> None:
        if not path:
            self.pending_path = None
            self.current_path = None
            self.original_image_width = 0
            self.original_image_height = 0
            self.pixmap = None
            self.overlay_pixmap = None
            self.overlay_path = None
            self.main_opacity = 1.0
            self.overlay_opacity = 0.0
            self._message = "Aucune image sélectionnée"
            self.update()
            return

        self.pending_path = path
        self._message = "Chargement de l'image..."
        if state_override is not None:
            self.apply_camera_state(state_override, emit_change=False)
        elif not preserve_view:
            self.camera_state = ViewerState(
                fit_mode=True,
                scale=1.0,
                center_norm_x=0.5,
                center_norm_y=0.5,
            )
        self.update()

    def set_error(self, path: str, error: str) -> None:
        if self.pending_path and path != self.pending_path:
            return
        self.pixmap = None
        self.overlay_pixmap = None
        self.overlay_path = None
        self.current_path = None
        self.original_image_width = 0
        self.original_image_height = 0
        self.main_opacity = 1.0
        self.overlay_opacity = 0.0
        self._message = f"Impossible de charger :\n{path}\n\n{error}"
        self.update()

    def set_qimage(
        self,
        path: str,
        image: QImage,
        original_w: int,
        original_h: int,
        preserve_view: Optional[bool] = None,
    ) -> None:
        if self.pending_path and path != self.pending_path:
            return
        pixmap = QPixmap.fromImage(image)
        if pixmap.isNull():
            self.set_error(path, "Image invalide")
            return

        had_image = self.has_image()
        self.pixmap = pixmap
        self.current_path = path
        self.pending_path = path
        self.original_image_width = int(original_w) if int(original_w or 0) > 0 else pixmap.width()
        self.original_image_height = int(original_h) if int(original_h or 0) > 0 else pixmap.height()
        self._message = ""

        if not had_image and self.camera_state.fit_mode:
            self.fit_to_window(emit_change=False)
        self.update()

    def fit_scale(self) -> float:
        if not self.has_image() or self.pixmap is None:
            return 1.0
        width = max(1, self.width())
        height = max(1, self.height())
        image_width = max(1, self.pixmap.width())
        image_height = max(1, self.pixmap.height())
        scale = min(width / image_width, height / image_height) * 0.98
        return max(self.min_scale, min(self.max_scale, scale))

    def effective_state(self) -> ViewerState:
        if not self.has_image() or self.pixmap is None:
            return ViewerState(fit_mode=True)
        if self.camera_state.fit_mode:
            return ViewerState(
                fit_mode=False,
                scale=self.fit_scale(),
                center_norm_x=0.5,
                center_norm_y=0.5,
                display_width=self.pixmap.width(),
                display_height=self.pixmap.height(),
            )
        return ViewerState(
            fit_mode=False,
            scale=max(self.min_scale, min(self.max_scale, float(self.camera_state.scale))),
            center_norm_x=float(self.camera_state.center_norm_x),
            center_norm_y=float(self.camera_state.center_norm_y),
            display_width=self.pixmap.width(),
            display_height=self.pixmap.height(),
        )

    def capture_camera_state(self) -> Optional[ViewerState]:
        if not self.has_image():
            return None
        return self.effective_state()

    def capture_state(self) -> ViewerState:
        return self.capture_camera_state() or ViewerState(fit_mode=True)

    def set_main_opacity(self, opacity: float) -> None:
        self.main_opacity = max(0.0, min(1.0, float(opacity)))
        self.update()

    def set_overlay_opacity(self, opacity: float) -> None:
        self.overlay_opacity = max(0.0, min(1.0, float(opacity)))
        self.update()

    def clear_overlay(self) -> None:
        self.overlay_pixmap = None
        self.overlay_path = None
        self.main_opacity = 1.0
        self.overlay_opacity = 0.0
        self.update()

    def set_overlay_qimage(self, path: str, image: QImage, opacity: float = 0.5) -> None:
        pixmap = QPixmap.fromImage(image)
        if pixmap.isNull():
            return
        self.overlay_pixmap = pixmap
        self.overlay_path = path
        self.overlay_opacity = max(0.0, min(1.0, float(opacity)))
        self.update()

    def apply_camera_state(self, state: ViewerState, emit_change: bool = False) -> None:
        width = self.pixmap.width() if self.pixmap is not None else int(state.display_width)
        height = self.pixmap.height() if self.pixmap is not None else int(state.display_height)
        self.camera_state = ViewerState(
            fit_mode=False,
            scale=max(self.min_scale, min(self.max_scale, float(state.scale))),
            center_norm_x=float(state.center_norm_x),
            center_norm_y=float(state.center_norm_y),
            display_width=width,
            display_height=height,
        )
        self.update()
        if emit_change and not self._suppress_camera_signal:
            self.camera_changed.emit(self.capture_camera_state())

    def fit_to_window(self, emit_change: bool = True) -> None:
        if not self.has_image() or self.pixmap is None:
            return
        self.camera_state = ViewerState(
            fit_mode=False,
            scale=self.fit_scale(),
            center_norm_x=0.5,
            center_norm_y=0.5,
            display_width=self.pixmap.width(),
            display_height=self.pixmap.height(),
        )
        self.update()
        if emit_change and not self._suppress_camera_signal:
            self.camera_changed.emit(self.capture_camera_state())

    def actual_size(self) -> None:
        if not self.has_image() or self.pixmap is None:
            return
        self.camera_state = ViewerState(
            fit_mode=False,
            scale=1.0,
            center_norm_x=0.5,
            center_norm_y=0.5,
            display_width=self.pixmap.width(),
            display_height=self.pixmap.height(),
        )
        self.update()
        if not self._suppress_camera_signal:
            self.camera_changed.emit(self.capture_camera_state())

    def _zoom_at(self, widget_pos: QPointF, factor: float) -> None:
        if not self.has_image() or self.pixmap is None:
            return
        state = self.effective_state()
        old_scale = max(self.min_scale, min(self.max_scale, float(state.scale)))
        new_scale = max(self.min_scale, min(self.max_scale, old_scale * factor))
        if abs(new_scale - old_scale) < 1e-9:
            return

        image_width = max(1, self.pixmap.width())
        image_height = max(1, self.pixmap.height())
        center_x = state.center_norm_x * image_width
        center_y = state.center_norm_y * image_height
        delta_x = float(widget_pos.x()) - self.width() / 2.0
        delta_y = float(widget_pos.y()) - self.height() / 2.0
        image_x_under_mouse = center_x + delta_x / old_scale
        image_y_under_mouse = center_y + delta_y / old_scale
        new_center_x = image_x_under_mouse - delta_x / new_scale
        new_center_y = image_y_under_mouse - delta_y / new_scale

        self.camera_state = ViewerState(
            fit_mode=False,
            scale=new_scale,
            center_norm_x=new_center_x / image_width,
            center_norm_y=new_center_y / image_height,
            display_width=image_width,
            display_height=image_height,
        )
        self.update()
        if not self._suppress_camera_signal:
            self.camera_changed.emit(self.capture_camera_state())

    def _pan_by(self, delta: QPointF) -> None:
        if not self.has_image() or self.pixmap is None:
            return
        state = self.effective_state()
        scale = max(self.min_scale, float(state.scale))
        image_width = max(1, self.pixmap.width())
        image_height = max(1, self.pixmap.height())
        center_x = state.center_norm_x * image_width - float(delta.x()) / scale
        center_y = state.center_norm_y * image_height - float(delta.y()) / scale
        self.camera_state = ViewerState(
            fit_mode=False,
            scale=scale,
            center_norm_x=center_x / image_width,
            center_norm_y=center_y / image_height,
            display_width=image_width,
            display_height=image_height,
        )
        self.update()
        if not self._suppress_camera_signal:
            self.camera_changed.emit(self.capture_camera_state())

    def _target_rect_for_state(self, state: ViewerState) -> Optional[QRectF]:
        if not self.has_image() or self.pixmap is None:
            return None
        scale = max(self.min_scale, float(state.scale))
        image_width = self.pixmap.width()
        image_height = self.pixmap.height()
        center_x = state.center_norm_x * image_width
        center_y = state.center_norm_y * image_height
        x = self.width() / 2.0 - center_x * scale
        y = self.height() / 2.0 - center_y * scale
        return QRectF(x, y, image_width * scale, image_height * scale)

    def _minimap_image_rect(self) -> Optional[Tuple[QRectF, int, int]]:
        if not self.show_minimap or not self.has_image() or self.pixmap is None:
            return None
        image_width = max(1, self.pixmap.width())
        image_height = max(1, self.pixmap.height())
        max_width, max_height = 170, 120
        margin = 12
        mini_scale = min(max_width / image_width, max_height / image_height)
        map_width = max(40, int(image_width * mini_scale))
        map_height = max(40, int(image_height * mini_scale))
        x = self.width() - map_width - margin
        y = self.height() - map_height - margin
        if x < margin or y < margin:
            return None
        return QRectF(x, y, map_width, map_height), image_width, image_height

    def _minimap_norm_from_pos(
        self,
        pos: QPointF,
        *,
        require_inside: bool,
    ) -> Optional[Tuple[float, float]]:
        info = self._minimap_image_rect()
        if info is None:
            return None
        image_rect, _width, _height = info
        if require_inside and not image_rect.contains(pos):
            return None
        nx = (pos.x() - image_rect.x()) / max(1.0, image_rect.width())
        ny = (pos.y() - image_rect.y()) / max(1.0, image_rect.height())
        return max(0.0, min(1.0, float(nx))), max(0.0, min(1.0, float(ny)))

    def _set_camera_from_minimap(
        self,
        nx: float,
        ny: float,
        scale: Optional[float] = None,
    ) -> None:
        if not self.has_image() or self.pixmap is None:
            return
        state = self.effective_state()
        new_scale = float(scale if scale is not None else state.scale)
        new_scale = max(self.min_scale, min(self.max_scale, new_scale))
        self.camera_state = ViewerState(
            fit_mode=False,
            scale=new_scale,
            center_norm_x=max(0.0, min(1.0, float(nx))),
            center_norm_y=max(0.0, min(1.0, float(ny))),
            display_width=self.pixmap.width(),
            display_height=self.pixmap.height(),
        )
        self.update()
        if not self._suppress_camera_signal:
            self.camera_changed.emit(self.capture_camera_state())

    def _handle_minimap_click(self, pos: QPointF) -> bool:
        norm = self._minimap_norm_from_pos(pos, require_inside=True)
        if norm is None:
            return False
        self._minimap_dragging = True
        self._set_camera_from_minimap(norm[0], norm[1])
        return True

    def _handle_minimap_drag(self, pos: QPointF) -> bool:
        if not self._minimap_dragging:
            return False
        norm = self._minimap_norm_from_pos(pos, require_inside=False)
        if norm is None:
            return False
        self._set_camera_from_minimap(norm[0], norm[1])
        return True

    def _handle_minimap_wheel(self, pos: QPointF, delta_y: int) -> bool:
        norm = self._minimap_norm_from_pos(pos, require_inside=True)
        if norm is None or delta_y == 0:
            return False
        state = self.effective_state()
        factor = 1.15 ** (delta_y / 120.0)
        new_scale = max(self.min_scale, min(self.max_scale, float(state.scale) * factor))
        self._set_camera_from_minimap(norm[0], norm[1], scale=new_scale)
        return True

    def wheelEvent(self, event) -> None:  # type: ignore[override]
        delta_y = event.angleDelta().y()
        if delta_y == 0:
            event.ignore()
            return
        if self._handle_minimap_wheel(event.position(), delta_y):
            event.accept()
            return
        factor = 1.15 ** (delta_y / 120.0)
        self._zoom_at(event.position(), factor)
        event.accept()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton and self.has_image():
            if self._handle_minimap_click(event.position()):
                event.accept()
                return
            self._dragging = True
            self._pan_last_mouse_pos = event.position()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._minimap_dragging and self.has_image():
            self._handle_minimap_drag(event.position())
            event.accept()
            return
        if self._dragging and self.has_image():
            delta = event.position() - self._pan_last_mouse_pos
            self._pan_last_mouse_pos = event.position()
            self._pan_by(delta)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton and self._minimap_dragging:
            self._minimap_dragging = False
            event.accept()
            return
        if event.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            self._pan_last_mouse_pos = event.position()
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton and self.has_image():
            state = self.effective_state()
            if abs(state.scale - self.fit_scale()) < 0.0005:
                self.actual_size()
            else:
                self.fit_to_window()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self.update()

    def _draw_canvas_info(self, painter: QPainter) -> None:
        if not self.info_text:
            return
        metrics = painter.fontMetrics()
        text_rect = metrics.boundingRect(self.info_text).adjusted(-10, -5, 10, 5)
        text_rect.moveTopLeft(QPoint(max(8, (self.width() - text_rect.width()) // 2), 8))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 155))
        painter.drawRoundedRect(QRectF(text_rect), 5, 5)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(text_rect, Qt.AlignCenter, self.info_text)

    def _draw_canvas_minimap(self, painter: QPainter, state: ViewerState) -> None:
        info = self._minimap_image_rect()
        if info is None or self.pixmap is None:
            return
        image_rect, image_width, image_height = info
        x = int(image_rect.x())
        y = int(image_rect.y())
        map_width = int(image_rect.width())
        map_height = int(image_rect.height())

        outer = QRectF(x - 5, y - 5, map_width + 10, map_height + 10)
        painter.setPen(QColor(255, 255, 255, 80))
        painter.setBrush(QColor(0, 0, 0, 145))
        painter.drawRoundedRect(outer, 6, 6)
        image_rect = QRectF(x, y, map_width, map_height)
        painter.setPen(QColor(255, 255, 255, 120))
        painter.setBrush(QColor(120, 120, 120, 120))
        painter.drawRect(image_rect)

        painter.save()
        painter.setOpacity(0.58)
        painter.drawPixmap(image_rect, self.pixmap, QRectF(self.pixmap.rect()))
        painter.restore()

        zoom = max(0.0001, float(state.scale))
        visible_width = self.width() / zoom
        visible_height = self.height() / zoom
        center_x = state.center_norm_x * image_width
        center_y = state.center_norm_y * image_height
        left = max(0.0, min(float(image_width), center_x - visible_width / 2.0))
        top = max(0.0, min(float(image_height), center_y - visible_height / 2.0))
        right = max(0.0, min(float(image_width), center_x + visible_width / 2.0))
        bottom = max(0.0, min(float(image_height), center_y + visible_height / 2.0))
        view_rect = QRectF(
            x + (left / image_width) * map_width,
            y + (top / image_height) * map_height,
            max(2.0, ((right - left) / image_width) * map_width),
            max(2.0, ((bottom - top) / image_height) * map_height),
        )
        painter.setPen(QColor(255, 255, 255, 230))
        painter.setBrush(QColor(255, 255, 255, 35))
        painter.drawRect(view_rect)

    def _paint_images(self, painter: QPainter, target: QRectF) -> None:
        if not self.has_image() or self.pixmap is None:
            return
        painter.save()
        painter.setOpacity(self.main_opacity)
        painter.drawPixmap(target, self.pixmap, QRectF(self.pixmap.rect()))
        painter.restore()

        if self.overlay_pixmap is not None and not self.overlay_pixmap.isNull():
            painter.save()
            painter.setOpacity(self.overlay_opacity)
            painter.drawPixmap(target, self.overlay_pixmap, QRectF(self.overlay_pixmap.rect()))
            painter.restore()

        border_pen = QPen(image_border_color_for_background(self.bg_color), 2)
        border_pen.setCosmetic(True)
        painter.setPen(border_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(target)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        try:
            painter.fillRect(self.rect(), self.bg_color)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            if not self.has_image():
                painter.setPen(QColor(235, 235, 235))
                painter.drawText(self.rect(), Qt.AlignCenter, self._message)
                return

            state = self.effective_state()
            target = self._target_rect_for_state(state)
            if target is None:
                return

            self._paint_images(painter, target)
            self._draw_canvas_info(painter)
            self._draw_canvas_minimap(painter, state)

            percent = max(self.min_scale, float(state.scale)) * 100.0
            zoom_text = f"Zoom : {percent:.0f}%" if percent >= 10 else f"Zoom : {percent:.1f}%"
            metrics = painter.fontMetrics()
            text_rect = metrics.boundingRect(zoom_text).adjusted(-7, -4, 7, 4)
            text_rect.moveTopLeft(QPoint(8, 8))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, 150))
            painter.drawRoundedRect(QRectF(text_rect), 4, 4)
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(text_rect, Qt.AlignCenter, zoom_text)
        finally:
            painter.end()

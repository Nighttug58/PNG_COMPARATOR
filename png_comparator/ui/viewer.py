from __future__ import annotations

import json
from typing import Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..models import DrawingItem, ViewerState
from ..utils import canonical_image_key, color_to_tuple, image_border_color_for_background


class CompareImageCanvas(QWidget):
    """Canvas unique de visualisation et comparaison.

    Il dessine l'image avec QPainter et n'utilise aucune scrollbar Qt.
    Les deux canvases de comparaison lisent exactement le même ViewerState
    (scale + centre normalisé), ce qui évite les dérives de synchro.
    """

    camera_changed = Signal(object)
    drawing_changed = Signal()
    canvas_activated = Signal(object)

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
        self.camera_state = ViewerState(fit_mode=True, scale=1.0, center_norm_x=0.5, center_norm_y=0.5)
        self._dragging = False
        self._minimap_dragging = False
        self._last_mouse_pos = QPointF()
        self._suppress_camera_signal = False
        self._message = "Aucune image sélectionnée"
        self.show_minimap = True
        self.info_text = ""
        self.min_scale = 0.10
        self.max_scale = 40.0
        # V2.70+ : la qualité affichée est gérée uniquement par "Taille max image affichée".
        # Plus de bascule automatique/manuelle en pleine qualité.

        # V2.55 : dessin/screenshot. Les dessins sont stockés par chemin image
        # en coordonnées image, donc ils suivent naturellement zoom/pan.
        self.drawing_enabled = False
        self.drawing_tool = "freehand"
        self.drawing_color: Tuple[int, int, int] = (255, 40, 40)
        self.drawing_width = 4
        self.drawings_by_path: Dict[str, List[DrawingItem]] = {}
        self.drawing_redo_by_path: Dict[str, List[DrawingItem]] = {}
        self._drawing_active = False
        self._drawing_points: List[Tuple[float, float]] = []
        self.drawings_visible = True
        self._eraser_removed_items: List[DrawingItem] = []

    def has_image(self) -> bool:
        return self.pixmap is not None and not self.pixmap.isNull()

    def set_background(self, color: QColor) -> None:
        self.bg_color = QColor(color)
        self.update()

    def set_inspection_overlays(self, *, minimap: Optional[bool] = None, info_text: Optional[str] = None, **_ignored) -> None:
        if minimap is not None:
            self.show_minimap = bool(minimap)
        if info_text is not None:
            self.info_text = str(info_text)
        self.update()

    def set_loading(self, path: Optional[str], preserve_view: bool = True, state_override: Optional[ViewerState] = None) -> None:
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
            self.camera_state = ViewerState(fit_mode=True, scale=1.0, center_norm_x=0.5, center_norm_y=0.5)
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

    def set_qimage(self, path: str, image: QImage, _original_w: int, _original_h: int, preserve_view: Optional[bool] = None) -> None:
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
        self.original_image_width = int(_original_w) if int(_original_w or 0) > 0 else pixmap.width()
        self.original_image_height = int(_original_h) if int(_original_h or 0) > 0 else pixmap.height()
        self._message = ""

        if not had_image and self.camera_state.fit_mode:
            self.fit_to_window(emit_change=False)

        self.update()

    def fit_scale(self) -> float:
        if not self.has_image():
            return 1.0
        w = max(1, self.width())
        h = max(1, self.height())
        iw = max(1, self.pixmap.width())
        ih = max(1, self.pixmap.height())
        return max(self.min_scale, min(self.max_scale, min(w / iw, h / ih) * 0.98))

    def effective_state(self) -> ViewerState:
        if not self.has_image():
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
        state = self.capture_camera_state()
        return state if state is not None else ViewerState(fit_mode=True)

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
        if not self.has_image():
            self.camera_state = ViewerState(
                fit_mode=False,
                scale=max(self.min_scale, min(self.max_scale, float(state.scale))),
                center_norm_x=float(state.center_norm_x),
                center_norm_y=float(state.center_norm_y),
                display_width=int(state.display_width),
                display_height=int(state.display_height),
            )
            return
        self.camera_state = ViewerState(
            fit_mode=False,
            scale=max(self.min_scale, min(self.max_scale, float(state.scale))),
            center_norm_x=float(state.center_norm_x),
            center_norm_y=float(state.center_norm_y),
            display_width=self.pixmap.width(),
            display_height=self.pixmap.height(),
        )
        self.update()
        if emit_change and not self._suppress_camera_signal:
            self.camera_changed.emit(self.capture_camera_state())

    def fit_to_window(self, emit_change: bool = True) -> None:
        if not self.has_image():
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
        if not self.has_image():
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
        if not self.has_image():
            return
        state = self.effective_state()
        old_scale = max(self.min_scale, min(self.max_scale, float(state.scale)))
        new_scale = max(self.min_scale, min(self.max_scale, old_scale * factor))
        if abs(new_scale - old_scale) < 1e-9:
            return
        iw = max(1, self.pixmap.width())
        ih = max(1, self.pixmap.height())
        cx = state.center_norm_x * iw
        cy = state.center_norm_y * ih
        dx = float(widget_pos.x()) - self.width() / 2.0
        dy = float(widget_pos.y()) - self.height() / 2.0
        image_x_under_mouse = cx + dx / old_scale
        image_y_under_mouse = cy + dy / old_scale
        new_cx = image_x_under_mouse - dx / new_scale
        new_cy = image_y_under_mouse - dy / new_scale
        self.camera_state = ViewerState(
            fit_mode=False,
            scale=new_scale,
            center_norm_x=new_cx / iw,
            center_norm_y=new_cy / ih,
            display_width=iw,
            display_height=ih,
        )
        self.update()
        if not self._suppress_camera_signal:
            self.camera_changed.emit(self.capture_camera_state())
    def _pan_by(self, delta: QPointF) -> None:
        if not self.has_image():
            return
        state = self.effective_state()
        scale = max(self.min_scale, float(state.scale))
        iw = max(1, self.pixmap.width())
        ih = max(1, self.pixmap.height())
        cx = state.center_norm_x * iw - float(delta.x()) / scale
        cy = state.center_norm_y * ih - float(delta.y()) / scale
        self.camera_state = ViewerState(
            fit_mode=False,
            scale=scale,
            center_norm_x=cx / iw,
            center_norm_y=cy / ih,
            display_width=iw,
            display_height=ih,
        )
        self.update()
        if not self._suppress_camera_signal:
            self.camera_changed.emit(self.capture_camera_state())

    def _minimap_image_rect(self) -> Optional[Tuple[QRectF, int, int]]:
        if not getattr(self, "show_minimap", False) or not self.has_image():
            return None
        iw = max(1, self.pixmap.width())
        ih = max(1, self.pixmap.height())
        max_w, max_h = 170, 120
        margin = 12
        mini_scale = min(max_w / iw, max_h / ih)
        map_w = max(40, int(iw * mini_scale))
        map_h = max(40, int(ih * mini_scale))
        x = self.width() - map_w - margin
        y = self.height() - map_h - margin
        if x < margin or y < margin:
            return None
        return QRectF(x, y, map_w, map_h), iw, ih

    def _minimap_norm_from_pos(self, pos: QPointF, *, require_inside: bool) -> Optional[Tuple[float, float]]:
        info = self._minimap_image_rect()
        if info is None:
            return None
        img_rect, _iw, _ih = info
        if require_inside and not img_rect.contains(pos):
            return None
        nx = (pos.x() - img_rect.x()) / max(1.0, img_rect.width())
        ny = (pos.y() - img_rect.y()) / max(1.0, img_rect.height())
        return max(0.0, min(1.0, float(nx))), max(0.0, min(1.0, float(ny)))

    def _minimap_norm_at(self, pos: QPointF) -> Optional[Tuple[float, float]]:
        return self._minimap_norm_from_pos(pos, require_inside=True)

    def _set_camera_from_minimap(self, nx: float, ny: float, scale: Optional[float] = None) -> None:
        if not self.has_image():
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
        norm = self._minimap_norm_at(pos)
        if norm is None:
            return False
        self._minimap_dragging = True
        self._set_camera_from_minimap(norm[0], norm[1])
        return True

    def _handle_minimap_drag(self, pos: QPointF) -> bool:
        if not getattr(self, "_minimap_dragging", False):
            return False
        norm = self._minimap_norm_from_pos(pos, require_inside=False)
        if norm is None:
            return False
        self._set_camera_from_minimap(norm[0], norm[1])
        return True

    def _handle_minimap_wheel(self, pos: QPointF, delta_y: int) -> bool:
        norm = self._minimap_norm_at(pos)
        if norm is None or delta_y == 0:
            return False
        state = self.effective_state()
        steps = delta_y / 120.0
        factor = 1.15 ** steps
        new_scale = max(self.min_scale, min(self.max_scale, float(state.scale) * factor))
        self._set_camera_from_minimap(norm[0], norm[1], scale=new_scale)
        return True

    def set_drawing_enabled(self, enabled: bool) -> None:
        self.drawing_enabled = bool(enabled)
        if not enabled:
            self._drawing_active = False
            self._drawing_points = []
            self.unsetCursor()
        else:
            self.setCursor(Qt.CrossCursor)
        self.update()

    def set_drawing_tool(self, tool: str) -> None:
        self.drawing_tool = str(tool or "freehand")

    def set_drawing_color(self, color: QColor) -> None:
        if color.isValid():
            self.drawing_color = color_to_tuple(color)

    def set_drawing_width(self, width: int) -> None:
        self.drawing_width = max(1, min(80, int(width)))


    def toggle_drawings_visible(self) -> bool:
        self.drawings_visible = not self.drawings_visible
        self.update()
        return self.drawings_visible

    def _drawing_key(self) -> Optional[str]:
        return canonical_image_key(self.current_path) if self.current_path else None

    def _current_drawing_list(self) -> List[DrawingItem]:
        key = self._drawing_key()
        if not key:
            return []
        return self.drawings_by_path.setdefault(key, [])

    def _current_redo_list(self) -> List[DrawingItem]:
        key = self._drawing_key()
        if not key:
            return []
        return self.drawing_redo_by_path.setdefault(key, [])


    def _drawing_item_signature_runtime(self, item: DrawingItem) -> str:
        """Signature stable pour comparer des DrawingItem même après sauvegarde/session."""
        try:
            return json.dumps(
                {
                    "kind": item.kind,
                    "points": [[round(float(x), 4), round(float(y), 4)] for x, y in item.points],
                    "color": list(item.color),
                    "width": int(item.width),
                    "ref_width": int(item.ref_width),
                    "ref_height": int(item.ref_height),
                },
                sort_keys=True,
                ensure_ascii=False,
            )
        except Exception:
            return f"{item.kind}|{item.color}|{item.width}|{item.ref_width}|{item.ref_height}|{item.points}"

    def _visible_drawing_items(self, items: Optional[Sequence[DrawingItem]] = None) -> List[DrawingItem]:
        """Reconstruit les dessins visibles en appliquant les actions gomme/effacer.

        V2.77 : Effacer ne remplace plus toute la liste par une seule action.
        On garde l'historique en mémoire, et on applique les eraser_action au rendu.
        """
        source = list(items if items is not None else self._current_drawing_list())
        visible: List[DrawingItem] = []
        for item in source:
            if item.kind == "eraser_action":
                erased_ids = {id(erased) for erased in item.erased_items}
                erased_sigs = {self._drawing_item_signature_runtime(erased) for erased in item.erased_items}
                visible = [
                    drawing for drawing in visible
                    if id(drawing) not in erased_ids
                    and self._drawing_item_signature_runtime(drawing) not in erased_sigs
                ]
            elif item.kind in {"freehand", "line", "rect", "ellipse"} and item.points:
                visible.append(item)
        return visible

    def clear_current_drawings(self) -> None:
        key = self._drawing_key()
        if not key:
            return
        drawings = self.drawings_by_path.setdefault(key, [])
        visible_existing = self._visible_drawing_items(drawings)
        if visible_existing:
            action = DrawingItem(
                kind="eraser_action",
                points=[],
                color=tuple(self.drawing_color),
                width=int(self.drawing_width),
                ref_width=self.pixmap.width() if self.pixmap is not None else 0,
                ref_height=self.pixmap.height() if self.pixmap is not None else 0,
                erased_items=list(visible_existing),
            )
            # Ne pas écraser drawings_by_path[key] : sinon on perd l'historique
            # des boutons Dessin précédent / Dessin suivant.
            drawings.append(action)
            self.update()
            self.drawing_changed.emit()

    def undo_drawing(self) -> None:
        drawings = self._current_drawing_list()
        if not drawings:
            return
        item = drawings.pop()
        if item.kind == "eraser_action":
            # Annuler une gomme / un effacement global = restaurer les éléments supprimés.
            restored_ids = {id(existing) for existing in drawings}
            restored_sigs = {self._drawing_item_signature_runtime(existing) for existing in drawings}
            for erased in item.erased_items:
                sig = self._drawing_item_signature_runtime(erased)
                if id(erased) not in restored_ids and sig not in restored_sigs:
                    drawings.append(erased)
                    restored_ids.add(id(erased))
                    restored_sigs.add(sig)
        self._current_redo_list().append(item)
        self.update()
        self.drawing_changed.emit()

    def redo_drawing(self) -> None:
        redo = self._current_redo_list()
        if not redo:
            return
        item = redo.pop()
        drawings = self._current_drawing_list()
        if item.kind == "eraser_action":
            # V2.77 : on conserve l'historique et le rendu applique l'action.
            drawings.append(item)
        else:
            drawings.append(item)
        self.update()
        self.drawing_changed.emit()

    def _image_point_from_widget(self, pos: QPointF) -> Optional[Tuple[float, float]]:
        if not self.has_image():
            return None
        state = self.effective_state()
        target = self._target_rect_for_state(state)
        if target is None or target.width() <= 0 or target.height() <= 0:
            return None
        if not target.contains(pos):
            return None
        ix = (pos.x() - target.x()) / target.width() * self.pixmap.width()
        iy = (pos.y() - target.y()) / target.height() * self.pixmap.height()
        ix = max(0.0, min(float(self.pixmap.width()), float(ix)))
        iy = max(0.0, min(float(self.pixmap.height()), float(iy)))
        return ix, iy


    def _distance_point_to_segment(self, p: Tuple[float, float], a: Tuple[float, float], b: Tuple[float, float]) -> float:
        px, py = float(p[0]), float(p[1])
        ax, ay = float(a[0]), float(a[1])
        bx, by = float(b[0]), float(b[1])
        vx, vy = bx - ax, by - ay
        wx, wy = px - ax, py - ay
        length2 = vx * vx + vy * vy
        if length2 <= 0.000001:
            return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
        t = max(0.0, min(1.0, (wx * vx + wy * vy) / length2))
        cx, cy = ax + t * vx, ay + t * vy
        return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5

    def _drawing_item_hit_by_eraser(self, item: DrawingItem, current_point: Tuple[float, float], radius_current: float) -> bool:
        if not item.points or self.pixmap is None:
            return False
        cur_w = max(1.0, float(self.pixmap.width()))
        cur_h = max(1.0, float(self.pixmap.height()))
        ref_w = max(1.0, float(item.ref_width or cur_w))
        ref_h = max(1.0, float(item.ref_height or cur_h))
        point = (float(current_point[0]) / cur_w * ref_w, float(current_point[1]) / cur_h * ref_h)
        radius = float(radius_current) * ((ref_w / cur_w + ref_h / cur_h) / 2.0)
        points = list(item.points)
        if item.kind == "freehand":
            if len(points) == 1:
                return self._distance_point_to_segment(point, points[0], points[0]) <= radius
            return any(self._distance_point_to_segment(point, a, b) <= radius for a, b in zip(points, points[1:]))
        if item.kind == "line" and len(points) >= 2:
            return self._distance_point_to_segment(point, points[0], points[-1]) <= radius
        if item.kind in ("rect", "ellipse") and len(points) >= 2:
            x1, y1 = points[0]
            x2, y2 = points[-1]
            left, right = sorted((float(x1), float(x2)))
            top, bottom = sorted((float(y1), float(y2)))
            if item.kind == "rect":
                edges = [
                    ((left, top), (right, top)),
                    ((right, top), (right, bottom)),
                    ((right, bottom), (left, bottom)),
                    ((left, bottom), (left, top)),
                ]
                return any(self._distance_point_to_segment(point, a, b) <= radius for a, b in edges)
            cx = (left + right) / 2.0
            cy = (top + bottom) / 2.0
            rx = max(1.0, (right - left) / 2.0)
            ry = max(1.0, (bottom - top) / 2.0)
            # Approximation suffisante pour gomme : distance normalisée au bord de l'ellipse.
            value = ((point[0] - cx) / rx) ** 2 + ((point[1] - cy) / ry) ** 2
            return abs(value - 1.0) <= max(0.08, radius / max(rx, ry))
        return False

    def _erase_drawing_at(self, pos: QPointF) -> bool:
        point = self._image_point_from_widget(pos)
        if point is None:
            return False
        key = self._drawing_key()
        if not key:
            return False
        drawings = self.drawings_by_path.get(key, [])
        if not drawings:
            return False
        # V2.64 : la gomme utilise maintenant une taille en coordonnées image,
        # cohérente avec l'épaisseur des traits qui suit le zoom.
        # V2.77 : on gomme uniquement ce qui est réellement visible. Si Effacer
        # a ajouté une action d'historique, les anciens traits cachés ne doivent
        # pas être touchés par la gomme.
        radius = max(1.0, float(self.drawing_width))
        visible = self._visible_drawing_items(drawings)
        removed: List[DrawingItem] = []
        for item in visible:
            if self._drawing_item_hit_by_eraser(item, point, radius):
                removed.append(item)
        if removed:
            removed_ids = {id(item) for item in removed}
            removed_sigs = {self._drawing_item_signature_runtime(item) for item in removed}
            self.drawings_by_path[key] = [
                item for item in drawings
                if id(item) not in removed_ids
                and self._drawing_item_signature_runtime(item) not in removed_sigs
            ]
            self._eraser_removed_items.extend(removed)
            self.update()
            return True
        return False

    def _start_drawing(self, pos: QPointF) -> bool:
        point = self._image_point_from_widget(pos)
        if point is None:
            return False
        if self.drawing_tool == "eraser":
            self._drawing_active = True
            self._drawing_points = []
            self._eraser_removed_items = []
            self.setCursor(Qt.CrossCursor)
            self._erase_drawing_at(pos)
            return True
        self._drawing_active = True
        self._drawing_points = [point]
        self.setCursor(Qt.CrossCursor)
        self.update()
        return True

    def _update_drawing(self, pos: QPointF) -> bool:
        if not self._drawing_active:
            return False
        if self.drawing_tool == "eraser":
            self._erase_drawing_at(pos)
            return True
        point = self._image_point_from_widget(pos)
        if point is None:
            return True
        if self.drawing_tool == "freehand":
            self._drawing_points.append(point)
        else:
            self._drawing_points = [self._drawing_points[0], point]
        self.update()
        return True

    def _finish_drawing(self) -> bool:
        if not self._drawing_active:
            return False
        self._drawing_active = False
        points = list(self._drawing_points)
        self._drawing_points = []
        self.unsetCursor()
        if self.drawing_tool == "eraser":
            removed = list(self._eraser_removed_items)
            self._eraser_removed_items = []
            if removed:
                action = DrawingItem(
                    kind="eraser_action",
                    points=[],
                    color=tuple(self.drawing_color),
                    width=int(self.drawing_width),
                    ref_width=self.pixmap.width() if self.pixmap is not None else 0,
                    ref_height=self.pixmap.height() if self.pixmap is not None else 0,
                    erased_items=removed,
                )
                self._current_drawing_list().append(action)
                key = self._drawing_key()
                if key:
                    self.drawing_redo_by_path[key] = []
            self.update()
            if removed:
                self.drawing_changed.emit()
            return True
        if len(points) < 2:
            self.update()
            return True
        item = DrawingItem(
            kind=self.drawing_tool,
            points=points,
            color=tuple(self.drawing_color),
            width=int(self.drawing_width),
            ref_width=self.pixmap.width() if self.pixmap is not None else 0,
            ref_height=self.pixmap.height() if self.pixmap is not None else 0,
        )
        self._current_drawing_list().append(item)
        key = self._drawing_key()
        if key:
            self.drawing_redo_by_path[key] = []
        self.update()
        self.drawing_changed.emit()
        return True

    def _draw_one_drawing_item(self, painter: QPainter, item: DrawingItem, target: QRectF) -> None:
        if not item.points:
            return
        # V2.64 : l'épaisseur du dessin suit maintenant le zoom de l'image.
        # Avant, le pen était cosmetic=True, donc le trait gardait toujours la
        # même épaisseur écran. Ici, l'épaisseur est calculée depuis la taille
        # de référence du dessin vers la taille affichée dans le viewer.
        pen = QPen(QColor(*item.color))
        pen.setStyle(Qt.SolidLine)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setBrush(Qt.NoBrush)

        # V2.60 : projection stable. Les points sont enregistrés selon la taille
        # du pixmap au moment du dessin, puis reprojetés sur le target actuel.
        # Cela évite les dessins décalés après changement d'image / recharge preview.
        ref_w = float(item.ref_width or (self.pixmap.width() if self.pixmap is not None else 1))
        ref_h = float(item.ref_height or (self.pixmap.height() if self.pixmap is not None else 1))
        ref_w = max(1.0, ref_w)
        ref_h = max(1.0, ref_h)

        stroke_scale = ((target.width() / ref_w) + (target.height() / ref_h)) / 2.0
        stroke_width = max(0.75, float(item.width) * max(0.0001, stroke_scale))
        pen.setWidthF(stroke_width)
        pen.setCosmetic(False)
        painter.setPen(pen)

        def to_widget(point: Tuple[float, float]) -> QPointF:
            return QPointF(
                target.x() + (float(point[0]) / ref_w) * target.width(),
                target.y() + (float(point[1]) / ref_h) * target.height(),
            )

        pts = [to_widget(p) for p in item.points]
        if item.kind == "freehand":
            for a, b in zip(pts, pts[1:]):
                painter.drawLine(a, b)
        elif item.kind == "line" and len(pts) >= 2:
            painter.drawLine(pts[0], pts[-1])
        elif item.kind in ("rect", "ellipse") and len(pts) >= 2:
            rect = QRectF(pts[0], pts[-1]).normalized()
            if item.kind == "rect":
                painter.drawRect(rect)
            else:
                painter.drawEllipse(rect)

    def _draw_all_drawings(self, painter: QPainter, target: QRectF) -> None:
        if not self.has_image() or not self.drawings_visible:
            return
        key = self._drawing_key()
        if key:
            for item in self._visible_drawing_items(self.drawings_by_path.get(key, [])):
                self._draw_one_drawing_item(painter, item, target)
        if self._drawing_active and self.drawing_tool != "eraser" and len(self._drawing_points) >= 1:
            preview = DrawingItem(
                kind=self.drawing_tool,
                points=list(self._drawing_points),
                color=tuple(self.drawing_color),
                width=int(self.drawing_width),
                ref_width=self.pixmap.width() if self.pixmap is not None else 0,
                ref_height=self.pixmap.height() if self.pixmap is not None else 0,
            )
            self._draw_one_drawing_item(painter, preview, target)


    def _draw_eraser_cursor(self, painter: QPainter, target: QRectF) -> None:
        """Affiche le cercle d'action de la gomme sans l'enregistrer dans les dessins."""
        if not (self.drawing_enabled and self.drawing_tool == "eraser" and self.has_image()):
            return
        if not target.contains(self._last_mouse_pos):
            return
        iw = max(1.0, float(self.pixmap.width() if self.pixmap is not None else 1))
        ih = max(1.0, float(self.pixmap.height() if self.pixmap is not None else 1))
        screen_radius = max(3.0, float(self.drawing_width) * ((target.width() / iw + target.height() / ih) / 2.0))
        pen = QPen(QColor(255, 255, 255, 230))
        pen.setWidthF(1.25)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(QColor(0, 0, 0, 35))
        center = self._last_mouse_pos
        painter.drawEllipse(QRectF(center.x() - screen_radius, center.y() - screen_radius, screen_radius * 2.0, screen_radius * 2.0))

    def wheelEvent(self, event) -> None:  # type: ignore[override]
        if event.angleDelta().y() == 0:
            event.ignore()
            return
        if self._handle_minimap_wheel(event.position(), event.angleDelta().y()):
            event.accept()
            return
        steps = event.angleDelta().y() / 120.0
        factor = 1.15 ** steps
        self._zoom_at(event.position(), factor)
        event.accept()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton and self.has_image():
            self.canvas_activated.emit(self)
            if self._handle_minimap_click(event.position()):
                event.accept()
                return
            if self.drawing_enabled and self._start_drawing(event.position()):
                event.accept()
                return
            self._dragging = True
            self._last_mouse_pos = event.position()
            self._pan_last_mouse_pos = event.position()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        self._last_mouse_pos = event.position()
        if self.drawing_enabled and self.drawing_tool == "eraser" and self.has_image():
            self.update()
        if self._minimap_dragging and self.has_image():
            self._handle_minimap_drag(event.position())
            event.accept()
            return
        if self._drawing_active and self.has_image():
            self._update_drawing(event.position())
            event.accept()
            return
        if self._dragging and self.has_image():
            # _last_mouse_pos vient d'être mis à jour pour le curseur gomme ; on recalcule
            # le delta depuis la position précédente conservée temporairement.
            delta = event.position() - getattr(self, "_pan_last_mouse_pos", event.position())
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
        if event.button() == Qt.LeftButton and self._drawing_active:
            self._finish_drawing()
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

    def _target_rect_for_state(self, state: ViewerState) -> Optional[QRectF]:
        if not self.has_image():
            return None
        scale = max(self.min_scale, float(state.scale))
        iw = self.pixmap.width()
        ih = self.pixmap.height()
        cx = state.center_norm_x * iw
        cy = state.center_norm_y * ih
        x = self.width() / 2.0 - cx * scale
        y = self.height() / 2.0 - cy * scale
        return QRectF(x, y, iw * scale, ih * scale)

    def _draw_canvas_info(self, painter: QPainter) -> None:
        if not self.info_text:
            return
        fm = painter.fontMetrics()
        text_rect = fm.boundingRect(self.info_text).adjusted(-10, -5, 10, 5)
        text_rect.moveTopLeft(QPoint(max(8, (self.width() - text_rect.width()) // 2), 8))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 155))
        painter.drawRoundedRect(QRectF(text_rect), 5, 5)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(text_rect, Qt.AlignCenter, self.info_text)

    def _draw_canvas_minimap(self, painter: QPainter, state: ViewerState) -> None:
        info = self._minimap_image_rect()
        if info is None:
            return
        img_rect, iw, ih = info
        x = int(img_rect.x())
        y = int(img_rect.y())
        map_w = int(img_rect.width())
        map_h = int(img_rect.height())
        outer = QRectF(x - 5, y - 5, map_w + 10, map_h + 10)
        painter.setPen(QColor(255, 255, 255, 80))
        painter.setBrush(QColor(0, 0, 0, 145))
        painter.drawRoundedRect(outer, 6, 6)
        img_rect = QRectF(x, y, map_w, map_h)
        painter.setPen(QColor(255, 255, 255, 120))
        painter.setBrush(QColor(120, 120, 120, 120))
        painter.drawRect(img_rect)

        # V2.29 : aperçu réel de l'image dans la mini-map du comparateur.
        if self.pixmap is not None and not self.pixmap.isNull():
            painter.save()
            painter.setOpacity(0.58)
            painter.drawPixmap(img_rect, self.pixmap, QRectF(self.pixmap.rect()))
            painter.restore()

        zoom = max(0.0001, float(state.scale))
        visible_w = self.width() / zoom
        visible_h = self.height() / zoom
        cx = state.center_norm_x * iw
        cy = state.center_norm_y * ih
        left = max(0.0, min(float(iw), cx - visible_w / 2.0))
        top = max(0.0, min(float(ih), cy - visible_h / 2.0))
        right = max(0.0, min(float(iw), cx + visible_w / 2.0))
        bottom = max(0.0, min(float(ih), cy + visible_h / 2.0))
        view_rect = QRectF(
            x + (left / iw) * map_w,
            y + (top / ih) * map_h,
            max(2.0, ((right - left) / iw) * map_w),
            max(2.0, ((bottom - top) / ih) * map_h),
        )
        painter.setPen(QColor(255, 255, 255, 230))
        painter.setBrush(QColor(255, 255, 255, 35))
        painter.drawRect(view_rect)

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
            scale = max(self.min_scale, float(state.scale))
            target = self._target_rect_for_state(state)
            if target is None:
                return
            self._paint_image_and_drawings(painter, target, draw_eraser_cursor=True, draw_border=True)

            self._draw_canvas_info(painter)
            self._draw_canvas_minimap(painter, state)

            percent = scale * 100.0
            zoom_text = f"Zoom : {percent:.0f}%" if percent >= 10 else f"Zoom : {percent:.1f}%"
            fm = painter.fontMetrics()
            text_rect = fm.boundingRect(zoom_text).adjusted(-7, -4, 7, 4)
            text_rect.moveTopLeft(QPoint(8, 8))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, 150))
            painter.drawRoundedRect(QRectF(text_rect), 4, 4)
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(text_rect, Qt.AlignCenter, zoom_text)
        finally:
            painter.end()

    def _paint_image_and_drawings(
        self,
        painter: QPainter,
        target: QRectF,
        *,
        draw_eraser_cursor: bool = False,
        draw_border: bool = False,
    ) -> None:
        """Peint seulement le contenu image utile."""
        if not self.has_image() or self.pixmap is None:
            return
        iw = self.pixmap.width()
        ih = self.pixmap.height()
        painter.save()
        painter.setOpacity(self.main_opacity)
        painter.drawPixmap(target, self.pixmap, QRectF(0, 0, iw, ih))
        painter.restore()

        if self.overlay_pixmap is not None and not self.overlay_pixmap.isNull():
            painter.save()
            painter.setOpacity(self.overlay_opacity)
            painter.drawPixmap(target, self.overlay_pixmap, QRectF(self.overlay_pixmap.rect()))
            painter.restore()

        self._draw_all_drawings(painter, target)
        if draw_eraser_cursor:
            self._draw_eraser_cursor(painter, target)

        if draw_border:
            border_pen = QPen(image_border_color_for_background(self.bg_color), 2)
            border_pen.setCosmetic(True)
            painter.setPen(border_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(target)

    def grab_clean_content(self) -> QPixmap:
        """Capture le cadre viewer sans overlays UI.

        Inclus : fond, image affichée, éventuelle image de superposition visible,
        dessins. Exclus : zoom, mini-map, flèches, infos et curseur gomme.
        """
        pixmap = QPixmap(max(1, self.width()), max(1, self.height()))
        pixmap.fill(self.bg_color)
        painter = QPainter(pixmap)
        try:
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            if self.has_image():
                target = self._target_rect_for_state(self.effective_state())
                if target is not None:
                    self._paint_image_and_drawings(painter, target, draw_eraser_cursor=False, draw_border=False)
            else:
                painter.setPen(QColor(235, 235, 235))
                painter.drawText(QRectF(pixmap.rect()), Qt.AlignCenter, self._message)
        finally:
            painter.end()
        return pixmap

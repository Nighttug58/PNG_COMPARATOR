from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QPoint, QSize, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMenu,
    QMessageBox, QPushButton, QScrollArea, QToolButton, QVBoxLayout, QWidget,
)

from ..config import APP_ROOT_DIR
from .screenshot_preview import ScreenshotPreviewCanvas


class ScreenshotLibraryDialog(QDialog):
    """Bibliothèque flottante simple pour screenshots du viewer, style bandeau Snagit."""

    def __init__(self, tab: "CamTab", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.tab = tab
        self.viewer = tab.viewer
        self.setWindowTitle("Screenshots")
        self.setModal(False)
        self.resize(980, 720)
        self.current_pixmap: Optional[QPixmap] = None
        self.current_path: Optional[Path] = None
        self.screenshot_paths: List[Path] = []
        self.thumb_buttons: Dict[str, QToolButton] = {}
        self.root_dir = self.default_root_dir()
        self.confirm_delete_enabled = True

        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("Nom :"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Nom optionnel pour la prochaine capture / enregistrer sous")
        self.name_edit.setMinimumWidth(260)
        top.addWidget(self.name_edit)
        self.btn_capture = QPushButton("Capturer viewer")
        self.btn_capture.setToolTip("Sauvegarde uniquement l'image visible + les dessins, sans zoom/minimap/flèches.")
        self.btn_capture.clicked.connect(self.capture_current_viewer)
        top.addWidget(self.btn_capture)
        self.btn_browse = QPushButton("Parcourir")
        self.btn_browse.setToolTip("Choisir un dossier de screenshots à afficher.")
        self.btn_browse.clicked.connect(self.browse_root_dir)
        top.addWidget(self.btn_browse)
        self.btn_refresh = QPushButton("Actualiser")
        self.btn_refresh.clicked.connect(lambda _checked=False: self.refresh_list())
        top.addWidget(self.btn_refresh)
        self.btn_open_folder = QPushButton("Ouvrir dossier")
        self.btn_open_folder.setToolTip("Ouvre le dossier racine contenant les screenshots du logiciel.")
        self.btn_open_folder.clicked.connect(self.open_screenshots_folder)
        top.addWidget(self.btn_open_folder)
        self.btn_delete = QPushButton("🗑 Supprimer")
        self.btn_delete.setToolTip("Supprime le screenshot sélectionné. Clic droit : activer/désactiver la confirmation.")
        self.btn_delete.clicked.connect(self.delete_selected_screenshot)
        self.btn_delete.setContextMenuPolicy(Qt.CustomContextMenu)
        self.btn_delete.customContextMenuRequested.connect(self.open_delete_options_menu)
        top.addWidget(self.btn_delete)
        layout.addLayout(top)

        controls = QHBoxLayout()
        self.btn_fit = QPushButton("Ajuster")
        self.btn_fit.setToolTip("Réinitialise le zoom du viewer screenshots. Molette = zoom, clic gauche + drag = pan.")
        self.btn_fit.clicked.connect(lambda: self.preview_canvas.fit_to_window())
        controls.addWidget(self.btn_fit)
        self.btn_save_as = QPushButton("Enregistrer sous")
        self.btn_save_as.clicked.connect(self.save_selected_as)
        controls.addWidget(self.btn_save_as)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.path_label = QLabel(str(self.root_dir))
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.path_label)

        self.preview_canvas = ScreenshotPreviewCanvas(self)
        layout.addWidget(self.preview_canvas, 1)

        thumb_title = QLabel("Captures")
        thumb_title.setStyleSheet("font-weight: bold; color: #f0f0f0;")
        layout.addWidget(thumb_title)

        self.thumb_scroll = QScrollArea()
        self.thumb_scroll.setWidgetResizable(True)
        self.thumb_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.thumb_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.thumb_scroll.setFixedHeight(116)
        self.thumb_container = QWidget()
        self.thumb_layout = QHBoxLayout(self.thumb_container)
        self.thumb_layout.setContentsMargins(6, 6, 6, 6)
        self.thumb_layout.setSpacing(8)
        self.thumb_layout.addStretch(1)
        self.thumb_scroll.setWidget(self.thumb_container)
        layout.addWidget(self.thumb_scroll)

        self.refresh_list()

    def default_root_dir(self) -> Path:
        try:
            window = self.tab.window()
            if hasattr(window, "exports_dir_path"):
                return Path(window.exports_dir_path()) / "screenshots"
        except Exception:
            pass
        return APP_ROOT_DIR / "exports" / "screenshots"

    def sanitize_name(self, value: str) -> str:
        value = str(value or "").strip()
        if not value:
            return ""
        value = re.sub(r"[^A-Za-z0-9._ -]+", "_", value)
        value = value.strip(" ._-")
        return value[:80]

    def current_record_info(self) -> Tuple[str, str, str]:
        record = self.tab.current_record()
        if record is None:
            return "REF", f"CAM{self.tab.cam_number}", "image"
        return record.ref, f"CAM{record.cam_number}", Path(record.path).stem

    def capture_current_viewer(self) -> None:
        record = self.tab.current_record()
        if record is None:
            self.tab.request_status_message.emit("Aucune image active pour le screenshot")
            return
        pixmap = self.viewer.grab_clean_content()
        if pixmap.isNull():
            QMessageBox.warning(self, "Screenshot impossible", "Le viewer n'a pas pu être capturé.")
            return
        ref, cam, stem = self.current_record_info()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder_name = f"{timestamp}_{ref}_{cam}"
        target_dir = self.root_dir / folder_name
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            QMessageBox.critical(self, "Dossier impossible", f"Impossible de créer le dossier screenshot :\n{exc}")
            return
        custom = self.sanitize_name(self.name_edit.text())
        image_name = f"{custom}.png" if custom else f"{stem}_screenshot_{timestamp}.png"
        image_path = target_dir / image_name
        if not pixmap.save(str(image_path), "PNG"):
            QMessageBox.critical(self, "Screenshot impossible", "Impossible d'enregistrer le screenshot.")
            return
        state = self.viewer.capture_state()
        metadata = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "reference": record.ref,
            "cam": record.cam_number,
            "source_image": record.path,
            "source_file": record.file_name,
            "screenshot_file": str(image_path),
            "capture_mode": "clean_image_plus_drawings",
            "excluded_overlays": ["zoom", "minimap", "nav_arrows", "viewer_ui"],
            "viewer": {
                "zoom_percent": round(float(state.scale) * 100.0, 3),
                "center_norm_x": float(state.center_norm_x),
                "center_norm_y": float(state.center_norm_y),
                "display_width": int(state.display_width),
                "display_height": int(state.display_height),
            },
            "background_rgb": list(self.tab.bg_colors[self.tab.active_bg_index]) if getattr(self.tab, "bg_colors", None) else [],
            "drawings_visible": bool(getattr(self.viewer, "drawings_visible", True)),
        }
        try:
            (target_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
            (target_dir / "viewer_state.json").write_text(json.dumps(metadata["viewer"], indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        self.name_edit.clear()
        self.tab.request_status_message.emit(f"Screenshot sauvegardé : {image_path}")
        self.refresh_list(select_path=image_path)

    def browse_root_dir(self) -> None:
        start = str(self.root_dir if self.root_dir.exists() else self.default_root_dir())
        path = QFileDialog.getExistingDirectory(self, "Choisir dossier screenshots", start)
        if not path:
            return
        self.root_dir = Path(path)
        self.current_path = None
        self.current_pixmap = None
        self.refresh_list()

    def _safe_mtime(self, path: Path) -> float:
        try:
            return path.stat().st_mtime if path.exists() else 0.0
        except Exception:
            return 0.0

    def _clear_thumb_layout(self) -> None:
        while self.thumb_layout.count() > 0:
            item = self.thumb_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.thumb_buttons.clear()

    def _short_name(self, path: Path, max_chars: int = 18) -> str:
        name = path.stem
        return name if len(name) <= max_chars else name[: max_chars - 1] + "…"

    def _make_thumbnail_icon(self, path: Path, selected: bool = False) -> QIcon:
        base = QPixmap(104, 64)
        base.fill(QColor(38, 42, 48))
        source = QPixmap(str(path))
        painter = QPainter(base)
        try:
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            if not source.isNull():
                scaled = source.scaled(98, 58, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                x = (base.width() - scaled.width()) // 2
                y = (base.height() - scaled.height()) // 2
                painter.drawPixmap(x, y, scaled)
            pen = QPen(QColor(255, 255, 255, 235), 1)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(1, 1, base.width() - 2, base.height() - 2)
            if selected:
                sel_pen = QPen(QColor(255, 105, 105), 3)
                sel_pen.setCosmetic(True)
                painter.setPen(sel_pen)
                painter.drawRect(3, 3, base.width() - 6, base.height() - 6)
        finally:
            painter.end()
        return QIcon(base)

    def _style_thumb_button(self, button: QToolButton, selected: bool) -> None:
        if selected:
            button.setStyleSheet(
                "QToolButton { background-color: rgba(200,70,70,0.45); color: white; border: 2px solid #ff8b8b; border-radius: 6px; padding: 3px; }"
                "QToolButton:hover { background-color: rgba(220,85,85,0.58); }"
            )
        else:
            button.setStyleSheet(
                "QToolButton { background-color: rgba(255,255,255,0.055); color: #e6e6e6; border: 1px solid rgba(255,255,255,0.22); border-radius: 6px; padding: 3px; }"
                "QToolButton:hover { background-color: rgba(255,255,255,0.12); border: 1px solid rgba(255,255,255,0.55); }"
            )

    def refresh_list(self, select_path: Optional[Path] = None) -> None:
        if isinstance(select_path, bool):
            select_path = None
        elif select_path is not None:
            try:
                select_path = Path(select_path)
            except TypeError:
                select_path = None
        self.path_label.setText(str(self.root_dir))
        try:
            self.root_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            return

        self.screenshot_paths = sorted(self.root_dir.glob("**/*.png"), key=self._safe_mtime, reverse=True)
        if select_path is not None:
            self.current_path = Path(select_path)
        elif self.current_path not in self.screenshot_paths:
            self.current_path = self.screenshot_paths[0] if self.screenshot_paths else None

        self._rebuild_thumbnails()
        if self.current_path is not None:
            self.set_current_path(self.current_path)
        else:
            self.current_pixmap = None
            self.preview_canvas.pixmap = None
            self.preview_canvas.update()

    def _rebuild_thumbnails(self) -> None:
        self._clear_thumb_layout()
        for path in self.screenshot_paths:
            selected = bool(self.current_path and path == self.current_path)
            button = QToolButton()
            button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            button.setIcon(self._make_thumbnail_icon(path, selected=selected))
            button.setIconSize(QSize(104, 64))
            button.setText(self._short_name(path))
            button.setToolTip(str(path))
            button.setFixedSize(126, 94)
            button.clicked.connect(lambda _checked=False, p=path: self.set_current_path(p))
            self._style_thumb_button(button, selected)
            self.thumb_layout.addWidget(button)
            self.thumb_buttons[str(path)] = button
        self.thumb_layout.addStretch(1)

    def selected_path(self) -> Optional[Path]:
        return Path(self.current_path) if self.current_path else None

    def set_current_path(self, path: Path) -> None:
        if path is None or not Path(path).exists():
            return
        path = Path(path)
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return
        self.current_path = path
        self.current_pixmap = pixmap
        self.preview_canvas.set_pixmap(pixmap)
        for raw_path, button in self.thumb_buttons.items():
            selected = Path(raw_path) == path
            button.setIcon(self._make_thumbnail_icon(Path(raw_path), selected=selected))
            self._style_thumb_button(button, selected)

    def save_selected_as(self) -> None:
        if self.current_path is None or not self.current_path.exists():
            return
        suggested = self.current_path.name
        custom = self.sanitize_name(self.name_edit.text())
        if custom:
            suggested = f"{custom}.png"
        target, _ = QFileDialog.getSaveFileName(self, "Enregistrer screenshot sous", suggested, "PNG (*.png)")
        if not target:
            return
        try:
            shutil.copy2(self.current_path, target)
            self.tab.request_status_message.emit(f"Screenshot copié : {target}")
        except Exception as exc:
            QMessageBox.critical(self, "Copie impossible", str(exc))

    def copy_current_image(self) -> None:
        if self.current_pixmap is None or self.current_pixmap.isNull():
            return
        QApplication.clipboard().setPixmap(self.current_pixmap)
        self.tab.request_status_message.emit("Screenshot copié dans le presse-papiers")

    def open_screenshots_folder(self) -> None:
        try:
            self.root_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.root_dir)))

    def open_delete_options_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        confirm_action = menu.addAction("Confirmation suppression")
        confirm_action.setCheckable(True)
        confirm_action.setChecked(bool(self.confirm_delete_enabled))
        chosen = menu.exec(self.btn_delete.mapToGlobal(pos))
        if chosen == confirm_action:
            self.confirm_delete_enabled = not self.confirm_delete_enabled
            state = "activée" if self.confirm_delete_enabled else "désactivée"
            self.tab.request_status_message.emit(f"Confirmation suppression {state}")

    def delete_selected_screenshot(self) -> None:
        path = self.selected_path()
        if path is None or not path.exists():
            return
        if self.confirm_delete_enabled:
            reply = QMessageBox.question(
                self,
                "Supprimer screenshot",
                f"Supprimer ce screenshot ?\n\n{path.name}",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
        parent = path.parent
        try:
            path.unlink()
            if not any(parent.glob("*.png")):
                for extra in ("metadata.json", "viewer_state.json"):
                    extra_path = parent / extra
                    if extra_path.exists():
                        try:
                            extra_path.unlink()
                        except Exception:
                            pass
                try:
                    parent.rmdir()
                except Exception:
                    pass
            self.current_path = None
            self.current_pixmap = None
            self.preview_canvas.pixmap = None
            self.preview_canvas.update()
            self.refresh_list()
            self.tab.request_status_message.emit("Screenshot supprimé")
        except Exception as exc:
            QMessageBox.critical(self, "Suppression impossible", str(exc))

    def open_preview_context_menu(self, global_pos: QPoint) -> None:
        menu = QMenu(self)
        copy_action = menu.addAction("Copier image")
        save_action = menu.addAction("Enregistrer sous...")
        delete_action = menu.addAction("Supprimer")
        chosen = menu.exec(global_pos)
        if chosen == copy_action:
            self.copy_current_image()
        elif chosen == save_action:
            self.save_selected_as()
        elif chosen == delete_action:
            self.delete_selected_screenshot()

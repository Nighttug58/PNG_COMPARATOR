from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QLabel

import png_comparator_v3_01_alpha_cleanup as legacy

from png_comparator.shortcuts import SHORTCUT_DEFINITIONS as MODULAR_SHORTCUT_DEFINITIONS
from png_comparator.ui.cam_tab import CamTab
from png_comparator.ui.startup_dialog import StartupDialog as ModularStartupDialog


# Conservé temporairement uniquement pour ignorer d'anciennes clés présentes dans
# des preferences.json créés avant le nettoyage du registre de raccourcis.
_DISABLED_SHORTCUT_IDS = {
    "save_session", "load_session", "undo_modification", "redo_modification",
    "mark_done_next", "mark_fix_next", "open_drawings", "open_screenshots",
}

ONE_SHOT_SHORTCUT_DEFINITIONS = list(MODULAR_SHORTCUT_DEFINITIONS)


def one_shot_shortcut_default_preferences() -> dict[str, str]:
    return {str(item["id"]): str(item.get("default", "")) for item in ONE_SHOT_SHORTCUT_DEFINITIONS}


class OneShotStartupDialog(ModularStartupDialog):
    def __init__(self, main_window) -> None:
        super().__init__(main_window)
        if hasattr(self, "btn_load_session"):
            self.btn_load_session.hide()
            self.btn_load_session.setEnabled(False)
        self.setWindowTitle("Démarrage visionneuse")

    def populate_folder_tree(self) -> None:
        """Évite de relire deux fois la même arborescence au premier affichage."""
        root_text = self.root_path_edit.text().strip().strip('"') if hasattr(self, "root_path_edit") else ""
        if (
            root_text
            and getattr(self, "_folder_tree_root", "") == root_text
            and hasattr(self, "folder_tree")
            and self.folder_tree.topLevelItemCount() > 0
        ):
            self.refresh_selected_ref_validation()
            self.refresh_state()
            return
        super().populate_folder_tree()


class OneShotMainWindow(legacy.MainWindow):
    """Transition vers une visionneuse pure, avec CamTab déjà totalement modulaire."""

    def load_recent_sessions(self) -> List[str]:
        return []

    def load_state(self) -> None:
        return

    def save_state(self, silent: bool = False) -> None:
        return

    def save_recent_sessions(self) -> None:
        return

    def add_recent_session(self, _path: str) -> None:
        return

    def update_recent_sessions_menu(self) -> None:
        return

    def save_session_as(self) -> None:
        return

    def save_session_file(self, _path: str, silent: bool = False) -> None:
        return

    def load_session_dialog(self) -> None:
        return

    def load_session_file(self, _path: str) -> None:
        return

    def autosave_current_work(self) -> None:
        return

    def relink_drawings_to_scan_records(self) -> None:
        return

    def apply_pending_drawings_to_tab(self, _tab) -> None:
        return

    def on_annotation_changed(self) -> None:
        return

    def on_drawing_changed(self) -> None:
        return

    def update_validation_summary(self) -> None:
        return

    def on_status_filter_changed(self, _value: str) -> None:
        return

    def undo_last_modification(self) -> None:
        return

    def redo_last_modification(self) -> None:
        return

    def mark_current_done_next(self) -> None:
        return

    def mark_current_fix_next(self) -> None:
        return

    def _build_ui(self) -> None:
        super()._build_ui()
        for name in (
            "btn_save_session", "btn_load_session", "btn_done_next", "btn_fix_next",
            "btn_undo_modification", "btn_redo_modification",
        ):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.hide()
                widget.setEnabled(False)

        group = self.active_table_holder.parentWidget() if hasattr(self, "active_table_holder") else None
        if group is not None and hasattr(group, "setTitle"):
            group.setTitle("Liste images - CAM actif")
        if hasattr(self, "active_table_placeholder"):
            self.active_table_placeholder.setText("Scanne puis choisis une CAM. La liste des images s'affichera ici.")

    def _build_menu(self) -> None:
        super()._build_menu()
        disabled_texts = {
            "Retour modification", "Modification suivante",
            "Sauver session projet...", "Charger session projet...", "Sessions récentes",
            "Emplacements des données",
        }
        for top_action in list(self.menuBar().actions()):
            if top_action.text().replace("&", "") == "Paramètres chemins":
                self.menuBar().removeAction(top_action)
                continue
            menu = top_action.menu()
            if menu is None:
                continue
            for action in list(menu.actions()):
                if action.text().replace("&", "") in disabled_texts:
                    action.setShortcut(QKeySequence())
                    action.setEnabled(False)
                    menu.removeAction(action)

    def __init__(self) -> None:
        super().__init__()
        self.annotations = {}
        self.drawings_by_path = {}
        self.drawing_redo_by_path = {}
        self._pending_drawings_manifest = []
        self._dirty_annotations = False
        self.current_session_path = None
        self.recent_sessions = []
        self.global_status_filter = "Tous"
        self.shortcut_preferences = {
            key: value for key, value in self.shortcut_preferences.items()
            if key not in _DISABLED_SHORTCUT_IDS
        }
        for timer_name in ("autosave_timer", "drawing_save_timer"):
            timer = getattr(self, timer_name, None)
            if timer is not None:
                timer.stop()
        if hasattr(self, "status_filter_combo"):
            self.status_filter_combo.hide()
            self.status_filter_combo.setEnabled(False)
        if hasattr(self, "validation_progress"):
            self.validation_progress.hide()
        if hasattr(self, "validation_stats_label"):
            self.validation_stats_label.hide()

    def new_comparison(self) -> None:
        self._dirty_annotations = False
        super().new_comparison()
        self.annotations = {}
        self.drawings_by_path = {}
        self.drawing_redo_by_path = {}

    def rebuild_tabs(self) -> None:
        current_cam: Optional[int] = None
        if self.tabs.currentWidget() is not None:
            for cam, tab in self.cam_tabs.items():
                if tab is self.tabs.currentWidget():
                    current_cam = cam
                    break

        self.clear_tabs_only()
        records = self.filtered_records()
        cams = sorted({record.cam_number for record in records})
        if not cams:
            empty = QLabel("Aucune image CAM trouvée avec la sélection actuelle.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("font-size: 18px; color: white;")
            self.tabs.addTab(empty, "Aucune CAM")
            self.update_active_image_table()
            return

        for cam in cams:
            cam_records = [record for record in records if record.cam_number == cam]
            tab = CamTab(
                cam_number=cam,
                records=cam_records,
                bg_colors=self.bg_colors,
                active_bg_index=self.active_bg_index,
                cache=self.image_cache,
                preload_radius=self.spin_preload_radius.value(),
                preload_enabled=self.chk_global_preload.isChecked(),
                preserve_view_enabled=self.chk_global_preserve.isChecked(),
            )
            tab.shortcut_provider = self
            tab.request_color_select.connect(self.on_bg_selected)
            tab.request_color_edit.connect(self.edit_bg_color)
            tab.request_status_message.connect(lambda msg: self.statusBar().showMessage(msg, 1800))
            tab.current_image_changed.connect(self.on_cam_current_image_changed)
            tab.request_detach_viewer.connect(self.toggle_detached_viewer)
            self.cam_tabs[cam] = tab
            self.tabs.addTab(tab, f"CAM{cam} ({len(cam_records)})")

        if current_cam in self.cam_tabs:
            index = list(self.cam_tabs).index(current_cam)
            self.tabs.setCurrentIndex(index)
        self.update_active_image_table()


def install_one_shot_mode(app_module) -> None:
    app_module.SHORTCUT_DEFINITIONS = ONE_SHOT_SHORTCUT_DEFINITIONS
    app_module.shortcut_default_preferences = one_shot_shortcut_default_preferences
    app_module.StartupDialog = OneShotStartupDialog
    app_module.CamTab = CamTab
    app_module.MainWindow = OneShotMainWindow

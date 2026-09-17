from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QLabel, QTableWidgetItem

import png_comparator_v3_01_alpha_cleanup as legacy

from png_comparator.utils import wildcard_text_match

_DISABLED_SHORTCUT_IDS = {
    "save_session", "load_session", "undo_modification", "redo_modification",
    "mark_done_next", "mark_fix_next", "open_drawings", "open_screenshots",
}

ONE_SHOT_SHORTCUT_DEFINITIONS = [
    item for item in legacy.SHORTCUT_DEFINITIONS
    if str(item.get("id", "")) not in _DISABLED_SHORTCUT_IDS
]


def one_shot_shortcut_default_preferences() -> dict[str, str]:
    return {str(item["id"]): str(item.get("default", "")) for item in ONE_SHOT_SHORTCUT_DEFINITIONS}


class OneShotStartupDialog(legacy.StartupDialog):
    def __init__(self, main_window) -> None:
        super().__init__(main_window)
        if hasattr(self, "btn_load_session"):
            self.btn_load_session.hide()
            self.btn_load_session.setEnabled(False)
        self.setWindowTitle("Démarrage visionneuse")


class OneShotCamTab(legacy.CamTab):
    """CamTab sans annotations, statuts, commentaires, dessin ni screenshots."""

    ONE_SHOT_HEADERS = ["Réf", "Fichier", "Tags"]

    def __init__(self, *args, **kwargs) -> None:
        kwargs["annotations"] = {}
        kwargs["status_filter"] = "Tous"
        super().__init__(*args, **kwargs)

        self.annotations = {}
        self.status_filter = "Tous"
        self.drawing_dialog = None
        self.screenshot_library_dialog = None

        for name in ("btn_drawing_tools", "btn_toggle_drawings", "btn_screenshot_library"):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.hide()
                widget.setEnabled(False)

        for viewer in (self.viewer, self.compare_viewer):
            viewer.drawing_enabled = False
            viewer.drawings_visible = False
            viewer.drawings_by_path = {}
            viewer.drawing_redo_by_path = {}

        self.table.blockSignals(True)
        try:
            self.table.setSortingEnabled(False)
            self.table.clearContents()
            self.table.setColumnCount(3)
            self.table.setHorizontalHeaderLabels(self.ONE_SHOT_HEADERS)
            self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            header = self.table.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(1, QHeaderView.Stretch)
            header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
            self.table.setSortingEnabled(True)
        finally:
            self.table.blockSignals(False)

        for name in ("column_filter_status_edit", "column_filter_comment_edit"):
            edit = getattr(self, name, None)
            if edit is not None:
                edit.clear()
                edit.hide()

        self.populate_table()
        self.update_filter_visuals()

    def _column_filter_edits(self):
        return [self.column_filter_ref_edit, self.column_filter_file_edit, self.column_filter_tags_edit]

    def _base_header_labels(self) -> List[str]:
        return list(self.ONE_SHOT_HEADERS)

    def set_status_filter(self, _status_filter: str) -> None:
        self.status_filter = "Tous"

    def apply_filter(self, *_args) -> None:
        if getattr(self, "_suppress_filter_apply", False):
            return
        col_ref = self.column_filter_ref_edit.text().strip() if hasattr(self, "column_filter_ref_edit") else ""
        col_file = self.column_filter_file_edit.text().strip() if hasattr(self, "column_filter_file_edit") else ""
        col_tags = self.column_filter_tags_edit.text().strip() if hasattr(self, "column_filter_tags_edit") else ""

        def matches(pattern: str, *values: str) -> bool:
            return True if not pattern else wildcard_text_match(pattern, *values)

        self.records = [
            record for record in self.all_records
            if matches(col_ref, record.ref)
            and matches(col_file, record.file_name, record.stem, record.path)
            and matches(col_tags, " ".join(record.tags))
        ]
        self.records.sort(key=lambda r: (r.ref.lower(), r.file_name.lower(), r.path.lower()))
        self.populate_table()
        self.populate_compare_selector()
        self.count_label.setText(f"{len(self.records)} image(s)")
        self.update_filter_visuals()
        self.update_nav_overlays()

        if self.records:
            self.current_index = -1
            self.select_row(0, preserve_view=False)
        else:
            self.current_index = -1
            self.viewer.set_loading(None)
            self.current_image_changed.emit(self.cam_number, "", "", 0, 0)

    def populate_table(self) -> None:
        self._updating_table = True
        old_updates = self.table.updatesEnabled()
        old_sorting = self.table.isSortingEnabled()
        self.table.setUpdatesEnabled(False)
        self.table.setSortingEnabled(False)
        self.table.blockSignals(True)
        try:
            if self.table.columnCount() != 3:
                self.table.setColumnCount(3)
                self.table.setHorizontalHeaderLabels(self.ONE_SHOT_HEADERS)
            self.table.clearContents()
            self.table.setRowCount(len(self.records))
            for row, record in enumerate(self.records):
                ref_item = QTableWidgetItem(record.ref)
                ref_item.setData(Qt.UserRole, record.path)
                ref_item.setFlags(ref_item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row, 0, ref_item)

                file_item = QTableWidgetItem(record.file_name)
                file_item.setData(Qt.UserRole, record.path)
                file_item.setToolTip(record.path)
                file_item.setFlags(file_item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row, 1, file_item)

                tags_item = QTableWidgetItem(", ".join(record.tags))
                tags_item.setData(Qt.UserRole, record.path)
                tags_item.setFlags(tags_item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row, 2, tags_item)
        finally:
            self.table.blockSignals(False)
            self.table.setSortingEnabled(old_sorting)
            self.table.setUpdatesEnabled(old_updates)
            self._updating_table = False
            self.table.viewport().update()

    def on_table_cell_clicked(self, _row: int, _column: int) -> None:
        return

    def on_table_item_changed(self, _item) -> None:
        return

    def open_drawing_tools(self) -> None:
        return

    def open_screenshot_library(self) -> None:
        return

    def toggle_drawings_visibility(self) -> None:
        return

    def set_drawing_enabled_for_all(self, _enabled: bool) -> None:
        return

    def set_drawing_tool_for_all(self, _tool: str) -> None:
        return

    def set_drawing_color_for_all(self, _color) -> None:
        return

    def set_drawing_width_for_all(self, _width: int) -> None:
        return

    def set_current_status_and_comment(self, *_args, **_kwargs) -> None:
        return

    def restore_annotation_snapshot(self, *_args, **_kwargs) -> bool:
        return False


class OneShotMainWindow(legacy.MainWindow):
    """Fenêtre principale sans état projet persistant ni workflow de validation."""

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
        cams = sorted({r.cam_number for r in records})
        if not cams:
            empty = QLabel("Aucune image CAM trouvée avec la sélection actuelle.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("font-size: 18px; color: white;")
            self.tabs.addTab(empty, "Aucune CAM")
            self.update_active_image_table()
            return

        for cam in cams:
            cam_records = [r for r in records if r.cam_number == cam]
            tab = OneShotCamTab(
                cam_number=cam,
                records=cam_records,
                annotations={},
                bg_colors=self.bg_colors,
                active_bg_index=self.active_bg_index,
                cache=self.image_cache,
                preload_radius=self.spin_preload_radius.value(),
                preload_enabled=self.chk_global_preload.isChecked(),
                preserve_view_enabled=self.chk_global_preserve.isChecked(),
                status_filter="Tous",
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
    app_module.CamTab = OneShotCamTab
    app_module.MainWindow = OneShotMainWindow

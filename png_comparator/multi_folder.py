from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableWidgetItem,
)

from .one_shot import OneShotCamTab, OneShotMainWindow, install_one_shot_mode
from .utils import wildcard_text_match


class MultiFolderCamTab(OneShotCamTab):
    """Visionneuse one-shot avec identité explicite dossier + fichier.

    Le chemin complet reste la clé technique. L'affichage du dossier utilise le
    chemin relatif au tronc commun des résultats afin de rester lisible tout en
    distinguant deux dossiers terminant par le même nom (ex. plusieurs IMG).
    """

    COL_REF = 0
    COL_FOLDER = 1
    COL_FILE = 2
    COL_TAGS = 3
    MULTI_FOLDER_HEADERS = ["Réf", "Dossier", "Fichier", "Tags"]

    def __init__(self, *args, **kwargs) -> None:
        self._folder_common_root = ""
        super().__init__(*args, **kwargs)
        self._folder_common_root = self._compute_folder_common_root()

        self.column_filter_folder_edit = QLineEdit(self)
        self.column_filter_folder_edit.setPlaceholderText("Filtre Dossier")
        self.column_filter_folder_edit.setClearButtonEnabled(True)
        self.column_filter_folder_edit.setMinimumWidth(90)
        self.column_filter_folder_edit.setToolTip("Filtre le dossier relatif, son nom ou son chemin complet. * fonctionne comme joker.")
        self.column_filter_folder_edit.hide()
        self.column_filter_folder_edit.textChanged.connect(self.apply_filter)

        self.table.blockSignals(True)
        try:
            self.table.setSortingEnabled(False)
            self.table.clearContents()
            self.table.setColumnCount(4)
            self.table.setHorizontalHeaderLabels(self.MULTI_FOLDER_HEADERS)
            self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            header = self.table.horizontalHeader()
            header.setStretchLastSection(False)
            header.setSectionResizeMode(self.COL_REF, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(self.COL_FOLDER, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(self.COL_FILE, QHeaderView.Stretch)
            header.setSectionResizeMode(self.COL_TAGS, QHeaderView.ResizeToContents)
        finally:
            self.table.blockSignals(False)

        if hasattr(self, "compare_ref_table"):
            table = self.compare_ref_table
            table.blockSignals(True)
            try:
                table.clearContents()
                table.setColumnCount(2)
                table.setHorizontalHeaderLabels(["Dossier", "Fichier"])
                table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
                table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
            finally:
                table.blockSignals(False)

        self.populate_table()
        self.populate_compare_selector()
        self.update_filter_visuals()

    @staticmethod
    def folder_name(record) -> str:
        raw = str(getattr(record, "img_dir", "") or "").strip()
        if raw:
            name = Path(raw).name
            if name:
                return name
        path = str(getattr(record, "path", "") or "").strip()
        return Path(path).parent.name if path else ""

    @staticmethod
    def folder_path(record) -> str:
        raw = str(getattr(record, "img_dir", "") or "").strip()
        if raw:
            return raw
        path = str(getattr(record, "path", "") or "").strip()
        return str(Path(path).parent) if path else ""

    def _compute_folder_common_root(self) -> str:
        folders = [self.folder_path(record) for record in getattr(self, "all_records", [])]
        folders = [folder for folder in folders if folder]
        if not folders:
            return ""
        try:
            common = os.path.commonpath(folders)
        except (ValueError, OSError):
            return ""
        return str(common)

    def folder_label(self, record) -> str:
        full = self.folder_path(record)
        if not full:
            return ""
        root = str(getattr(self, "_folder_common_root", "") or "")
        if root:
            try:
                relative = os.path.relpath(full, root)
                if relative not in {"", "."}:
                    return relative
            except (ValueError, OSError):
                pass
        return Path(full).name or full

    def _column_filter_edits(self):
        if not hasattr(self, "column_filter_folder_edit"):
            return [self.column_filter_ref_edit, self.column_filter_file_edit, self.column_filter_tags_edit]
        return [
            self.column_filter_ref_edit,
            self.column_filter_folder_edit,
            self.column_filter_file_edit,
            self.column_filter_tags_edit,
        ]

    def _base_header_labels(self) -> List[str]:
        return list(self.MULTI_FOLDER_HEADERS)

    def apply_filter(self, *_args) -> None:
        if getattr(self, "_suppress_filter_apply", False):
            return

        col_ref = self.column_filter_ref_edit.text().strip() if hasattr(self, "column_filter_ref_edit") else ""
        col_folder = self.column_filter_folder_edit.text().strip() if hasattr(self, "column_filter_folder_edit") else ""
        col_file = self.column_filter_file_edit.text().strip() if hasattr(self, "column_filter_file_edit") else ""
        col_tags = self.column_filter_tags_edit.text().strip() if hasattr(self, "column_filter_tags_edit") else ""

        def matches(pattern: str, *values: str) -> bool:
            return True if not pattern else wildcard_text_match(pattern, *values)

        self.records = [
            record for record in self.all_records
            if matches(col_ref, record.ref)
            and matches(col_folder, self.folder_label(record), self.folder_name(record), self.folder_path(record))
            and matches(col_file, record.file_name, record.stem, record.path)
            and matches(col_tags, " ".join(record.tags))
        ]
        self.records.sort(
            key=lambda record: (
                record.ref.lower(),
                self.folder_label(record).lower(),
                record.file_name.lower(),
                record.path.lower(),
            )
        )

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
            if self.table.columnCount() != 4:
                self.table.setColumnCount(4)
                self.table.setHorizontalHeaderLabels(self.MULTI_FOLDER_HEADERS)

            self.table.clearContents()
            self.table.setRowCount(len(self.records))

            for row, record in enumerate(self.records):
                folder_label = self.folder_label(record)
                folder_path = self.folder_path(record)

                ref_item = QTableWidgetItem(record.ref)
                ref_item.setData(Qt.UserRole, record.path)
                ref_item.setFlags(ref_item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row, self.COL_REF, ref_item)

                folder_item = QTableWidgetItem(folder_label)
                folder_item.setData(Qt.UserRole, record.path)
                folder_item.setData(Qt.UserRole + 1, folder_path)
                folder_item.setToolTip(folder_path)
                folder_item.setFlags(folder_item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row, self.COL_FOLDER, folder_item)

                file_item = QTableWidgetItem(record.file_name)
                file_item.setData(Qt.UserRole, record.path)
                file_item.setData(Qt.UserRole + 1, folder_path)
                file_item.setToolTip(record.path)
                file_item.setFlags(file_item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row, self.COL_FILE, file_item)

                tags_item = QTableWidgetItem(", ".join(record.tags))
                tags_item.setData(Qt.UserRole, record.path)
                tags_item.setFlags(tags_item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row, self.COL_TAGS, tags_item)
        finally:
            self.table.blockSignals(False)
            self.table.setSortingEnabled(old_sorting)
            self.table.setUpdatesEnabled(old_updates)
            self._updating_table = False
            self.table.viewport().update()

    def populate_compare_selector(self) -> None:
        self._updating_compare_selector = True
        table = getattr(self, "compare_ref_table", None)
        if table is not None:
            table.blockSignals(True)
        try:
            if table is not None:
                table.setRowCount(0)
                if table.columnCount() != 2:
                    table.setColumnCount(2)
                    table.setHorizontalHeaderLabels(["Dossier", "Fichier"])

            for index, record in enumerate(self.records):
                if table is None:
                    continue
                row = table.rowCount()
                table.insertRow(row)

                folder_item = QTableWidgetItem(self.folder_label(record))
                file_item = QTableWidgetItem(record.file_name)
                for item in (folder_item, file_item):
                    item.setData(Qt.UserRole, index)
                    item.setData(Qt.UserRole + 1, record.path)
                    item.setToolTip(record.path)
                    item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)

                table.setItem(row, 0, folder_item)
                table.setItem(row, 1, file_item)

            if self.records:
                target_index = self.compare_index
                if target_index < 0 or target_index >= len(self.records):
                    target_index = 0
                self.compare_index = target_index
                self.update_compare_selector_from_index(target_index, block=True)
            else:
                self.compare_index = -1
        finally:
            if table is not None:
                table.blockSignals(False)
            self._updating_compare_selector = False


class MultiFolderMainWindow(OneShotMainWindow):
    """Fenêtre one-shot utilisant le CamTab multi-dossiers."""

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
            tab = MultiFolderCamTab(
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


def install_multi_folder_mode(app_module) -> None:
    install_one_shot_mode(app_module)
    app_module.CamTab = MultiFolderCamTab
    app_module.MainWindow = MultiFolderMainWindow

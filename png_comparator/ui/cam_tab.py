from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional, Tuple

from PySide6.QtCore import QEvent, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QImage, QIntValidator
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..config import DEFAULT_PRELOAD_RADIUS
from ..image_cache import ImageMemoryCache
from ..models import ImageRecord, ViewerState
from ..utils import open_path_default, reveal_in_file_manager, tuple_to_color, wildcard_text_match
from .color_button import ColorButton
from .overlay_nav import OverlayNavButton
from .viewer import CompareImageCanvas


class CamTab(QWidget):
    """Onglet CAM one-shot autonome, sans suivi, commentaire, dessin ni session."""

    COL_REF = 0
    COL_FOLDER = 1
    COL_FILE = 2
    COL_TAGS = 3
    TABLE_HEADERS = ["Réf", "Dossier", "Fichier", "Tags"]

    request_color_select = Signal(int)
    request_color_edit = Signal(int)
    request_status_message = Signal(str)
    current_image_changed = Signal(int, str, str, int, int)
    request_detach_viewer = Signal()

    def __init__(
        self,
        cam_number: int,
        records: List[ImageRecord],
        bg_colors: List[Tuple[int, int, int]],
        active_bg_index: int,
        cache: ImageMemoryCache,
        preload_radius: int = DEFAULT_PRELOAD_RADIUS,
        preload_enabled: bool = True,
        preserve_view_enabled: bool = True,
        parent: Optional[QWidget] = None,
        **_legacy_ignored,
    ) -> None:
        super().__init__(parent)
        self.cam_number = int(cam_number)
        self.all_records = list(records)
        self.records: List[ImageRecord] = []
        self.bg_colors = list(bg_colors)
        self.active_bg_index = int(active_bg_index)
        self.current_index = -1
        self._updating_table = False
        self.cache = cache
        self.preload_radius = int(preload_radius)
        self.preload_enabled = bool(preload_enabled)
        self.preserve_view_enabled = bool(preserve_view_enabled)
        self._suppress_filter_apply = False
        self.shortcut_provider = None
        self.viewer_focus_mode = False
        self.compare_enabled = False
        self.overlay_enabled = False
        self.compare_index = -1
        self._updating_compare_selector = False
        self._syncing_compare_views = False
        self._compare_shared_state: Optional[ViewerState] = None
        self.overlay_active_image = 1
        self.overlay_image1_visible = True
        self.overlay_image2_visible = False
        self.show_minimap_overlay = True
        self._folder_common_root = self._compute_folder_common_root()

        self.cache.image_ready.connect(self.on_image_ready)
        self.cache.image_failed.connect(self.on_image_failed)

        self.btn_clear_custom_filter = QPushButton("Enlever tous les filtres")
        self.btn_clear_custom_filter.setToolTip("Supprime tous les filtres actifs sur la liste.")
        self.btn_clear_custom_filter.clicked.connect(self.clear_all_table_filters)
        self.count_label = QLabel("0 image")

        # Point de compatibilité temporaire avec MainWindow legacy.
        self.chk_preload = QCheckBox("Précharger autour")
        self.chk_preload.setChecked(self.preload_enabled)
        self.chk_preload.toggled.connect(self.set_preload_enabled)
        self.chk_preload.hide()

        self.btn_fit = QPushButton("Ajuster")
        self.btn_fit.setToolTip("Adapter l'image entière à la taille du viewer.")
        self.zoom_percent_edit = QLineEdit("100")
        self.zoom_percent_edit.setFixedWidth(72)
        self.zoom_percent_edit.setAlignment(Qt.AlignCenter)
        self.zoom_percent_edit.setValidator(QIntValidator(10, 4000, self.zoom_percent_edit))
        self.zoom_percent_edit.setToolTip("Zoom manuel en pourcentage.")
        self.zoom_percent_debounce = QTimer(self)
        self.zoom_percent_debounce.setSingleShot(True)
        self.zoom_percent_debounce.setInterval(350)
        self.zoom_percent_debounce.timeout.connect(self.apply_zoom_percent_from_edit)

        self.btn_focus_mode = QPushButton("Masquer interface")
        self.btn_focus_mode.setToolTip("Cache les contrôles du viewer sans changer zoom/pan.")
        self.btn_minimap = QPushButton("Mini-map")
        self.btn_minimap.setCheckable(True)
        self.btn_minimap.setChecked(True)
        self.btn_detach_viewer = QPushButton("Détacher viewer")
        self.btn_compare_mode = QPushButton("Comparer côte à côte")
        self.btn_compare_mode.setCheckable(True)
        self.btn_overlay_mode = QPushButton("Superposer")
        self.btn_overlay_mode.setCheckable(True)
        self.btn_overlay_mode.setEnabled(False)
        self.btn_exit_focus_mode = QPushButton("Afficher interface")

        self.btn_fit.clicked.connect(self.viewer_fit)
        self.zoom_percent_edit.returnPressed.connect(self.apply_zoom_percent_from_edit)
        self.zoom_percent_edit.editingFinished.connect(self.apply_zoom_percent_from_edit)
        self.zoom_percent_edit.textEdited.connect(lambda _text: self.zoom_percent_debounce.start())
        self.btn_focus_mode.clicked.connect(self.toggle_focus_mode)
        self.btn_minimap.toggled.connect(self.update_inspection_overlays)
        self.btn_detach_viewer.clicked.connect(self.request_detach_viewer.emit)
        self.btn_compare_mode.toggled.connect(self.set_compare_mode)
        self.btn_overlay_mode.toggled.connect(self.set_overlay_mode)
        self.btn_exit_focus_mode.clicked.connect(lambda: self.set_focus_mode(False))

        self.viewer = CompareImageCanvas(self)
        self.viewer.set_background(tuple_to_color(self.bg_colors[self.active_bg_index]))
        self.viewer.camera_changed.connect(self.on_main_viewer_camera_changed)

        self.compare_viewer = CompareImageCanvas(self)
        self.compare_viewer.set_background(tuple_to_color(self.bg_colors[self.active_bg_index]))
        self.compare_viewer.camera_changed.connect(lambda state: self.on_compare_canvas_changed("right", state))

        self.viewer_prev_overlay = OverlayNavButton("‹", self.viewer)
        self.viewer_next_overlay = OverlayNavButton("›", self.viewer)
        self.compare_prev_overlay = OverlayNavButton("‹", self.compare_viewer)
        self.compare_next_overlay = OverlayNavButton("›", self.compare_viewer)
        self.viewer_prev_overlay.clicked.connect(self.previous_image)
        self.viewer_next_overlay.clicked.connect(self.next_image)
        self.compare_prev_overlay.clicked.connect(self.previous_compare_image)
        self.compare_next_overlay.clicked.connect(self.next_compare_image)
        self.viewer.installEventFilter(self)
        self.compare_viewer.installEventFilter(self)

        self.compare_selector_pane = QFrame()
        self.compare_selector_pane.setMinimumWidth(180)
        self.compare_selector_pane.setMaximumWidth(340)
        self.compare_selector_pane.setStyleSheet(
            "QFrame { background-color: #1d1d1d; border: 1px solid #343434; border-radius: 6px; }"
            "QLabel { color: #eeeeee; font-weight: bold; }"
            "QTableWidget { background-color: #1a1a1a; color: #dddddd; gridline-color: #2d2d2d; border: none; }"
            "QTableWidget::item { padding: 5px; }"
            "QTableWidget::item:selected { background-color: #444444; color: white; }"
        )
        compare_selector_layout = QVBoxLayout(self.compare_selector_pane)
        compare_selector_layout.setContentsMargins(6, 6, 6, 6)
        compare_selector_layout.setSpacing(6)
        compare_selector_layout.addWidget(QLabel("Image 2"))
        compare_selector_hint = QLabel("Dossier / fichier")
        compare_selector_hint.setStyleSheet("color: #aaaaaa; font-weight: normal;")
        compare_selector_layout.addWidget(compare_selector_hint)
        self.compare_ref_table = QTableWidget(0, 2)
        self.compare_ref_table.setHorizontalHeaderLabels(["Dossier", "Fichier"])
        self.compare_ref_table.verticalHeader().setVisible(False)
        self.compare_ref_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.compare_ref_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.compare_ref_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.compare_ref_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.compare_ref_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.compare_ref_table.itemSelectionChanged.connect(self.on_compare_ref_selection_changed)
        compare_selector_layout.addWidget(self.compare_ref_table, 1)
        self.compare_selector_pane.hide()

        self.overlay_opacity_widget = QWidget()
        overlay_layout = QHBoxLayout(self.overlay_opacity_widget)
        overlay_layout.setContentsMargins(0, 4, 0, 0)
        self.btn_switch_overlay_image = QPushButton("Afficher image 2")
        self.btn_switch_overlay_image.clicked.connect(self.switch_overlay_image)
        overlay_layout.addStretch(1)
        overlay_layout.addWidget(QLabel("Superposition :"))
        overlay_layout.addWidget(self.btn_switch_overlay_image)
        overlay_layout.addStretch(1)
        self.overlay_opacity_widget.hide()

        self.color_buttons: List[ColorButton] = []
        color_layout = QHBoxLayout()
        color_layout.setContentsMargins(0, 0, 0, 0)
        for i, rgb in enumerate(self.bg_colors):
            btn = ColorButton(i, rgb)
            if i == 2:
                btn.setText("Fond 3 custom")
            btn.clicked_index.connect(self.select_bg_index)
            btn.edit_requested.connect(lambda index: self.request_color_edit.emit(index))
            self.color_buttons.append(btn)
            color_layout.addWidget(btn)
        color_layout.addStretch(1)

        self.table = QTableWidget(0, len(self.TABLE_HEADERS))
        self.table.setHorizontalHeaderLabels(self.TABLE_HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(False)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSectionsClickable(True)
        self.table.horizontalHeader().setSortIndicatorShown(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.setTextElideMode(Qt.ElideRight)
        self.table.setStyleSheet(
            "QTableWidget { background-color: #1d1d1d; gridline-color: #333333; color: #dddddd; border: 1px solid #343434; }"
            "QTableWidget::item { background-color: #1d1d1d; color: #dddddd; padding: 2px; }"
            "QTableWidget::item:selected { background-color: #3a3a3a; color: white; }"
            "QHeaderView::section { background-color: #262626; color: #eeeeee; padding: 5px; border: 1px solid #3d3d3d; }"
        )
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(48)
        header.setSectionResizeMode(self.COL_REF, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.COL_FOLDER, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.COL_FILE, QHeaderView.Stretch)
        header.setSectionResizeMode(self.COL_TAGS, QHeaderView.ResizeToContents)
        self.table.itemSelectionChanged.connect(self.on_table_selection_changed)
        self.table.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.horizontalHeader().customContextMenuRequested.connect(self.open_column_filter_menu)
        self.table.horizontalHeader().sortIndicatorChanged.connect(
            lambda _col, _order: QTimer.singleShot(0, self.on_table_sort_changed)
        )
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.open_image_row_context_menu)

        self.column_filter_ref_edit = self._make_hidden_filter("Filtre Réf")
        self.column_filter_folder_edit = self._make_hidden_filter("Filtre Dossier")
        self.column_filter_file_edit = self._make_hidden_filter("Filtre Fichier")
        self.column_filter_tags_edit = self._make_hidden_filter("Filtre Tags")

        self.top_controls_widget = QWidget()
        top_controls_outer = QVBoxLayout(self.top_controls_widget)
        top_controls_outer.setContentsMargins(0, 0, 0, 0)
        top_controls_outer.setSpacing(4)
        top_controls_panel = QFrame()
        top_controls = QHBoxLayout(top_controls_panel)
        top_controls.setContentsMargins(8, 5, 8, 5)
        top_controls.setSpacing(8)
        top_controls.addWidget(self.btn_clear_custom_filter)
        self.count_label.setStyleSheet("font-weight: bold;")
        top_controls.addWidget(self.count_label)
        top_controls.addStretch(1)
        top_controls_outer.addWidget(top_controls_panel)

        self.color_controls_widget = QWidget()
        self.color_controls_widget.setLayout(color_layout)

        self.viewer_controls_widget = QWidget()
        viewer_controls = QHBoxLayout(self.viewer_controls_widget)
        viewer_controls.setContentsMargins(0, 0, 0, 0)
        viewer_controls.addWidget(self.btn_fit)
        viewer_controls.addWidget(QLabel("Zoom :"))
        viewer_controls.addWidget(self.zoom_percent_edit)
        viewer_controls.addWidget(QLabel("%"))
        viewer_controls.addWidget(self.btn_focus_mode)
        viewer_controls.addWidget(self.btn_minimap)
        viewer_controls.addWidget(self.btn_detach_viewer)
        viewer_controls.addWidget(self.btn_compare_mode)
        viewer_controls.addWidget(self.btn_overlay_mode)
        viewer_controls.addStretch(1)

        self.focus_controls_widget = QWidget()
        focus_controls = QHBoxLayout(self.focus_controls_widget)
        focus_controls.setContentsMargins(0, 0, 0, 0)
        self.focus_info_label = QLabel("Mode image seule : Échap ou bouton pour afficher l'interface.")
        focus_controls.addWidget(self.focus_info_label, 1)
        focus_controls.addWidget(self.btn_exit_focus_mode)
        self.focus_controls_widget.hide()

        layout = QVBoxLayout(self)
        layout.addWidget(self.color_controls_widget)
        layout.addWidget(self.viewer_controls_widget)
        layout.addWidget(self.focus_controls_widget)

        self.left_viewer_pane = QWidget()
        left_layout = QVBoxLayout(self.left_viewer_pane)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.compare_left_top_widget = QWidget()
        self.compare_left_top_widget.hide()
        left_layout.addWidget(self.viewer, 1)

        self.compare_pane = QWidget()
        compare_layout = QVBoxLayout(self.compare_pane)
        compare_layout.setContentsMargins(0, 0, 0, 0)
        compare_layout.addWidget(self.compare_viewer, 1)
        self.compare_pane.hide()

        self.viewer_splitter = QSplitter(Qt.Horizontal)
        self.viewer_splitter.addWidget(self.left_viewer_pane)
        self.viewer_splitter.addWidget(self.compare_pane)
        self.viewer_splitter.addWidget(self.compare_selector_pane)
        self.viewer_splitter.setStretchFactor(0, 1)
        self.viewer_splitter.setStretchFactor(1, 1)
        self.viewer_splitter.setStretchFactor(2, 0)
        self.viewer_splitter.setSizes([850, 850, 220])
        layout.addWidget(self.viewer_splitter, 1)
        layout.addWidget(self.overlay_opacity_widget)

        self._install_keyboard_navigation()
        self.apply_filter()

    def _make_hidden_filter(self, placeholder: str) -> QLineEdit:
        edit = QLineEdit(self)
        edit.setPlaceholderText(placeholder)
        edit.setClearButtonEnabled(True)
        edit.setMinimumWidth(90)
        edit.setToolTip("Filtre cette colonne. * fonctionne comme joker.")
        edit.hide()
        edit.textChanged.connect(self.apply_filter)
        return edit

    @staticmethod
    def folder_name(record: ImageRecord) -> str:
        raw = str(getattr(record, "img_dir", "") or "").strip()
        if raw:
            return Path(raw).name
        return Path(record.path).parent.name if record.path else ""

    @staticmethod
    def folder_path(record: ImageRecord) -> str:
        raw = str(getattr(record, "img_dir", "") or "").strip()
        return raw or (str(Path(record.path).parent) if record.path else "")

    def _compute_folder_common_root(self) -> str:
        folders = [self.folder_path(record) for record in self.all_records]
        folders = [folder for folder in folders if folder]
        if not folders:
            return ""
        try:
            return str(os.path.commonpath(folders))
        except (ValueError, OSError):
            return ""

    def folder_label(self, record: ImageRecord) -> str:
        full = self.folder_path(record)
        if not full:
            return ""
        if self._folder_common_root:
            try:
                relative = os.path.relpath(full, self._folder_common_root)
                if relative not in {"", "."}:
                    return relative
            except (ValueError, OSError):
                pass
        return Path(full).name or full

    def _column_filter_edits(self) -> List[QLineEdit]:
        return [
            self.column_filter_ref_edit,
            self.column_filter_folder_edit,
            self.column_filter_file_edit,
            self.column_filter_tags_edit,
        ]

    def _base_header_labels(self) -> List[str]:
        return list(self.TABLE_HEADERS)

    def apply_filter(self, *_args) -> None:
        if self._suppress_filter_apply:
            return
        col_ref = self.column_filter_ref_edit.text().strip()
        col_folder = self.column_filter_folder_edit.text().strip()
        col_file = self.column_filter_file_edit.text().strip()
        col_tags = self.column_filter_tags_edit.text().strip()

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
            self.table.clearContents()
            self.table.setRowCount(len(self.records))
            for row, record in enumerate(self.records):
                values = (
                    record.ref,
                    self.folder_label(record),
                    record.file_name,
                    ", ".join(record.tags),
                )
                for col, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setData(Qt.UserRole, record.path)
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    if col == self.COL_FOLDER:
                        item.setToolTip(self.folder_path(record))
                    elif col == self.COL_FILE:
                        item.setToolTip(record.path)
                    self.table.setItem(row, col, item)
        finally:
            self.table.blockSignals(False)
            self.table.setSortingEnabled(old_sorting)
            self.table.setUpdatesEnabled(old_updates)
            self._updating_table = False
            self.table.viewport().update()

    def populate_compare_selector(self) -> None:
        self._updating_compare_selector = True
        table = self.compare_ref_table
        table.blockSignals(True)
        try:
            table.setRowCount(0)
            for index, record in enumerate(self.records):
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
                target = self.compare_index if 0 <= self.compare_index < len(self.records) else 0
                self.compare_index = target
                self.update_compare_selector_from_index(target, block=True)
            else:
                self.compare_index = -1
        finally:
            table.blockSignals(False)
            self._updating_compare_selector = False

    # Compatibilité temporaire avec MainWindow legacy jusqu'à son extraction.
    def set_status_filter(self, _status_filter: str) -> None:
        return

    def _install_keyboard_navigation(self) -> None:
        """Capture les raccourcis même lorsque le focus est sur la table ou le viewer."""
        self.setFocusPolicy(Qt.StrongFocus)
        self.table.setFocusPolicy(Qt.StrongFocus)
        self.viewer.setFocusPolicy(Qt.StrongFocus)
        widgets = (
            self,
            self.table,
            self.table.viewport(),
            self.viewer,
            self.compare_viewer,
        )
        for widget in widgets:
            widget.installEventFilter(self)

    def _position_nav_buttons_for_viewer(self, viewer: QWidget, prev_button: QPushButton, next_button: QPushButton) -> None:
        if hasattr(prev_button, "update_edge_positions"):
            prev_button.update_edge_positions(viewer)
        if hasattr(next_button, "update_edge_positions"):
            next_button.update_edge_positions(viewer)
        prev_button.raise_()
        next_button.raise_()

    def position_nav_overlays(self) -> None:
        self._position_nav_buttons_for_viewer(self.viewer, self.viewer_prev_overlay, self.viewer_next_overlay)
        self._position_nav_buttons_for_viewer(self.compare_viewer, self.compare_prev_overlay, self.compare_next_overlay)

    def update_nav_overlays(self) -> None:
        """Affiche les flèches overlay hors mode superposition."""
        if not hasattr(self, "viewer_prev_overlay"):
            return
        self.position_nav_overlays()
        show_main = bool(self.records) and not self.overlay_enabled
        show_compare = bool(self.records) and self.compare_enabled and not self.overlay_enabled
        self.viewer_prev_overlay.setVisible(show_main)
        self.viewer_next_overlay.setVisible(show_main)
        self.compare_prev_overlay.setVisible(show_compare)
        self.compare_next_overlay.setVisible(show_compare)
        current_visual_row = self._visual_table_row_for_record_index(self.current_index) if self.current_index >= 0 else -1
        compare_visual_row = self._visual_table_row_for_record_index(self.compare_index) if self.compare_index >= 0 else -1
        self.viewer_prev_overlay.setEnabled(current_visual_row > 0)
        self.viewer_next_overlay.setEnabled(0 <= current_visual_row < self.table.rowCount() - 1)
        self.compare_prev_overlay.setEnabled(compare_visual_row > 0)
        self.compare_next_overlay.setEnabled(0 <= compare_visual_row < self.table.rowCount() - 1)
        for button in (self.viewer_prev_overlay, self.viewer_next_overlay, self.compare_prev_overlay, self.compare_next_overlay):
            button.set_rest_opacity()

    def _focus_is_text_editor(self) -> bool:
        """Ne pas voler les flèches quand l'utilisateur tape dans un champ texte/filtre."""
        focus = QApplication.focusWidget()
        if focus is None:
            return False
        return isinstance(focus, (QLineEdit, QTextEdit, QPlainTextEdit, QComboBox))

    def eventFilter(self, obj, event) -> bool:  # type: ignore[override]
        if event.type() == QEvent.Resize and obj in (self.viewer, self.compare_viewer):
            QTimer.singleShot(0, self.position_nav_overlays)
        if event.type() == QEvent.KeyPress and self._handle_navigation_key(event):
            return True
        return super().eventFilter(obj, event)

    def _handle_navigation_key(self, event) -> bool:
        provider = getattr(self, "shortcut_provider", None)
        if provider is not None and hasattr(provider, "action_id_for_key_event"):
            action_id = provider.action_id_for_key_event(event)
            if not action_id:
                return False
            provider.trigger_shortcut_action(action_id, source_tab=self)
            event.accept()
            return True
        if self._focus_is_text_editor():
            return False
        key = event.key()
        modifiers = event.modifiers()
        if modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier):
            return False
        if key in (Qt.Key_Right, Qt.Key_Down, Qt.Key_Space, Qt.Key_PageDown):
            self.next_image(); event.accept(); return True
        if key in (Qt.Key_Left, Qt.Key_Up, Qt.Key_Backspace, Qt.Key_PageUp):
            self.previous_image(); event.accept(); return True
        if key == Qt.Key_Home:
            self.jump_first(); event.accept(); return True
        if key == Qt.Key_End:
            self.jump_last(); event.accept(); return True
        if key == Qt.Key_F:
            self.viewer.fit_to_window(); event.accept(); return True
        if key == Qt.Key_Z:
            self.zoom_percent_edit.setFocus(); self.zoom_percent_edit.selectAll(); event.accept(); return True
        if key == Qt.Key_Escape and self.viewer_focus_mode:
            self.set_focus_mode(False); event.accept(); return True
        return False

    def cleanup(self) -> None:
        try:
            self.cache.image_ready.disconnect(self.on_image_ready)
            self.cache.image_failed.disconnect(self.on_image_failed)
        except Exception:
            pass

    def set_preload_radius(self, radius: int) -> None:
        self.preload_radius = int(radius)
        self.preload_neighbors()

    def set_preload_enabled(self, enabled: bool) -> None:
        self.preload_enabled = bool(enabled)
        if enabled:
            self.preload_neighbors()

    def set_preserve_view_enabled(self, enabled: bool) -> None:
        self.preserve_view_enabled = bool(enabled)

    def set_background_colors(self, colors: List[Tuple[int, int, int]], active_index: int) -> None:
        self.bg_colors = colors
        self.active_bg_index = active_index
        for i, rgb in enumerate(colors):
            if i < len(self.color_buttons):
                self.color_buttons[i].set_color(rgb)
        self.viewer.set_background(tuple_to_color(self.bg_colors[self.active_bg_index]))
        self.compare_viewer.set_background(tuple_to_color(self.bg_colors[self.active_bg_index]))

    def select_bg_index(self, index: int) -> None:
        self.active_bg_index = index
        self.viewer.set_background(tuple_to_color(self.bg_colors[index]))
        self.compare_viewer.set_background(tuple_to_color(self.bg_colors[index]))
        self.request_color_select.emit(index)

    def update_inspection_overlays(self, _checked: bool = False) -> None:
        self.show_minimap_overlay = bool(self.btn_minimap.isChecked()) if hasattr(self, "btn_minimap") else True
        self.viewer.set_inspection_overlays(minimap=self.show_minimap_overlay, info_text=self._overlay_info_for_index(self.current_index))
        self.compare_viewer.set_inspection_overlays(minimap=self.show_minimap_overlay, info_text=self._overlay_info_for_index(self.compare_index))

    def _overlay_info_for_index(self, index: int) -> str:
        if not (0 <= index < len(self.records)):
            return f"CAM{self.cam_number}"
        record = self.records[index]
        visual_row = self._visual_table_row_for_record_index(index)
        display_index = visual_row + 1 if visual_row >= 0 else index + 1
        return f"CAM{self.cam_number} | {display_index}/{len(self.records)} | {record.ref}"

    def set_compare_mode(self, enabled: bool) -> None:
        if enabled:
            self.apply_zoom_percent_from_edit()
        self.compare_enabled = bool(enabled)
        self.btn_compare_mode.setText("Fermer comparaison" if self.compare_enabled else "Comparer côte à côte")
        self.btn_overlay_mode.setEnabled(self.compare_enabled)

        if not self.compare_enabled:
            if self.btn_overlay_mode.isChecked():
                self.btn_overlay_mode.blockSignals(True)
                self.btn_overlay_mode.setChecked(False)
                self.btn_overlay_mode.blockSignals(False)
            self.overlay_enabled = False
            self.compare_index = -1
            self.compare_left_top_widget.hide()
            self.viewer.show()
            self.compare_pane.hide()
            if hasattr(self, "compare_selector_pane"):
                self.compare_selector_pane.hide()
            self.overlay_opacity_widget.hide()
            self.viewer.clear_overlay()
            self.viewer.set_main_opacity(1.0)
            self.compare_viewer.set_loading(None)
            self.update_nav_overlays()
            self.update_inspection_overlays()
            self.request_status_message.emit("Comparaison désactivée")
            return

        self.compare_left_top_widget.show()
        self._compare_shared_state = self.viewer.capture_camera_state() if self.viewer.has_image() else None
        self.populate_compare_selector()
        self.apply_compare_layout()
        self.load_compare_left_image()
        self.load_compare_image()
        self.apply_shared_compare_state(source="left")
        QTimer.singleShot(0, lambda: self.apply_shared_compare_state(source="left"))
        self.update_nav_overlays()
        self.update_inspection_overlays()
        self.request_status_message.emit("Comparaison activée")

    def set_overlay_mode(self, enabled: bool) -> None:
        self.apply_zoom_percent_from_edit()
        if self.viewer.has_image():
            self._compare_shared_state = self.viewer.capture_camera_state()
        if enabled and not self.compare_enabled:
            self.btn_compare_mode.setChecked(True)
        self.overlay_enabled = bool(enabled and self.compare_enabled)
        self.btn_overlay_mode.setText("Superposition ON" if self.overlay_enabled else "Superposer")
        self.apply_compare_layout()
        self.update_nav_overlays()
        if self.overlay_enabled:
            self.overlay_active_image = 1
            self.compare_viewer.set_loading(None)
            self.on_overlay_visibility_changed()
            self.load_compare_image()
            self.request_status_message.emit("Mode superposition activé")
        else:
            if self.viewer.has_image():
                self._compare_shared_state = self.viewer.capture_camera_state()
            self.viewer.clear_overlay()
            self.viewer.set_main_opacity(1.0)
            if self.compare_enabled:
                self.load_compare_left_image()
                self.load_compare_image()
                self.apply_shared_compare_state(source="left")
                QTimer.singleShot(0, lambda: self.apply_shared_compare_state(source="left"))
                self.request_status_message.emit("Mode côte à côte activé")

    def apply_compare_layout(self) -> None:
        side_by_side = self.compare_enabled and not self.overlay_enabled
        self.compare_left_top_widget.setVisible(False)
        self.viewer.setVisible(True)
        self.compare_pane.setVisible(side_by_side)
        if hasattr(self, "compare_selector_pane"):
            self.compare_selector_pane.setVisible(self.compare_enabled)
        self.overlay_opacity_widget.setVisible((not self.viewer_focus_mode) and self.compare_enabled and self.overlay_enabled)

    def update_compare_selector_from_index(self, index: int, block: bool = False) -> None:
        if not hasattr(self, "compare_ref_table"):
            return
        table = self.compare_ref_table
        old_block = table.blockSignals(block)
        try:
            table.clearSelection()
            for row in range(table.rowCount()):
                item = table.item(row, 0)
                if item and int(item.data(Qt.UserRole) or -1) == int(index):
                    table.selectRow(row)
                    table.scrollToItem(item, QAbstractItemView.PositionAtCenter)
                    break
        finally:
            table.blockSignals(old_block)

    def on_compare_ref_selection_changed(self) -> None:
        if self._updating_compare_selector or not hasattr(self, "compare_ref_table"):
            return
        items = self.compare_ref_table.selectedItems()
        if not items:
            return
        item = items[0]
        index = int(item.data(Qt.UserRole) or -1)
        if index < 0 or index >= len(self.records):
            return
        self.compare_index = index
        if self.compare_enabled:
            self.load_compare_image()
        self.update_nav_overlays()
        self.update_inspection_overlays()

    def load_compare_left_image(self) -> None:
        if not self.compare_enabled or self.overlay_enabled:
            return
        if self.current_index < 0 or self.current_index >= len(self.records):
            return
        if self._compare_shared_state is not None and self.viewer.has_image():
            self.viewer.apply_camera_state(self._compare_shared_state, emit_change=False)

    def load_compare_image(self) -> None:
        if not self.compare_enabled:
            return
        if self.compare_index < 0 or self.compare_index >= len(self.records):
            self.compare_viewer.set_loading(None)
            self.viewer.clear_overlay()
            self.update_nav_overlays()
            return
        record = self.records[self.compare_index]
        if self.overlay_enabled:
            if self.viewer.overlay_path == record.path and self.viewer.overlay_pixmap is not None:
                self.on_overlay_visibility_changed()
                return
            self.cache.request(record.path)
            if self.viewer.has_image() and self.viewer.overlay_path != record.path:
                self.viewer.clear_overlay()
                self.on_overlay_visibility_changed()
            return

        self.compare_viewer.set_loading(record.path, preserve_view=True, state_override=self._compare_shared_state)
        self.cache.request(record.path)
        self.update_nav_overlays()
        self.update_inspection_overlays()

    def switch_overlay_image(self) -> None:
        self.overlay_active_image = 2 if self.overlay_active_image == 1 else 1
        self.on_overlay_visibility_changed()

    def on_overlay_visibility_changed(self, _checked: bool = False) -> None:
        self.overlay_image1_visible = self.overlay_active_image == 1
        self.overlay_image2_visible = self.overlay_active_image == 2
        if hasattr(self, "btn_switch_overlay_image"):
            self.btn_switch_overlay_image.setText("Afficher image 2" if self.overlay_image1_visible else "Afficher image 1")
        if self.overlay_enabled:
            self.viewer.set_main_opacity(1.0 if self.overlay_image1_visible else 0.0)
            self.viewer.set_overlay_opacity(1.0 if self.overlay_image2_visible else 0.0)

    def on_main_viewer_camera_changed(self, state: object) -> None:
        if isinstance(state, ViewerState):
            self.update_zoom_percent_edit(state.scale)
        self.on_compare_canvas_changed("left", state)

    def update_zoom_percent_edit(self, scale: float) -> None:
        if not hasattr(self, "zoom_percent_edit"):
            return
        percent = int(round(max(0.0, float(scale)) * 100.0))
        current_text = self.zoom_percent_edit.text().strip()
        if current_text == str(percent):
            return
        self.zoom_percent_edit.blockSignals(True)
        try:
            self.zoom_percent_edit.setText(str(percent))
        finally:
            self.zoom_percent_edit.blockSignals(False)

    def apply_zoom_percent_from_edit(self) -> None:
        text = self.zoom_percent_edit.text().strip().replace("%", "")
        if not text:
            return
        try:
            percent = int(text)
        except ValueError:
            return
        percent = max(10, min(4000, percent))
        self.zoom_percent_edit.blockSignals(True)
        try:
            self.zoom_percent_edit.setText(str(percent))
        finally:
            self.zoom_percent_edit.blockSignals(False)
        if not self.viewer.has_image():
            return
        state = self.viewer.capture_camera_state() or ViewerState(fit_mode=False)
        new_state = ViewerState(
            fit_mode=False,
            scale=percent / 100.0,
            center_norm_x=state.center_norm_x,
            center_norm_y=state.center_norm_y,
            display_width=state.display_width,
            display_height=state.display_height,
        )
        self.viewer.apply_camera_state(new_state, emit_change=True)
        if self.compare_enabled and not self.overlay_enabled:
            self._compare_shared_state = self.viewer.capture_camera_state()
            self.apply_shared_compare_state(source="left")

    def on_compare_canvas_changed(self, source: str, state: object) -> None:
        if isinstance(state, ViewerState):
            self.update_zoom_percent_edit(state.scale)
        if not self.compare_enabled or self.overlay_enabled or self._syncing_compare_views:
            return
        if not isinstance(state, ViewerState):
            return
        self._compare_shared_state = state
        self.apply_shared_compare_state(source=source)

    def apply_shared_compare_state(self, source: str = "") -> None:
        if not self.compare_enabled or self.overlay_enabled or self._syncing_compare_views:
            return
        state = self._compare_shared_state
        if state is None:
            return
        self._syncing_compare_views = True
        try:
            if source != "left" and self.viewer.has_image():
                self.viewer.apply_camera_state(state, emit_change=False)
            if source != "right" and self.compare_viewer.has_image():
                self.compare_viewer.apply_camera_state(state, emit_change=False)
        finally:
            self._syncing_compare_views = False

    def on_table_sort_changed(self) -> None:
        if self._updating_table:
            return
        if 0 <= self.current_index < len(self.records):
            table_row = self.table_row_for_record_index(self.current_index)
            if table_row >= 0 and self.table.currentRow() != table_row:
                self.table.selectRow(table_row)
        self.update_nav_overlays()
        self.refresh_table_row_styles()

    def _set_filter_text(self, edit: QLineEdit, text: str) -> None:
        old = edit.blockSignals(True)
        try:
            edit.setText(text)
        finally:
            edit.blockSignals(old)

    def _visual_table_row_for_record_index(self, record_index: int) -> int:
        return self.table_row_for_record_index(record_index)

    def _record_index_for_visual_row(self, table_row: int) -> int:
        return self.record_index_for_table_row(table_row)

    def _select_visual_row(self, table_row: int, preserve_view: Optional[bool] = None) -> None:
        record_index = self._record_index_for_visual_row(table_row)
        if 0 <= record_index < len(self.records):
            self.select_row(record_index, preserve_view=preserve_view)

    def _column_filter_edit(self, column: int) -> Optional[QLineEdit]:
        edits = self._column_filter_edits()
        if 0 <= column < len(edits):
            return edits[column]
        return None

    def update_filter_visuals(self) -> None:
        if not hasattr(self, "table"):
            return
        labels = self._base_header_labels()
        for col, edit in enumerate(self._column_filter_edits()):
            if edit.text().strip():
                labels[col] = f"{labels[col]} 🔎"
        self.table.setHorizontalHeaderLabels(labels)
        for col, label in enumerate(self._base_header_labels()):
            self.table.model().setHeaderData(
                col,
                Qt.Horizontal,
                f"{label} — clic gauche : trier | clic droit : filtrer / effacer le filtre",
                Qt.ToolTipRole,
            )

    def open_column_filter_menu(self, pos) -> None:
        header = self.table.horizontalHeader()
        column = header.logicalIndexAt(pos)
        if column < 0:
            return
        edit = self._column_filter_edit(column)
        if edit is None:
            return
        label = self._base_header_labels()[column]
        menu = QMenu(self)
        filter_action = menu.addAction(f"Filtrer texte {label}...")
        clear_action = menu.addAction(f"Effacer filtre texte {label}")
        clear_action.setEnabled(bool(edit.text().strip()))
        action = menu.exec(header.mapToGlobal(pos))
        if action is None:
            return
        if action is filter_action:
            self.open_column_filter_dialog(column)
        elif action is clear_action:
            self._set_filter_text(edit, "")
            self.apply_filter()

    def open_column_filter_dialog(self, column: int) -> None:
        edit = self._column_filter_edit(column)
        if edit is None:
            return
        label = self._base_header_labels()[column]
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Filtrer : {label}")
        dialog.setModal(True)
        layout = QVBoxLayout(dialog)
        info = QLabel(
            f"Texte à chercher dans la colonne {label}.\n"
            "Astuce : * fonctionne comme joker. Exemple : *MAIN*"
        )
        info.setWordWrap(True)
        layout.addWidget(info)
        input_edit = QLineEdit(edit.text())
        input_edit.setClearButtonEnabled(True)
        input_edit.selectAll()
        layout.addWidget(input_edit)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        btn_clear = QPushButton("Vider")
        btn_cancel = QPushButton("Annuler")
        btn_ok = QPushButton("OK")
        buttons.addWidget(btn_clear)
        buttons.addWidget(btn_cancel)
        buttons.addWidget(btn_ok)
        layout.addLayout(buttons)
        btn_clear.clicked.connect(lambda: (input_edit.clear(), dialog.accept()))
        btn_cancel.clicked.connect(dialog.reject)
        btn_ok.clicked.connect(dialog.accept)
        input_edit.returnPressed.connect(dialog.accept)
        if dialog.exec() == QDialog.Accepted:
            self._set_filter_text(edit, input_edit.text().strip())
            self.apply_filter()

    def open_image_row_context_menu(self, pos) -> None:
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        record_index = self.record_index_for_table_row(row)
        if record_index < 0 or record_index >= len(self.records):
            return
        self._select_visual_row(row, preserve_view=True)
        record = self.records[record_index]
        menu = QMenu(self)
        copy_path_action = menu.addAction("Copier chemin")
        copy_file_action = menu.addAction("Copier nom de l’image")
        copy_ref_action = menu.addAction("Copier référence")
        menu.addSeparator()
        open_folder_action = menu.addAction("Ouvrir dossier")
        open_image_action = menu.addAction("Ouvrir image")
        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if action is None:
            return
        if action is copy_path_action:
            QApplication.clipboard().setText(record.path)
            self.request_status_message.emit("Chemin image copié")
        elif action is copy_file_action:
            QApplication.clipboard().setText(record.file_name)
            self.request_status_message.emit("Nom image copié")
        elif action is copy_ref_action:
            QApplication.clipboard().setText(record.ref)
            self.request_status_message.emit("Référence copiée")
        elif action is open_folder_action:
            if not reveal_in_file_manager(record.path):
                QMessageBox.warning(self, "Ouverture impossible", f"Impossible d'ouvrir le dossier :\n{record.path}")
        elif action is open_image_action:
            if not open_path_default(record.path):
                QMessageBox.warning(self, "Ouverture impossible", f"Impossible d'ouvrir l'image :\n{record.path}")

    def clear_all_table_filters(self) -> None:
        self._suppress_filter_apply = True
        try:
            for edit in self._column_filter_edits():
                self._set_filter_text(edit, "")
        finally:
            self._suppress_filter_apply = False
        self.apply_filter()

    def table_row_for_path(self, path: str) -> int:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, self.COL_REF)
            if item is not None and item.data(Qt.UserRole) == path:
                return row
        return -1

    def record_index_for_table_row(self, row: int) -> int:
        if row < 0 or row >= self.table.rowCount():
            return -1
        item = self.table.item(row, self.COL_REF)
        path = item.data(Qt.UserRole) if item is not None else None
        if not path:
            return -1
        for idx, record in enumerate(self.records):
            if record.path == path:
                return idx
        return -1

    def table_row_for_record_index(self, record_index: int) -> int:
        if 0 <= record_index < len(self.records):
            return self.table_row_for_path(self.records[record_index].path)
        return -1

    def refresh_table_row_styles(self) -> None:
        self.table.viewport().update()

    def on_table_selection_changed(self) -> None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            return
        table_row = rows[0].row()
        record_index = self.record_index_for_table_row(table_row)
        if 0 <= record_index < len(self.records) and record_index != self.current_index:
            self.select_row(record_index)

    def select_row(self, row: int, preserve_view: Optional[bool] = None) -> None:
        if row < 0 or row >= len(self.records):
            return
        if row == self.current_index:
            table_row = self.table_row_for_record_index(row)
            if table_row >= 0 and self.table.currentRow() != table_row:
                self.table.selectRow(table_row)
            self.refresh_table_row_styles()
            return
        if preserve_view is None:
            preserve_view = self.preserve_view_enabled
        locked_state = (self._compare_shared_state or self.viewer.capture_state()) if (preserve_view and self.compare_enabled) else (self.viewer.capture_state() if preserve_view else None)
        self.current_index = row
        table_row = self.table_row_for_record_index(row)
        if table_row >= 0 and self.table.currentRow() != table_row:
            self.table.selectRow(table_row)
        self.refresh_table_row_styles()
        record = self.records[row]
        visual_row = self.table_row_for_record_index(row)
        display_index = visual_row + 1 if visual_row >= 0 else row + 1
        self.current_image_changed.emit(self.cam_number, record.ref, record.file_name, display_index, len(self.records))
        self.update_inspection_overlays()
        self.update_nav_overlays()
        if self.compare_enabled and locked_state is not None:
            self._compare_shared_state = locked_state
        self.viewer.set_loading(record.path, preserve_view=preserve_view, state_override=locked_state)
        self.cache.request(record.path)
        self.preload_neighbors()
        if self.compare_enabled:
            if self.overlay_enabled:
                self.load_compare_image()
            else:
                self.load_compare_left_image()

    def preload_neighbors(self) -> None:
        if not self.preload_enabled or not self.records or self.current_index < 0:
            return
        paths: List[str] = []
        for offset in range(1, self.preload_radius + 1):
            for idx in (self.current_index + offset, self.current_index - offset):
                if 0 <= idx < len(self.records):
                    paths.append(self.records[idx].path)
        self.cache.prefetch(paths)

    def previous_image(self) -> None:
        if not self.records or self.current_index < 0:
            return
        visual_row = self._visual_table_row_for_record_index(self.current_index)
        if visual_row <= 0:
            return
        self._select_visual_row(visual_row - 1)

    def next_image(self) -> None:
        if not self.records or self.current_index < 0:
            return
        visual_row = self._visual_table_row_for_record_index(self.current_index)
        if visual_row < 0 or visual_row >= self.table.rowCount() - 1:
            return
        self._select_visual_row(visual_row + 1)

    def jump_first(self) -> None:
        if self.records and self.table.rowCount() > 0:
            self._select_visual_row(0)

    def jump_last(self) -> None:
        if self.records and self.table.rowCount() > 0:
            self._select_visual_row(self.table.rowCount() - 1)

    def toggle_focus_mode(self) -> None:
        self.set_focus_mode(not self.viewer_focus_mode)

    def set_focus_mode(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if self.viewer_focus_mode == enabled:
            return
        self.viewer_focus_mode = enabled
        self.top_controls_widget.setVisible(True)
        self.color_controls_widget.setVisible(not enabled)
        self.viewer_controls_widget.setVisible(not enabled)
        self.overlay_opacity_widget.setVisible((not enabled) and self.compare_enabled and self.overlay_enabled)
        self.focus_controls_widget.setVisible(enabled)
        if enabled:
            self.request_status_message.emit("Interface du viewer masquée - Échap pour revenir")
            self.focus_controls_widget.show()
        else:
            self.focus_controls_widget.hide()
            self.request_status_message.emit("Interface du viewer affichée")
        self.update_inspection_overlays()
        self.viewer.setFocus()

    def current_record(self) -> Optional[ImageRecord]:
        if 0 <= self.current_index < len(self.records):
            return self.records[self.current_index]
        return None

    def previous_compare_image(self) -> None:
        if not self.compare_enabled or self.overlay_enabled or self.compare_index < 0:
            return
        visual_row = self._visual_table_row_for_record_index(self.compare_index)
        if visual_row <= 0:
            return
        new_index = self._record_index_for_visual_row(visual_row - 1)
        if 0 <= new_index < len(self.records):
            self.compare_index = new_index
            self.update_compare_selector_from_index(new_index, block=True)
            self.load_compare_image()
            self.update_nav_overlays()
            self.update_inspection_overlays()

    def next_compare_image(self) -> None:
        if not self.compare_enabled or self.overlay_enabled or self.compare_index < 0:
            return
        visual_row = self._visual_table_row_for_record_index(self.compare_index)
        if visual_row < 0 or visual_row >= self.table.rowCount() - 1:
            return
        new_index = self._record_index_for_visual_row(visual_row + 1)
        if 0 <= new_index < len(self.records):
            self.compare_index = new_index
            self.update_compare_selector_from_index(new_index, block=True)
            self.load_compare_image()
            self.update_nav_overlays()
            self.update_inspection_overlays()

    def viewer_fit(self) -> None:
        if self.compare_enabled and not self.overlay_enabled:
            self.viewer.fit_to_window(emit_change=True)
            state = self.viewer.capture_camera_state()
            if state is not None:
                self._compare_shared_state = state
                self.apply_shared_compare_state(source="left")
            return
        self.viewer.fit_to_window()
        state = self.viewer.capture_camera_state()
        if state is not None:
            self.update_zoom_percent_edit(state.scale)

    @Slot(str, QImage, int, int)
    def on_image_ready(self, path: str, image: QImage, original_w: int, original_h: int) -> None:
        handled = False
        if 0 <= self.current_index < len(self.records):
            current_path = self.records[self.current_index].path
            if path == current_path:
                preserve_main = True if self.compare_enabled and not self.overlay_enabled else None
                self.viewer.set_qimage(path, image, original_w, original_h, preserve_view=preserve_main)
                if self.compare_enabled and not self.overlay_enabled:
                    if self._compare_shared_state is None:
                        self._compare_shared_state = self.viewer.capture_camera_state()
                    if self._compare_shared_state is not None:
                        self._syncing_compare_views = True
                        try:
                            self.viewer.apply_camera_state(self._compare_shared_state, emit_change=False)
                            if self.compare_viewer.has_image():
                                self.compare_viewer.apply_camera_state(self._compare_shared_state, emit_change=False)
                        finally:
                            self._syncing_compare_views = False
                if self.compare_enabled and self.overlay_enabled:
                    self.viewer.set_main_opacity(1.0 if self.overlay_image1_visible else 0.0)
                handled = True
                if self.compare_enabled and self.overlay_enabled:
                    self.load_compare_image()

        if self.compare_enabled and 0 <= self.compare_index < len(self.records):
            compare_path = self.records[self.compare_index].path
            if path == compare_path:
                if self.overlay_enabled:
                    self.viewer.set_overlay_qimage(path, image, opacity=(1.0 if self.overlay_image2_visible else 0.0))
                    self.on_overlay_visibility_changed()
                else:
                    self.compare_viewer.set_qimage(path, image, original_w, original_h, preserve_view=True)
                    if self._compare_shared_state is None:
                        self._compare_shared_state = self.viewer.capture_camera_state()
                    if self._compare_shared_state is not None:
                        self._syncing_compare_views = True
                        try:
                            if self.viewer.has_image():
                                self.viewer.apply_camera_state(self._compare_shared_state, emit_change=False)
                            self.compare_viewer.apply_camera_state(self._compare_shared_state, emit_change=False)
                        finally:
                            self._syncing_compare_views = False
                handled = True

        if not handled:
            return
        if 0 <= self.current_index < len(self.records) and path == self.records[self.current_index].path:
            visual_row = self.table_row_for_record_index(self.current_index)
            display_index = visual_row + 1 if visual_row >= 0 else self.current_index + 1
            record = self.records[self.current_index]
            self.current_image_changed.emit(self.cam_number, record.ref, record.file_name, display_index, len(self.records))
        self.request_status_message.emit("Image chargée")

    @Slot(str, str)
    def on_image_failed(self, path: str, error: str) -> None:
        if 0 <= self.current_index < len(self.records) and path == self.records[self.current_index].path:
            self.viewer.set_error(path, error)
            self.request_status_message.emit(f"Erreur image : {error}")
        if self.compare_enabled and 0 <= self.compare_index < len(self.records) and path == self.records[self.compare_index].path:
            if self.overlay_enabled:
                self.viewer.clear_overlay()
            else:
                self.compare_viewer.set_error(path, error)
            self.request_status_message.emit(f"Erreur image comparaison : {error}")

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if self._handle_navigation_key(event):
            return
        super().keyPressEvent(event)

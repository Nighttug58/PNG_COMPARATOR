from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List, Tuple

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QDialog, QFileDialog, QGridLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMenu, QMessageBox,
    QPlainTextEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ..utils import open_path_default


class StartupDialog(QDialog):
    """Fenêtre de démarrage rapide avec sélection hybride des références.

    La liste dynamique de gauche est la seule source de vérité.
    Elle peut être alimentée par import manuel ou par explorateur récursif.
    """

    VALID_COLOR = QColor(116, 218, 125)
    INVALID_COLOR = QColor(255, 106, 106)
    NEUTRAL_COLOR = QColor(230, 230, 230)

    def __init__(self, main_window: "MainWindow") -> None:
        super().__init__(main_window)
        self.main_window = main_window
        self._folder_tree_root = ""
        self._folder_ref_index: Dict[str, str] = {}
        self.setWindowTitle("Démarrage comparaison")
        self.setModal(False)
        self.resize(1180, 860)
        self.setMinimumSize(980, 760)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(8)

        title = QLabel("Démarrage rapide")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        info = QLabel(
            "Choisis la racine, puis alimente la liste finale soit avec l'import manuel, "
            "soit avec l'explorateur intégré. La liste dynamique à gauche est la source officielle du scan."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        root_group = QGroupBox("Dossier racine")
        root_layout = QGridLayout(root_group)
        root_layout.setContentsMargins(10, 8, 10, 8)
        root_layout.setHorizontalSpacing(8)
        self.root_path_edit = QLineEdit()
        self.root_path_edit.setPlaceholderText("Chemin racine copiable/collable...")
        self.root_path_edit.setText(self.main_window.root_edit.text().strip())
        self.root_path_edit.setToolTip("Chemin copiable. Tu peux le coller/modifier directement.")
        self.btn_browse_root = QPushButton("Parcourir")
        self.btn_refresh_tree = QPushButton("Lire dossiers")
        self.btn_browse_root.setToolTip("Choisir le dossier racine dans l'explorateur.")
        self.btn_refresh_tree.setToolTip("Lit récursivement les sous-dossiers et remplit l'explorateur intégré.")
        root_layout.addWidget(self.root_path_edit, 0, 0)
        root_layout.addWidget(self.btn_browse_root, 0, 1)
        root_layout.addWidget(self.btn_refresh_tree, 0, 2)
        layout.addWidget(root_group)

        refs_group = QGroupBox("Sélection des références")
        refs_layout = QGridLayout(refs_group)
        refs_layout.setContentsMargins(10, 8, 10, 8)
        refs_layout.setColumnStretch(0, 2)
        refs_layout.setColumnStretch(1, 0)
        refs_layout.setColumnStretch(2, 3)

        self.selected_refs_table = QTableWidget(0, 3)
        self.selected_refs_table.setHorizontalHeaderLabels(["Références actives", "État", ""])
        self.selected_refs_table.verticalHeader().setVisible(False)
        self.selected_refs_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.selected_refs_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.selected_refs_table.horizontalHeader().setStretchLastSection(False)
        self.selected_refs_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.selected_refs_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.selected_refs_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.selected_refs_table.setToolTip(
            "Liste finale utilisée par le scan. Vert = chemin/dossier trouvé, rouge = introuvable. "
            "Clique sur x pour retirer une ligne. Clic droit = copier/ouvrir la référence."
        )
        self.selected_refs_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.selected_refs_table.customContextMenuRequested.connect(self.open_selected_ref_context_menu)

        self.btn_manual_import = QPushButton("Import manuel")
        self.btn_manual_import.setToolTip(
            "Ouvre une zone de collage. Les références ne sont ajoutées qu'après clic sur Valider."
        )
        self.btn_clear_selected_refs = QPushButton("Vider liste")
        self.btn_clear_selected_refs.setToolTip("Vide uniquement la liste finale des références actives.")

        self.btn_add_refs = QPushButton("← Ajouter")
        self.btn_add_refs.setMinimumWidth(96)
        self.btn_add_refs.setToolTip("Ajoute la sélection de droite dans la liste finale des références à scanner.")

        self.folder_tree = QTreeWidget()
        self.folder_tree.setHeaderLabels(["Explorateur dossiers", "Ref"])
        self.folder_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.folder_tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.folder_tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.folder_tree.setToolTip(
            "Explorateur natif : dossiers lus récursivement depuis la racine. Double-clic ou flèche pour ajouter."
        )

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        left_layout.addWidget(QLabel("Liste finale / source de vérité"))
        left_layout.addWidget(self.selected_refs_table, 1)
        left_buttons = QHBoxLayout()
        left_buttons.addWidget(self.btn_manual_import)
        left_buttons.addWidget(self.btn_clear_selected_refs)
        left_layout.addLayout(left_buttons)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)
        right_layout.addWidget(QLabel("Explorateur récursif intégré"))
        right_layout.addWidget(self.folder_tree, 1)

        refs_layout.addWidget(left_panel, 0, 0, 1, 1)
        refs_layout.addWidget(self.btn_add_refs, 0, 1, 1, 1, Qt.AlignCenter)
        refs_layout.addWidget(right_panel, 0, 2, 1, 1)
        layout.addWidget(refs_group, 1)

        options_group = QGroupBox("Options avant scan")
        options_layout = QGridLayout(options_group)
        options_layout.setContentsMargins(10, 8, 10, 8)
        self.recursive_check = QCheckBox("Chercher refs dans sous-dossiers")
        self.recursive_check.setChecked(self.main_window.chk_recursive_refs.isChecked())
        self.recursive_check.setToolTip("Active une recherche récursive optimisée depuis un dossier parent.")
        self.main_only_check = QCheckBox("Scan _MAIN_ only")
        self.main_only_check.setChecked(self.main_window.chk_main_only.isChecked())
        self.main_only_check.setToolTip(
            "Pendant le scan, ne garde que les PNG dont le nom contient MAIN. Les autres images ne sont pas chargées dans le projet."
        )

        expected_label = QLabel("CAM attendues :")
        expected_label.setToolTip("0 = désactivé. Sinon contrôle CAM1 à CAMn après le scan.")
        self.expected_cams_spin = QSpinBox()
        self.expected_cams_spin.setRange(0, 99)
        self.expected_cams_spin.setValue(self.main_window.spin_expected_cams.value())
        self.expected_cams_spin.setToolTip(
            "Contrôle automatique après scan : si CAM attendues > 0, un popup indique les CAM manquantes ou confirme que tout est trouvé."
        )

        quality_label = QLabel("Qualité viewer :")
        quality_label.setToolTip("Taille max des images chargées dans le viewer. Les presets sont des raccourcis, la valeur reste modifiable manuellement.")
        self.preview_spin = QSpinBox()
        self.preview_spin.setRange(100, 4000)
        self.preview_spin.setSingleStep(100)
        self.preview_spin.setSuffix(" px")
        self.preview_spin.setValue(self.main_window.spin_preview_max.value())
        self.preview_spin.setToolTip("Plus bas = plus rapide/flou. Plus haut = plus détaillé/lourd. Appliqué avant le scan.")

        presets_layout = QHBoxLayout()
        presets_layout.setSpacing(5)
        self.preview_preset_buttons: List[QPushButton] = []
        for value in (500, 1000, 2000, 4000):
            btn = QPushButton(f"{value}")
            btn.setToolTip(f"Appliquer rapidement {value} px")
            btn.setFixedWidth(58)
            btn.clicked.connect(lambda _checked=False, v=value: self._set_preview_preset(v))
            self.preview_preset_buttons.append(btn)
            presets_layout.addWidget(btn)
        presets_layout.addStretch(1)

        options_layout.addWidget(self.recursive_check, 0, 0, 1, 2)
        options_layout.addWidget(self.main_only_check, 1, 0, 1, 2)
        options_layout.addWidget(expected_label, 2, 0)
        options_layout.addWidget(self.expected_cams_spin, 2, 1)
        options_layout.addWidget(quality_label, 3, 0)
        options_layout.addWidget(self.preview_spin, 3, 1)
        options_layout.addWidget(QLabel("Presets px :"), 4, 0)
        options_layout.addLayout(presets_layout, 4, 1)
        layout.addWidget(options_group)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.status_label.setStyleSheet("color: #eeeeee; padding: 5px 7px; background: rgba(255,255,255,0.045); border-radius: 6px;")
        layout.addWidget(self.status_label)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.btn_load_session = QPushButton("Charger une session")
        self.btn_close = QPushButton("Fermer")
        self.btn_scan = QPushButton("Scanner")
        self.btn_scan.setEnabled(False)
        self.btn_scan.setToolTip("Lance le scan. Disponible seulement quand racine + liste sont renseignées.")
        buttons.addWidget(self.btn_load_session)
        buttons.addWidget(self.btn_close)
        buttons.addWidget(self.btn_scan)
        layout.addLayout(buttons)

        self.btn_browse_root.clicked.connect(self._browse_root)
        self.btn_refresh_tree.clicked.connect(self.populate_folder_tree)
        self.btn_add_refs.clicked.connect(self.add_selected_folders_to_refs)
        self.btn_manual_import.clicked.connect(self.open_manual_import_dialog)
        self.btn_clear_selected_refs.clicked.connect(self.clear_selected_refs)
        self.folder_tree.itemDoubleClicked.connect(lambda _item, _col: self.add_selected_folders_to_refs())
        self.btn_load_session.clicked.connect(self.main_window.load_session_dialog)
        self.btn_close.clicked.connect(self.hide)
        self.btn_scan.clicked.connect(self._scan_clicked)
        self.root_path_edit.textChanged.connect(self._root_changed)
        self.preview_spin.valueChanged.connect(self._preview_changed)
        self.expected_cams_spin.valueChanged.connect(self._expected_cams_changed)
        self.recursive_check.toggled.connect(self._recursive_changed)
        self.main_only_check.toggled.connect(self._main_only_changed)

        self.main_window.root_edit.textChanged.connect(lambda _text: self.refresh_state())
        self.main_window.refs_edit.textChanged.connect(lambda: self.refresh_state())
        self.main_window.spin_preview_max.valueChanged.connect(lambda _value: self.refresh_state())
        self.main_window.spin_expected_cams.valueChanged.connect(lambda _value: self.refresh_state())
        self.main_window.chk_recursive_refs.toggled.connect(lambda _checked: self.refresh_state())
        self.main_window.chk_main_only.toggled.connect(lambda _checked: self.refresh_state())

        self.refresh_state()
        QTimer.singleShot(0, self.populate_folder_tree)

    def _browse_root(self) -> None:
        start = self.root_path_edit.text().strip().strip('"') or self.main_window.root_edit.text().strip().strip('"') or str(Path.home())
        path = QFileDialog.getExistingDirectory(self, "Choisir le chemin racine", start)
        if path:
            self.root_path_edit.setText(path)
            self.populate_folder_tree()
            self.refresh_state()

    def _root_changed(self, text: str) -> None:
        if self.main_window.root_edit.text() != text:
            self.main_window.root_edit.blockSignals(True)
            self.main_window.root_edit.setText(text)
            self.main_window.root_edit.blockSignals(False)
        self.refresh_selected_ref_validation()
        self.refresh_state()

    def _preview_changed(self, value: int) -> None:
        if self.main_window.spin_preview_max.value() != int(value):
            self.main_window.spin_preview_max.setValue(int(value))
        self.refresh_state()

    def _expected_cams_changed(self, value: int) -> None:
        if self.main_window.spin_expected_cams.value() != int(value):
            self.main_window.spin_expected_cams.setValue(int(value))
        self.refresh_state()

    def _set_preview_preset(self, value: int) -> None:
        self.preview_spin.setValue(int(value))
        self.refresh_state()

    def _recursive_changed(self, checked: bool) -> None:
        if self.main_window.chk_recursive_refs.isChecked() != bool(checked):
            self.main_window.chk_recursive_refs.setChecked(bool(checked))
        self.refresh_selected_ref_validation()
        self.refresh_state()

    def _main_only_changed(self, checked: bool) -> None:
        if self.main_window.chk_main_only.isChecked() != bool(checked):
            self.main_window.chk_main_only.setChecked(bool(checked))
        self.refresh_state()

    def _has_root(self) -> bool:
        root_text = self.main_window.root_edit.text().strip().strip('"')
        return bool(root_text)

    def current_selected_refs(self) -> List[str]:
        refs: List[str] = []
        for row in range(self.selected_refs_table.rowCount()):
            item = self.selected_refs_table.item(row, 0)
            if item:
                value = item.text().strip()
                if value and value not in refs:
                    refs.append(value)
        return refs

    def sync_selected_refs_from_main(self) -> None:
        refs = self.main_window.refs()
        current = self.current_selected_refs()
        if refs == current:
            return
        self.selected_refs_table.setRowCount(0)
        for ref in refs:
            self._append_selected_ref(ref, source_label="session / texte")
        self.refresh_selected_ref_validation(push=False)

    def _ref_exists_in_table(self, ref: str) -> bool:
        ref_lower = ref.strip().lower()
        for row in range(self.selected_refs_table.rowCount()):
            item = self.selected_refs_table.item(row, 0)
            if item and item.text().strip().lower() == ref_lower:
                return True
        return False

    def _resolve_ref_source_path(self, ref: str, preferred_path: str = "") -> str:
        preferred_path = str(preferred_path or "").strip().strip('"')
        if preferred_path and Path(preferred_path).exists() and Path(preferred_path).is_dir():
            return str(Path(preferred_path))
        ref = str(ref or "").strip().strip('"')
        if not ref:
            return ""
        direct = Path(ref)
        if direct.exists() and direct.is_dir():
            return str(direct)
        root_text = self.main_window.root_edit.text().strip().strip('"')
        if root_text:
            root = Path(root_text)
            if root.exists() and root.is_dir():
                direct_under_root = root / ref
                if direct_under_root.exists() and direct_under_root.is_dir():
                    return str(direct_under_root)
                indexed = self._folder_ref_index.get(ref.lower())
                if indexed and Path(indexed).exists() and Path(indexed).is_dir():
                    return indexed
        return ""

    def _validate_ref_row(self, row: int) -> Tuple[bool, str]:
        item = self.selected_refs_table.item(row, 0)
        state_item = self.selected_refs_table.item(row, 1)
        if item is None:
            return False, ""
        ref = item.text().strip()
        original_path = str(item.data(Qt.UserRole) or "")
        resolved_path = self._resolve_ref_source_path(ref, original_path)
        valid = bool(resolved_path)
        item.setData(Qt.UserRole, resolved_path)
        if state_item is None:
            state_item = QTableWidgetItem()
            state_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.selected_refs_table.setItem(row, 1, state_item)
        if valid:
            item.setForeground(QBrush(self.VALID_COLOR))
            state_item.setForeground(QBrush(self.VALID_COLOR))
            state_item.setText("OK")
            tooltip = f"Référence : {ref}\nChemin trouvé : {resolved_path}"
        else:
            item.setForeground(QBrush(self.INVALID_COLOR))
            state_item.setForeground(QBrush(self.INVALID_COLOR))
            state_item.setText("Introuvable")
            tooltip = f"Référence : {ref}\nChemin introuvable depuis la racine actuelle."
        item.setToolTip(tooltip)
        state_item.setToolTip(tooltip)
        return valid, resolved_path

    def refresh_selected_ref_validation(self, push: bool = False) -> Tuple[int, int]:
        valid_count = 0
        invalid_count = 0
        if not hasattr(self, "selected_refs_table"):
            return 0, 0
        for row in range(self.selected_refs_table.rowCount()):
            valid, _path = self._validate_ref_row(row)
            if valid:
                valid_count += 1
            else:
                invalid_count += 1
        if push:
            self.push_refs_to_main()
        return valid_count, invalid_count

    def _append_selected_ref(self, ref: str, source_path: str = "", source_label: str = "") -> bool:
        ref = str(ref).strip().strip('"')
        if not ref or self._ref_exists_in_table(ref):
            return False
        row = self.selected_refs_table.rowCount()
        self.selected_refs_table.insertRow(row)
        item = QTableWidgetItem(ref)
        item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        item.setData(Qt.UserRole, source_path)
        self.selected_refs_table.setItem(row, 0, item)
        state_item = QTableWidgetItem("…")
        state_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self.selected_refs_table.setItem(row, 1, state_item)
        btn = QPushButton("x")
        btn.setToolTip("Retirer cette référence")
        btn.setFixedWidth(30)
        btn.clicked.connect(lambda _checked=False, b=btn: self.remove_selected_ref_button(b))
        self.selected_refs_table.setCellWidget(row, 2, btn)
        self._validate_ref_row(row)
        if source_label:
            item.setToolTip(item.toolTip() + f"\nOrigine : {source_label}")
        return True

    def remove_selected_ref_button(self, button: QPushButton) -> None:
        for row in range(self.selected_refs_table.rowCount()):
            if self.selected_refs_table.cellWidget(row, 2) is button:
                self.selected_refs_table.removeRow(row)
                break
        self.push_refs_to_main()

    def clear_selected_refs(self) -> None:
        self.selected_refs_table.setRowCount(0)
        self.push_refs_to_main()

    def selected_ref_info_for_row(self, row: int) -> Tuple[str, str]:
        if row < 0 or row >= self.selected_refs_table.rowCount():
            return "", ""
        item = self.selected_refs_table.item(row, 0)
        if item is None:
            return "", ""
        ref = item.text().strip()
        stored_path = str(item.data(Qt.UserRole) or "").strip()
        resolved_path = self._resolve_ref_source_path(ref, stored_path)
        if resolved_path:
            item.setData(Qt.UserRole, resolved_path)
        return ref, resolved_path

    def find_img_folder_for_ref_path(self, ref_root_path: str) -> str:
        ref_root = Path(str(ref_root_path or "").strip().strip('"'))
        if not ref_root.exists() or not ref_root.is_dir():
            return ""
        try:
            for child in ref_root.iterdir():
                if child.is_dir() and child.name.lower() == "img":
                    return str(child)
        except Exception:
            return ""

        def on_walk_error(_exc: OSError) -> None:
            return None

        try:
            for current, dirs, _files in os.walk(ref_root, topdown=True, onerror=on_walk_error):
                dirs[:] = sorted(
                    [d for d in dirs if not d.startswith('.') and d.lower() not in {'__pycache__'}],
                    key=str.lower,
                )
                for dirname in dirs:
                    if dirname.lower() == "img":
                        return str(Path(current) / dirname)
        except Exception:
            return ""
        return ""

    def open_selected_ref_context_menu(self, pos) -> None:
        row = self.selected_refs_table.rowAt(pos.y())
        if row < 0:
            return
        self.selected_refs_table.selectRow(row)
        ref, ref_root_path = self.selected_ref_info_for_row(row)
        if not ref:
            return

        menu = QMenu(self)
        copy_ref_action = menu.addAction("Copier référence")
        copy_path_action = menu.addAction("Copier chemin")
        menu.addSeparator()
        open_img_action = menu.addAction("Ouvrir chemin IMG")

        action = menu.exec(self.selected_refs_table.viewport().mapToGlobal(pos))
        if action is None:
            return
        if action is copy_ref_action:
            QApplication.clipboard().setText(ref)
            self.main_window.statusBar().showMessage("Référence copiée", 2000)
            return
        if action is copy_path_action:
            if ref_root_path:
                QApplication.clipboard().setText(ref_root_path)
                self.main_window.statusBar().showMessage("Chemin référence copié", 2000)
            else:
                QMessageBox.warning(self, "Chemin introuvable", f"Aucun chemin valide n'a été trouvé pour la référence :\n{ref}")
            return
        if action is open_img_action:
            if not ref_root_path:
                QMessageBox.warning(self, "Chemin référence introuvable", f"Impossible d'ouvrir le dossier IMG : la référence est introuvable.\n\nRéférence : {ref}")
                self.main_window.log(f"WARNING : référence introuvable depuis la liste finale : {ref}")
                return
            img_path = self.find_img_folder_for_ref_path(ref_root_path)
            if img_path:
                if not open_path_default(img_path):
                    QMessageBox.warning(self, "Ouverture impossible", f"Impossible d'ouvrir le dossier IMG :\n{img_path}")
                return
            warning_text = (
                "Le dossier IMG n'est pas trouvé pour cette référence.\n\n"
                f"Référence : {ref}\n"
                f"Dossier racine référence : {ref_root_path}\n\n"
                "Ouverture du dossier racine de la référence à la place."
            )
            self.main_window.log(f"WARNING : dossier IMG introuvable pour {ref}. Ouverture du dossier racine : {ref_root_path}")
            QMessageBox.warning(self, "Dossier IMG introuvable", warning_text)
            if not open_path_default(ref_root_path):
                QMessageBox.warning(self, "Ouverture impossible", f"Impossible d'ouvrir le dossier référence :\n{ref_root_path}")

    def push_refs_to_main(self) -> None:
        text = "\n".join(self.current_selected_refs())
        if self.main_window.refs_edit.toPlainText() != text:
            self.main_window.refs_edit.blockSignals(True)
            self.main_window.refs_edit.setPlainText(text)
            self.main_window.refs_edit.blockSignals(False)
            self.main_window.update_refs_count_label()
            self.main_window.update_startup_dialog_state()
        self.refresh_state()

    def _tokenize_manual_refs_text(self, text: str) -> List[str]:
        tokens: List[str] = []
        for line in text.splitlines():
            cleaned = line.strip().strip('"')
            if not cleaned:
                continue
            parts = re.split(r"[\t,;]+", cleaned)
            for part in parts:
                value = part.strip().strip('"')
                if value:
                    tokens.append(value)
        return tokens

    def _manual_token_to_ref(self, token: str) -> Tuple[str, str, str]:
        token = token.strip().strip('"')
        if not token:
            return "", "", ""
        path = Path(token)
        if path.exists() and path.is_dir():
            return path.name, str(path), "collage chemin valide"
        resolved = self._resolve_ref_source_path(token)
        if resolved:
            return Path(resolved).name, resolved, "collage ref trouvée"
        return token, "", "collage manuel"

    def import_manual_refs_text(self, text: str) -> None:
        added = False
        for token in self._tokenize_manual_refs_text(text):
            ref, source_path, source_label = self._manual_token_to_ref(token)
            if ref:
                added = self._append_selected_ref(ref, source_path=source_path, source_label=source_label) or added
        if added:
            self.push_refs_to_main()
        else:
            self.refresh_selected_ref_validation()
            self.refresh_state()

    def open_manual_import_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Import manuel des références")
        dialog.resize(660, 390)
        layout = QVBoxLayout(dialog)
        label = QLabel(
            "Colle ici une liste de références ou de chemins. Rien n'est ajouté à la liste finale tant que tu ne cliques pas sur Valider."
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        edit = QPlainTextEdit()
        edit.setPlaceholderText("REF001\nREF002\nC:/Projet/Images/REF003")
        layout.addWidget(edit, 1)

        feedback = QLabel("0 ligne détectée")
        feedback.setStyleSheet("color: #cccccc;")
        feedback.setWordWrap(True)
        layout.addWidget(feedback)

        hint = QLabel("Valider = ajouter à la liste finale | Fermer = fermer sans importer. Ctrl+Entrée valide, Échap ferme.")
        hint.setStyleSheet("color: #cccccc;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        def refresh_feedback() -> None:
            tokens = self._tokenize_manual_refs_text(edit.toPlainText())
            valid_count = 0
            invalid_count = 0
            for token in tokens:
                ref, source_path, _source_label = self._manual_token_to_ref(token)
                if ref and self._resolve_ref_source_path(ref, source_path):
                    valid_count += 1
                elif ref:
                    invalid_count += 1
            feedback.setText(
                f"{len(tokens)} ligne(s) détectée(s) | "
                f"<span style='color:#74da7d'>valides {valid_count}</span> / "
                f"<span style='color:#ff6b6b'>introuvables {invalid_count}</span>"
            )

        def validate_and_close() -> None:
            self.import_manual_refs_text(edit.toPlainText())
            dialog.accept()

        edit.textChanged.connect(refresh_feedback)
        refresh_feedback()

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        validate_btn = QPushButton("Valider")
        clear_btn = QPushButton("Vider")
        close_btn = QPushButton("Fermer")
        validate_btn.setToolTip("Ajoute les références collées dans la liste finale.")
        clear_btn.setToolTip("Vide uniquement le texte de cette fenêtre, sans toucher à la liste finale.")
        close_btn.setToolTip("Ferme la fenêtre sans importer automatiquement.")
        validate_btn.setShortcut(QKeySequence("Ctrl+Return"))
        close_btn.setShortcut(QKeySequence("Esc"))
        validate_btn.clicked.connect(validate_and_close)
        clear_btn.clicked.connect(edit.clear)
        close_btn.clicked.connect(dialog.reject)
        buttons.addWidget(validate_btn)
        buttons.addWidget(clear_btn)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)
        dialog.exec()

    def populate_folder_tree(self) -> None:
        root_text = self.root_path_edit.text().strip().strip('"')
        self.folder_tree.clear()
        self._folder_tree_root = root_text
        self._folder_ref_index = {}
        if not root_text:
            self.refresh_selected_ref_validation()
            self.refresh_state()
            return
        root = Path(root_text)
        if not root.exists() or not root.is_dir():
            self.refresh_selected_ref_validation()
            self.refresh_state()
            return
        count = 0
        skipped_count = 0
        root_item = QTreeWidgetItem([root.name or str(root), root.name])
        root_item.setData(0, Qt.UserRole, str(root))
        root_item.setData(1, Qt.UserRole, root.name)
        self.folder_tree.addTopLevelItem(root_item)
        path_to_item = {str(root): root_item}
        self._folder_ref_index[root.name.lower()] = str(root)

        def on_walk_error(_exc: OSError) -> None:
            nonlocal skipped_count
            skipped_count += 1

        for current, dirs, _files in os.walk(root, topdown=True, onerror=on_walk_error):
            dirs[:] = sorted(
                [d for d in dirs if not d.startswith('.') and d.lower() not in {'__pycache__'}],
                key=str.lower,
            )
            current_path = Path(current)
            parent_item = path_to_item.get(str(current_path), root_item)
            for dirname in dirs:
                child_path = current_path / dirname
                rel = str(child_path.relative_to(root))
                ref_name = child_path.name
                item = QTreeWidgetItem([rel, ref_name])
                item.setData(0, Qt.UserRole, str(child_path))
                item.setData(1, Qt.UserRole, ref_name)
                parent_item.addChild(item)
                path_to_item[str(child_path)] = item
                self._folder_ref_index.setdefault(ref_name.lower(), str(child_path))
                count += 1
        root_item.setExpanded(True)
        self.folder_tree.resizeColumnToContents(1)
        self.status_label.setToolTip(
            f"Explorateur natif : {count} dossier(s) lus récursivement. Dossiers ignorés/inaccessibles : {skipped_count}."
        )
        self.refresh_selected_ref_validation()
        self.refresh_state()

    def add_selected_folders_to_refs(self) -> None:
        added = False
        for item in self.folder_tree.selectedItems():
            ref = str(item.data(1, Qt.UserRole) or item.text(1) or item.text(0)).strip()
            source_path = str(item.data(0, Qt.UserRole) or "").strip()
            if ref:
                added = self._append_selected_ref(ref, source_path=source_path, source_label="explorateur récursif") or added
        if added:
            self.push_refs_to_main()
        else:
            self.refresh_state()

    def refresh_state(self) -> None:
        root_text = self.main_window.root_edit.text().strip().strip('"')
        if hasattr(self, "root_path_edit") and self.root_path_edit.text().strip().strip('"') != root_text:
            self.root_path_edit.blockSignals(True)
            self.root_path_edit.setText(root_text)
            self.root_path_edit.blockSignals(False)
        if hasattr(self, "selected_refs_table"):
            self.sync_selected_refs_from_main()
        if hasattr(self, "preview_spin"):
            self.preview_spin.blockSignals(True)
            self.preview_spin.setValue(self.main_window.spin_preview_max.value())
            self.preview_spin.blockSignals(False)
        if hasattr(self, "expected_cams_spin"):
            self.expected_cams_spin.blockSignals(True)
            self.expected_cams_spin.setValue(self.main_window.spin_expected_cams.value())
            self.expected_cams_spin.blockSignals(False)
        if hasattr(self, "recursive_check"):
            self.recursive_check.blockSignals(True)
            self.recursive_check.setChecked(self.main_window.chk_recursive_refs.isChecked())
            self.recursive_check.blockSignals(False)
        if hasattr(self, "main_only_check"):
            self.main_only_check.blockSignals(True)
            self.main_only_check.setChecked(self.main_window.chk_main_only.isChecked())
            self.main_only_check.blockSignals(False)

        valid_count, invalid_count = self.refresh_selected_ref_validation() if hasattr(self, "selected_refs_table") else (0, 0)
        refs_count = len(self.main_window.refs())
        root_ok = self._has_root()
        recursive_text = "activée" if self.main_window.chk_recursive_refs.isChecked() else "désactivée"
        main_text = "MAIN uniquement" if self.main_window.chk_main_only.isChecked() else "toutes images"
        expected_count = self.main_window.spin_expected_cams.value() if hasattr(self.main_window, "spin_expected_cams") else 0
        expected_text = f"CAM1 à CAM{expected_count}" if expected_count > 0 else "désactivée"
        self.status_label.setText(
            f"<b>Références :</b> {refs_count} "
            f"<span style='color:#74da7d'>OK {valid_count}</span> / "
            f"<span style='color:#ff6b6b'>KO {invalid_count}</span> | "
            f"<b>Sous-dossiers :</b> {recursive_text} | "
            f"<b>Scan :</b> {main_text} | "
            f"<b>CAM attendues :</b> {expected_text} | "
            f"<b>Qualité :</b> {self.main_window.spin_preview_max.value()} px"
        )
        self.btn_scan.setEnabled(root_ok and refs_count > 0)

    def _scan_clicked(self) -> None:
        self.push_refs_to_main()
        self.refresh_state()
        if not self.btn_scan.isEnabled():
            return
        self.main_window.run_scan()

    def allow_close_after_scan(self) -> None:
        self.hide()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        event.accept()

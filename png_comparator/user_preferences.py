from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict

from PySide6.QtCore import QByteArray, QTimer
from PySide6.QtGui import QKeySequence

from . import config
from .multi_folder import MultiFolderMainWindow, install_multi_folder_mode
from .one_shot import _DISABLED_SHORTCUT_IDS
from .shortcuts import portable_shortcut_text, shortcut_default_preferences


PREFERENCES_SCHEMA = 1


def _read_preferences() -> Dict[str, Any]:
    path = config.PREFERENCES_FILE
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write_preferences(data: Dict[str, Any]) -> None:
    path = config.PREFERENCES_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


class UserPreferencesMainWindow(MultiFolderMainWindow):
    """Visionneuse one-shot avec préférences locales au compte OS courant.

    Ce fichier ne contient volontairement aucun état de session métier : pas de
    statut, commentaire, scan sauvegardé, sélection de dossiers ni annotations.
    """

    def __init__(self) -> None:
        super().__init__()

        # Autosave léger des seules préférences. Il est séparé de l'ancien
        # autosave projet/session, qui reste désactivé en mode one-shot.
        self._preferences_save_timer = QTimer(self)
        self._preferences_save_timer.setSingleShot(True)
        self._preferences_save_timer.setInterval(900)
        self._preferences_save_timer.timeout.connect(lambda: self.save_state(silent=True))

        def schedule_save(*_args) -> None:
            self._preferences_save_timer.start()

        for widget_name, signal_name in (
            ("root_edit", "textChanged"),
            ("refs_edit", "textChanged"),
            ("chk_recursive_refs", "toggled"),
            ("chk_main_only", "toggled"),
            ("spin_expected_cams", "valueChanged"),
            ("spin_preview_max", "valueChanged"),
            ("spin_preload_radius", "valueChanged"),
            ("chk_global_preload", "toggled"),
            ("chk_global_preserve", "toggled"),
        ):
            widget = getattr(self, widget_name, None)
            signal = getattr(widget, signal_name, None) if widget is not None else None
            if signal is not None:
                signal.connect(schedule_save)

        # Les placeholders ne doivent contenir aucune référence ou chemin métier.
        if hasattr(self, "root_edit"):
            self.root_edit.setPlaceholderText("Choisir un dossier racine...")
        if hasattr(self, "refs_edit"):
            self.refs_edit.setPlaceholderText("Une référence par ligne...")

    def _preferences_payload(self) -> Dict[str, Any]:
        geometry = ""
        try:
            geometry = bytes(self.saveGeometry()).hex()
        except Exception:
            pass

        shortcuts = {}
        for key, value in getattr(self, "shortcut_preferences", {}).items():
            if key in _DISABLED_SHORTCUT_IDS:
                continue
            shortcuts[str(key)] = portable_shortcut_text(str(value or ""))

        return {
            "schema": PREFERENCES_SCHEMA,
            "app": config.APP_NAME,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "source_root": self.root_edit.text().strip() if hasattr(self, "root_edit") else "",
            "references": self.refs_edit.toPlainText() if hasattr(self, "refs_edit") else "",
            "recursive_refs": bool(self.chk_recursive_refs.isChecked()) if hasattr(self, "chk_recursive_refs") else True,
            "main_only": bool(self.chk_main_only.isChecked()) if hasattr(self, "chk_main_only") else True,
            "expected_cams": int(self.spin_expected_cams.value()) if hasattr(self, "spin_expected_cams") else 0,
            "preview_max_side": int(self.spin_preview_max.value()) if hasattr(self, "spin_preview_max") else config.DEFAULT_PREVIEW_MAX_SIDE,
            "preload_radius": int(self.spin_preload_radius.value()) if hasattr(self, "spin_preload_radius") else config.DEFAULT_PRELOAD_RADIUS,
            "global_preload": bool(self.chk_global_preload.isChecked()) if hasattr(self, "chk_global_preload") else True,
            "global_preserve": bool(self.chk_global_preserve.isChecked()) if hasattr(self, "chk_global_preserve") else True,
            "bg_colors": [list(color) for color in getattr(self, "bg_colors", config.DEFAULT_BG_COLORS)],
            "active_bg_index": int(getattr(self, "active_bg_index", 0)),
            "shortcuts": shortcuts,
            "main_window_geometry": geometry,
        }

    def load_state(self) -> None:
        data = _read_preferences()
        if not data:
            if hasattr(self, "root_edit"):
                self.root_edit.setText(config.DEFAULT_SOURCE_ROOT)
            if hasattr(self, "refs_edit"):
                self.refs_edit.setPlainText("\n".join(config.DEFAULT_REFERENCES))
            return

        if hasattr(self, "root_edit"):
            self.root_edit.setText(str(data.get("source_root", config.DEFAULT_SOURCE_ROOT) or ""))
        if hasattr(self, "refs_edit"):
            refs = data.get("references", "")
            if isinstance(refs, list):
                refs = "\n".join(str(item) for item in refs if str(item).strip())
            self.refs_edit.setPlainText(str(refs or ""))

        if hasattr(self, "chk_recursive_refs"):
            self.chk_recursive_refs.setChecked(bool(data.get("recursive_refs", True)))
        if hasattr(self, "chk_main_only"):
            self.chk_main_only.setChecked(bool(data.get("main_only", True)))
        if hasattr(self, "spin_expected_cams"):
            value = int(data.get("expected_cams", 0) or 0)
            self.spin_expected_cams.setValue(max(self.spin_expected_cams.minimum(), min(self.spin_expected_cams.maximum(), value)))
        if hasattr(self, "spin_preview_max"):
            value = int(data.get("preview_max_side", config.DEFAULT_PREVIEW_MAX_SIDE) or config.DEFAULT_PREVIEW_MAX_SIDE)
            self.spin_preview_max.setValue(max(self.spin_preview_max.minimum(), min(self.spin_preview_max.maximum(), value)))
        if hasattr(self, "spin_preload_radius"):
            value = int(data.get("preload_radius", config.DEFAULT_PRELOAD_RADIUS) or config.DEFAULT_PRELOAD_RADIUS)
            self.spin_preload_radius.setValue(max(self.spin_preload_radius.minimum(), min(self.spin_preload_radius.maximum(), value)))
        if hasattr(self, "chk_global_preload"):
            self.chk_global_preload.setChecked(bool(data.get("global_preload", True)))
        if hasattr(self, "chk_global_preserve"):
            self.chk_global_preserve.setChecked(bool(data.get("global_preserve", True)))

        colors = data.get("bg_colors")
        if isinstance(colors, list) and len(colors) == 3:
            parsed = []
            try:
                for color in colors:
                    values = list(color)[:3]
                    if len(values) != 3:
                        raise ValueError
                    parsed.append(tuple(max(0, min(255, int(value))) for value in values))
                self.bg_colors = parsed
            except Exception:
                self.bg_colors = list(config.DEFAULT_BG_COLORS)

        active_bg_index = int(data.get("active_bg_index", 0) or 0)
        self.active_bg_index = active_bg_index if 0 <= active_bg_index < len(self.bg_colors) else 0

        shortcut_data = data.get("shortcuts", {})
        if isinstance(shortcut_data, dict):
            defaults = shortcut_default_preferences()
            loaded = dict(defaults)
            for key in defaults:
                if key in _DISABLED_SHORTCUT_IDS:
                    continue
                if key in shortcut_data:
                    loaded[key] = portable_shortcut_text(str(shortcut_data.get(key, "") or ""))
            self.shortcut_preferences = loaded
            if hasattr(self, "apply_shortcuts_to_menu_actions"):
                self.apply_shortcuts_to_menu_actions()

        geometry = str(data.get("main_window_geometry", "") or "").strip()
        if geometry:
            try:
                self.restoreGeometry(QByteArray.fromHex(geometry.encode("ascii")))
            except Exception:
                pass

    def save_state(self, silent: bool = False) -> None:
        try:
            _write_preferences(self._preferences_payload())
            if not silent and hasattr(self, "statusBar"):
                self.statusBar().showMessage(f"Préférences utilisateur sauvegardées : {config.PREFERENCES_FILE}", 3500)
        except Exception as exc:
            if not silent and hasattr(self, "statusBar"):
                self.statusBar().showMessage(f"Préférences non sauvegardées : {exc}", 5000)

    def save_recent_sessions(self) -> None:
        return

    def load_recent_sessions(self):
        return []

    def add_recent_session(self, _path: str) -> None:
        return

    def update_recent_sessions_menu(self) -> None:
        return

    def apply_shortcut_preferences_from_editors(self) -> None:
        if getattr(self, "_building_shortcut_editors", False):
            return
        for action_id, editor in getattr(self, "shortcut_editors", {}).items():
            if action_id in _DISABLED_SHORTCUT_IDS:
                continue
            self.shortcut_preferences[action_id] = portable_shortcut_text(
                editor.keySequence().toString(QKeySequence.PortableText)
            )
        self.apply_shortcuts_to_menu_actions()
        self.update_shortcut_status_label()
        self.save_state(silent=True)


def install_user_preferences_mode(app_module) -> None:
    """Active multi-dossiers puis remplace l'état partagé par des préférences par utilisateur."""
    install_multi_folder_mode(app_module)
    app_module.MainWindow = UserPreferencesMainWindow

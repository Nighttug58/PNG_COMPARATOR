"""Point d'entrée modulaire de PNG Comparator en mode visionneuse one-shot."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

import png_comparator_v3_01_alpha_cleanup as legacy_app

from png_comparator import config
from png_comparator.image_cache import ImageMemoryCache
from png_comparator.models import ImageRecord, ImageScanResult, ViewerState
from png_comparator.scanner import ImageScanner, extract_tags
from png_comparator.shortcuts import (
    SHORTCUT_ALIASES,
    SHORTCUT_DEFINITIONS,
    portable_shortcut_text,
    shortcut_default_preferences,
)
from png_comparator.theme import apply_application_dark_theme, apply_windows_dark_titlebar
from png_comparator.ui.windows import DetachedViewerWindow, WidgetPopupDialog
from png_comparator.user_preferences import install_user_preferences_mode
from png_comparator.utils import (
    color_to_tuple,
    human_file_size,
    image_metadata_summary_fast,
    open_path_default,
    reveal_in_file_manager,
    tuple_to_color,
)


def install_modular_components() -> None:
    """Branche uniquement les dépendances legacy encore réellement consommées."""

    legacy_app.APP_NAME = config.APP_NAME
    legacy_app.CHECKBOX_VISUAL_STYLE = ""
    legacy_app.APP_INSTALL_DIR = config.APP_INSTALL_DIR
    legacy_app.APP_ROOT_DIR = config.APP_ROOT_DIR
    legacy_app.STATE_FILE = config.STATE_FILE
    legacy_app.SESSION_RECENTS_FILE = config.SESSION_RECENTS_FILE
    legacy_app.LEGACY_STATE_FILE = config.LEGACY_STATE_FILE
    legacy_app.AUTOSAVE_INTERVAL_MS = config.AUTOSAVE_INTERVAL_MS
    legacy_app.MAX_RECENT_SESSIONS = config.MAX_RECENT_SESSIONS
    legacy_app.MAX_BACKUPS_PER_FILE = config.MAX_BACKUPS_PER_FILE
    legacy_app.DEFAULT_BG_COLORS = config.DEFAULT_BG_COLORS
    legacy_app.DEFAULT_PREVIEW_MAX_SIDE = config.DEFAULT_PREVIEW_MAX_SIDE
    legacy_app.DEFAULT_PRELOAD_RADIUS = config.DEFAULT_PRELOAD_RADIUS

    legacy_app.ImageRecord = ImageRecord
    legacy_app.ViewerState = ViewerState
    legacy_app.ImageScanResult = ImageScanResult
    legacy_app.ImageScanner = ImageScanner
    legacy_app.extract_tags = extract_tags
    legacy_app.ImageMemoryCache = ImageMemoryCache

    legacy_app.SHORTCUT_DEFINITIONS = SHORTCUT_DEFINITIONS
    legacy_app.SHORTCUT_ALIASES = SHORTCUT_ALIASES
    legacy_app.shortcut_default_preferences = shortcut_default_preferences
    legacy_app.portable_shortcut_text = portable_shortcut_text

    legacy_app.color_to_tuple = color_to_tuple
    legacy_app.tuple_to_color = tuple_to_color
    legacy_app.human_file_size = human_file_size
    legacy_app.image_metadata_summary_fast = image_metadata_summary_fast
    legacy_app.open_path_default = open_path_default
    legacy_app.reveal_in_file_manager = reveal_in_file_manager

    legacy_app.DetachedViewerWindow = DetachedViewerWindow
    legacy_app.WidgetPopupDialog = WidgetPopupDialog

    install_user_preferences_mode(legacy_app)


def main() -> int:
    install_modular_components()

    # Les QFileDialog natifs suivent le thème Windows. Pour garantir le sombre
    # même sur un poste configuré en clair, on utilise les dialogues Qt stylables.
    QApplication.setAttribute(Qt.AA_DontUseNativeDialogs, True)

    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    apply_application_dark_theme(app)

    window = legacy_app.MainWindow()
    if bool(getattr(window, "_restore_maximized", True)):
        window.showMaximized()
    else:
        window.show()
    apply_windows_dark_titlebar(window)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

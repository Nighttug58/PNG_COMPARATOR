"""Point d'entrée transitoire de la version modulaire de PNG Comparator.

Pendant le chantier de séparation, l'interface historique reste dans le fichier
V3.01, tandis que les composants déjà extraits sont injectés avant le démarrage.
Cela permet de migrer progressivement sans changer le comportement utilisateur.
"""

from __future__ import annotations

import png_comparator_v3_01_alpha_cleanup as legacy_app

from png_comparator import config
from png_comparator.image_cache import ImageMemoryCache
from png_comparator.models import Annotation, DrawingItem, ImageRecord, ImageScanResult, ViewerState
from png_comparator.scanner import ImageScanner, extract_tags
from png_comparator.shortcuts import (
    SHORTCUT_ALIASES,
    SHORTCUT_DEFINITIONS,
    portable_shortcut_text,
    shortcut_default_preferences,
)
from png_comparator.status import (
    STATUS_ALIASES,
    STATUS_CHOICES,
    STATUS_DEFAULT,
    has_annotation_content,
    is_default_status,
    normalize_status,
    status_text_color,
)
from png_comparator.utils import (
    canonical_image_key,
    color_to_tuple,
    format_rgb,
    human_file_size,
    image_border_color_for_background,
    image_metadata_summary_fast,
    loose_path_basename,
    open_path_default,
    reveal_in_file_manager,
    tuple_to_color,
    wildcard_text_match,
)


def install_modular_components() -> None:
    """Branche les composants extraits sur l'application historique.

    Les méthodes des classes historiques résolvent ces symboles dans les globals du
    module au moment de leur exécution. L'injection a donc lieu avant legacy_app.main().
    """

    # Configuration / chemins.
    legacy_app.APP_NAME = config.APP_NAME
    legacy_app.CHECKBOX_VISUAL_STYLE = config.CHECKBOX_VISUAL_STYLE
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

    # Modèles et services cœur.
    legacy_app.ImageRecord = ImageRecord
    legacy_app.Annotation = Annotation
    legacy_app.ViewerState = ViewerState
    legacy_app.DrawingItem = DrawingItem
    legacy_app.ImageScanResult = ImageScanResult
    legacy_app.ImageScanner = ImageScanner
    legacy_app.extract_tags = extract_tags
    legacy_app.ImageMemoryCache = ImageMemoryCache

    # Statuts.
    legacy_app.STATUS_DEFAULT = STATUS_DEFAULT
    legacy_app.STATUS_CHOICES = STATUS_CHOICES
    legacy_app.STATUS_ALIASES = STATUS_ALIASES
    legacy_app.normalize_status = normalize_status
    legacy_app.is_default_status = is_default_status
    legacy_app.status_text_color = status_text_color
    legacy_app.has_annotation_content = has_annotation_content

    # Raccourcis.
    legacy_app.SHORTCUT_DEFINITIONS = SHORTCUT_DEFINITIONS
    legacy_app.SHORTCUT_ALIASES = SHORTCUT_ALIASES
    legacy_app.shortcut_default_preferences = shortcut_default_preferences
    legacy_app.portable_shortcut_text = portable_shortcut_text

    # Utilitaires partagés.
    legacy_app.canonical_image_key = canonical_image_key
    legacy_app.loose_path_basename = loose_path_basename
    legacy_app.image_border_color_for_background = image_border_color_for_background
    legacy_app.wildcard_text_match = wildcard_text_match
    legacy_app.format_rgb = format_rgb
    legacy_app.color_to_tuple = color_to_tuple
    legacy_app.tuple_to_color = tuple_to_color
    legacy_app.human_file_size = human_file_size
    legacy_app.image_metadata_summary_fast = image_metadata_summary_fast
    legacy_app.open_path_default = open_path_default
    legacy_app.reveal_in_file_manager = reveal_in_file_manager


def main() -> int:
    install_modular_components()
    return legacy_app.main()


if __name__ == "__main__":
    raise SystemExit(main())

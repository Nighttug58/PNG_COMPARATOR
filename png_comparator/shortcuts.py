from __future__ import annotations

from typing import Dict, List

from PySide6.QtGui import QKeySequence


# Source officielle des raccourcis de la visionneuse one-shot.
# Les anciennes actions sessions/validation/dessin/screenshots n'existent plus ici.
SHORTCUT_DEFINITIONS: List[dict] = [
    {"id": "new_comparison", "group": "Fichier", "label": "Nouvelle comparaison", "default": "Ctrl+N"},
    {"id": "scan", "group": "Fichier", "label": "Scanner", "default": "Ctrl+R"},
    {"id": "clear_cache", "group": "Fichier", "label": "Vider cache images", "default": "Ctrl+Shift+C"},
    {"id": "quit", "group": "Fichier", "label": "Quitter", "default": "Ctrl+Q"},
    {"id": "previous_image_left", "group": "Navigation images", "label": "Image précédente - flèche gauche", "default": "Left"},
    {"id": "previous_image_up", "group": "Navigation images", "label": "Image précédente - flèche haut", "default": "Up"},
    {"id": "previous_image_page", "group": "Navigation images", "label": "Image précédente - PageUp", "default": "PgUp"},
    {"id": "previous_image_backspace", "group": "Navigation images", "label": "Image précédente - Backspace", "default": "Backspace"},
    {"id": "next_image_right", "group": "Navigation images", "label": "Image suivante - flèche droite", "default": "Right"},
    {"id": "next_image_down", "group": "Navigation images", "label": "Image suivante - flèche bas", "default": "Down"},
    {"id": "next_image_page", "group": "Navigation images", "label": "Image suivante - PageDown", "default": "PgDown"},
    {"id": "next_image_space", "group": "Navigation images", "label": "Image suivante - Espace", "default": "Space"},
    {"id": "first_image", "group": "Navigation images", "label": "Première image", "default": "Home"},
    {"id": "last_image", "group": "Navigation images", "label": "Dernière image", "default": "End"},
    {"id": "previous_reference", "group": "Navigation références", "label": "Référence précédente", "default": ""},
    {"id": "next_reference", "group": "Navigation références", "label": "Référence suivante", "default": ""},
    {"id": "fit_viewer", "group": "Viewer", "label": "Ajuster à la fenêtre", "default": "F"},
    {"id": "focus_zoom_field", "group": "Viewer", "label": "Sélectionner le champ zoom", "default": "Z"},
    {"id": "toggle_focus_mode", "group": "Viewer", "label": "Masquer / afficher interface viewer", "default": ""},
    {"id": "exit_focus_mode", "group": "Viewer", "label": "Quitter mode image seule", "default": "Esc"},
    {"id": "toggle_compare", "group": "Viewer", "label": "Comparer côte à côte", "default": ""},
    {"id": "toggle_overlay", "group": "Viewer", "label": "Superposer", "default": ""},
    {"id": "copy_path", "group": "Image active", "label": "Copier chemin", "default": ""},
    {"id": "copy_file", "group": "Image active", "label": "Copier nom image", "default": ""},
    {"id": "copy_reference", "group": "Image active", "label": "Copier référence", "default": ""},
    {"id": "open_folder", "group": "Image active", "label": "Ouvrir dossier", "default": ""},
    {"id": "open_image", "group": "Image active", "label": "Ouvrir image", "default": ""},
]

SHORTCUT_ALIASES = {
    "PAGEUP": "PgUp",
    "PAGE UP": "PgUp",
    "PAGEDOWN": "PgDown",
    "PAGE DOWN": "PgDown",
    "ESCAPE": "Esc",
    "ESC": "Esc",
    "RETURN": "Enter",
    "DEL": "Delete",
}


def shortcut_default_preferences() -> Dict[str, str]:
    return {
        str(item["id"]): str(item.get("default", ""))
        for item in SHORTCUT_DEFINITIONS
    }


def portable_shortcut_text(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    upper = text.upper()
    if upper in SHORTCUT_ALIASES:
        text = SHORTCUT_ALIASES[upper]
    try:
        sequence = QKeySequence(text)
        normalized = sequence.toString(QKeySequence.PortableText)
        return normalized or text
    except Exception:
        return text

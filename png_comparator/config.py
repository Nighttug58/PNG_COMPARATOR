from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Tuple


APP_NAME = "PNG Comparator V3.01 ALPHA CLEANUP"

# Compatibilité temporaire avec le socle legacy. Le thème complet est désormais
# appliqué par png_comparator.theme depuis le launcher modulaire.
CHECKBOX_VISUAL_STYLE = ""

AUTOSAVE_INTERVAL_MS = 60_000
MAX_RECENT_SESSIONS = 10
MAX_BACKUPS_PER_FILE = 3
DEFAULT_PREVIEW_MAX_SIDE = 2200
DEFAULT_PRELOAD_RADIUS = 3

# Aucun chemin source ni aucune référence métier ne doit être préchargé dans le code.
DEFAULT_SOURCE_ROOT = ""
DEFAULT_REFERENCES: Tuple[str, ...] = ()

DEFAULT_BG_COLORS: List[Tuple[int, int, int]] = [
    (255, 255, 255),
    (0, 0, 0),
    (128, 128, 128),
]


def application_install_dir() -> Path:
    """Dossier contenant le script ou l'EXE, réservé aux ressources de l'app."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def default_user_data_dir() -> Path:
    """Dossier de données privé du compte OS courant.

    Sous Windows, LOCALAPPDATA est propre à chaque compte utilisateur. Deux
    utilisateurs lançant le même EXE partagé ne liront donc jamais le même
    fichier de préférences.
    """
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / "PNGComparator"
        return Path.home() / "AppData" / "Local" / "PNGComparator"

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "PNGComparator"

    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        return Path(xdg_config) / "PNGComparator"
    return Path.home() / ".config" / "PNGComparator"


def application_data_dir() -> Path:
    """Retourne toujours le stockage utilisateur, jamais le dossier de l'EXE."""
    path = default_user_data_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


APP_INSTALL_DIR = application_install_dir()
APP_USER_DATA_DIR = application_data_dir()

# APP_ROOT_DIR est conservé comme alias de compatibilité pendant la migration.
# Sa sémantique est désormais strictement « données utilisateur ».
APP_ROOT_DIR = APP_USER_DATA_DIR

PREFERENCES_FILE = APP_USER_DATA_DIR / "preferences.json"
STATE_FILE = APP_USER_DATA_DIR / ".png_comparator_v2_state.json"
SESSION_RECENTS_FILE = APP_USER_DATA_DIR / ".png_comparator_sessions_recent.json"
LEGACY_STATE_FILE = Path.home() / ".png_comparator_v1_state.json"

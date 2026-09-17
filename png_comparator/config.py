from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Tuple


APP_NAME = "PNG Comparator V3.01 ALPHA CLEANUP"

CHECKBOX_VISUAL_STYLE = """
QCheckBox {
    color: #f0f0f0;
    spacing: 6px;
    padding: 2px 5px;
    border-radius: 6px;
    background-color: rgba(255, 255, 255, 0.035);
}
QCheckBox:hover {
    background-color: rgba(255, 255, 255, 0.075);
}
QCheckBox::indicator {
    width: 12px;
    height: 12px;
    border-radius: 6px;
    border: 2px solid #8b95a3;
    background-color: #2f3540;
}
QCheckBox::indicator:unchecked:hover {
    border: 2px solid #c4ccd8;
    background-color: #3b4350;
}
QCheckBox::indicator:checked {
    border: 2px solid #ff8686;
    background-color: qradialgradient(cx:0.5, cy:0.5, radius:0.48, fx:0.5, fy:0.5,
                                      stop:0 #ffffff, stop:0.28 #ffffff,
                                      stop:0.31 #e34444, stop:1 #c83232);
}
QCheckBox::indicator:checked:hover {
    border: 2px solid #ffc0c0;
    background-color: qradialgradient(cx:0.5, cy:0.5, radius:0.48, fx:0.5, fy:0.5,
                                      stop:0 #ffffff, stop:0.30 #ffffff,
                                      stop:0.33 #f05252, stop:1 #dd3d3d);
}
"""

AUTOSAVE_INTERVAL_MS = 60_000
MAX_RECENT_SESSIONS = 10
MAX_BACKUPS_PER_FILE = 3
DEFAULT_PREVIEW_MAX_SIDE = 2200
DEFAULT_PRELOAD_RADIUS = 3

DEFAULT_BG_COLORS: List[Tuple[int, int, int]] = [
    (255, 255, 255),
    (0, 0, 0),
    (128, 128, 128),
]


def application_install_dir() -> Path:
    """Return the historical application directory after the package split.

    In source mode the old monolithic file lived one level above this package, so
    ``parent.parent`` preserves the previous storage location. PyInstaller keeps
    using the executable directory exactly as before.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def default_user_data_dir() -> Path:
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / "PNGComparator"
    return Path.home() / ".png_comparator"


def is_writable_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".png_comparator_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def application_data_dir() -> Path:
    install_dir = application_install_dir()
    if is_writable_dir(install_dir):
        return install_dir
    fallback = default_user_data_dir()
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


APP_INSTALL_DIR = application_install_dir()
APP_ROOT_DIR = application_data_dir()
STATE_FILE = APP_ROOT_DIR / ".png_comparator_v2_state.json"
SESSION_RECENTS_FILE = APP_ROOT_DIR / ".png_comparator_sessions_recent.json"
LEGACY_STATE_FILE = Path.home() / ".png_comparator_v1_state.json"

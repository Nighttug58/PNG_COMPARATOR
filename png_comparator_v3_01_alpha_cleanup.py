# -*- coding: utf-8 -*-
"""
PNG Comparator V3.01 ALPHA CLEANUP
Auteur : ChatGPT pour Tugay

But :
    Outil de comparaison/contrôle de PNG transparents par références, dossiers IMG* et CAM dynamiques.

Améliorations V2 :
    - Viewer fluide avec zoom molette centré sous la souris.
    - Drag/pan avec clic gauche lorsque l'image est zoomée.
    - Double clic : alterne ajusté fenêtre / 100%.
    - Cache mémoire LRU pour éviter de recharger les images déjà vues.
    - Chargement asynchrone des previews pour éviter de bloquer l'interface.
    - Préchargement des images avant/après l'image courante.
    - Preview redimensionnée configurable pour PNG 4000x4000.
    - Qualité viewer gérée uniquement par la taille max image affichée.
    - Fond transparent optimisé : la couleur du viewer change sans recomposer le PNG.
    - Option de conservation du zoom/position entre images pour comparer la même zone.

Dépendances :
    pip install PySide6

Compilation EXE conseillée :
    pyinstaller --noconsole --onedir --name PNGComparatorV3_01_ALPHA_CLEANUP png_comparator_v3_01_alpha_cleanup.py
"""

from __future__ import annotations

import json
import os
import shutil
import re
import sys
import subprocess
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

from PySide6.QtCore import (
    QObject,
    QUrl,
    QEvent,
    QByteArray,
    QPoint,
    QPointF,
    QRunnable,
    QRectF,
    QSize,
    Qt,
    QThreadPool,
    QTimer,
    QPropertyAnimation,
    QEasingCurve,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QAction,
    QBrush,
    QDesktopServices,
    QColor,
    QImage,
    QImageReader,
    QIcon,
    QIntValidator,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QKeySequenceEdit,
    QMenu,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QProgressBar,
    QProgressDialog,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QStyle,
    QStyleFactory,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QButtonGroup,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

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

def application_install_dir() -> Path:
    """Dossier réel du programme.

    En mode script Python : dossier du .py.
    En mode EXE PyInstaller onefile : dossier de l'exécutable, jamais le dossier
    temporaire _MEIxxxxx.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def default_user_data_dir() -> Path:
    """Dossier de secours stable et writable pour config/sessions/backups.

    Utilisé si le dossier de l'exe n'est pas writable, par exemple si l'exe est
    placé dans Program Files ou un emplacement verrouillé.
    """
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
    """Dossier stable pour les fichiers internes.

    Priorité : à côté du script/exe si possible.
    Fallback : AppData/PNGComparator si le dossier de l'exe n'est pas writable.
    """
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


def canonical_image_key(path: str) -> str:
    """Clé stable pour relier dessins/sessions aux images.

    Important : on normalise le chemin sans forcer de lecture disque. Sur SharePoint
    ou OneDrive, certaines opérations de résolution peuvent hydrater le fichier ; ici
    on reste sur de la normalisation purement textuelle autant que possible.
    """
    text = str(path or "").strip().strip('"')
    if not text:
        return ""
    try:
        text = os.path.normpath(text)
        text = os.path.abspath(text)
        text = os.path.normcase(text)
    except Exception:
        text = text.replace("/", os.sep).replace("\\", os.sep)
    return text


def loose_path_basename(path: str) -> str:
    """Nom de fichier robuste même si un chemin Windows est relu hors Windows."""
    text = str(path or "").strip().strip('"')
    if not text:
        return ""
    return re.split(r"[\\/]", text)[-1].lower()
AUTOSAVE_INTERVAL_MS = 60_000
MAX_RECENT_SESSIONS = 10
MAX_BACKUPS_PER_FILE = 3
LEGACY_STATE_FILE = Path.home() / ".png_comparator_v1_state.json"
CAM_RE = re.compile(r"CAM[\s_\-.]*(\d+)", re.IGNORECASE)
TOKEN_SPLIT_RE = re.compile(r"[\s_\-.()\[\]{}]+")

DEFAULT_BG_COLORS: List[Tuple[int, int, int]] = [
    (255, 255, 255),
    (0, 0, 0),
    (128, 128, 128),
]


def image_border_color_for_background(color: QColor) -> QColor:
    """Couleur de bordure toujours visible sur le fond du viewer."""
    r, g, b = color.red(), color.green(), color.blue()
    if r > 235 and g > 235 and b > 235:
        return QColor(0, 0, 0)
    if r < 20 and g < 20 and b < 20:
        return QColor(255, 255, 255)
    return QColor(255 - r, 255 - g, 255 - b)

DEFAULT_PREVIEW_MAX_SIDE = 2200
DEFAULT_PRELOAD_RADIUS = 3
STATUS_DEFAULT = "À contrôler"

STATUS_CHOICES = [
    STATUS_DEFAULT,
    "Terminé",
    "À corriger",
]

STATUS_ALIASES = {
    "A CONTROLER": STATUS_DEFAULT,
    "À CONTROLER": STATUS_DEFAULT,
    "A CONTRÔLER": STATUS_DEFAULT,
    "À CONTRÔLER": STATUS_DEFAULT,
    "NON VERIFIE": STATUS_DEFAULT,
    "NON VÉRIFIÉ": STATUS_DEFAULT,
    "NON VERIFIEE": STATUS_DEFAULT,
    "NON VÉRIFIÉE": STATUS_DEFAULT,
    "NON VÉRIFIÉES": STATUS_DEFAULT,
    "NON VERIFIEES": STATUS_DEFAULT,
    "": STATUS_DEFAULT,
    "OK": "Terminé",
    "TERMINE": "Terminé",
    "TERMINÉ": "Terminé",
    "CORRECTION À FAIRE": "À corriger",
    "CORRECTION A FAIRE": "À corriger",
    "IMAGE À RECOMMENCER": "À corriger",
    "IMAGE A RECOMMENCER": "À corriger",
    "À VÉRIFIER": "À corriger",
    "A VERIFIER": "À corriger",
    "RENDU MANQUANT": "À corriger",
}


def normalize_status(status: str) -> str:
    value = str(status or "").strip()
    if not value:
        return STATUS_DEFAULT
    if value in STATUS_CHOICES:
        return value
    return STATUS_ALIASES.get(value.upper(), "À corriger")


def is_default_status(status: str) -> bool:
    return normalize_status(status) == STATUS_DEFAULT


def status_text_color(status: str) -> QColor:
    """Couleur forte et lisible pour les statuts dans la liste."""
    value = normalize_status(status)
    if value == "Terminé":
        return QColor(70, 230, 120)
    if value == "À corriger":
        return QColor(255, 90, 90)
    return QColor(255, 215, 70)


def has_annotation_content(annotation: "Annotation") -> bool:
    """Vrai si l'annotation contient une information utilisateur réelle.

    Le statut par défaut "À contrôler" sert d'affichage standard mais ne doit pas
    transformer toutes les lignes en annotations sauvegardées.
    """
    return bool(annotation.marked or annotation.comment.strip() or not is_default_status(annotation.status))


SHORTCUT_DEFINITIONS: List[dict] = [
    {"id": "new_comparison", "group": "Fichier", "label": "Nouvelle comparaison", "default": "Ctrl+N"},
    {"id": "scan", "group": "Fichier", "label": "Scanner", "default": "Ctrl+R"},
    {"id": "save_session", "group": "Fichier", "label": "Sauver session projet", "default": "Ctrl+Shift+S"},
    {"id": "load_session", "group": "Fichier", "label": "Charger session projet", "default": "Ctrl+O"},
    {"id": "clear_cache", "group": "Fichier", "label": "Vider cache images", "default": "Ctrl+Shift+C"},
    {"id": "quit", "group": "Fichier", "label": "Quitter", "default": "Ctrl+Q"},
    {"id": "undo_modification", "group": "Review", "label": "Retour modification", "default": "Ctrl+Z"},
    {"id": "redo_modification", "group": "Review", "label": "Modification suivante", "default": "Ctrl+Y"},
    {"id": "mark_done_next", "group": "Review", "label": "Terminé + suivant", "default": ""},
    {"id": "mark_fix_next", "group": "Review", "label": "À corriger + suivant", "default": ""},
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
    {"id": "open_drawings", "group": "Outils", "label": "Ouvrir palette dessins", "default": ""},
    {"id": "open_screenshots", "group": "Outils", "label": "Ouvrir screenshots", "default": ""},
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
    return {str(item["id"]): str(item.get("default", "")) for item in SHORTCUT_DEFINITIONS}


def portable_shortcut_text(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    upper = text.upper()
    if upper in SHORTCUT_ALIASES:
        text = SHORTCUT_ALIASES[upper]
    try:
        seq = QKeySequence(text)
        normalized = seq.toString(QKeySequence.PortableText)
        return normalized or text
    except Exception:
        return text


@dataclass(frozen=True)
class ImageRecord:
    """Une image PNG détectée."""

    ref: str
    ref_dir: str
    img_dir: str
    path: str
    cam_number: int
    cam_name: str
    file_name: str
    stem: str
    tags: Tuple[str, ...] = field(default_factory=tuple)


@dataclass
class Annotation:
    marked: bool = False
    status: str = ""
    comment: str = ""

    def to_dict(self) -> dict:
        return {
            "marked": self.marked,
            "status": self.status,
            "comment": self.comment,
        }

    @staticmethod
    def from_dict(data: dict) -> "Annotation":
        return Annotation(
            marked=bool(data.get("marked", False)),
            status=str(data.get("status", "")),
            comment=str(data.get("comment", "")),
        )


@dataclass
class ViewerState:
    """État de vue pour conserver la même zone entre plusieurs images."""

    fit_mode: bool = True
    scale: float = 1.0
    center_norm_x: float = 0.5
    center_norm_y: float = 0.5
    display_width: int = 0
    display_height: int = 0


@dataclass
class DrawingItem:
    """Annotation dessinée sur une image, avec taille de référence stable.

    Les points restent dans le repère du pixmap au moment du dessin.
    ref_width/ref_height permettent de les recalculer correctement si l'image
    revient plus tard en preview ou en pleine qualité.
    """

    kind: str
    points: List[Tuple[float, float]]
    color: Tuple[int, int, int]
    width: int = 4
    ref_width: int = 0
    ref_height: int = 0
    erased_items: List["DrawingItem"] = field(default_factory=list)

    def to_dict(self) -> dict:
        data = {
            "schema": 3,
            "kind": str(self.kind),
            "points": [[float(x), float(y)] for x, y in self.points],
            "color": [int(self.color[0]), int(self.color[1]), int(self.color[2])],
            "width": int(self.width),
            "ref_width": int(self.ref_width),
            "ref_height": int(self.ref_height),
        }
        # V2.77 : les actions de gomme/effacement gardent leur mémoire.
        # Avant, erased_items n'était pas sauvegardé, donc un Effacer pouvait
        # casser l'historique Dessin précédent / Dessin suivant après session.
        if self.erased_items:
            data["erased_items"] = [item.to_dict() for item in self.erased_items]
        return data

    @staticmethod
    def from_dict(data: dict) -> "DrawingItem":
        points_raw = data.get("points", []) if isinstance(data, dict) else []
        points: List[Tuple[float, float]] = []
        if isinstance(points_raw, list):
            for p in points_raw:
                try:
                    if isinstance(p, (list, tuple)) and len(p) >= 2:
                        points.append((float(p[0]), float(p[1])))
                except Exception:
                    continue
        color_raw = data.get("color", [255, 40, 40]) if isinstance(data, dict) else [255, 40, 40]
        try:
            color = tuple(max(0, min(255, int(v))) for v in list(color_raw)[:3])
            if len(color) != 3:
                color = (255, 40, 40)
        except Exception:
            color = (255, 40, 40)
        kind = str(data.get("kind", "freehand") if isinstance(data, dict) else "freehand")
        if kind not in {"freehand", "line", "rect", "ellipse", "eraser_action"}:
            kind = "freehand"
        erased_items: List[DrawingItem] = []
        erased_raw = data.get("erased_items", []) if isinstance(data, dict) else []
        if isinstance(erased_raw, list):
            erased_items = [DrawingItem.from_dict(item) for item in erased_raw if isinstance(item, dict)]
            erased_items = [item for item in erased_items if item.kind in {"freehand", "line", "rect", "ellipse"} and item.points]
        return DrawingItem(
            kind=kind,
            points=points,
            color=color,  # type: ignore[arg-type]
            width=max(1, min(80, int(data.get("width", 4) if isinstance(data, dict) else 4))),
            ref_width=max(0, int(data.get("ref_width", 0) if isinstance(data, dict) else 0)),
            ref_height=max(0, int(data.get("ref_height", 0) if isinstance(data, dict) else 0)),
            erased_items=erased_items,
        )


class ImageScanResult:
    """Résultat complet d'un scan."""

    def __init__(self) -> None:
        self.records: List[ImageRecord] = []
        self.ref_dirs: Dict[str, List[Path]] = {}
        self.img_dirs_by_ref: Dict[str, List[Path]] = {}
        self.missing_refs: List[str] = []
        self.warnings: List[str] = []
        self.checked_dirs: int = 0
        self.cancelled: bool = False

    @property
    def img_dirs(self) -> List[Path]:
        all_dirs: List[Path] = []
        for dirs in self.img_dirs_by_ref.values():
            all_dirs.extend(dirs)
        return sorted(set(all_dirs), key=lambda p: str(p).lower())

    @property
    def cams(self) -> List[int]:
        return sorted({r.cam_number for r in self.records})


class ImageScanner:
    """Scan disque : références -> dossiers IMG* -> PNG contenant CAMn.

    V2.71 : la recherche récursive des références n'utilise plus un rglob complet
    pour chaque référence. On indexe l'arborescence une seule fois, avec callback
    de progression, ce qui évite les gros freezes et accélère fortement les scans
    depuis un dossier parent.
    """

    SKIP_DIR_NAMES = {
        ".git", ".svn", ".hg", "__pycache__", ".pytest_cache", ".mypy_cache",
        "node_modules", "venv", ".venv", "env", ".env", "dist", "build",
        "$RECYCLE.BIN", "System Volume Information",
    }

    def __init__(
        self,
        root: Path,
        refs: Sequence[str],
        recursive_ref_search: bool = False,
        contains_mode: bool = False,
        main_only: bool = True,
        progress_callback: Optional[Callable[[str, int], bool]] = None,
    ) -> None:
        self.root = root
        self.refs = [r.strip() for r in refs if r.strip()]
        self.recursive_ref_search = recursive_ref_search
        self.contains_mode = contains_mode
        self.main_only = bool(main_only)
        self.progress_callback = progress_callback
        self.checked_dirs = 0
        self.cancelled = False

    def scan(self) -> ImageScanResult:
        result = ImageScanResult()

        if not self.root.exists() or not self.root.is_dir():
            result.warnings.append(f"Chemin racine invalide : {self.root}")
            return result

        if self.recursive_ref_search:
            ref_index = self._find_reference_dirs_indexed()
            if self.cancelled:
                result.cancelled = True
                result.checked_dirs = self.checked_dirs
                result.warnings.append("Scan annulé pendant la recherche récursive des références.")
                return result
        else:
            ref_index = {ref: self._find_reference_dirs_shallow(ref) for ref in self.refs}

        for ref in self.refs:
            ref_dirs = ref_index.get(ref, [])
            if not ref_dirs:
                result.missing_refs.append(ref)
                continue

            result.ref_dirs[ref] = ref_dirs
            img_dirs_for_ref: List[Path] = []

            for ref_dir in ref_dirs:
                if self.cancelled:
                    break
                img_dirs = self._find_img_dirs(ref_dir)
                img_dirs_for_ref.extend(img_dirs)

                for img_dir in img_dirs:
                    pngs = self._find_pngs_in_dir(img_dir)
                    for png in pngs:
                        if self.main_only and "main" not in png.stem.lower():
                            continue
                        record = self._record_from_file(ref, ref_dir, img_dir, png)
                        if record:
                            result.records.append(record)

            result.img_dirs_by_ref[ref] = sorted(set(img_dirs_for_ref), key=lambda p: str(p).lower())

        result.records.sort(key=lambda r: (r.cam_number, r.ref.lower(), r.file_name.lower(), r.path.lower()))
        result.checked_dirs = self.checked_dirs
        result.cancelled = self.cancelled
        if self.cancelled:
            result.warnings.append("Scan annulé par l'utilisateur.")
        return result

    def _notify_progress(self, path: Path, force: bool = False) -> bool:
        if self.progress_callback is None:
            return True
        if force or self.checked_dirs <= 10 or self.checked_dirs % 25 == 0:
            try:
                return bool(self.progress_callback(str(path), int(self.checked_dirs)))
            except Exception:
                return True
        return True

    def _iter_dirs_fast(self, start: Path):
        """Parcours rapide et annulable des dossiers avec os.scandir."""
        stack = [start]
        while stack:
            current = stack.pop()
            try:
                with os.scandir(current) as it:
                    entries = list(it)
            except (PermissionError, OSError):
                continue

            dirs_to_add: List[Path] = []
            for entry in entries:
                try:
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                except (PermissionError, OSError):
                    continue
                name = entry.name
                if name in self.SKIP_DIR_NAMES:
                    continue
                child = Path(entry.path)
                self.checked_dirs += 1
                if not self._notify_progress(child):
                    self.cancelled = True
                    return
                yield child
                dirs_to_add.append(child)

            # Ordre stable et lisible, sans coût excessif.
            dirs_to_add.sort(key=lambda p: p.name.lower(), reverse=True)
            stack.extend(dirs_to_add)

    def _find_reference_dirs_indexed(self) -> Dict[str, List[Path]]:
        result: Dict[str, List[Path]] = {ref: [] for ref in self.refs}
        refs_lower = {ref.lower(): ref for ref in self.refs}
        refs_pairs = [(ref, ref.lower()) for ref in self.refs]

        # Cas robuste : si l'utilisateur choisit directement un dossier référence
        # comme racine, on doit aussi considérer la racine elle-même.
        root_name = self.root.name.lower()
        if self.contains_mode:
            for ref, ref_lower in refs_pairs:
                if ref_lower and ref_lower in root_name:
                    result[ref].append(self.root)
        else:
            ref = refs_lower.get(root_name)
            if ref:
                result[ref].append(self.root)

        for child in self._iter_dirs_fast(self.root):
            if self.cancelled:
                break
            name = child.name.lower()
            if self.contains_mode:
                for ref, ref_lower in refs_pairs:
                    if ref_lower and ref_lower in name and child not in result[ref]:
                        result[ref].append(child)
            else:
                ref = refs_lower.get(name)
                if ref and child not in result[ref]:
                    result[ref].append(child)

        for ref in list(result.keys()):
            result[ref] = sorted(set(result[ref]), key=lambda p: str(p).lower())
        return result

    def _find_reference_dirs_shallow(self, ref: str) -> List[Path]:
        candidates: List[Path] = []
        ref_lower = ref.lower()

        root_name = self.root.name.lower()
        if (ref_lower in root_name) if self.contains_mode else (root_name == ref_lower):
            candidates.append(self.root)

        direct = self.root / ref
        if direct.exists() and direct.is_dir():
            candidates.append(direct)

        try:
            with os.scandir(self.root) as it:
                for entry in it:
                    try:
                        if not entry.is_dir(follow_symlinks=False):
                            continue
                    except (PermissionError, OSError):
                        continue
                    child = Path(entry.path)
                    name = child.name.lower()
                    match = (ref_lower in name) if self.contains_mode else (name == ref_lower)
                    if match and child not in candidates:
                        candidates.append(child)
        except (PermissionError, OSError):
            pass

        return sorted(candidates, key=lambda p: str(p).lower())

    def _find_img_dirs(self, ref_dir: Path) -> List[Path]:
        dirs: List[Path] = []
        for p in self._iter_dirs_fast(ref_dir):
            if self.cancelled:
                break
            if p.name.upper().startswith("IMG"):
                dirs.append(p)
        return sorted(set(dirs), key=lambda p: str(p).lower())

    @staticmethod
    def _find_pngs_in_dir(img_dir: Path) -> List[Path]:
        pngs: List[Path] = []
        try:
            for p in img_dir.iterdir():
                if p.is_file() and p.suffix.lower() == ".png":
                    pngs.append(p)
        except (PermissionError, OSError):
            pass
        return sorted(pngs, key=lambda p: p.name.lower())

    @staticmethod
    def _record_from_file(ref: str, ref_dir: Path, img_dir: Path, png: Path) -> Optional[ImageRecord]:
        match = CAM_RE.search(png.stem)
        if not match:
            return None

        cam_number = int(match.group(1))
        cam_name = f"CAM{cam_number}"
        tags = extract_tags(png.stem, cam_name, ref)

        return ImageRecord(
            ref=ref,
            ref_dir=str(ref_dir),
            img_dir=str(img_dir),
            path=str(png),
            cam_number=cam_number,
            cam_name=cam_name,
            file_name=png.name,
            stem=png.stem,
            tags=tuple(tags),
        )


def extract_tags(stem: str, cam_name: str, ref: str) -> List[str]:
    """
    Détecte les tags utiles pour filtrer les rendus.

    Logique V2.4 stricte :
    - on cherche CAMn dans le nom ;
    - pour créer les filtres, on ignore tout ce qui est AVANT CAMn ;
    - seuls les tokens APRES CAMn deviennent des filtres.

    Exemple :
        REF001_Main_CAM1.png        -> aucun tag, car MAIN est avant CAM1
        REF001_CAM1_Main.png        -> tag MAIN
        REF001_CAM2_MID_CORR.png    -> tags MID, CORR
    """
    match = CAM_RE.search(stem)
    if not match:
        return []

    suffix = stem[match.end():]
    after_tokens = [
        t.strip().upper()
        for t in TOKEN_SPLIT_RE.split(suffix.lstrip(" _-.()[]{}"))
        if t.strip()
    ]

    ignore = {
        ref.upper(),
        cam_name.upper(),
        "PNG", "RENDER", "IMAGE", "IMG", "CAM",
    }

    useful: List[str] = []
    for token in after_tokens:
        if token in ignore:
            continue
        if token.isdigit():
            continue
        if len(token) <= 1:
            continue
        if token not in useful:
            useful.append(token)

    return useful


def wildcard_text_match(pattern: str, *values: str) -> bool:
    """Filtre custom simple : * agit comme joker sur le texte du fichier/référence/tags."""
    raw = pattern.strip()
    if not raw:
        return True

    haystack = " | ".join(str(v) for v in values if v).upper()
    parts = [p.strip() for p in re.split(r"[;,\n]+", raw) if p.strip()]
    if not parts:
        return True

    for part in parts:
        upper = part.upper()
        if "*" not in upper:
            if upper in haystack:
                return True
            continue

        regex = re.escape(upper).replace(r"\*", ".*")
        if re.search(regex, haystack, flags=re.IGNORECASE):
            return True

    return False




def format_rgb(rgb: Tuple[int, int, int]) -> str:
    return f"rgb({rgb[0]}, {rgb[1]}, {rgb[2]})"


def color_to_tuple(color: QColor) -> Tuple[int, int, int]:
    return (color.red(), color.green(), color.blue())


def tuple_to_color(rgb: Tuple[int, int, int]) -> QColor:
    return QColor(int(rgb[0]), int(rgb[1]), int(rgb[2]))






def human_file_size(size_bytes: int) -> str:
    """Formatte un poids fichier en unité lisible."""
    try:
        size = float(size_bytes)
    except Exception:
        return "-"
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size_bytes} B"





def image_metadata_summary_fast(
    path: str,
    original_size: Optional[Tuple[int, int]] = None,
    preview_size: Optional[Tuple[int, int]] = None,
) -> str:
    """Métadonnées rapides, sans relire lourdement le PNG dans le thread UI.

    Les dimensions exactes viennent du worker de chargement image une fois l'image
    disponible. Avant ce chargement, on affiche explicitement que les dimensions
    ne sont pas encore connues au lieu de laisser un libellé ambigu.
    """
    p = Path(path)
    try:
        stat = p.stat()
        size_text = human_file_size(int(stat.st_size))
        modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        size_text = "-"
        modified = "-"

    ow, oh = original_size or (0, 0)
    pw, ph = preview_size or (0, 0)
    if ow > 0 and oh > 0:
        dim_text = f"Dimensions : {ow} × {oh} px"
    else:
        dim_text = "Dimensions : en attente du chargement"

    preview_text = f"Aperçu : {pw} × {ph} px" if pw > 0 and ph > 0 else "Aperçu : -"
    return f"{dim_text} | {preview_text} | Poids : {size_text} | Modifié : {modified}"


def open_path_default(path: str) -> bool:
    """Ouvre un fichier/dossier avec l'application par défaut du système."""
    try:
        p = Path(path)
        if sys.platform.startswith("win") and hasattr(os, "startfile"):
            os.startfile(str(p))  # type: ignore[attr-defined]
            return True
        return QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))
    except Exception:
        return False


def reveal_in_file_manager(path: str) -> bool:
    """Ouvre le dossier de l'image, avec sélection du fichier sous Windows."""
    try:
        p = Path(path)
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", "/select,", str(p)])
            return True
        return QDesktopServices.openUrl(QUrl.fromLocalFile(str(p.parent)))
    except Exception:
        return False

def image_cache_key(path: str, preview_max_side: int) -> str:
    """Clé du cache mémoire, basée sur le chemin et la taille Preview max."""
    return f"{preview_max_side}::{path}"


class ImageLoadSignals(QObject):
    loaded = Signal(str, int, QImage, int, int)  # path, preview max, image, original w, original h
    failed = Signal(str, int, str)  # path, preview max, error


class ImageLoadTask(QRunnable):
    """Worker de chargement image. Charge du QImage, jamais de QPixmap hors thread UI."""

    def __init__(self, path: str, preview_max_side: int) -> None:
        super().__init__()
        self.path = path
        self.preview_max_side = int(preview_max_side)
        self.signals = ImageLoadSignals()
        self.setAutoDelete(True)

    def _can_emit(self) -> bool:
        """Retourne False quand l'application est déjà en fermeture.

        Sans cette protection, un worker QRunnable encore en cours peut finir après la
        destruction des objets Qt et provoquer ``RuntimeError: Signal source has been deleted``.
        """
        try:
            app = QApplication.instance()
            if app is None or QApplication.closingDown():
                return False
        except Exception:
            # Par sécurité, si Qt refuse l'état de fermeture, on tente quand même
            # l'émission puis on l'ignore proprement en cas de RuntimeError.
            return True
        return True

    def _emit_loaded_safe(self, image: QImage, original_w: int, original_h: int) -> None:
        if not self._can_emit():
            return
        try:
            self.signals.loaded.emit(self.path, self.preview_max_side, image, original_w, original_h)
        except RuntimeError:
            # Fermeture de l'application pendant le chargement : le résultat n'a plus de destinataire.
            return

    def _emit_failed_safe(self, error: str) -> None:
        if not self._can_emit():
            return
        try:
            self.signals.failed.emit(self.path, self.preview_max_side, error)
        except RuntimeError:
            return

    @Slot()
    def run(self) -> None:
        try:
            reader = QImageReader(self.path)
            reader.setAutoTransform(True)

            size = reader.size()
            original_w = int(size.width()) if size.isValid() else 0
            original_h = int(size.height()) if size.isValid() else 0

            if size.isValid():
                max_side = max(50, int(self.preview_max_side))
                w = size.width()
                h = size.height()
                if max(w, h) > max_side:
                    scale = max_side / float(max(w, h))
                    scaled_size = QSize(max(1, int(w * scale)), max(1, int(h * scale)))
                    reader.setScaledSize(scaled_size)

            image = reader.read()
            if image.isNull():
                self._emit_failed_safe(reader.errorString() or "Lecture impossible")
                return

            # Format rapide et stable pour affichage Qt, alpha conservé.
            image = image.convertToFormat(QImage.Format_ARGB32_Premultiplied)
            self._emit_loaded_safe(image, original_w, original_h)
        except RuntimeError:
            # Ne jamais laisser une exception Qt de fermeture sortir du worker.
            return


class ImageMemoryCache(QObject):
    """Cache mémoire LRU + chargement asynchrone."""

    image_ready = Signal(str, QImage, int, int)  # path, image, original w, original h
    image_failed = Signal(str, str)  # path, error
    cache_info_changed = Signal(int, int)  # preview count, pending count

    def __init__(self, preview_max_side: int = DEFAULT_PREVIEW_MAX_SIDE, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.preview_max_side = int(preview_max_side)
        self.preview_cache: OrderedDict[str, Tuple[QImage, int, int]] = OrderedDict()
        self.pending: Set[str] = set()
        self.preview_limit = 18
        self.pool = QThreadPool.globalInstance()
        self.pool.setMaxThreadCount(max(2, min(4, self.pool.maxThreadCount())))

    def set_preview_max_side(self, value: int) -> None:
        value = int(value)
        if value == self.preview_max_side:
            return
        self.preview_max_side = value
        self.preview_cache.clear()
        self.emit_cache_info()

    def clear(self) -> None:
        self.preview_cache.clear()
        self.pending.clear()
        self.emit_cache_info()

    def request(self, path: str) -> None:
        """Demande le chargement asynchrone d'une preview selon Preview max."""
        if not path:
            return
        key = image_cache_key(path, self.preview_max_side)

        if key in self.preview_cache:
            image, ow, oh = self.preview_cache.pop(key)
            self.preview_cache[key] = (image, ow, oh)
            QTimer.singleShot(0, lambda p=path, img=image, w=ow, h=oh: self.image_ready.emit(p, img, w, h))
            return

        if key in self.pending:
            return

        # V2.73/V2.74 : ne pas tester Path(path).is_file() ici. Sur SharePoint/OneDrive,
        # ce simple accès peut déclencher une hydratation réseau et geler l'UI.
        # On laisse le worker lire l'image en arrière-plan et remonter l'erreur si besoin.
        self.pending.add(key)
        task = ImageLoadTask(path=path, preview_max_side=self.preview_max_side)
        task.signals.loaded.connect(self._on_loaded)
        task.signals.failed.connect(self._on_failed)
        self.pool.start(task)
        self.emit_cache_info()

    @Slot(str, int, QImage, int, int)
    def _on_loaded(self, path: str, preview_max_side: int, image: QImage, original_w: int, original_h: int) -> None:
        key = image_cache_key(path, preview_max_side)
        self.pending.discard(key)

        # Ignore les anciennes previews si l'utilisateur a changé la taille max entre-temps.
        if preview_max_side != self.preview_max_side:
            self.emit_cache_info()
            return

        self.preview_cache[key] = (image, original_w, original_h)
        while len(self.preview_cache) > self.preview_limit:
            self.preview_cache.popitem(last=False)

        self.image_ready.emit(path, image, original_w, original_h)
        self.emit_cache_info()

    @Slot(str, int, str)
    def _on_failed(self, path: str, preview_max_side: int, error: str) -> None:
        key = image_cache_key(path, preview_max_side)
        self.pending.discard(key)
        self.image_failed.emit(path, error)
        self.emit_cache_info()

    def prefetch(self, paths: Sequence[str]) -> None:
        for path in paths:
            self.request(path)

    def emit_cache_info(self) -> None:
        self.cache_info_changed.emit(len(self.preview_cache), len(self.pending))






class CompareImageCanvas(QWidget):
    """Canvas unique de visualisation et comparaison.

    Il dessine l'image avec QPainter et n'utilise aucune scrollbar Qt.
    Les deux canvases de comparaison lisent exactement le même ViewerState
    (scale + centre normalisé), ce qui évite les dérives de synchro.
    """

    camera_changed = Signal(object)
    drawing_changed = Signal()
    canvas_activated = Signal(object)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(220, 180)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.bg_color = QColor(255, 255, 255)
        self.pixmap: Optional[QPixmap] = None
        self.overlay_pixmap: Optional[QPixmap] = None
        self.overlay_path: Optional[str] = None
        self.main_opacity = 1.0
        self.overlay_opacity = 0.0
        self.current_path: Optional[str] = None
        self.pending_path: Optional[str] = None
        self.original_image_width = 0
        self.original_image_height = 0
        self.camera_state = ViewerState(fit_mode=True, scale=1.0, center_norm_x=0.5, center_norm_y=0.5)
        self._dragging = False
        self._minimap_dragging = False
        self._last_mouse_pos = QPointF()
        self._suppress_camera_signal = False
        self._message = "Aucune image sélectionnée"
        self.show_minimap = True
        self.info_text = ""
        self.min_scale = 0.10
        self.max_scale = 40.0
        # V2.70+ : la qualité affichée est gérée uniquement par "Taille max image affichée".
        # Plus de bascule automatique/manuelle en pleine qualité.

        # V2.55 : dessin/screenshot. Les dessins sont stockés par chemin image
        # en coordonnées image, donc ils suivent naturellement zoom/pan.
        self.drawing_enabled = False
        self.drawing_tool = "freehand"
        self.drawing_color: Tuple[int, int, int] = (255, 40, 40)
        self.drawing_width = 4
        self.drawings_by_path: Dict[str, List[DrawingItem]] = {}
        self.drawing_redo_by_path: Dict[str, List[DrawingItem]] = {}
        self._drawing_active = False
        self._drawing_points: List[Tuple[float, float]] = []
        self.drawings_visible = True
        self._eraser_removed_items: List[DrawingItem] = []

    def has_image(self) -> bool:
        return self.pixmap is not None and not self.pixmap.isNull()

    def set_background(self, color: QColor) -> None:
        self.bg_color = QColor(color)
        self.update()

    def set_inspection_overlays(self, *, minimap: Optional[bool] = None, info_text: Optional[str] = None, **_ignored) -> None:
        if minimap is not None:
            self.show_minimap = bool(minimap)
        if info_text is not None:
            self.info_text = str(info_text)
        self.update()

    def set_loading(self, path: Optional[str], preserve_view: bool = True, state_override: Optional[ViewerState] = None) -> None:
        if not path:
            self.pending_path = None
            self.current_path = None
            self.original_image_width = 0
            self.original_image_height = 0
            self.pixmap = None
            self.overlay_pixmap = None
            self.overlay_path = None
            self.main_opacity = 1.0
            self.overlay_opacity = 0.0
            self._message = "Aucune image sélectionnée"
            self.update()
            return
        self.pending_path = path
        self._message = "Chargement de l'image..."
        if state_override is not None:
            self.apply_camera_state(state_override, emit_change=False)
        elif not preserve_view:
            self.camera_state = ViewerState(fit_mode=True, scale=1.0, center_norm_x=0.5, center_norm_y=0.5)
        self.update()

    def set_error(self, path: str, error: str) -> None:
        if self.pending_path and path != self.pending_path:
            return
        self.pixmap = None
        self.overlay_pixmap = None
        self.overlay_path = None
        self.current_path = None
        self.original_image_width = 0
        self.original_image_height = 0
        self.main_opacity = 1.0
        self.overlay_opacity = 0.0
        self._message = f"Impossible de charger :\n{path}\n\n{error}"
        self.update()

    def set_qimage(self, path: str, image: QImage, _original_w: int, _original_h: int, preserve_view: Optional[bool] = None) -> None:
        if self.pending_path and path != self.pending_path:
            return
        pixmap = QPixmap.fromImage(image)
        if pixmap.isNull():
            self.set_error(path, "Image invalide")
            return

        had_image = self.has_image()

        self.pixmap = pixmap
        self.current_path = path
        self.pending_path = path
        self.original_image_width = int(_original_w) if int(_original_w or 0) > 0 else pixmap.width()
        self.original_image_height = int(_original_h) if int(_original_h or 0) > 0 else pixmap.height()
        self._message = ""

        if not had_image and self.camera_state.fit_mode:
            self.fit_to_window(emit_change=False)

        self.update()

    def fit_scale(self) -> float:
        if not self.has_image():
            return 1.0
        w = max(1, self.width())
        h = max(1, self.height())
        iw = max(1, self.pixmap.width())
        ih = max(1, self.pixmap.height())
        return max(self.min_scale, min(self.max_scale, min(w / iw, h / ih) * 0.98))

    def effective_state(self) -> ViewerState:
        if not self.has_image():
            return ViewerState(fit_mode=True)
        if self.camera_state.fit_mode:
            return ViewerState(
                fit_mode=False,
                scale=self.fit_scale(),
                center_norm_x=0.5,
                center_norm_y=0.5,
                display_width=self.pixmap.width(),
                display_height=self.pixmap.height(),
            )
        return ViewerState(
            fit_mode=False,
            scale=max(self.min_scale, min(self.max_scale, float(self.camera_state.scale))),
            center_norm_x=float(self.camera_state.center_norm_x),
            center_norm_y=float(self.camera_state.center_norm_y),
            display_width=self.pixmap.width(),
            display_height=self.pixmap.height(),
        )

    def capture_camera_state(self) -> Optional[ViewerState]:
        if not self.has_image():
            return None
        return self.effective_state()

    def capture_state(self) -> ViewerState:
        state = self.capture_camera_state()
        return state if state is not None else ViewerState(fit_mode=True)

    def set_main_opacity(self, opacity: float) -> None:
        self.main_opacity = max(0.0, min(1.0, float(opacity)))
        self.update()

    def set_overlay_opacity(self, opacity: float) -> None:
        self.overlay_opacity = max(0.0, min(1.0, float(opacity)))
        self.update()

    def clear_overlay(self) -> None:
        self.overlay_pixmap = None
        self.overlay_path = None
        self.main_opacity = 1.0
        self.overlay_opacity = 0.0
        self.update()

    def set_overlay_qimage(self, path: str, image: QImage, opacity: float = 0.5) -> None:
        pixmap = QPixmap.fromImage(image)
        if pixmap.isNull():
            return
        self.overlay_pixmap = pixmap
        self.overlay_path = path
        self.overlay_opacity = max(0.0, min(1.0, float(opacity)))
        self.update()

    def apply_camera_state(self, state: ViewerState, emit_change: bool = False) -> None:
        if not self.has_image():
            self.camera_state = ViewerState(
                fit_mode=False,
                scale=max(self.min_scale, min(self.max_scale, float(state.scale))),
                center_norm_x=float(state.center_norm_x),
                center_norm_y=float(state.center_norm_y),
                display_width=int(state.display_width),
                display_height=int(state.display_height),
            )
            return
        self.camera_state = ViewerState(
            fit_mode=False,
            scale=max(self.min_scale, min(self.max_scale, float(state.scale))),
            center_norm_x=float(state.center_norm_x),
            center_norm_y=float(state.center_norm_y),
            display_width=self.pixmap.width(),
            display_height=self.pixmap.height(),
        )
        self.update()
        if emit_change and not self._suppress_camera_signal:
            self.camera_changed.emit(self.capture_camera_state())

    def fit_to_window(self, emit_change: bool = True) -> None:
        if not self.has_image():
            return
        self.camera_state = ViewerState(
            fit_mode=False,
            scale=self.fit_scale(),
            center_norm_x=0.5,
            center_norm_y=0.5,
            display_width=self.pixmap.width(),
            display_height=self.pixmap.height(),
        )
        self.update()
        if emit_change and not self._suppress_camera_signal:
            self.camera_changed.emit(self.capture_camera_state())

    def actual_size(self) -> None:
        if not self.has_image():
            return
        self.camera_state = ViewerState(
            fit_mode=False,
            scale=1.0,
            center_norm_x=0.5,
            center_norm_y=0.5,
            display_width=self.pixmap.width(),
            display_height=self.pixmap.height(),
        )
        self.update()
        if not self._suppress_camera_signal:
            self.camera_changed.emit(self.capture_camera_state())


    def _zoom_at(self, widget_pos: QPointF, factor: float) -> None:
        if not self.has_image():
            return
        state = self.effective_state()
        old_scale = max(self.min_scale, min(self.max_scale, float(state.scale)))
        new_scale = max(self.min_scale, min(self.max_scale, old_scale * factor))
        if abs(new_scale - old_scale) < 1e-9:
            return
        iw = max(1, self.pixmap.width())
        ih = max(1, self.pixmap.height())
        cx = state.center_norm_x * iw
        cy = state.center_norm_y * ih
        dx = float(widget_pos.x()) - self.width() / 2.0
        dy = float(widget_pos.y()) - self.height() / 2.0
        image_x_under_mouse = cx + dx / old_scale
        image_y_under_mouse = cy + dy / old_scale
        new_cx = image_x_under_mouse - dx / new_scale
        new_cy = image_y_under_mouse - dy / new_scale
        self.camera_state = ViewerState(
            fit_mode=False,
            scale=new_scale,
            center_norm_x=new_cx / iw,
            center_norm_y=new_cy / ih,
            display_width=iw,
            display_height=ih,
        )
        self.update()
        if not self._suppress_camera_signal:
            self.camera_changed.emit(self.capture_camera_state())
    def _pan_by(self, delta: QPointF) -> None:
        if not self.has_image():
            return
        state = self.effective_state()
        scale = max(self.min_scale, float(state.scale))
        iw = max(1, self.pixmap.width())
        ih = max(1, self.pixmap.height())
        cx = state.center_norm_x * iw - float(delta.x()) / scale
        cy = state.center_norm_y * ih - float(delta.y()) / scale
        self.camera_state = ViewerState(
            fit_mode=False,
            scale=scale,
            center_norm_x=cx / iw,
            center_norm_y=cy / ih,
            display_width=iw,
            display_height=ih,
        )
        self.update()
        if not self._suppress_camera_signal:
            self.camera_changed.emit(self.capture_camera_state())

    def _minimap_image_rect(self) -> Optional[Tuple[QRectF, int, int]]:
        if not getattr(self, "show_minimap", False) or not self.has_image():
            return None
        iw = max(1, self.pixmap.width())
        ih = max(1, self.pixmap.height())
        max_w, max_h = 170, 120
        margin = 12
        mini_scale = min(max_w / iw, max_h / ih)
        map_w = max(40, int(iw * mini_scale))
        map_h = max(40, int(ih * mini_scale))
        x = self.width() - map_w - margin
        y = self.height() - map_h - margin
        if x < margin or y < margin:
            return None
        return QRectF(x, y, map_w, map_h), iw, ih

    def _minimap_norm_from_pos(self, pos: QPointF, *, require_inside: bool) -> Optional[Tuple[float, float]]:
        info = self._minimap_image_rect()
        if info is None:
            return None
        img_rect, _iw, _ih = info
        if require_inside and not img_rect.contains(pos):
            return None
        nx = (pos.x() - img_rect.x()) / max(1.0, img_rect.width())
        ny = (pos.y() - img_rect.y()) / max(1.0, img_rect.height())
        return max(0.0, min(1.0, float(nx))), max(0.0, min(1.0, float(ny)))

    def _minimap_norm_at(self, pos: QPointF) -> Optional[Tuple[float, float]]:
        return self._minimap_norm_from_pos(pos, require_inside=True)

    def _set_camera_from_minimap(self, nx: float, ny: float, scale: Optional[float] = None) -> None:
        if not self.has_image():
            return
        state = self.effective_state()
        new_scale = float(scale if scale is not None else state.scale)
        new_scale = max(self.min_scale, min(self.max_scale, new_scale))
        self.camera_state = ViewerState(
            fit_mode=False,
            scale=new_scale,
            center_norm_x=max(0.0, min(1.0, float(nx))),
            center_norm_y=max(0.0, min(1.0, float(ny))),
            display_width=self.pixmap.width(),
            display_height=self.pixmap.height(),
        )
        self.update()
        if not self._suppress_camera_signal:
            self.camera_changed.emit(self.capture_camera_state())
    def _handle_minimap_click(self, pos: QPointF) -> bool:
        norm = self._minimap_norm_at(pos)
        if norm is None:
            return False
        self._minimap_dragging = True
        self._set_camera_from_minimap(norm[0], norm[1])
        return True

    def _handle_minimap_drag(self, pos: QPointF) -> bool:
        if not getattr(self, "_minimap_dragging", False):
            return False
        norm = self._minimap_norm_from_pos(pos, require_inside=False)
        if norm is None:
            return False
        self._set_camera_from_minimap(norm[0], norm[1])
        return True

    def _handle_minimap_wheel(self, pos: QPointF, delta_y: int) -> bool:
        norm = self._minimap_norm_at(pos)
        if norm is None or delta_y == 0:
            return False
        state = self.effective_state()
        steps = delta_y / 120.0
        factor = 1.15 ** steps
        new_scale = max(self.min_scale, min(self.max_scale, float(state.scale) * factor))
        self._set_camera_from_minimap(norm[0], norm[1], scale=new_scale)
        return True

    def set_drawing_enabled(self, enabled: bool) -> None:
        self.drawing_enabled = bool(enabled)
        if not enabled:
            self._drawing_active = False
            self._drawing_points = []
            self.unsetCursor()
        else:
            self.setCursor(Qt.CrossCursor)
        self.update()

    def set_drawing_tool(self, tool: str) -> None:
        self.drawing_tool = str(tool or "freehand")

    def set_drawing_color(self, color: QColor) -> None:
        if color.isValid():
            self.drawing_color = color_to_tuple(color)

    def set_drawing_width(self, width: int) -> None:
        self.drawing_width = max(1, min(80, int(width)))


    def toggle_drawings_visible(self) -> bool:
        self.drawings_visible = not self.drawings_visible
        self.update()
        return self.drawings_visible

    def _drawing_key(self) -> Optional[str]:
        return canonical_image_key(self.current_path) if self.current_path else None

    def _current_drawing_list(self) -> List[DrawingItem]:
        key = self._drawing_key()
        if not key:
            return []
        return self.drawings_by_path.setdefault(key, [])

    def _current_redo_list(self) -> List[DrawingItem]:
        key = self._drawing_key()
        if not key:
            return []
        return self.drawing_redo_by_path.setdefault(key, [])


    def _drawing_item_signature_runtime(self, item: DrawingItem) -> str:
        """Signature stable pour comparer des DrawingItem même après sauvegarde/session."""
        try:
            return json.dumps(
                {
                    "kind": item.kind,
                    "points": [[round(float(x), 4), round(float(y), 4)] for x, y in item.points],
                    "color": list(item.color),
                    "width": int(item.width),
                    "ref_width": int(item.ref_width),
                    "ref_height": int(item.ref_height),
                },
                sort_keys=True,
                ensure_ascii=False,
            )
        except Exception:
            return f"{item.kind}|{item.color}|{item.width}|{item.ref_width}|{item.ref_height}|{item.points}"

    def _visible_drawing_items(self, items: Optional[Sequence[DrawingItem]] = None) -> List[DrawingItem]:
        """Reconstruit les dessins visibles en appliquant les actions gomme/effacer.

        V2.77 : Effacer ne remplace plus toute la liste par une seule action.
        On garde l'historique en mémoire, et on applique les eraser_action au rendu.
        """
        source = list(items if items is not None else self._current_drawing_list())
        visible: List[DrawingItem] = []
        for item in source:
            if item.kind == "eraser_action":
                erased_ids = {id(erased) for erased in item.erased_items}
                erased_sigs = {self._drawing_item_signature_runtime(erased) for erased in item.erased_items}
                visible = [
                    drawing for drawing in visible
                    if id(drawing) not in erased_ids
                    and self._drawing_item_signature_runtime(drawing) not in erased_sigs
                ]
            elif item.kind in {"freehand", "line", "rect", "ellipse"} and item.points:
                visible.append(item)
        return visible

    def clear_current_drawings(self) -> None:
        key = self._drawing_key()
        if not key:
            return
        drawings = self.drawings_by_path.setdefault(key, [])
        visible_existing = self._visible_drawing_items(drawings)
        if visible_existing:
            action = DrawingItem(
                kind="eraser_action",
                points=[],
                color=tuple(self.drawing_color),
                width=int(self.drawing_width),
                ref_width=self.pixmap.width() if self.pixmap is not None else 0,
                ref_height=self.pixmap.height() if self.pixmap is not None else 0,
                erased_items=list(visible_existing),
            )
            # Ne pas écraser drawings_by_path[key] : sinon on perd l'historique
            # des boutons Dessin précédent / Dessin suivant.
            drawings.append(action)
            self.update()
            self.drawing_changed.emit()

    def undo_drawing(self) -> None:
        drawings = self._current_drawing_list()
        if not drawings:
            return
        item = drawings.pop()
        if item.kind == "eraser_action":
            # Annuler une gomme / un effacement global = restaurer les éléments supprimés.
            restored_ids = {id(existing) for existing in drawings}
            restored_sigs = {self._drawing_item_signature_runtime(existing) for existing in drawings}
            for erased in item.erased_items:
                sig = self._drawing_item_signature_runtime(erased)
                if id(erased) not in restored_ids and sig not in restored_sigs:
                    drawings.append(erased)
                    restored_ids.add(id(erased))
                    restored_sigs.add(sig)
        self._current_redo_list().append(item)
        self.update()
        self.drawing_changed.emit()

    def redo_drawing(self) -> None:
        redo = self._current_redo_list()
        if not redo:
            return
        item = redo.pop()
        drawings = self._current_drawing_list()
        if item.kind == "eraser_action":
            # V2.77 : on conserve l'historique et le rendu applique l'action.
            drawings.append(item)
        else:
            drawings.append(item)
        self.update()
        self.drawing_changed.emit()

    def _image_point_from_widget(self, pos: QPointF) -> Optional[Tuple[float, float]]:
        if not self.has_image():
            return None
        state = self.effective_state()
        target = self._target_rect_for_state(state)
        if target is None or target.width() <= 0 or target.height() <= 0:
            return None
        if not target.contains(pos):
            return None
        ix = (pos.x() - target.x()) / target.width() * self.pixmap.width()
        iy = (pos.y() - target.y()) / target.height() * self.pixmap.height()
        ix = max(0.0, min(float(self.pixmap.width()), float(ix)))
        iy = max(0.0, min(float(self.pixmap.height()), float(iy)))
        return ix, iy


    def _distance_point_to_segment(self, p: Tuple[float, float], a: Tuple[float, float], b: Tuple[float, float]) -> float:
        px, py = float(p[0]), float(p[1])
        ax, ay = float(a[0]), float(a[1])
        bx, by = float(b[0]), float(b[1])
        vx, vy = bx - ax, by - ay
        wx, wy = px - ax, py - ay
        length2 = vx * vx + vy * vy
        if length2 <= 0.000001:
            return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
        t = max(0.0, min(1.0, (wx * vx + wy * vy) / length2))
        cx, cy = ax + t * vx, ay + t * vy
        return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5

    def _drawing_item_hit_by_eraser(self, item: DrawingItem, current_point: Tuple[float, float], radius_current: float) -> bool:
        if not item.points or self.pixmap is None:
            return False
        cur_w = max(1.0, float(self.pixmap.width()))
        cur_h = max(1.0, float(self.pixmap.height()))
        ref_w = max(1.0, float(item.ref_width or cur_w))
        ref_h = max(1.0, float(item.ref_height or cur_h))
        point = (float(current_point[0]) / cur_w * ref_w, float(current_point[1]) / cur_h * ref_h)
        radius = float(radius_current) * ((ref_w / cur_w + ref_h / cur_h) / 2.0)
        points = list(item.points)
        if item.kind == "freehand":
            if len(points) == 1:
                return self._distance_point_to_segment(point, points[0], points[0]) <= radius
            return any(self._distance_point_to_segment(point, a, b) <= radius for a, b in zip(points, points[1:]))
        if item.kind == "line" and len(points) >= 2:
            return self._distance_point_to_segment(point, points[0], points[-1]) <= radius
        if item.kind in ("rect", "ellipse") and len(points) >= 2:
            x1, y1 = points[0]
            x2, y2 = points[-1]
            left, right = sorted((float(x1), float(x2)))
            top, bottom = sorted((float(y1), float(y2)))
            if item.kind == "rect":
                edges = [
                    ((left, top), (right, top)),
                    ((right, top), (right, bottom)),
                    ((right, bottom), (left, bottom)),
                    ((left, bottom), (left, top)),
                ]
                return any(self._distance_point_to_segment(point, a, b) <= radius for a, b in edges)
            cx = (left + right) / 2.0
            cy = (top + bottom) / 2.0
            rx = max(1.0, (right - left) / 2.0)
            ry = max(1.0, (bottom - top) / 2.0)
            # Approximation suffisante pour gomme : distance normalisée au bord de l'ellipse.
            value = ((point[0] - cx) / rx) ** 2 + ((point[1] - cy) / ry) ** 2
            return abs(value - 1.0) <= max(0.08, radius / max(rx, ry))
        return False

    def _erase_drawing_at(self, pos: QPointF) -> bool:
        point = self._image_point_from_widget(pos)
        if point is None:
            return False
        key = self._drawing_key()
        if not key:
            return False
        drawings = self.drawings_by_path.get(key, [])
        if not drawings:
            return False
        # V2.64 : la gomme utilise maintenant une taille en coordonnées image,
        # cohérente avec l'épaisseur des traits qui suit le zoom.
        # V2.77 : on gomme uniquement ce qui est réellement visible. Si Effacer
        # a ajouté une action d'historique, les anciens traits cachés ne doivent
        # pas être touchés par la gomme.
        radius = max(1.0, float(self.drawing_width))
        visible = self._visible_drawing_items(drawings)
        removed: List[DrawingItem] = []
        for item in visible:
            if self._drawing_item_hit_by_eraser(item, point, radius):
                removed.append(item)
        if removed:
            removed_ids = {id(item) for item in removed}
            removed_sigs = {self._drawing_item_signature_runtime(item) for item in removed}
            self.drawings_by_path[key] = [
                item for item in drawings
                if id(item) not in removed_ids
                and self._drawing_item_signature_runtime(item) not in removed_sigs
            ]
            self._eraser_removed_items.extend(removed)
            self.update()
            return True
        return False

    def _start_drawing(self, pos: QPointF) -> bool:
        point = self._image_point_from_widget(pos)
        if point is None:
            return False
        if self.drawing_tool == "eraser":
            self._drawing_active = True
            self._drawing_points = []
            self._eraser_removed_items = []
            self.setCursor(Qt.CrossCursor)
            self._erase_drawing_at(pos)
            return True
        self._drawing_active = True
        self._drawing_points = [point]
        self.setCursor(Qt.CrossCursor)
        self.update()
        return True

    def _update_drawing(self, pos: QPointF) -> bool:
        if not self._drawing_active:
            return False
        if self.drawing_tool == "eraser":
            self._erase_drawing_at(pos)
            return True
        point = self._image_point_from_widget(pos)
        if point is None:
            return True
        if self.drawing_tool == "freehand":
            self._drawing_points.append(point)
        else:
            self._drawing_points = [self._drawing_points[0], point]
        self.update()
        return True

    def _finish_drawing(self) -> bool:
        if not self._drawing_active:
            return False
        self._drawing_active = False
        points = list(self._drawing_points)
        self._drawing_points = []
        self.unsetCursor()
        if self.drawing_tool == "eraser":
            removed = list(self._eraser_removed_items)
            self._eraser_removed_items = []
            if removed:
                action = DrawingItem(
                    kind="eraser_action",
                    points=[],
                    color=tuple(self.drawing_color),
                    width=int(self.drawing_width),
                    ref_width=self.pixmap.width() if self.pixmap is not None else 0,
                    ref_height=self.pixmap.height() if self.pixmap is not None else 0,
                    erased_items=removed,
                )
                self._current_drawing_list().append(action)
                key = self._drawing_key()
                if key:
                    self.drawing_redo_by_path[key] = []
            self.update()
            if removed:
                self.drawing_changed.emit()
            return True
        if len(points) < 2:
            self.update()
            return True
        item = DrawingItem(
            kind=self.drawing_tool,
            points=points,
            color=tuple(self.drawing_color),
            width=int(self.drawing_width),
            ref_width=self.pixmap.width() if self.pixmap is not None else 0,
            ref_height=self.pixmap.height() if self.pixmap is not None else 0,
        )
        self._current_drawing_list().append(item)
        key = self._drawing_key()
        if key:
            self.drawing_redo_by_path[key] = []
        self.update()
        self.drawing_changed.emit()
        return True

    def _draw_one_drawing_item(self, painter: QPainter, item: DrawingItem, target: QRectF) -> None:
        if not item.points:
            return
        # V2.64 : l'épaisseur du dessin suit maintenant le zoom de l'image.
        # Avant, le pen était cosmetic=True, donc le trait gardait toujours la
        # même épaisseur écran. Ici, l'épaisseur est calculée depuis la taille
        # de référence du dessin vers la taille affichée dans le viewer.
        pen = QPen(QColor(*item.color))
        pen.setStyle(Qt.SolidLine)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setBrush(Qt.NoBrush)

        # V2.60 : projection stable. Les points sont enregistrés selon la taille
        # du pixmap au moment du dessin, puis reprojetés sur le target actuel.
        # Cela évite les dessins décalés après changement d'image / recharge preview.
        ref_w = float(item.ref_width or (self.pixmap.width() if self.pixmap is not None else 1))
        ref_h = float(item.ref_height or (self.pixmap.height() if self.pixmap is not None else 1))
        ref_w = max(1.0, ref_w)
        ref_h = max(1.0, ref_h)

        stroke_scale = ((target.width() / ref_w) + (target.height() / ref_h)) / 2.0
        stroke_width = max(0.75, float(item.width) * max(0.0001, stroke_scale))
        pen.setWidthF(stroke_width)
        pen.setCosmetic(False)
        painter.setPen(pen)

        def to_widget(point: Tuple[float, float]) -> QPointF:
            return QPointF(
                target.x() + (float(point[0]) / ref_w) * target.width(),
                target.y() + (float(point[1]) / ref_h) * target.height(),
            )

        pts = [to_widget(p) for p in item.points]
        if item.kind == "freehand":
            for a, b in zip(pts, pts[1:]):
                painter.drawLine(a, b)
        elif item.kind == "line" and len(pts) >= 2:
            painter.drawLine(pts[0], pts[-1])
        elif item.kind in ("rect", "ellipse") and len(pts) >= 2:
            rect = QRectF(pts[0], pts[-1]).normalized()
            if item.kind == "rect":
                painter.drawRect(rect)
            else:
                painter.drawEllipse(rect)

    def _draw_all_drawings(self, painter: QPainter, target: QRectF) -> None:
        if not self.has_image() or not self.drawings_visible:
            return
        key = self._drawing_key()
        if key:
            for item in self._visible_drawing_items(self.drawings_by_path.get(key, [])):
                self._draw_one_drawing_item(painter, item, target)
        if self._drawing_active and self.drawing_tool != "eraser" and len(self._drawing_points) >= 1:
            preview = DrawingItem(
                kind=self.drawing_tool,
                points=list(self._drawing_points),
                color=tuple(self.drawing_color),
                width=int(self.drawing_width),
                ref_width=self.pixmap.width() if self.pixmap is not None else 0,
                ref_height=self.pixmap.height() if self.pixmap is not None else 0,
            )
            self._draw_one_drawing_item(painter, preview, target)


    def _draw_eraser_cursor(self, painter: QPainter, target: QRectF) -> None:
        """Affiche le cercle d'action de la gomme sans l'enregistrer dans les dessins."""
        if not (self.drawing_enabled and self.drawing_tool == "eraser" and self.has_image()):
            return
        if not target.contains(self._last_mouse_pos):
            return
        iw = max(1.0, float(self.pixmap.width() if self.pixmap is not None else 1))
        ih = max(1.0, float(self.pixmap.height() if self.pixmap is not None else 1))
        screen_radius = max(3.0, float(self.drawing_width) * ((target.width() / iw + target.height() / ih) / 2.0))
        pen = QPen(QColor(255, 255, 255, 230))
        pen.setWidthF(1.25)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(QColor(0, 0, 0, 35))
        center = self._last_mouse_pos
        painter.drawEllipse(QRectF(center.x() - screen_radius, center.y() - screen_radius, screen_radius * 2.0, screen_radius * 2.0))

    def wheelEvent(self, event) -> None:  # type: ignore[override]
        if event.angleDelta().y() == 0:
            event.ignore()
            return
        if self._handle_minimap_wheel(event.position(), event.angleDelta().y()):
            event.accept()
            return
        steps = event.angleDelta().y() / 120.0
        factor = 1.15 ** steps
        self._zoom_at(event.position(), factor)
        event.accept()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton and self.has_image():
            self.canvas_activated.emit(self)
            if self._handle_minimap_click(event.position()):
                event.accept()
                return
            if self.drawing_enabled and self._start_drawing(event.position()):
                event.accept()
                return
            self._dragging = True
            self._last_mouse_pos = event.position()
            self._pan_last_mouse_pos = event.position()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        self._last_mouse_pos = event.position()
        if self.drawing_enabled and self.drawing_tool == "eraser" and self.has_image():
            self.update()
        if self._minimap_dragging and self.has_image():
            self._handle_minimap_drag(event.position())
            event.accept()
            return
        if self._drawing_active and self.has_image():
            self._update_drawing(event.position())
            event.accept()
            return
        if self._dragging and self.has_image():
            # _last_mouse_pos vient d'être mis à jour pour le curseur gomme ; on recalcule
            # le delta depuis la position précédente conservée temporairement.
            delta = event.position() - getattr(self, "_pan_last_mouse_pos", event.position())
            self._pan_last_mouse_pos = event.position()
            self._pan_by(delta)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton and self._minimap_dragging:
            self._minimap_dragging = False
            event.accept()
            return
        if event.button() == Qt.LeftButton and self._drawing_active:
            self._finish_drawing()
            event.accept()
            return
        if event.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            self._pan_last_mouse_pos = event.position()
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton and self.has_image():
            state = self.effective_state()
            if abs(state.scale - self.fit_scale()) < 0.0005:
                self.actual_size()
            else:
                self.fit_to_window()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self.update()

    def _target_rect_for_state(self, state: ViewerState) -> Optional[QRectF]:
        if not self.has_image():
            return None
        scale = max(self.min_scale, float(state.scale))
        iw = self.pixmap.width()
        ih = self.pixmap.height()
        cx = state.center_norm_x * iw
        cy = state.center_norm_y * ih
        x = self.width() / 2.0 - cx * scale
        y = self.height() / 2.0 - cy * scale
        return QRectF(x, y, iw * scale, ih * scale)

    def _draw_canvas_info(self, painter: QPainter) -> None:
        if not self.info_text:
            return
        fm = painter.fontMetrics()
        text_rect = fm.boundingRect(self.info_text).adjusted(-10, -5, 10, 5)
        text_rect.moveTopLeft(QPoint(max(8, (self.width() - text_rect.width()) // 2), 8))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 155))
        painter.drawRoundedRect(QRectF(text_rect), 5, 5)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(text_rect, Qt.AlignCenter, self.info_text)

    def _draw_canvas_minimap(self, painter: QPainter, state: ViewerState) -> None:
        info = self._minimap_image_rect()
        if info is None:
            return
        img_rect, iw, ih = info
        x = int(img_rect.x())
        y = int(img_rect.y())
        map_w = int(img_rect.width())
        map_h = int(img_rect.height())
        outer = QRectF(x - 5, y - 5, map_w + 10, map_h + 10)
        painter.setPen(QColor(255, 255, 255, 80))
        painter.setBrush(QColor(0, 0, 0, 145))
        painter.drawRoundedRect(outer, 6, 6)
        img_rect = QRectF(x, y, map_w, map_h)
        painter.setPen(QColor(255, 255, 255, 120))
        painter.setBrush(QColor(120, 120, 120, 120))
        painter.drawRect(img_rect)

        # V2.29 : aperçu réel de l'image dans la mini-map du comparateur.
        if self.pixmap is not None and not self.pixmap.isNull():
            painter.save()
            painter.setOpacity(0.58)
            painter.drawPixmap(img_rect, self.pixmap, QRectF(self.pixmap.rect()))
            painter.restore()

        zoom = max(0.0001, float(state.scale))
        visible_w = self.width() / zoom
        visible_h = self.height() / zoom
        cx = state.center_norm_x * iw
        cy = state.center_norm_y * ih
        left = max(0.0, min(float(iw), cx - visible_w / 2.0))
        top = max(0.0, min(float(ih), cy - visible_h / 2.0))
        right = max(0.0, min(float(iw), cx + visible_w / 2.0))
        bottom = max(0.0, min(float(ih), cy + visible_h / 2.0))
        view_rect = QRectF(
            x + (left / iw) * map_w,
            y + (top / ih) * map_h,
            max(2.0, ((right - left) / iw) * map_w),
            max(2.0, ((bottom - top) / ih) * map_h),
        )
        painter.setPen(QColor(255, 255, 255, 230))
        painter.setBrush(QColor(255, 255, 255, 35))
        painter.drawRect(view_rect)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        try:
            painter.fillRect(self.rect(), self.bg_color)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            if not self.has_image():
                painter.setPen(QColor(235, 235, 235))
                painter.drawText(self.rect(), Qt.AlignCenter, self._message)
                return
            state = self.effective_state()
            scale = max(self.min_scale, float(state.scale))
            target = self._target_rect_for_state(state)
            if target is None:
                return
            self._paint_image_and_drawings(painter, target, draw_eraser_cursor=True, draw_border=True)

            self._draw_canvas_info(painter)
            self._draw_canvas_minimap(painter, state)

            percent = scale * 100.0
            zoom_text = f"Zoom : {percent:.0f}%" if percent >= 10 else f"Zoom : {percent:.1f}%"
            fm = painter.fontMetrics()
            text_rect = fm.boundingRect(zoom_text).adjusted(-7, -4, 7, 4)
            text_rect.moveTopLeft(QPoint(8, 8))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, 150))
            painter.drawRoundedRect(QRectF(text_rect), 4, 4)
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(text_rect, Qt.AlignCenter, zoom_text)
        finally:
            painter.end()

    def _paint_image_and_drawings(
        self,
        painter: QPainter,
        target: QRectF,
        *,
        draw_eraser_cursor: bool = False,
        draw_border: bool = False,
    ) -> None:
        """Peint seulement le contenu image utile."""
        if not self.has_image() or self.pixmap is None:
            return
        iw = self.pixmap.width()
        ih = self.pixmap.height()
        painter.save()
        painter.setOpacity(self.main_opacity)
        painter.drawPixmap(target, self.pixmap, QRectF(0, 0, iw, ih))
        painter.restore()

        if self.overlay_pixmap is not None and not self.overlay_pixmap.isNull():
            painter.save()
            painter.setOpacity(self.overlay_opacity)
            painter.drawPixmap(target, self.overlay_pixmap, QRectF(self.overlay_pixmap.rect()))
            painter.restore()

        self._draw_all_drawings(painter, target)
        if draw_eraser_cursor:
            self._draw_eraser_cursor(painter, target)

        if draw_border:
            border_pen = QPen(image_border_color_for_background(self.bg_color), 2)
            border_pen.setCosmetic(True)
            painter.setPen(border_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(target)

    def grab_clean_content(self) -> QPixmap:
        """Capture le cadre viewer sans overlays UI.

        Inclus : fond, image affichée, éventuelle image de superposition visible,
        dessins. Exclus : zoom, mini-map, flèches, infos et curseur gomme.
        """
        pixmap = QPixmap(max(1, self.width()), max(1, self.height()))
        pixmap.fill(self.bg_color)
        painter = QPainter(pixmap)
        try:
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            if self.has_image():
                target = self._target_rect_for_state(self.effective_state())
                if target is not None:
                    self._paint_image_and_drawings(painter, target, draw_eraser_cursor=False, draw_border=False)
            else:
                painter.setPen(QColor(235, 235, 235))
                painter.drawText(QRectF(pixmap.rect()), Qt.AlignCenter, self._message)
        finally:
            painter.end()
        return pixmap



class DetachedViewerWindow(QMainWindow):
    """Fenêtre flottante qui héberge le viewer principal et tous les onglets CAM."""

    reattach_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Viewer flottant")
        self.resize(1350, 900)
        self.suppress_reattach = False
        self._tabs_widget: Optional[QWidget] = None

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)

        top = QHBoxLayout()
        self.info_label = QLabel("Aucune image affichée")
        self.info_label.setStyleSheet("font-size: 16px; font-weight: bold; color: white;")
        self.info_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.info_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        top.addWidget(self.info_label, 1)

        self.tabs_holder = QWidget()
        self.tabs_holder_layout = QVBoxLayout(self.tabs_holder)
        self.tabs_holder_layout.setContentsMargins(0, 0, 0, 0)

        layout.addLayout(top)
        layout.addWidget(self.tabs_holder, 1)
        self.setCentralWidget(central)

    def set_tabs_widget(self, tabs_widget: QWidget) -> None:
        if self._tabs_widget is tabs_widget:
            return
        if self._tabs_widget is not None:
            self._tabs_widget.setParent(None)
        self._tabs_widget = tabs_widget
        tabs_widget.setParent(None)
        self.tabs_holder_layout.addWidget(tabs_widget, 1)
        tabs_widget.show()

    def take_tabs_widget(self) -> Optional[QWidget]:
        tabs = self._tabs_widget
        if tabs is None:
            return None
        self.tabs_holder_layout.removeWidget(tabs)
        tabs.setParent(None)
        self._tabs_widget = None
        return tabs

    def update_current_info(self, cam_text: str = "", ref: str = "", file_name: str = "", index: int = 0, total: int = 0) -> None:
        if cam_text and ref:
            pos = f"{index}/{total}" if total else ""
            self.info_label.setText(f"{cam_text}  |  {ref}  |  {pos}  |  {file_name}")
            self.setWindowTitle(f"Viewer flottant - {cam_text} - {ref}")
        elif cam_text:
            self.info_label.setText(cam_text)
            self.setWindowTitle(f"Viewer flottant - {cam_text}")
        else:
            self.info_label.setText("Aucune image affichée")
            self.setWindowTitle("Viewer flottant")

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self.suppress_reattach:
            event.accept()
            return
        self.reattach_requested.emit()
        event.ignore()
        self.hide()


class WidgetPopupDialog(QDialog):
    """Popup réutilisable qui héberge un widget existant sans dupliquer les données."""

    def __init__(self, title: str, widget: QWidget, parent: Optional[QWidget] = None, info: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(900, 650)
        layout = QVBoxLayout(self)
        if info:
            label = QLabel(info)
            label.setStyleSheet("color: white;")
            label.setWordWrap(True)
            layout.addWidget(label)

        widget.setParent(self)
        layout.addWidget(widget, 1)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        btn_close = QPushButton("Fermer")
        btn_close.clicked.connect(self.hide)
        bottom.addWidget(btn_close)
        layout.addLayout(bottom)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        event.ignore()
        self.hide()


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
        # V2.97 : même largeur qu'avant, mais fenêtre plus haute pour rendre
        # toute la zone Démarrage rapide directement lisible au lancement.
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

        # Feedback live : la ligne Racine/Références doit suivre les changements
        # venant de la page de démarrage comme ceux venant de la fenêtre principale.
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
        """Retourne (référence, chemin racine résolu) pour une ligne de la liste finale."""
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
        """Trouve le dossier IMG d'une référence, en privilégiant IMG direct puis récursif."""
        ref_root = Path(str(ref_root_path or "").strip().strip('"'))
        if not ref_root.exists() or not ref_root.is_dir():
            return ""

        # Cas prioritaire : dossier IMG directement sous la référence, avec tolérance casse.
        try:
            for child in ref_root.iterdir():
                if child.is_dir() and child.name.lower() == "img":
                    return str(child)
        except Exception:
            return ""

        # Fallback : recherche récursive, utile si l'arborescence contient un niveau intermédiaire.
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
        """Menu clic droit sur la liste finale/source de vérité des références."""
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
                QMessageBox.warning(
                    self,
                    "Chemin introuvable",
                    f"Aucun chemin valide n'a été trouvé pour la référence :\n{ref}",
                )
            return

        if action is open_img_action:
            if not ref_root_path:
                QMessageBox.warning(
                    self,
                    "Chemin référence introuvable",
                    f"Impossible d'ouvrir le dossier IMG : la référence est introuvable.\n\nRéférence : {ref}",
                )
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
            self.main_window.log(
                f"WARNING : dossier IMG introuvable pour {ref}. Ouverture du dossier racine : {ref_root_path}"
            )
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

class ColorButton(QToolButton):
    """Petit bouton de fond avec swatch couleur, sans stylesheet dynamique.

    Les anciennes versions appliquaient un setStyleSheet() par bouton et par
    refresh. Sur certains styles Windows/PySide6, Qt loggait en boucle
    "Could not parse stylesheet of object ColorButton" et pouvait bloquer
    le scan. Ici, le bouton garde le style natif Qt et seule une petite icône
    colorée représente le fond.
    """

    clicked_index = Signal(int)
    edit_requested = Signal(int)

    def __init__(self, index: int, color: Tuple[int, int, int], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.index = index
        self.rgb = color
        self.setText(f"Fond {index + 1}")
        self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.setMinimumWidth(95)
        self.setIconSize(QSize(18, 18))
        self.set_color(color)
        self.clicked.connect(lambda: self.clicked_index.emit(self.index))
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(lambda _pos: self.edit_requested.emit(self.index))

    def _make_color_icon(self, color: Tuple[int, int, int]) -> QIcon:
        pixmap = QPixmap(18, 18)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setPen(QPen(QColor(70, 70, 70), 1))
            painter.setBrush(QColor(*color))
            painter.drawRoundedRect(QRectF(1, 1, 16, 16), 3, 3)
        finally:
            painter.end()
        return QIcon(pixmap)

    def set_color(self, color: Tuple[int, int, int]) -> None:
        self.rgb = color
        self.setIcon(self._make_color_icon(color))
        self.setToolTip(
            f"Fond {self.index + 1} : {format_rgb(color)}\n"
            "Clic gauche = choisir ce fond | clic droit = modifier la couleur"
        )


class NoWheelComboBox(QComboBox):
    """ComboBox dont la valeur ne change pas avec la molette.

    Utilisé uniquement comme éditeur temporaire de la colonne Statut.
    On ne crée plus un combo permanent par ligne : c'était lourd pendant le scan.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.ClickFocus)


    def wheelEvent(self, event) -> None:  # type: ignore[override]
        event.ignore()


class StatusComboDelegate(QStyledItemDelegate):
    """Colonne Statut visible comme une liste déroulante, sans widgets permanents.

    V2.74 : le tableau doit rester léger, mais la colonne Statut doit ressembler
    en permanence à une vraie liste déroulante. Le ComboBox n'est créé qu'au clic,
    puis son popup s'ouvre automatiquement.
    """

    def paint(self, painter, option, index) -> None:  # type: ignore[override]
        # Rendu custom : la flèche de la liste déroulante est beaucoup plus visible
        # que le rendu système sombre par défaut.
        value = normalize_status(str(index.data(Qt.EditRole) or index.data(Qt.DisplayRole) or ""))
        painter.save()
        try:
            rect = option.rect.adjusted(4, 3, -4, -3)
            selected = bool(option.state & QStyle.State_Selected)
            bg = QColor(45, 45, 45) if selected else QColor(31, 31, 31)
            border = QColor(135, 135, 135) if selected else QColor(84, 84, 84)
            arrow_bg = QColor(72, 72, 72) if selected else QColor(55, 55, 55)
            text_color = status_text_color(value)
            arrow_color = QColor(245, 245, 245)

            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setPen(QPen(border, 1))
            painter.setBrush(bg)
            painter.drawRoundedRect(QRectF(rect), 5, 5)

            arrow_rect = rect.adjusted(max(0, rect.width() - 36), 1, -1, -1)
            painter.setPen(Qt.NoPen)
            painter.setBrush(arrow_bg)
            painter.drawRoundedRect(QRectF(arrow_rect), 4, 4)

            text_rect = rect.adjusted(8, 0, -40, 0)
            painter.setPen(text_color)
            painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, value)

            painter.setPen(arrow_color)
            painter.drawText(arrow_rect, Qt.AlignCenter, "▼")
        finally:
            painter.restore()

    def createEditor(self, parent, option, index):  # type: ignore[override]
        editor = NoWheelComboBox(parent)
        editor.addItems(STATUS_CHOICES)
        for idx, status in enumerate(STATUS_CHOICES):
            editor.setItemData(idx, QBrush(status_text_color(status)), Qt.ForegroundRole)
        editor.setStyleSheet(
            "QComboBox { background-color: #1f1f1f; color: #f0f0f0; border: 1px solid #777; padding: 3px; }"
            "QComboBox QAbstractItemView { background-color: #202020; color: #f0f0f0; selection-background-color: #444; }"
        )
        QTimer.singleShot(0, editor.showPopup)
        return editor

    def setEditorData(self, editor, index) -> None:  # type: ignore[override]
        if isinstance(editor, QComboBox):
            value = normalize_status(str(index.data(Qt.EditRole) or index.data(Qt.DisplayRole) or ""))
            pos = editor.findText(value)
            editor.setCurrentIndex(max(0, pos))

    def setModelData(self, editor, model, index) -> None:  # type: ignore[override]
        if isinstance(editor, QComboBox):
            model.setData(index, normalize_status(editor.currentText()), Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index) -> None:  # type: ignore[override]
        editor.setGeometry(option.rect.adjusted(3, 3, -3, -3))


class CommentLineEditDelegate(QStyledItemDelegate):
    """Colonne Commentaire affichée comme zone de texte légère.

    V2.74 : aucun QLineEdit permanent par ligne, mais un rendu visuel de champ
    texte et édition au simple clic.
    """

    def paint(self, painter, option, index) -> None:  # type: ignore[override]
        painter.save()
        try:
            rect = option.rect.adjusted(3, 3, -3, -3)
            if option.state & QStyle.State_Selected:
                painter.fillRect(option.rect, QColor(63, 75, 90))
                border = QColor(125, 150, 180)
                bg = QColor(55, 63, 75)
                text_color = QColor(255, 255, 255)
            else:
                border = QColor(74, 82, 96)
                bg = QColor(31, 36, 44)
                text_color = QColor(230, 230, 230)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setPen(QPen(border, 1))
            painter.setBrush(bg)
            painter.drawRoundedRect(QRectF(rect), 4, 4)
            text = str(index.data(Qt.DisplayRole) or "")
            painter.setPen(text_color)
            text_rect = rect.adjusted(7, 0, -7, 0)
            painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, text)
        finally:
            painter.restore()

    def createEditor(self, parent, option, index):  # type: ignore[override]
        editor = QLineEdit(parent)
        editor.setFrame(False)
        editor.setClearButtonEnabled(True)
        return editor

    def setEditorData(self, editor, index) -> None:  # type: ignore[override]
        if isinstance(editor, QLineEdit):
            editor.setText(str(index.data(Qt.EditRole) or index.data(Qt.DisplayRole) or ""))
            editor.selectAll()

    def setModelData(self, editor, model, index) -> None:  # type: ignore[override]
        if isinstance(editor, QLineEdit):
            model.setData(index, editor.text().strip(), Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index) -> None:  # type: ignore[override]
        editor.setGeometry(option.rect.adjusted(6, 5, -6, -5))


class DrawingToolsDialog(QDialog):
    """Palette dessin verticale compacte, au format barre d'outils."""

    def __init__(self, tab: "CamTab", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.tab = tab
        self.current_color = QColor(*self.tab.active_drawing_viewer().drawing_color)
        self.setWindowTitle("Dessiner")
        self.setModal(False)
        self.setFixedSize(150, 338)
        self.setSizeGripEnabled(False)
        self.setStyleSheet(
            "QDialog { background-color: #232323; }"
            "QToolButton { background-color: #4a4a4a; border: 1px solid #5d5d5d; border-radius: 4px; }"
            "QToolButton:hover { background-color: #5a5a5a; }"
            "QToolButton:checked { background-color: #6a6a6a; border: 1px solid #8a8a8a; }"
            "QLabel { color: #f0f0f0; font-weight: bold; }"
            "QLabel#DrawingSizeValue { background-color: #2f2f2f; color: #ffffff; border: 1px solid #707070; border-radius: 4px; padding: 4px; }"
            "QPushButton#DrawingSizeButton { background-color: #454545; color: #ffffff; border: 1px solid #777777; border-radius: 4px; font-weight: bold; }"
            "QPushButton#DrawingSizeButton:hover { background-color: #5a5a5a; border-color: #ffffff; }"
            "QPushButton { background-color: #3a3a3a; color: white; border: 1px solid #4d4d4d; padding: 4px; }"
            "QPushButton:hover { background-color: #4a4a4a; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)
        tools_widget = QWidget()
        tools_grid = QGridLayout(tools_widget)
        tools_grid.setContentsMargins(0, 0, 0, 0)
        tools_grid.setHorizontalSpacing(8)
        tools_grid.setVerticalSpacing(6)
        self.tool_buttons: Dict[str, QToolButton] = {}

        tool_specs = [
            ("undo", "Dessin précédent", "undo"),
            ("redo", "Dessin suivant", "redo"),
            ("freehand", "Main levée", "freehand"),
            ("line", "Ligne droite", "line"),
            ("rect", "Rectangle", "rect"),
            ("ellipse", "Ellipse", "ellipse"),
            ("eraser", "Gomme", "eraser"),
            ("color", "Couleur du trait", "color"),
        ]

        for idx, (tool_key, tooltip, icon_kind) in enumerate(tool_specs):
            btn = QToolButton()
            btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
            btn.setIconSize(QSize(26, 26))
            btn.setMinimumSize(44, 40)
            btn.setMaximumSize(46, 42)
            btn.setToolTip(tooltip)

            if tool_key == "undo":
                btn.setIcon(self._make_tool_icon(icon_kind))
                btn.clicked.connect(self.undo_drawing)
            elif tool_key == "redo":
                btn.setIcon(self._make_tool_icon(icon_kind))
                btn.clicked.connect(self.redo_drawing)
            elif tool_key == "color":
                self.btn_color = btn
                btn.setIcon(self._make_color_icon(self.current_color))
                btn.clicked.connect(self.choose_color)
            else:
                btn.setCheckable(True)
                btn.setIcon(self._make_tool_icon(icon_kind))
                btn.clicked.connect(lambda checked=False, tk=tool_key: self.select_tool(tk))
                self.tool_group.addButton(btn)
                self.tool_buttons[tool_key] = btn

            tools_grid.addWidget(btn, idx // 2, idx % 2)

        layout.addWidget(tools_widget, 0, Qt.AlignHCenter)

        label_size = QLabel("Taille")
        label_size.setAlignment(Qt.AlignCenter)
        label_size.setStyleSheet("QLabel { color: #f0f0f0; font-size: 14px; font-weight: bold; }")
        layout.addWidget(label_size)

        self.current_width = max(1, min(80, int(self.tab.active_drawing_viewer().drawing_width)))
        size_row = QHBoxLayout()
        size_row.setContentsMargins(0, 0, 0, 0)
        size_row.setSpacing(5)
        self.btn_width_minus = QPushButton("-")
        self.btn_width_minus.setObjectName("DrawingSizeButton")
        self.btn_width_minus.setFixedSize(32, 26)
        self.btn_width_minus.setToolTip("Diminuer la taille")
        self.btn_width_minus.clicked.connect(lambda: self.change_width_delta(-1))
        self.width_value_label = QLabel(str(self.current_width))
        self.width_value_label.setObjectName("DrawingSizeValue")
        self.width_value_label.setAlignment(Qt.AlignCenter)
        self.width_value_label.setFixedSize(42, 26)
        self.width_value_label.setToolTip("Épaisseur du trait / taille de la gomme")
        self.btn_width_plus = QPushButton("+")
        self.btn_width_plus.setObjectName("DrawingSizeButton")
        self.btn_width_plus.setFixedSize(32, 26)
        self.btn_width_plus.setToolTip("Augmenter la taille")
        self.btn_width_plus.clicked.connect(lambda: self.change_width_delta(1))
        size_row.addWidget(self.btn_width_minus)
        size_row.addWidget(self.width_value_label)
        size_row.addWidget(self.btn_width_plus)
        layout.addLayout(size_row)

        # V2.77 : plus de grand stretch entre Taille et Effacer.
        layout.addSpacing(4)
        self.btn_clear = QPushButton("Effacer")
        self.btn_clear.setFixedHeight(24)
        self.btn_clear.setToolTip("Effacer tous les dessins de l'image active")
        self.btn_clear.clicked.connect(self.clear_current_drawings)
        # Bordure rouge légère uniquement pour signaler l'action destructive.
        self.btn_clear.setStyleSheet(
            "QPushButton { background-color: #3a3a3a; color: white; border: 1px solid #d64b4b; padding: 3px; }"
            "QPushButton:hover { background-color: #4a3030; }"
        )
        layout.addWidget(self.btn_clear)

        self.btn_close = QPushButton("Fermer")
        self.btn_close.setFixedHeight(24)
        self.btn_close.clicked.connect(self.close)
        layout.addWidget(self.btn_close)

        self.apply_color(self.current_color)
        self.apply_width(self.current_width)
        self.tab.set_drawing_enabled_for_all(True)
        self.select_tool(str(self.tab.active_drawing_viewer().drawing_tool or "freehand"))

    def _make_color_icon(self, color: QColor) -> QIcon:
        pixmap = QPixmap(28, 28)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setPen(QPen(QColor(65, 65, 65), 1))
            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(4, 4, 20, 20), 4, 4)
        finally:
            painter.end()
        return QIcon(pixmap)

    def _make_tool_icon(self, kind: str) -> QIcon:
        pixmap = QPixmap(28, 28)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)
            pen = QPen(QColor(238, 238, 238), 2)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            if kind == "undo":
                painter.drawLine(QPointF(11, 9), QPointF(6, 14))
                painter.drawLine(QPointF(6, 14), QPointF(11, 19))
                painter.drawLine(QPointF(7, 14), QPointF(18, 14))
                painter.drawLine(QPointF(18, 14), QPointF(18, 19))
            elif kind == "redo":
                painter.drawLine(QPointF(17, 9), QPointF(22, 14))
                painter.drawLine(QPointF(22, 14), QPointF(17, 19))
                painter.drawLine(QPointF(21, 14), QPointF(10, 14))
                painter.drawLine(QPointF(10, 14), QPointF(10, 19))
            elif kind == "freehand":
                pts = [QPointF(5, 19), QPointF(9, 11), QPointF(13, 16), QPointF(18, 8), QPointF(23, 13)]
                for a, b in zip(pts, pts[1:]):
                    painter.drawLine(a, b)
            elif kind == "line":
                painter.drawLine(QPointF(6, 22), QPointF(22, 6))
            elif kind == "rect":
                painter.drawRect(QRectF(6, 7, 16, 13))
            elif kind == "ellipse":
                painter.drawEllipse(QRectF(6, 7, 16, 13))
            elif kind == "eraser":
                painter.drawLine(QPointF(8, 18), QPointF(14, 9))
                painter.drawLine(QPointF(14, 9), QPointF(21, 14))
                painter.drawLine(QPointF(21, 14), QPointF(15, 23))
                painter.drawLine(QPointF(15, 23), QPointF(8, 18))
                painter.drawLine(QPointF(6, 23), QPointF(22, 23))
        finally:
            painter.end()
        return QIcon(pixmap)

    def select_tool(self, tool_key: str) -> None:
        tool_key = str(tool_key or "freehand")
        btn = self.tool_buttons.get(tool_key)
        if btn is not None:
            btn.setChecked(True)
        self.tab.set_drawing_tool_for_all(tool_key)

    def undo_drawing(self) -> None:
        self.tab.active_drawing_viewer().undo_drawing()

    def redo_drawing(self) -> None:
        self.tab.active_drawing_viewer().redo_drawing()

    def clear_current_drawings(self) -> None:
        self.tab.active_drawing_viewer().clear_current_drawings()

    def change_width_delta(self, delta: int) -> None:
        self.apply_width(self.current_width + int(delta))

    def apply_width(self, value: int) -> None:
        self.current_width = max(1, min(80, int(value)))
        if hasattr(self, "width_value_label"):
            self.width_value_label.setText(str(self.current_width))
        self.tab.set_drawing_width_for_all(self.current_width)

    def apply_color(self, color: QColor) -> None:
        self.tab.set_drawing_color_for_all(color)

    def choose_color(self) -> None:
        color = QColorDialog.getColor(self.current_color, self, "Couleur du trait")
        if not color.isValid():
            return
        self.current_color = color
        self.btn_color.setIcon(self._make_color_icon(color))
        self.apply_color(color)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.tab.set_drawing_enabled_for_all(False)
        super().closeEvent(event)


class ScreenshotPreviewCanvas(QWidget):
    """Viewer simple pour captures : molette = zoom, clic gauche = pan, sans scrollbars."""

    def __init__(self, owner: "ScreenshotLibraryDialog", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.owner = owner
        self.pixmap: Optional[QPixmap] = None
        self.zoom_factor = 1.0
        self.center_norm_x = 0.5
        self.center_norm_y = 0.5
        self._dragging = False
        self._last_mouse_pos = QPointF()
        self.setMinimumSize(360, 260)
        self.setMouseTracking(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.open_context_menu)

    def set_pixmap(self, pixmap: QPixmap) -> None:
        self.pixmap = pixmap
        self.fit_to_window()

    def has_pixmap(self) -> bool:
        return self.pixmap is not None and not self.pixmap.isNull()

    def fit_scale(self) -> float:
        if not self.has_pixmap():
            return 1.0
        return max(0.05, min(20.0, min(self.width() / max(1, self.pixmap.width()), self.height() / max(1, self.pixmap.height())) * 0.98))

    def fit_to_window(self) -> None:
        self.zoom_factor = self.fit_scale()
        self.center_norm_x = 0.5
        self.center_norm_y = 0.5
        self.update()

    def target_rect(self) -> Optional[QRectF]:
        if not self.has_pixmap():
            return None
        iw = self.pixmap.width()
        ih = self.pixmap.height()
        cx = self.center_norm_x * iw
        cy = self.center_norm_y * ih
        x = self.width() / 2.0 - cx * self.zoom_factor
        y = self.height() / 2.0 - cy * self.zoom_factor
        return QRectF(x, y, iw * self.zoom_factor, ih * self.zoom_factor)

    def zoom_at(self, pos: QPointF, factor: float) -> None:
        if not self.has_pixmap():
            return
        old_rect = self.target_rect()
        if old_rect is None:
            return
        iw = max(1, self.pixmap.width())
        ih = max(1, self.pixmap.height())
        img_x = (pos.x() - old_rect.x()) / max(0.0001, self.zoom_factor)
        img_y = (pos.y() - old_rect.y()) / max(0.0001, self.zoom_factor)
        new_zoom = max(0.05, min(20.0, self.zoom_factor * float(factor)))
        self.zoom_factor = new_zoom
        cx = img_x - (pos.x() - self.width() / 2.0) / max(0.0001, new_zoom)
        cy = img_y - (pos.y() - self.height() / 2.0) / max(0.0001, new_zoom)
        self.center_norm_x = cx / iw
        self.center_norm_y = cy / ih
        self.update()


    def wheelEvent(self, event) -> None:  # type: ignore[override]
        if event.angleDelta().y() == 0:
            event.ignore()
            return
        steps = event.angleDelta().y() / 120.0
        self.zoom_at(event.position(), 1.15 ** steps)
        event.accept()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton and self.has_pixmap():
            self._dragging = True
            self._last_mouse_pos = event.position()
            self._pan_last_mouse_pos = event.position()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._dragging and self.has_pixmap():
            delta = event.position() - self._last_mouse_pos
            self._last_mouse_pos = event.position()
            iw = max(1, self.pixmap.width())
            ih = max(1, self.pixmap.height())
            self.center_norm_x -= float(delta.x()) / max(0.0001, self.zoom_factor) / iw
            self.center_norm_y -= float(delta.y()) / max(0.0001, self.zoom_factor) / ih
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            self._pan_last_mouse_pos = event.position()
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton:
            self.fit_to_window()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def open_context_menu(self, pos: QPoint) -> None:
        self.owner.open_preview_context_menu(self.mapToGlobal(pos))

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        try:
            painter.fillRect(self.rect(), QColor(26, 29, 34))
            if not self.has_pixmap():
                painter.setPen(QColor(235, 235, 235))
                painter.drawText(self.rect(), Qt.AlignCenter, "Aucun screenshot sélectionné")
                return
            target = self.target_rect()
            if target is None:
                return
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.drawPixmap(target, self.pixmap, QRectF(self.pixmap.rect()))
            percent = self.zoom_factor * 100.0
            label = f"Zoom : {percent:.0f}%"
            fm = painter.fontMetrics()
            text_rect = fm.boundingRect(label).adjusted(-7, -4, 7, 4)
            text_rect.moveTopLeft(QPoint(8, 8))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, 150))
            painter.drawRoundedRect(QRectF(text_rect), 4, 4)
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(text_rect, Qt.AlignCenter, label)
        finally:
            painter.end()


class ScreenshotLibraryDialog(QDialog):
    """Bibliothèque flottante simple pour screenshots du viewer, style bandeau Snagit."""

    def __init__(self, tab: "CamTab", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.tab = tab
        self.viewer = tab.viewer
        self.setWindowTitle("Screenshots")
        self.setModal(False)
        self.resize(980, 720)
        self.current_pixmap: Optional[QPixmap] = None
        self.current_path: Optional[Path] = None
        self.screenshot_paths: List[Path] = []
        self.thumb_buttons: Dict[str, QToolButton] = {}
        self.root_dir = self.default_root_dir()
        self.confirm_delete_enabled = True

        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("Nom :"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Nom optionnel pour la prochaine capture / enregistrer sous")
        self.name_edit.setMinimumWidth(260)
        top.addWidget(self.name_edit)
        self.btn_capture = QPushButton("Capturer viewer")
        self.btn_capture.setToolTip("Sauvegarde uniquement l'image visible + les dessins, sans zoom/minimap/flèches.")
        self.btn_capture.clicked.connect(self.capture_current_viewer)
        top.addWidget(self.btn_capture)
        self.btn_browse = QPushButton("Parcourir")
        self.btn_browse.setToolTip("Choisir un dossier de screenshots à afficher.")
        self.btn_browse.clicked.connect(self.browse_root_dir)
        top.addWidget(self.btn_browse)
        self.btn_refresh = QPushButton("Actualiser")
        self.btn_refresh.clicked.connect(lambda _checked=False: self.refresh_list())
        top.addWidget(self.btn_refresh)
        self.btn_open_folder = QPushButton("Ouvrir dossier")
        self.btn_open_folder.setToolTip("Ouvre le dossier racine contenant les screenshots du logiciel.")
        self.btn_open_folder.clicked.connect(self.open_screenshots_folder)
        top.addWidget(self.btn_open_folder)
        self.btn_delete = QPushButton("🗑 Supprimer")
        self.btn_delete.setToolTip("Supprime le screenshot sélectionné. Clic droit : activer/désactiver la confirmation.")
        self.btn_delete.clicked.connect(self.delete_selected_screenshot)
        self.btn_delete.setContextMenuPolicy(Qt.CustomContextMenu)
        self.btn_delete.customContextMenuRequested.connect(self.open_delete_options_menu)
        top.addWidget(self.btn_delete)
        layout.addLayout(top)

        controls = QHBoxLayout()
        self.btn_fit = QPushButton("Ajuster")
        self.btn_fit.setToolTip("Réinitialise le zoom du viewer screenshots. Molette = zoom, clic gauche + drag = pan.")
        self.btn_fit.clicked.connect(lambda: self.preview_canvas.fit_to_window())
        controls.addWidget(self.btn_fit)
        self.btn_save_as = QPushButton("Enregistrer sous")
        self.btn_save_as.clicked.connect(self.save_selected_as)
        controls.addWidget(self.btn_save_as)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.path_label = QLabel(str(self.root_dir))
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.path_label)

        self.preview_canvas = ScreenshotPreviewCanvas(self)
        layout.addWidget(self.preview_canvas, 1)

        thumb_title = QLabel("Captures")
        thumb_title.setStyleSheet("font-weight: bold; color: #f0f0f0;")
        layout.addWidget(thumb_title)

        self.thumb_scroll = QScrollArea()
        self.thumb_scroll.setWidgetResizable(True)
        self.thumb_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.thumb_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.thumb_scroll.setFixedHeight(116)
        self.thumb_container = QWidget()
        self.thumb_layout = QHBoxLayout(self.thumb_container)
        self.thumb_layout.setContentsMargins(6, 6, 6, 6)
        self.thumb_layout.setSpacing(8)
        self.thumb_layout.addStretch(1)
        self.thumb_scroll.setWidget(self.thumb_container)
        layout.addWidget(self.thumb_scroll)

        self.refresh_list()

    def default_root_dir(self) -> Path:
        try:
            window = self.tab.window()
            if hasattr(window, "exports_dir_path"):
                return Path(window.exports_dir_path()) / "screenshots"
        except Exception:
            pass
        return APP_ROOT_DIR / "exports" / "screenshots"

    def sanitize_name(self, value: str) -> str:
        value = str(value or "").strip()
        if not value:
            return ""
        value = re.sub(r"[^A-Za-z0-9._ -]+", "_", value)
        value = value.strip(" ._-")
        return value[:80]

    def current_record_info(self) -> Tuple[str, str, str]:
        record = self.tab.current_record()
        if record is None:
            return "REF", f"CAM{self.tab.cam_number}", "image"
        return record.ref, f"CAM{record.cam_number}", Path(record.path).stem

    def capture_current_viewer(self) -> None:
        record = self.tab.current_record()
        if record is None:
            self.tab.request_status_message.emit("Aucune image active pour le screenshot")
            return
        pixmap = self.viewer.grab_clean_content()
        if pixmap.isNull():
            QMessageBox.warning(self, "Screenshot impossible", "Le viewer n'a pas pu être capturé.")
            return
        ref, cam, stem = self.current_record_info()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder_name = f"{timestamp}_{ref}_{cam}"
        target_dir = self.root_dir / folder_name
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            QMessageBox.critical(self, "Dossier impossible", f"Impossible de créer le dossier screenshot :\n{exc}")
            return
        custom = self.sanitize_name(self.name_edit.text())
        image_name = f"{custom}.png" if custom else f"{stem}_screenshot_{timestamp}.png"
        image_path = target_dir / image_name
        if not pixmap.save(str(image_path), "PNG"):
            QMessageBox.critical(self, "Screenshot impossible", "Impossible d'enregistrer le screenshot.")
            return
        state = self.viewer.capture_state()
        metadata = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "reference": record.ref,
            "cam": record.cam_number,
            "source_image": record.path,
            "source_file": record.file_name,
            "screenshot_file": str(image_path),
            "capture_mode": "clean_image_plus_drawings",
            "excluded_overlays": ["zoom", "minimap", "nav_arrows", "viewer_ui"],
            "viewer": {
                "zoom_percent": round(float(state.scale) * 100.0, 3),
                "center_norm_x": float(state.center_norm_x),
                "center_norm_y": float(state.center_norm_y),
                "display_width": int(state.display_width),
                "display_height": int(state.display_height),
            },
            "background_rgb": list(self.tab.bg_colors[self.tab.active_bg_index]) if getattr(self.tab, "bg_colors", None) else [],
            "drawings_visible": bool(getattr(self.viewer, "drawings_visible", True)),
        }
        try:
            (target_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
            (target_dir / "viewer_state.json").write_text(json.dumps(metadata["viewer"], indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        self.name_edit.clear()
        self.tab.request_status_message.emit(f"Screenshot sauvegardé : {image_path}")
        self.refresh_list(select_path=image_path)

    def browse_root_dir(self) -> None:
        start = str(self.root_dir if self.root_dir.exists() else self.default_root_dir())
        path = QFileDialog.getExistingDirectory(self, "Choisir dossier screenshots", start)
        if not path:
            return
        self.root_dir = Path(path)
        self.current_path = None
        self.current_pixmap = None
        self.refresh_list()

    def _safe_mtime(self, path: Path) -> float:
        try:
            return path.stat().st_mtime if path.exists() else 0.0
        except Exception:
            return 0.0

    def _clear_thumb_layout(self) -> None:
        while self.thumb_layout.count() > 0:
            item = self.thumb_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.thumb_buttons.clear()

    def _short_name(self, path: Path, max_chars: int = 18) -> str:
        name = path.stem
        return name if len(name) <= max_chars else name[: max_chars - 1] + "…"

    def _make_thumbnail_icon(self, path: Path, selected: bool = False) -> QIcon:
        base = QPixmap(104, 64)
        base.fill(QColor(38, 42, 48))
        source = QPixmap(str(path))
        painter = QPainter(base)
        try:
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            if not source.isNull():
                scaled = source.scaled(98, 58, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                x = (base.width() - scaled.width()) // 2
                y = (base.height() - scaled.height()) // 2
                painter.drawPixmap(x, y, scaled)
            pen = QPen(QColor(255, 255, 255, 235), 1)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(1, 1, base.width() - 2, base.height() - 2)
            if selected:
                sel_pen = QPen(QColor(255, 105, 105), 3)
                sel_pen.setCosmetic(True)
                painter.setPen(sel_pen)
                painter.drawRect(3, 3, base.width() - 6, base.height() - 6)
        finally:
            painter.end()
        return QIcon(base)

    def _style_thumb_button(self, button: QToolButton, selected: bool) -> None:
        if selected:
            button.setStyleSheet(
                "QToolButton { background-color: rgba(200,70,70,0.45); color: white; border: 2px solid #ff8b8b; border-radius: 6px; padding: 3px; }"
                "QToolButton:hover { background-color: rgba(220,85,85,0.58); }"
            )
        else:
            button.setStyleSheet(
                "QToolButton { background-color: rgba(255,255,255,0.055); color: #e6e6e6; border: 1px solid rgba(255,255,255,0.22); border-radius: 6px; padding: 3px; }"
                "QToolButton:hover { background-color: rgba(255,255,255,0.12); border: 1px solid rgba(255,255,255,0.55); }"
            )

    def refresh_list(self, select_path: Optional[Path] = None) -> None:
        if isinstance(select_path, bool):
            select_path = None
        elif select_path is not None:
            try:
                select_path = Path(select_path)
            except TypeError:
                select_path = None
        self.path_label.setText(str(self.root_dir))
        try:
            self.root_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            return

        self.screenshot_paths = sorted(self.root_dir.glob("**/*.png"), key=self._safe_mtime, reverse=True)
        if select_path is not None:
            self.current_path = Path(select_path)
        elif self.current_path not in self.screenshot_paths:
            self.current_path = self.screenshot_paths[0] if self.screenshot_paths else None

        self._rebuild_thumbnails()
        if self.current_path is not None:
            self.set_current_path(self.current_path)
        else:
            self.current_pixmap = None
            self.preview_canvas.pixmap = None
            self.preview_canvas.update()

    def _rebuild_thumbnails(self) -> None:
        self._clear_thumb_layout()
        for path in self.screenshot_paths:
            selected = bool(self.current_path and path == self.current_path)
            button = QToolButton()
            button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            button.setIcon(self._make_thumbnail_icon(path, selected=selected))
            button.setIconSize(QSize(104, 64))
            button.setText(self._short_name(path))
            button.setToolTip(str(path))
            button.setFixedSize(126, 94)
            button.clicked.connect(lambda _checked=False, p=path: self.set_current_path(p))
            self._style_thumb_button(button, selected)
            self.thumb_layout.addWidget(button)
            self.thumb_buttons[str(path)] = button
        self.thumb_layout.addStretch(1)

    def selected_path(self) -> Optional[Path]:
        return Path(self.current_path) if self.current_path else None

    def set_current_path(self, path: Path) -> None:
        if path is None or not Path(path).exists():
            return
        path = Path(path)
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return
        self.current_path = path
        self.current_pixmap = pixmap
        self.preview_canvas.set_pixmap(pixmap)
        for raw_path, button in self.thumb_buttons.items():
            selected = (Path(raw_path) == path)
            button.setIcon(self._make_thumbnail_icon(Path(raw_path), selected=selected))
            self._style_thumb_button(button, selected)

    def save_selected_as(self) -> None:
        if self.current_path is None or not self.current_path.exists():
            return
        suggested = self.current_path.name
        custom = self.sanitize_name(self.name_edit.text())
        if custom:
            suggested = f"{custom}.png"
        target, _ = QFileDialog.getSaveFileName(self, "Enregistrer screenshot sous", suggested, "PNG (*.png)")
        if not target:
            return
        try:
            shutil.copy2(self.current_path, target)
            self.tab.request_status_message.emit(f"Screenshot copié : {target}")
        except Exception as exc:
            QMessageBox.critical(self, "Copie impossible", str(exc))

    def copy_current_image(self) -> None:
        if self.current_pixmap is None or self.current_pixmap.isNull():
            return
        QApplication.clipboard().setPixmap(self.current_pixmap)
        self.tab.request_status_message.emit("Screenshot copié dans le presse-papiers")

    def open_screenshots_folder(self) -> None:
        try:
            self.root_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.root_dir)))

    def open_delete_options_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        confirm_action = menu.addAction("Confirmation suppression")
        confirm_action.setCheckable(True)
        confirm_action.setChecked(bool(self.confirm_delete_enabled))
        chosen = menu.exec(self.btn_delete.mapToGlobal(pos))
        if chosen == confirm_action:
            self.confirm_delete_enabled = not self.confirm_delete_enabled
            state = "activée" if self.confirm_delete_enabled else "désactivée"
            self.tab.request_status_message.emit(f"Confirmation suppression {state}")

    def delete_selected_screenshot(self) -> None:
        path = self.selected_path()
        if path is None or not path.exists():
            return
        if self.confirm_delete_enabled:
            reply = QMessageBox.question(
                self,
                "Supprimer screenshot",
                f"Supprimer ce screenshot ?\n\n{path.name}",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
        parent = path.parent
        try:
            path.unlink()
            if not any(parent.glob("*.png")):
                for extra in ("metadata.json", "viewer_state.json"):
                    extra_path = parent / extra
                    if extra_path.exists():
                        try:
                            extra_path.unlink()
                        except Exception:
                            pass
                try:
                    parent.rmdir()
                except Exception:
                    pass
            self.current_path = None
            self.current_pixmap = None
            self.preview_canvas.pixmap = None
            self.preview_canvas.update()
            self.refresh_list()
            self.tab.request_status_message.emit("Screenshot supprimé")
        except Exception as exc:
            QMessageBox.critical(self, "Suppression impossible", str(exc))

    def open_preview_context_menu(self, global_pos: QPoint) -> None:
        menu = QMenu(self)
        copy_action = menu.addAction("Copier image")
        save_action = menu.addAction("Enregistrer sous...")
        delete_action = menu.addAction("Supprimer")
        chosen = menu.exec(global_pos)
        if chosen == copy_action:
            self.copy_current_image()
        elif chosen == save_action:
            self.save_selected_as()
        elif chosen == delete_action:
            self.delete_selected_screenshot()


class OverlayNavButton(QWidget):
    """Zone de navigation flottante avec bouton visuel animé.

    La zone sensible reste fixe et confortable dans le viewer. Seul le bouton
    visuel glisse légèrement vers le bord au repos puis revient au hover.
    """

    clicked = Signal()

    def __init__(self, text: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.side = "left" if "‹" in text or "◀" in text else "right"
        self.rest_pos = QPoint(0, 0)
        self.visual_rest_pos = QPoint(0, 0)
        self.visual_hover_pos = QPoint(0, 0)
        self.zone_width = 64
        self.zone_height = 58
        self.button_size = 44
        self.visible_strip = 10
        self.setFixedSize(self.zone_width, self.zone_height)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setToolTip("Image précédente" if self.side == "left" else "Image suivante")

        self.visual_button = QPushButton("◀" if self.side == "left" else "▶", self)
        self.visual_button.setFixedSize(self.button_size, self.button_size)
        self.visual_button.setCursor(Qt.PointingHandCursor)
        self.visual_button.setFocusPolicy(Qt.NoFocus)
        self.visual_button.clicked.connect(self.clicked.emit)
        self.visual_button.setStyleSheet(
            "QPushButton {"
            " background-color: rgba(38, 43, 50, 232);"
            " color: rgba(255,255,255,250);"
            " border: 1px solid rgba(255,255,255,190);"
            " border-radius: 7px;"
            " font-size: 21px;"
            " font-weight: bold;"
            " padding: 0px;"
            " margin: 0px;"
            " text-align: center;"
            "}"
            "QPushButton:hover {"
            " background-color: rgba(48, 54, 63, 248);"
            " border: 1px solid rgba(255,255,255,230);"
            "}"
            "QPushButton:disabled {"
            " color: rgba(255,255,255,110);"
            " background-color: rgba(30,34,40,130);"
            " border: 1px solid rgba(255,255,255,70);"
            "}"
        )

        self.opacity_effect = QGraphicsOpacityEffect(self.visual_button)
        self.visual_button.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(0.25)

        self.move_animation = QPropertyAnimation(self.visual_button, b"pos", self)
        self.move_animation.setDuration(145)
        self.move_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.opacity_animation = QPropertyAnimation(self.opacity_effect, b"opacity", self)
        self.opacity_animation.setDuration(130)
        self.opacity_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.raise_()

    def update_edge_positions(self, viewer: QWidget) -> None:
        y = max(8, (viewer.height() - self.height()) // 2)
        if self.side == "left":
            self.rest_pos = QPoint(0, y)
            self.visual_rest_pos = QPoint(-(self.button_size - self.visible_strip), (self.height() - self.button_size) // 2)
            self.visual_hover_pos = QPoint(8, (self.height() - self.button_size) // 2)
        else:
            self.rest_pos = QPoint(max(0, viewer.width() - self.width()), y)
            self.visual_rest_pos = QPoint(self.width() - self.visible_strip, (self.height() - self.button_size) // 2)
            self.visual_hover_pos = QPoint(max(0, self.width() - self.button_size - 8), (self.height() - self.button_size) // 2)
        self.move(self.rest_pos)
        if not self.underMouse():
            self.visual_button.move(self.visual_rest_pos)
            self.opacity_effect.setOpacity(0.25)
        else:
            self.visual_button.move(self.visual_hover_pos)
            self.opacity_effect.setOpacity(1.0)
        self.raise_()

    def animate_visual_to(self, pos: QPoint, opacity: float) -> None:
        self.move_animation.stop()
        self.move_animation.setStartValue(self.visual_button.pos())
        self.move_animation.setEndValue(pos)
        self.move_animation.start()
        self.opacity_animation.stop()
        self.opacity_animation.setStartValue(self.opacity_effect.opacity())
        self.opacity_animation.setEndValue(opacity)
        self.opacity_animation.start()

    def set_rest_opacity(self) -> None:
        """Remet l'état repos/hover sans déplacer la zone sensible."""
        if self.underMouse():
            self.visual_button.move(self.visual_hover_pos)
            self.opacity_effect.setOpacity(1.0)
        else:
            self.visual_button.move(self.visual_rest_pos)
            self.opacity_effect.setOpacity(0.25)
        self.raise_()

    def setEnabled(self, enabled: bool) -> None:  # type: ignore[override]
        super().setEnabled(enabled)
        self.visual_button.setEnabled(enabled)

    def enterEvent(self, event) -> None:  # type: ignore[override]
        self.animate_visual_to(self.visual_hover_pos, 1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        self.animate_visual_to(self.visual_rest_pos, 0.25)
        super().leaveEvent(event)


class CamTab(QWidget):
    """Un onglet CAMn : filtre, table, viewer, annotations."""

    COL_REF = 0
    COL_FILE = 1
    COL_TAGS = 2
    COL_STATUS = 3
    COL_COMMENT = 4
    TABLE_HEADERS = ["Réf", "Fichier", "Tags", "Statut", "Commentaire"]

    annotation_changed = Signal()
    annotation_about_to_change = Signal(int, str, int, object)
    request_color_select = Signal(int)
    request_color_edit = Signal(int)
    request_status_message = Signal(str)
    current_image_changed = Signal(int, str, str, int, int)
    request_detach_viewer = Signal()

    def __init__(
        self,
        cam_number: int,
        records: List[ImageRecord],
        annotations: Dict[str, Annotation],
        bg_colors: List[Tuple[int, int, int]],
        active_bg_index: int,
        cache: ImageMemoryCache,
        preload_radius: int = DEFAULT_PRELOAD_RADIUS,
        preload_enabled: bool = True,
        preserve_view_enabled: bool = True,
        status_filter: str = "Tous",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.cam_number = cam_number
        self.all_records = records
        self.records: List[ImageRecord] = []
        self.annotations = annotations
        self.bg_colors = bg_colors
        self.active_bg_index = active_bg_index
        self.current_index = -1
        self._updating_table = False
        self.cache = cache
        self.preload_radius = int(preload_radius)
        self.preload_enabled = bool(preload_enabled)
        self.preserve_view_enabled = bool(preserve_view_enabled)
        self.status_filter = status_filter or "Tous"
        self._suppress_filter_apply = False
        self.shortcut_provider = None
        self.drawing_dialog: Optional[DrawingToolsDialog] = None
        self.screenshot_library_dialog: Optional[ScreenshotLibraryDialog] = None

        self.cache.image_ready.connect(self.on_image_ready)
        self.cache.image_failed.connect(self.on_image_failed)

        self.btn_clear_custom_filter = QPushButton("Enlever tous les filtres")
        self.btn_clear_custom_filter.setToolTip("Supprime tous les filtres actifs sur la liste.")
        self.btn_clear_custom_filter.clicked.connect(self.clear_all_table_filters)

        self.count_label = QLabel("0 image")
        self.chk_preload = QCheckBox("Précharger autour")
        self.chk_preload.setChecked(self.preload_enabled)
        self.chk_preload.setToolTip("Prépare en arrière-plan les images autour de l’image affichée. Exemple ±3 = 3 précédentes + 3 suivantes déjà prêtes en cache.")
        self.chk_preload.toggled.connect(self.set_preload_enabled)

        self.btn_fit = QPushButton("Ajuster")
        self.btn_fit.setToolTip("Adapter l'image entière à la taille du viewer.")
        self.zoom_percent_edit = QLineEdit("100")
        self.zoom_percent_edit.setFixedWidth(72)
        self.zoom_percent_edit.setAlignment(Qt.AlignCenter)
        self.zoom_percent_edit.setValidator(QIntValidator(10, 4000, self.zoom_percent_edit))
        self.zoom_percent_edit.setToolTip("Zoom manuel en pourcentage. Exemple : tape 132 puis Entrée pour afficher à 132%.")
        self.zoom_percent_debounce = QTimer(self)
        self.zoom_percent_debounce.setSingleShot(True)
        self.zoom_percent_debounce.setInterval(350)
        self.zoom_percent_debounce.timeout.connect(self.apply_zoom_percent_from_edit)
        # V2.70+ : bouton Pleine qualité supprimé. La qualité est pilotée par le réglage global "Taille max image affichée".
        self.btn_focus_mode = QPushButton("Masquer interface")
        self.btn_focus_mode.setToolTip("Cache les contrôles du viewer et garde exactement le même viewer, zoom, pan et cache.")
        self.btn_minimap = QPushButton("Mini-map")
        self.btn_minimap.setCheckable(True)
        self.btn_minimap.setChecked(True)
        self.btn_minimap.setToolTip("Affiche/cache la mini-map de navigation quand l'image est zoomée.")
        self.btn_detach_viewer = QPushButton("Détacher viewer")
        self.btn_detach_viewer.setToolTip("Détache ce viewer et ses onglets CAM dans une fenêtre flottante.")
        self.btn_compare_mode = QPushButton("Comparer côte à côte")
        self.btn_compare_mode.setCheckable(True)
        self.btn_compare_mode.setToolTip("Affiche une deuxième image à droite, avec zoom/pan synchronisés.")
        self.btn_overlay_mode = QPushButton("Superposer")
        self.btn_overlay_mode.setCheckable(True)
        self.btn_overlay_mode.setEnabled(False)
        self.btn_overlay_mode.setToolTip("Superpose l'image 2 sur l'image 1 dans un seul viewer.")
        self.btn_exit_focus_mode = QPushButton("Afficher interface")
        self.btn_exit_focus_mode.setToolTip("Réaffiche les filtres, fonds, boutons et chemin du viewer.")
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

        # V2.45 : le viewer principal EST le canvas gauche du comparateur.
        # Le flux ne repose plus que sur les deux canvases utiles : image 1 et image 2.
        # Une seule logique de pan/zoom/mini-map sert au mode simple et au mode comparaison.
        self.viewer = CompareImageCanvas(self)
        self.viewer.set_background(tuple_to_color(self.bg_colors[self.active_bg_index]))
        self.viewer.camera_changed.connect(self.on_main_viewer_camera_changed)
        self.viewer.canvas_activated.connect(self.set_active_drawing_viewer)

        self.compare_viewer = CompareImageCanvas(self)
        self.compare_viewer.set_background(tuple_to_color(self.bg_colors[self.active_bg_index]))
        self.compare_viewer.camera_changed.connect(lambda state: self.on_compare_canvas_changed("right", state))
        self.compare_viewer.canvas_activated.connect(self.set_active_drawing_viewer)
        self._active_drawing_canvas = self.viewer

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
        self.update_inspection_overlays()
        self.update_nav_overlays()

        self.compare_selector_pane = QFrame()
        self.compare_selector_pane.setMinimumWidth(150)
        self.compare_selector_pane.setMaximumWidth(230)
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
        compare_selector_title = QLabel("Image 2")
        compare_selector_hint = QLabel("Références")
        compare_selector_hint.setStyleSheet("color: #aaaaaa; font-weight: normal;")
        self.compare_ref_table = QTableWidget(0, 1)
        self.compare_ref_table.setHorizontalHeaderLabels(["Ref"])
        self.compare_ref_table.verticalHeader().setVisible(False)
        self.compare_ref_table.horizontalHeader().setStretchLastSection(True)
        self.compare_ref_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.compare_ref_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.compare_ref_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.compare_ref_table.setToolTip("Sélectionne ici la référence/image affichée en image 2. L'image 1 reste sélectionnée dans la liste principale.")
        self.compare_ref_table.itemSelectionChanged.connect(self.on_compare_ref_selection_changed)
        compare_selector_layout.addWidget(compare_selector_title)
        compare_selector_layout.addWidget(compare_selector_hint)
        compare_selector_layout.addWidget(self.compare_ref_table, 1)
        self.compare_selector_pane.hide()

        self.overlay_opacity_widget = QWidget()
        overlay_opacity_layout = QHBoxLayout(self.overlay_opacity_widget)
        overlay_opacity_layout.setContentsMargins(0, 4, 0, 0)
        self.btn_switch_overlay_image = QPushButton("Afficher image 2")
        self.btn_switch_overlay_image.setToolTip("Mode superposition : alterne entre l'image 1 et l'image 2 dans le même viewer.")
        self.btn_switch_overlay_image.clicked.connect(self.switch_overlay_image)
        overlay_opacity_layout.addStretch(1)
        overlay_opacity_layout.addWidget(QLabel("Superposition :"))
        overlay_opacity_layout.addWidget(self.btn_switch_overlay_image)
        overlay_opacity_layout.addStretch(1)
        self.overlay_opacity_widget.hide()

        self.color_buttons: List[ColorButton] = []
        color_layout = QHBoxLayout()
        color_layout.setContentsMargins(0, 0, 0, 0)
        for i, rgb in enumerate(bg_colors):
            btn = ColorButton(i, rgb)
            if i == 2:
                btn.setText("Fond 3 custom")
            btn.clicked_index.connect(self.select_bg_index)
            btn.edit_requested.connect(lambda index: self.request_color_edit.emit(index))
            self.color_buttons.append(btn)
            color_layout.addWidget(btn)
        self.btn_drawing_tools = QPushButton("Dessiner")
        self.btn_drawing_tools.setToolTip("Ouvre la palette pour dessiner/annoter sur le viewer.")
        self.btn_drawing_tools.clicked.connect(self.open_drawing_tools)
        color_layout.addWidget(self.btn_drawing_tools)
        self.btn_toggle_drawings = QPushButton("Masquer dessins")
        self.btn_toggle_drawings.setToolTip("Affiche ou cache les dessins / annotations du viewer actif.")
        self.btn_toggle_drawings.clicked.connect(self.toggle_drawings_visibility)
        color_layout.addWidget(self.btn_toggle_drawings)
        self.btn_screenshot_library = QPushButton("Screenshots")
        self.btn_screenshot_library.setToolTip("Ouvre la bibliothèque flottante de screenshots : capture auto, zoom/dézoom, enregistrer sous, clic droit copier.")
        self.btn_screenshot_library.clicked.connect(self.open_screenshot_library)
        color_layout.addWidget(self.btn_screenshot_library)
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
        self.table.setItemDelegateForColumn(self.COL_STATUS, StatusComboDelegate(self.table))
        self.table.setItemDelegateForColumn(self.COL_COMMENT, CommentLineEditDelegate(self.table))
        self.table.setEditTriggers(
            QAbstractItemView.SelectedClicked
            | QAbstractItemView.EditKeyPressed
            | QAbstractItemView.AnyKeyPressed
        )
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.setTextElideMode(Qt.ElideRight)
        self.table.setStyleSheet(
            "QTableWidget { background-color: #1d1d1d; alternate-background-color: #1d1d1d; "
            "gridline-color: #333333; color: #dddddd; border: 1px solid #343434; }"
            "QTableWidget::item { background-color: #1d1d1d; color: #dddddd; padding: 2px; }"
            "QTableWidget::item:selected { background-color: #3a3a3a; color: white; }"
            "QHeaderView::section { background-color: #262626; color: #eeeeee; padding: 5px; border: 1px solid #3d3d3d; }"
            "QHeaderView::section:hover { background-color: #303030; }"
        )
        # V2.90 : le tableau ne doit plus déborder. Les colonnes utiles restent
        # redimensionnables, et Commentaire absorbe l'espace restant sans scrollbar horizontale.
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setMinimumSectionSize(48)
        for col in range(len(self.TABLE_HEADERS)):
            header.setSectionResizeMode(col, QHeaderView.Interactive)
        header.setSectionResizeMode(self.COL_COMMENT, QHeaderView.Stretch)
        self.table.setColumnWidth(self.COL_REF, 78)
        self.table.setColumnWidth(self.COL_FILE, 250)
        self.table.setColumnWidth(self.COL_TAGS, 88)
        self.table.setColumnWidth(self.COL_STATUS, 138)
        self.table.itemSelectionChanged.connect(self.on_table_selection_changed)
        self.table.cellClicked.connect(self.on_table_cell_clicked)
        self.table.itemChanged.connect(self.on_table_item_changed)
        self.table.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.horizontalHeader().customContextMenuRequested.connect(self.open_column_filter_menu)
        self.table.horizontalHeader().sortIndicatorChanged.connect(lambda _col, _order: QTimer.singleShot(0, self.on_table_sort_changed))
        self.table.horizontalHeader().setToolTip(
            "Clic gauche sur une colonne : trier. Clic droit : filtrer ou effacer le filtre de la colonne."
        )
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.open_image_row_context_menu)

        # Champs logiques uniquement : ils ne sont pas affichés dans l'UI.
        # Parentés à CamTab pour éviter des widgets orphelins en mémoire.
        self.column_filter_ref_edit = QLineEdit()
        self.column_filter_ref_edit.setPlaceholderText("Filtre Réf")
        self.column_filter_file_edit = QLineEdit()
        self.column_filter_file_edit.setPlaceholderText("Filtre Fichier")
        self.column_filter_tags_edit = QLineEdit()
        self.column_filter_tags_edit.setPlaceholderText("Filtre Tags")
        self.column_filter_status_edit = QLineEdit()
        self.column_filter_status_edit.setPlaceholderText("Filtre Statut")
        self.column_filter_comment_edit = QLineEdit()
        self.column_filter_comment_edit.setPlaceholderText("Filtre Commentaire")
        for edit in (
            self.column_filter_ref_edit,
            self.column_filter_file_edit,
            self.column_filter_tags_edit,
            self.column_filter_status_edit,
            self.column_filter_comment_edit,
        ):
            edit.setClearButtonEnabled(True)
            edit.setMinimumWidth(90)
            edit.setToolTip("Filtre cette colonne. * fonctionne comme joker.")
            edit.hide()
            edit.textChanged.connect(self.apply_filter)

        self.top_controls_widget = QWidget()
        top_controls_outer = QVBoxLayout(self.top_controls_widget)
        top_controls_outer.setContentsMargins(0, 0, 0, 0)
        top_controls_outer.setSpacing(4)

        top_controls_panel = QFrame()
        top_controls_panel.setStyleSheet(
            "QFrame { background-color: #202020; border: 1px solid #343434; border-radius: 6px; }"
            "QPushButton { background-color: #2d2d2d; color: #eeeeee; border: 1px solid #505050; border-radius: 4px; padding: 5px 10px; }"
            "QPushButton:hover { background-color: #383838; border-color: #777777; }"
            "QLabel { color: #dcdcdc; }"
        )
        top_controls = QHBoxLayout(top_controls_panel)
        top_controls.setContentsMargins(8, 5, 8, 5)
        top_controls.setSpacing(8)
        self.btn_clear_custom_filter.setText("Enlever tous les filtres")
        self.btn_clear_custom_filter.setToolTip("Supprime tous les filtres actifs sur la liste.")
        top_controls.addWidget(self.btn_clear_custom_filter)
        self.count_label.setStyleSheet("color: #dcdcdc; font-weight: bold;")
        top_controls.addWidget(self.count_label)
        top_controls.addStretch(1)
        top_controls_outer.addWidget(top_controls_panel)

        # Les filtres de colonnes sont pilotés par clic droit sur les en-têtes,
        # façon Explorateur Windows. Aucun champ de filtre n’est affiché en permanence.

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
        self.focus_info_label = QLabel("Mode image seule : le viewer reste le même. Échap ou bouton = afficher l'interface.")
        self.focus_info_label.setStyleSheet("color: white;")
        focus_controls.addWidget(self.focus_info_label, 1)
        focus_controls.addWidget(self.btn_exit_focus_mode)
        self.focus_controls_widget.hide()

        layout = QVBoxLayout(self)
        # V2.76 : les filtres de table sont reparentés dans le panneau gauche, au-dessus de la liste images.
        layout.addWidget(self.color_controls_widget)
        layout.addWidget(self.viewer_controls_widget)
        layout.addWidget(self.focus_controls_widget)

        self.left_viewer_pane = QWidget()
        left_viewer_layout = QVBoxLayout(self.left_viewer_pane)
        left_viewer_layout.setContentsMargins(0, 0, 0, 0)
        self.compare_left_top_widget = QWidget()
        # V2.91 : l'image 1 se sélectionne désormais uniquement via la liste principale.
        # Le widget est conservé comme point de compatibilité, mais il reste masqué.
        self.compare_left_top_widget.hide()
        left_viewer_layout.addWidget(self.viewer, 1)

        self.compare_pane = QWidget()
        compare_layout = QVBoxLayout(self.compare_pane)
        compare_layout.setContentsMargins(0, 0, 0, 0)
        # V2.91 : plus de liste déroulante au-dessus du viewer 2.
        # La sélection image 2 se fait dans le panneau de références à droite.
        compare_layout.addWidget(self.compare_viewer, 1)
        self.compare_pane.hide()

        self.viewer_splitter = QSplitter(Qt.Horizontal)
        self.viewer_splitter.addWidget(self.left_viewer_pane)
        self.viewer_splitter.addWidget(self.compare_pane)
        self.viewer_splitter.addWidget(self.compare_selector_pane)
        self.viewer_splitter.setStretchFactor(0, 1)
        self.viewer_splitter.setStretchFactor(1, 1)
        self.viewer_splitter.setStretchFactor(2, 0)
        self.viewer_splitter.setSizes([850, 850, 180])
        layout.addWidget(self.viewer_splitter, 1)
        layout.addWidget(self.overlay_opacity_widget)
        # V2.90 : la barre texte de bas de viewer est supprimée. Les infos utiles
        # sont affichées en overlay permanent dans le canvas.

        self._install_keyboard_navigation()
        self.apply_filter()


    def _install_keyboard_navigation(self) -> None:
        """Capture les raccourcis même lorsque le focus est sur la table ou le viewer."""
        self.setFocusPolicy(Qt.StrongFocus)
        self.table.setFocusPolicy(Qt.StrongFocus)
        self.viewer.setFocusPolicy(Qt.StrongFocus)
        # V2.44 : le viewer principal est un CompareImageCanvas QWidget simple.
        # Plus de viewport séparé à intercepter ici.
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

        # Fallback si l'onglet est utilisé seul, hors MainWindow.
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

    def set_status_filter(self, value: str) -> None:
        self.status_filter = value or "Tous"
        self.apply_filter()

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

    def active_drawing_viewer(self) -> CompareImageCanvas:
        viewer = getattr(self, "_active_drawing_canvas", None)
        if viewer in (self.viewer, self.compare_viewer):
            return viewer
        return self.viewer

    def set_active_drawing_viewer(self, viewer: object) -> None:
        if viewer in (self.viewer, self.compare_viewer):
            self._active_drawing_canvas = viewer  # type: ignore[assignment]

    def set_drawing_enabled_for_all(self, enabled: bool) -> None:
        self.viewer.set_drawing_enabled(enabled)
        self.compare_viewer.set_drawing_enabled(enabled)

    def set_drawing_tool_for_all(self, tool: str) -> None:
        self.viewer.set_drawing_tool(tool)
        self.compare_viewer.set_drawing_tool(tool)

    def set_drawing_color_for_all(self, color: QColor) -> None:
        self.viewer.set_drawing_color(color)
        self.compare_viewer.set_drawing_color(color)

    def set_drawing_width_for_all(self, width: int) -> None:
        self.viewer.set_drawing_width(width)
        self.compare_viewer.set_drawing_width(width)

    def toggle_drawings_visibility(self) -> None:
        visible = self.viewer.toggle_drawings_visible()
        self.compare_viewer.drawings_visible = visible
        self.compare_viewer.update()
        self.btn_toggle_drawings.setText("Masquer dessins" if visible else "Afficher dessins")
        self.request_status_message.emit("Dessins visibles" if visible else "Dessins cachés")

    def open_drawing_tools(self) -> None:
        if self.drawing_dialog is None:
            self.drawing_dialog = DrawingToolsDialog(self, self)
            self.drawing_dialog.finished.connect(lambda _code: setattr(self, "drawing_dialog", None))
        self.drawing_dialog.show()
        self.drawing_dialog.raise_()
        self.drawing_dialog.activateWindow()
        self.set_drawing_enabled_for_all(True)

    def open_screenshot_library(self) -> None:
        if self.screenshot_library_dialog is None:
            self.screenshot_library_dialog = ScreenshotLibraryDialog(self, self)
            self.screenshot_library_dialog.finished.connect(lambda _code: setattr(self, "screenshot_library_dialog", None))
        self.screenshot_library_dialog.show()
        self.screenshot_library_dialog.raise_()
        self.screenshot_library_dialog.activateWindow()


    def update_inspection_overlays(self, _checked: bool = False) -> None:
        self.show_minimap_overlay = bool(self.btn_minimap.isChecked()) if hasattr(self, "btn_minimap") else True
        # V2.90 : l'overlay d'information est permanent, pas seulement en mode interface masquée.
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
            # Si l'utilisateur vient de taper un zoom manuel puis clique directement
            # sur Comparer, on force l'application du champ avant de capturer l'état.
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
        # La superposition garde un seul flux preview pour éviter les recharges inutiles
        # et les décalages de zoom/pan.
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

    def populate_compare_selector(self) -> None:
        """Remplit la liste visible de sélection image 2 en mode comparaison/superposition."""
        self._updating_compare_selector = True
        if hasattr(self, "compare_ref_table"):
            self.compare_ref_table.blockSignals(True)
        try:
            if hasattr(self, "compare_ref_table"):
                self.compare_ref_table.setRowCount(0)

            for index, record in enumerate(self.records):
                if hasattr(self, "compare_ref_table"):
                    row = self.compare_ref_table.rowCount()
                    self.compare_ref_table.insertRow(row)
                    item = QTableWidgetItem(str(record.ref))
                    item.setData(Qt.UserRole, index)
                    item.setToolTip(record.file_name)
                    item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    self.compare_ref_table.setItem(row, 0, item)

            if self.records:
                target_index = self.compare_index
                if target_index < 0 or target_index >= len(self.records):
                    target_index = 0
                self.compare_index = target_index
                self.update_compare_selector_from_index(target_index, block=True)
            else:
                self.compare_index = -1
        finally:
            if hasattr(self, "compare_ref_table"):
                self.compare_ref_table.blockSignals(False)
            self._updating_compare_selector = False

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
        # V2.44 : le viewer principal est déjà le viewer gauche.
        # Le chargement de l'image 1 est donc géré par select_row()/on_image_ready().
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
            # V2.46 : ne pas vider/recharger l'overlay si c'est déjà la bonne image.
            # Ne pas vider/recharger l'overlay si c'est déjà la bonne image : cela évite
            # les flashs en vue superposée.
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
        # En mode superposition, on n'affiche qu'une image à la fois.
        # Le bouton alterne directement entre image 1 et image 2.
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
        """Un des deux canvases a changé la caméra : on applique exactement le même état aux deux."""
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
        """Garde la navigation cohérente avec l'ordre visuel trié par l'utilisateur."""
        if self._updating_table:
            return
        if 0 <= self.current_index < len(self.records):
            table_row = self.table_row_for_record_index(self.current_index)
            if table_row >= 0 and self.table.currentRow() != table_row:
                self.table.selectRow(table_row)
        self.update_nav_overlays()
        self.refresh_table_row_styles()

    def _set_filter_text(self, edit: QLineEdit, text: str) -> None:
        """Change un filtre sans déclencher un rebuild de table intermédiaire."""
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


    def _column_filter_edits(self) -> List[QLineEdit]:
        return [
            self.column_filter_ref_edit,
            self.column_filter_file_edit,
            self.column_filter_tags_edit,
            self.column_filter_status_edit,
            self.column_filter_comment_edit,
        ]

    def _column_filter_edit(self, column: int) -> Optional[QLineEdit]:
        edits = self._column_filter_edits()
        if 0 <= column < len(edits):
            return edits[column]
        return None

    def _base_header_labels(self) -> List[str]:
        return list(self.TABLE_HEADERS)

    def update_filter_visuals(self) -> None:
        """Indique les filtres actifs sans afficher les champs texte en permanence."""
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
        """Menu contextuel sur une ligne image : accès rapide aux actions Image active."""
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

    def apply_filter(self, *_args) -> None:
        if getattr(self, "_suppress_filter_apply", False):
            return
        status_filter = (self.status_filter or "Tous").strip()
        col_ref = self.column_filter_ref_edit.text().strip() if hasattr(self, "column_filter_ref_edit") else ""
        col_file = self.column_filter_file_edit.text().strip() if hasattr(self, "column_filter_file_edit") else ""
        col_tags = self.column_filter_tags_edit.text().strip() if hasattr(self, "column_filter_tags_edit") else ""
        col_status = self.column_filter_status_edit.text().strip() if hasattr(self, "column_filter_status_edit") else ""
        col_comment = self.column_filter_comment_edit.text().strip() if hasattr(self, "column_filter_comment_edit") else ""

        def col_match(pattern: str, *values: str) -> bool:
            if not pattern:
                return True
            return wildcard_text_match(pattern, *values)

        def record_matches(record: ImageRecord) -> bool:
            ann = self.annotations.get(record.path, Annotation())
            status = normalize_status(ann.status)
            comment = ann.comment or ""
            if not col_match(col_ref, record.ref):
                return False
            if not col_match(col_file, record.file_name, record.stem, record.path):
                return False
            if not col_match(col_tags, " ".join(record.tags)):
                return False
            if not col_match(col_status, status):
                return False
            if not col_match(col_comment, comment):
                return False

            if status_filter == "À corriger" and status != "À corriger":
                return False
            if status_filter == "Terminées" and status != "Terminé":
                return False
            if status_filter in ("À contrôler", "Non vérifiées") and status != STATUS_DEFAULT:
                return False

            return True

        self.records = [r for r in self.all_records if record_matches(r)]
        self.records.sort(key=lambda r: (r.ref.lower(), r.file_name.lower(), r.path.lower()))
        self.populate_table()
        self.populate_compare_selector()
        self.count_label.setText(f"{len(self.records)} image(s)")
        self.update_filter_visuals()
        self.update_nav_overlays()

        if self.records:
            # Après changement de filtre, la liste peut changer alors que l'index reste identique.
            # On force donc la première image du nouveau résultat filtré à devenir l'image active.
            self.current_index = -1
            self.select_row(0, preserve_view=False)
        else:
            self.current_index = -1
            self.viewer.set_loading(None)
            self.current_image_changed.emit(self.cam_number, "", "", 0, 0)

    def populate_table(self) -> None:
        """Remplit la table sans créer de widget permanent par ligne.

        Hotfix V2.52 UI : les ComboBox permanents de la colonne Statut
        ralentissaient énormément le scan/rebuild. Le statut est maintenant
        un item texte édité par un delegate léger uniquement au clic.
        """
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
                ann = self.annotations.get(record.path, Annotation())

                ref_item = QTableWidgetItem(record.ref)
                ref_item.setData(Qt.UserRole, record.path)
                ref_item.setFlags(ref_item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row, self.COL_REF, ref_item)

                file_item = QTableWidgetItem(record.file_name)
                file_item.setData(Qt.UserRole, record.path)
                file_item.setToolTip(record.path)
                file_item.setFlags(file_item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row, self.COL_FILE, file_item)

                tags_item = QTableWidgetItem(", ".join(record.tags))
                tags_item.setData(Qt.UserRole, record.path)
                tags_item.setFlags(tags_item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row, self.COL_TAGS, tags_item)

                normalized_status = normalize_status(ann.status)
                ann.status = normalized_status
                status_item = QTableWidgetItem(normalized_status)
                status_item.setData(Qt.UserRole, record.path)
                status_item.setForeground(QBrush(status_text_color(normalized_status)))
                status_item.setToolTip("Statut de contrôle : clic puis choix. La molette ne modifie pas le statut.")
                self.table.setItem(row, self.COL_STATUS, status_item)

                comment_item = QTableWidgetItem(ann.comment)
                comment_item.setData(Qt.UserRole, record.path)
                self.table.setItem(row, self.COL_COMMENT, comment_item)
        finally:
            self.table.blockSignals(False)
            self.table.setSortingEnabled(old_sorting)
            self.table.setUpdatesEnabled(old_updates)
            self._updating_table = False
            self.table.viewport().update()

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
        """Rafraîchissement léger.

        La couleur de ligne active est gérée par la sélection Qt/styling de la table.
        On évite donc de parcourir toutes les lignes à chaque changement, ce qui
        était coûteux sur de gros lots d'images.
        """
        self.table.viewport().update()

    def on_table_selection_changed(self) -> None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            return
        table_row = rows[0].row()
        record_index = self.record_index_for_table_row(table_row)
        if 0 <= record_index < len(self.records) and record_index != self.current_index:
            self.select_row(record_index)

    def on_table_cell_clicked(self, row: int, column: int) -> None:
        """Édition directe de la table de contrôle.

        V2.76 : la première colonne de coche a disparu. Le tri Qt peut changer
        l'ordre visuel, donc toute action table repasse par le chemin stocké en UserRole.
        """
        if self._updating_table or row < 0 or row >= self.table.rowCount():
            return
        if column not in (self.COL_STATUS, self.COL_COMMENT):
            return
        item = self.table.item(row, column)
        if item is None:
            return
        self.table.setCurrentCell(row, column)
        QTimer.singleShot(0, lambda item=item: self.table.editItem(item))


    def on_table_item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating_table:
            return
        path = item.data(Qt.UserRole)
        if not path:
            row = item.row()
            first = self.table.item(row, self.COL_REF) if row >= 0 else None
            path = first.data(Qt.UserRole) if first is not None else ""
        if not path:
            return
        record_index = next((idx for idx, record in enumerate(self.records) if record.path == path), -1)
        if record_index < 0:
            return
        record = self.records[record_index]

        old_ann = self.annotations.get(record.path, Annotation())
        new_ann = Annotation(old_ann.marked, normalize_status(old_ann.status), old_ann.comment)

        if item.column() == self.COL_STATUS:
            new_ann.status = normalize_status(item.text().strip())
            if item.text() != new_ann.status:
                self._updating_table = True
                try:
                    item.setText(new_ann.status)
                finally:
                    self._updating_table = False
            item.setForeground(QBrush(status_text_color(new_ann.status)))
        elif item.column() == self.COL_COMMENT:
            new_ann.comment = item.text().strip()
        else:
            return

        if (old_ann.marked, normalize_status(old_ann.status), old_ann.comment) == (new_ann.marked, new_ann.status, new_ann.comment):
            return

        self.annotation_about_to_change.emit(self.cam_number, record.path, record_index, old_ann.to_dict())

        if has_annotation_content(new_ann):
            self.annotations[record.path] = new_ann
        else:
            self.annotations.pop(record.path, None)

        self.refresh_table_row_styles()
        self.update_inspection_overlays()
        self.annotation_changed.emit()

    def select_row(self, row: int, preserve_view: Optional[bool] = None) -> None:
        if row < 0 or row >= len(self.records):
            return

        # V2.8 : si on demande la même ligne/image, on ne touche à rien.
        # Important quand on appuie sur Suivante à la dernière image ou Précédente à la première :
        # aucun rechargement, aucun recentrage, aucun micro-déplacement du pan.
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
                # V2.29 : en côte à côte, le viewer 1 est un canvas séparé.
                # Il doit recevoir son propre set_loading au changement d'image,
                # sinon son pending_path reste sur l'ancienne image et le nouveau pixmap est ignoré.
                self.load_compare_left_image()
            # V2.18 : pas de sync immédiate en côte à côte pendant un changement d'image.
            # La synchro ne doit se faire que sur pan/zoom manuel, sinon elle peut introduire
            # un léger décalage cumulatif entre les deux viewers.

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
        # Les filtres de liste restent dans la page principale et restent visibles.
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

        # Ne pas modifier le zoom/pan ici. On laisse le même canvas et le même état de vue.
        # Si le viewer est en mode Ajuster, son resizeEvent fera naturellement le recalcul.
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

    def set_current_status_and_comment(self, status: str, comment: str = "", go_next: bool = True) -> None:
        record = self.current_record()
        if record is None:
            return

        ann = self.annotations.setdefault(record.path, Annotation())
        ann.status = normalize_status(status)
        if comment.strip():
            current_comment = ann.comment.strip()
            new_comment = comment.strip()
            ann.comment = f"{current_comment} | {new_comment}" if current_comment else new_comment

        row = self.table_row_for_record_index(self.current_index)
        self._updating_table = True
        try:
            status_item = self.table.item(row, self.COL_STATUS) if row >= 0 else None
            if status_item is not None:
                status_item.setText(ann.status)
                status_item.setForeground(QBrush(status_text_color(ann.status)))
            item = self.table.item(row, self.COL_COMMENT) if row >= 0 else None
            if item is not None:
                item.setText(ann.comment)
        finally:
            self._updating_table = False

        self.refresh_table_row_styles()
        self.update_inspection_overlays()
        self.annotation_changed.emit()
        if go_next:
            self.next_image()

    def restore_annotation_snapshot(self, path: str, annotation: Annotation, row_hint: int = -1) -> bool:
        if not path:
            return False
        restored = Annotation(annotation.marked, normalize_status(annotation.status), annotation.comment)
        if has_annotation_content(restored):
            self.annotations[path] = restored
        else:
            self.annotations.pop(path, None)

        target_row = -1
        if 0 <= row_hint < len(self.records) and self.records[row_hint].path == path:
            target_row = row_hint
        else:
            for idx, record in enumerate(self.records):
                if record.path == path:
                    target_row = idx
                    break

        if target_row >= 0:
            if target_row != self.current_index:
                self.select_row(target_row, preserve_view=True)
            table_row = self.table_row_for_record_index(target_row)
            self._updating_table = True
            try:
                status_item = self.table.item(table_row, self.COL_STATUS) if table_row >= 0 else None
                if status_item is not None:
                    normalized_status = normalize_status(annotation.status)
                    status_item.setText(normalized_status)
                    status_item.setForeground(QBrush(status_text_color(normalized_status)))
                comment_item = self.table.item(table_row, self.COL_COMMENT) if table_row >= 0 else None
                if comment_item is not None:
                    comment_item.setText(annotation.comment)
            finally:
                self._updating_table = False
            self.refresh_table_row_styles()
        else:
            self.apply_filter()

        self.update_inspection_overlays()
        self.annotation_changed.emit()
        return True



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


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1550, 930)

        self.scan_result = ImageScanResult()
        self.annotations: Dict[str, Annotation] = {}
        self.selected_img_dirs: Set[str] = set()
        self.bg_colors: List[Tuple[int, int, int]] = list(DEFAULT_BG_COLORS)
        self.active_bg_index = 0
        self.cam_tabs: Dict[int, CamTab] = {}
        self._building_tree = False
        self._dirty_annotations = False
        self.global_status_filter = "Tous"
        self.modification_undo_stack: List[dict] = []
        self.modification_redo_stack: List[dict] = []
        # V2.70 : mémoire centrale des dessins partagée entre tous les onglets CAM.
        # Les dessins ne dépendent plus du widget/onglet actif, ce qui évite leur perte
        # lors d'un changement de CAM ou d'une reconstruction d'onglets.
        self.drawings_by_path: Dict[str, List[DrawingItem]] = {}
        self.drawing_redo_by_path: Dict[str, List[DrawingItem]] = {}
        self._pending_drawings_manifest: List[dict] = []

        # V2.78 : préférences clavier volontairement séparées des sessions/autosave.
        # Elles ne changent que via import/export JSON ou modifications dans l'onglet dédié.
        self.shortcut_preferences: Dict[str, str] = shortcut_default_preferences()
        self.shortcut_editors: Dict[str, QKeySequenceEdit] = {}
        self.shortcut_actions: Dict[str, QAction] = {}
        self.menu_shortcut_actions: Dict[str, QAction] = {}
        self._building_shortcut_editors = False
        self.shortcuts_dialog: Optional[QDialog] = None

        # Chemins configurables par l'utilisateur.
        self.path_sessions_edit = QLineEdit(str(APP_ROOT_DIR / "sessions"))
        self.path_autosave_edit = QLineEdit(str(APP_ROOT_DIR))
        self.path_backups_edit = QLineEdit(str(APP_ROOT_DIR / "_png_comparator_backups"))
        self.path_exports_edit = QLineEdit(str(APP_ROOT_DIR / "exports"))
        for edit in (self.path_sessions_edit, self.path_autosave_edit, self.path_backups_edit, self.path_exports_edit):
            edit.setMinimumWidth(430)
            edit.setToolTip("Chemin configurable. Laisse le chemin par défaut si tu ne veux pas le personnaliser.")
        self.btn_browse_sessions_path = QPushButton("...")
        self.btn_browse_autosave_path = QPushButton("...")
        self.btn_browse_backups_path = QPushButton("...")
        self.btn_browse_exports_path = QPushButton("...")
        self.btn_save_paths = QPushButton("Sauver chemins")

        self.image_cache = ImageMemoryCache(preview_max_side=DEFAULT_PREVIEW_MAX_SIDE, parent=self)
        self.image_cache.cache_info_changed.connect(self.on_cache_info_changed)

        self.root_edit = QLineEdit()
        self.root_edit.setPlaceholderText("Chemin racine de recherche...")
        self.btn_browse = QPushButton("Parcourir")
        self.btn_scan = QPushButton("Scanner")
        self.btn_clear_cache = QPushButton("Vider cache")
        self.btn_detach_tabs = QPushButton("Détacher viewer")
        self.btn_refs_popup = QPushButton("Sélection références")
        self.btn_tree_popup = QPushButton("Arbre dossiers")
        self.btn_log_popup = QPushButton("Log")
        self.btn_done_next = QPushButton("Terminé + suivant")
        self.btn_fix_next = QPushButton("À corriger + suivant")
        self.btn_undo_modification = QPushButton("↶ Retour modification")
        self.btn_redo_modification = QPushButton("Modification suivante ↷")
        self.status_filter_combo = QComboBox()
        self.status_filter_combo.addItems(["Tous", "À contrôler", "À corriger", "Terminées"])
        self.status_filter_combo.setToolTip("Filtre la liste et le viewer selon le statut de validation.")
        self.spin_expected_cams = QSpinBox()
        self.spin_expected_cams.setRange(0, 99)
        self.spin_expected_cams.setValue(0)
        self.spin_expected_cams.setToolTip("0 = désactivé. Sinon l'outil vérifie que chaque référence possède CAM1 à CAMn.")
        self.btn_check_missing_cams = QPushButton("Vérifier CAM manquantes")
        self.btn_check_missing_cams.setToolTip("Liste les CAM attendues mais absentes pour les références actives.")

        self.btn_prev_ref = QPushButton("Réf précédente")
        self.btn_next_ref = QPushButton("Réf suivante")
        self.btn_copy_path = QPushButton("Copier chemin")
        self.btn_copy_file = QPushButton("Copier nom image")
        self.btn_copy_ref = QPushButton("Copier réf")
        self.btn_open_folder = QPushButton("Ouvrir dossier")
        self.btn_open_external = QPushButton("Ouvrir image")
        self.current_metadata_label = QLabel("Métadonnées : -")
        self.current_metadata_label.setWordWrap(False)
        self.current_metadata_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.current_metadata_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.current_metadata_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.current_metadata_label.setMinimumHeight(24)
        self.current_metadata_label.setStyleSheet(
            "QLabel { color: #dddddd; background-color: #1f1f1f; border-top: 1px solid #343434; padding: 4px 8px; }"
        )
        self.current_metadata_label.setToolTip("Dimensions, poids, date de modification et chemin de l'image active.")

        self.validation_progress = QProgressBar()
        self.validation_progress.setRange(0, 100)
        self.validation_progress.setValue(0)
        self.validation_progress.setFormat("Validation : 0%")
        self.validation_stats_label = QLabel("Terminé : 0 | À corriger : 0 | À contrôler : 0")
        self.validation_stats_label.setStyleSheet("color: white;")
        self.detached_viewer_window: Optional[DetachedViewerWindow] = None
        self.refs_popup_dialog: Optional[WidgetPopupDialog] = None
        self.tree_popup_dialog: Optional[WidgetPopupDialog] = None
        self.log_popup_dialog: Optional[WidgetPopupDialog] = None
        self.viewer_detached = False
        self._app_closing = False
        self.current_session_path: Optional[str] = None
        self.recent_sessions: List[str] = self.load_recent_sessions()
        self._pending_session_selected_img_dirs: Optional[Set[str]] = None
        self._pending_detached_geometry_hex: str = ""
        self.recent_sessions_menu = None
        self.startup_dialog: Optional[StartupDialog] = None
        self.root_edit.textChanged.connect(self.update_startup_dialog_state)
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(AUTOSAVE_INTERVAL_MS)
        self.autosave_timer.timeout.connect(self.autosave_current_work)
        self.autosave_timer.start()

        self.drawing_save_timer = QTimer(self)
        self.drawing_save_timer.setSingleShot(True)
        self.drawing_save_timer.setInterval(1200)
        self.drawing_save_timer.timeout.connect(self.autosave_current_work)

        self.btn_save_session = QPushButton("Sauver session")
        self.btn_load_session = QPushButton("Charger session")
        self.btn_startup_quick = QPushButton("Démarrage rapide")
        self.btn_startup_quick.setToolTip("Ouvre la page de démarrage rapide pour choisir la racine, gérer les références et lancer un scan.")
        self.btn_save_session.setToolTip("Sauvegarde un fichier session projet avec chemin, références, filtres, annotations et réglages.")
        self.btn_load_session.setToolTip("Recharge une session projet et relance le scan si le chemin existe.")

        self.chk_recursive_refs = QCheckBox("Chercher refs dans sous-dossiers")
        self.chk_recursive_refs.setChecked(True)
        self.chk_recursive_refs.setToolTip("Permet de choisir un dossier plus haut : le scan cherche les dossiers références dans toute l'arborescence sous la racine.")
        self.chk_main_only = QCheckBox("Scan _MAIN_ only")
        self.chk_main_only.setChecked(True)
        self.chk_main_only.setToolTip("Pendant le scan, ne garde que les PNG dont le nom contient MAIN. Les autres images ne sont pas chargées dans le projet.")

        self.spin_preview_max = QSpinBox()
        self.spin_preview_max.setRange(100, 4000)
        self.spin_preview_max.setSingleStep(200)
        self.spin_preview_max.setSuffix(" px")
        self.spin_preview_max.setValue(DEFAULT_PREVIEW_MAX_SIDE)
        self.spin_preview_max.setToolTip("Taille max des images affichées dans le viewer. Plus bas = plus fluide, plus haut = plus détaillé. C’est maintenant le seul réglage de qualité.")
        self.spin_preview_max.valueChanged.connect(self.on_preview_size_changed)

        self.spin_preload_radius = QSpinBox()
        self.spin_preload_radius.setRange(0, 10)
        self.spin_preload_radius.setValue(DEFAULT_PRELOAD_RADIUS)
        self.spin_preload_radius.setToolTip("Rayon de préchargement. Exemple 3 = prépare les 3 images avant et les 3 images après l’image courante.")
        self.spin_preload_radius.valueChanged.connect(self.on_preload_radius_changed)

        self.chk_global_preload = QCheckBox("Précharger autour")
        self.chk_global_preload.setChecked(True)
        self.chk_global_preload.toggled.connect(self.on_global_preload_changed)

        self.chk_global_preserve = QCheckBox("Garder zoom/position")
        self.chk_global_preserve.setChecked(True)
        self.chk_global_preserve.toggled.connect(self.on_global_preserve_changed)

        self.cache_label = QLabel("Cache : 0 image(s) | 0 en attente")
        self.cache_label.setStyleSheet("color: white;")

        self.refs_edit = QPlainTextEdit()
        self.refs_edit.setPlaceholderText("Colle ici ta liste de références, une par ligne...\nREF1\nREF2\nREF3")
        self.refs_edit.setMinimumHeight(320)
        self.refs_edit.textChanged.connect(self.update_refs_count_label)
        self.refs_edit.textChanged.connect(self.update_startup_dialog_state)
        self.refs_count_label = QLabel("0 réf")
        self.refs_count_label.setStyleSheet("color: white;")

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Références / dossiers IMG trouvés", "Images"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree.itemChanged.connect(self.on_tree_item_changed)
        self.tree_count_label = QLabel("0 dossier IMG")
        self.tree_count_label.setStyleSheet("color: white;")

        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMinimumHeight(360)
        self.log_edit.textChanged.connect(self.update_log_count_label)
        self.log_count_label = QLabel("0 ligne")
        self.log_count_label.setStyleSheet("color: white;")

        self.active_table_label = QLabel("Aucune CAM active")
        self.active_table_label.setStyleSheet("font-weight: bold;")
        self.active_table_placeholder = QLabel("Scanne puis choisis une CAM. La liste des images/annotations s'affichera ici.")
        self.active_table_placeholder.setAlignment(Qt.AlignCenter)
        self.active_table_placeholder.setWordWrap(True)
        self.active_table_placeholder.setStyleSheet("color: white; padding: 12px;")

        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.South)
        self.tabs.setTabsClosable(False)
        self.tabs.setMovable(True)
        self.tabs.currentChanged.connect(self.update_active_image_table)

        self.summary_label = QLabel("Aucun scan lancé")
        self.summary_label.setStyleSheet("font-weight: bold;")

        self._build_ui()
        self._apply_button_tooltips()
        self._build_menu()
        self.setStatusBar(QStatusBar())
        self.load_state()
        self.update_refs_count_label()
        self.update_tree_count_label()
        self.update_log_count_label()
        self.update_validation_summary()
        QTimer.singleShot(350, self.show_start_help)

    def _apply_button_tooltips(self) -> None:
        """Centralise les infobulles pour les boutons ambigus de l'interface principale."""
        tooltip_map = {
            self.btn_browse: "Choisir le dossier racine où rechercher les références et dossiers IMG.",
            self.btn_startup_quick: "Ouvrir la page de démarrage rapide. Le chemin racine n'est plus affiché en permanence dans la page principale.",
            self.btn_scan: "Lancer le scan depuis le chemin racine et la liste de références.",
            self.btn_clear_cache: "Vider le cache image en mémoire. Utile si tu changes beaucoup de gros PNG.",
            self.btn_detach_tabs: "Détacher/réattacher le viewer principal et ses onglets CAM dans une fenêtre flottante.",
            self.btn_refs_popup: "Ouvrir la sélection native des références avec explorateur récursif et liste dynamique.",
            self.btn_tree_popup: "Ouvrir l'arbre des dossiers IMG trouvés pour cocher/décocher les sources.",
            self.btn_log_popup: "Afficher le journal complet du scan et des actions.",
            self.btn_done_next: "Marquer l'image active comme Terminée, puis passer à l'image suivante.",
            self.btn_fix_next: "Marquer l'image active comme À corriger puis passer à l'image suivante. Bloqué si aucun commentaire n'est renseigné.",
            self.btn_undo_modification: "Annuler la dernière modification de statut/commentaire. Raccourci : Ctrl+Z.",
            self.btn_redo_modification: "Rétablir la modification annulée. Raccourci : Ctrl+Y.",
            self.btn_check_missing_cams: "Vérifier les CAM manquantes selon le nombre de CAM attendues.",
            self.btn_prev_ref: "Aller à la référence précédente en conservant le CAM et les filtres actifs.",
            self.btn_next_ref: "Aller à la référence suivante en conservant le CAM et les filtres actifs.",
            self.btn_copy_path: "Copier le chemin complet de l'image active dans le presse-papiers.",
            self.btn_copy_file: "Copier uniquement le nom de l'image active.",
            self.btn_copy_ref: "Copier uniquement la référence active.",
            self.btn_open_folder: "Ouvrir le dossier contenant l'image active dans l'explorateur Windows.",
            self.btn_open_external: "Ouvrir l'image active avec l'application par défaut Windows.",
            self.btn_save_session: "Sauvegarder une session projet complète dans un fichier .pngcomp.json.",
            self.btn_load_session: "Charger une session projet sauvegardée et restaurer ses réglages.",
        }
        for widget, tip in tooltip_map.items():
            if widget.toolTip() == "":
                widget.setToolTip(tip)

    def _build_shortcuts_tab(self) -> QWidget:
        """Construit l'onglet de mapping clavier.

        Les raccourcis sont des préférences logiciel import/export uniquement :
        ils ne sont pas écrits dans les sessions projet ni dans l'autosave.
        """
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(8)

        title = QLabel("Raccourcis clavier")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        root_layout.addWidget(title)

        info = QLabel(
            "Clique dans une case puis tape le raccourci. "
            "Le bouton Vider désactive le raccourci de la fonction. "
            "Import/export JSON uniquement : ces préférences ne font pas partie des sessions."
        )
        info.setWordWrap(True)
        root_layout.addWidget(info)

        buttons = QHBoxLayout()
        btn_import = QPushButton("Importer JSON")
        btn_export = QPushButton("Exporter JSON")
        btn_reset = QPushButton("Réinitialiser défauts")
        btn_import.clicked.connect(self.import_shortcuts_json)
        btn_export.clicked.connect(self.export_shortcuts_json)
        btn_reset.clicked.connect(self.reset_shortcuts_to_defaults)
        buttons.addWidget(btn_import)
        buttons.addWidget(btn_export)
        buttons.addWidget(btn_reset)
        buttons.addStretch(1)
        root_layout.addLayout(buttons)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        grid = QGridLayout(content)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(5)
        grid.addWidget(QLabel("Fonction"), 0, 0)
        grid.addWidget(QLabel("Raccourci"), 0, 1)
        grid.addWidget(QLabel("Action"), 0, 2)

        row = 1
        current_group = None
        self.shortcut_editors.clear()
        self._building_shortcut_editors = True
        try:
            for item in SHORTCUT_DEFINITIONS:
                group = str(item.get("group", ""))
                if group != current_group:
                    current_group = group
                    group_label = QLabel(group)
                    group_label.setStyleSheet("font-weight: bold; padding-top: 8px; color: #ffffff;")
                    grid.addWidget(group_label, row, 0, 1, 3)
                    row += 1

                action_id = str(item["id"])
                label = QLabel(str(item.get("label", action_id)))
                label.setWordWrap(True)
                editor = QKeySequenceEdit()
                editor.setKeySequence(QKeySequence(self.shortcut_preferences.get(action_id, "")))
                editor.setToolTip("Clique ici puis tape un raccourci, ou laisse vide pour désactiver.")
                editor.editingFinished.connect(self.apply_shortcut_preferences_from_editors)
                clear_btn = QPushButton("Vider")
                clear_btn.setToolTip("Désactive ce raccourci.")
                clear_btn.clicked.connect(lambda _checked=False, aid=action_id: self.clear_shortcut(aid))
                grid.addWidget(label, row, 0)
                grid.addWidget(editor, row, 1)
                grid.addWidget(clear_btn, row, 2)
                self.shortcut_editors[action_id] = editor
                row += 1
        finally:
            self._building_shortcut_editors = False

        grid.setColumnStretch(0, 2)
        grid.setColumnStretch(1, 2)
        grid.setColumnStretch(2, 0)
        scroll.setWidget(content)
        root_layout.addWidget(scroll, 1)

        self.shortcut_status_label = QLabel("Raccourcis prêts")
        self.shortcut_status_label.setWordWrap(True)
        root_layout.addWidget(self.shortcut_status_label)
        return root

    def clear_shortcut(self, action_id: str) -> None:
        editor = self.shortcut_editors.get(action_id)
        if editor is not None:
            editor.setKeySequence(QKeySequence())
        self.apply_shortcut_preferences_from_editors()

    def refresh_shortcut_editors(self) -> None:
        self._building_shortcut_editors = True
        try:
            for action_id, editor in self.shortcut_editors.items():
                editor.setKeySequence(QKeySequence(self.shortcut_preferences.get(action_id, "")))
        finally:
            self._building_shortcut_editors = False
        self.apply_shortcuts_to_menu_actions()

    def apply_shortcut_preferences_from_editors(self) -> None:
        if getattr(self, "_building_shortcut_editors", False):
            return
        for action_id, editor in self.shortcut_editors.items():
            self.shortcut_preferences[action_id] = portable_shortcut_text(
                editor.keySequence().toString(QKeySequence.PortableText)
            )
        self.apply_shortcuts_to_menu_actions()
        self.update_shortcut_status_label()

    def update_shortcut_status_label(self) -> None:
        if not hasattr(self, "shortcut_status_label"):
            return
        used: Dict[str, List[str]] = {}
        labels = {str(item["id"]): str(item.get("label", item["id"])) for item in SHORTCUT_DEFINITIONS}
        for action_id, shortcut in self.shortcut_preferences.items():
            key = portable_shortcut_text(shortcut)
            if key:
                used.setdefault(key.lower(), []).append(labels.get(action_id, action_id))
        conflicts = [names for names in used.values() if len(names) > 1]
        if conflicts:
            text = "Attention : doublon détecté : " + " | ".join(", ".join(names) for names in conflicts[:3])
        else:
            text = "Raccourcis prêts. Les cases vides désactivent bien les raccourcis correspondants."
        self.shortcut_status_label.setText(text)

    def reset_shortcuts_to_defaults(self) -> None:
        self.shortcut_preferences = shortcut_default_preferences()
        self.refresh_shortcut_editors()
        self.statusBar().showMessage("Raccourcis réinitialisés", 2500)

    def import_shortcuts_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Importer raccourcis", str(APP_ROOT_DIR), "JSON (*.json)")
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("shortcuts"), dict):
                data = data["shortcuts"]
            if not isinstance(data, dict):
                raise ValueError("Format JSON invalide")
            defaults = shortcut_default_preferences()
            imported = dict(defaults)
            for key in defaults:
                if key in data:
                    imported[key] = portable_shortcut_text(str(data.get(key, "") or ""))
            self.shortcut_preferences = imported
            self.refresh_shortcut_editors()
            self.statusBar().showMessage("Raccourcis importés", 2500)
        except Exception as exc:
            QMessageBox.critical(self, "Import impossible", f"Impossible d'importer les raccourcis :\n{exc}")

    def export_shortcuts_json(self) -> None:
        self.apply_shortcut_preferences_from_editors()
        suggested = str(APP_ROOT_DIR / "png_comparator_shortcuts.json")
        path, _ = QFileDialog.getSaveFileName(self, "Exporter raccourcis", suggested, "JSON (*.json)")
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        payload = {
            "app": APP_NAME,
            "type": "shortcut_preferences",
            "note": "Préférences clavier import/export uniquement. Non liées aux sessions projet.",
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "shortcuts": self.shortcut_preferences,
        }
        try:
            Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            self.statusBar().showMessage("Raccourcis exportés", 2500)
        except Exception as exc:
            QMessageBox.critical(self, "Export impossible", f"Impossible d'exporter les raccourcis :\n{exc}")

    def apply_shortcuts_to_menu_actions(self) -> None:
        for action_id, action in getattr(self, "menu_shortcut_actions", {}).items():
            action.setShortcut(QKeySequence(self.shortcut_preferences.get(action_id, "")))
        self.rebuild_extra_shortcut_actions()

    def register_menu_shortcut_action(self, action_id: str, action: QAction) -> None:
        self.menu_shortcut_actions[action_id] = action
        action.setShortcut(QKeySequence(self.shortcut_preferences.get(action_id, "")))

    def rebuild_extra_shortcut_actions(self) -> None:
        for action in getattr(self, "shortcut_actions", {}).values():
            try:
                self.removeAction(action)
            except Exception:
                pass
        self.shortcut_actions = {}
        for item in SHORTCUT_DEFINITIONS:
            action_id = str(item["id"])
            if action_id in getattr(self, "menu_shortcut_actions", {}):
                continue
            shortcut = self.shortcut_preferences.get(action_id, "")
            if not shortcut:
                continue
            # Pour éviter de voler la saisie dans les commentaires/filtres, les raccourcis
            # sans modificateur sont gérés par l'eventFilter des viewers/tables uniquement.
            # Les raccourcis globaux QAction restent réservés aux combinaisons Ctrl/Alt/Meta.
            shortcut_upper = portable_shortcut_text(shortcut).upper()
            if not any(token in shortcut_upper for token in ("CTRL+", "ALT+", "META+")):
                continue
            action = QAction(self)
            action.setShortcut(QKeySequence(shortcut))
            action.setShortcutContext(Qt.ApplicationShortcut)
            action.triggered.connect(lambda _checked=False, aid=action_id: self.trigger_shortcut_action(aid))
            self.shortcut_actions[action_id] = action
            self.addAction(action)

    def _shortcut_text_from_event(self, event) -> str:
        key = int(event.key())
        if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
            return ""
        try:
            seq = QKeySequence(event.keyCombination())
            return portable_shortcut_text(seq.toString(QKeySequence.PortableText))
        except Exception:
            try:
                mods = event.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier | Qt.AltModifier | Qt.MetaModifier)
                mod_value = int(mods.value) if hasattr(mods, "value") else int(mods)
                seq = QKeySequence(mod_value | key)
                return portable_shortcut_text(seq.toString(QKeySequence.PortableText))
            except Exception:
                return ""

    def _focus_is_text_editor_global(self) -> bool:
        focus = QApplication.focusWidget()
        if focus is None:
            return False
        return isinstance(focus, (QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QKeySequenceEdit))

    def action_id_for_key_event(self, event) -> str:
        text = self._shortcut_text_from_event(event)
        if not text:
            return ""
        # Les raccourcis simples sans modificateur ne doivent pas écrire à la place de l'utilisateur
        # quand il est dans une case texte/commentaire/filtre.
        mods = event.modifiers() & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)
        has_strong_modifier = bool(mods)
        if self._focus_is_text_editor_global() and not has_strong_modifier:
            # Exception : Esc doit toujours pouvoir quitter le mode image seule.
            if portable_shortcut_text(text).lower() != portable_shortcut_text(self.shortcut_preferences.get("exit_focus_mode", "")).lower():
                return ""
        text_norm = portable_shortcut_text(text).lower()
        for item in SHORTCUT_DEFINITIONS:
            action_id = str(item["id"])
            configured = portable_shortcut_text(self.shortcut_preferences.get(action_id, ""))
            if configured and configured.lower() == text_norm:
                return action_id
        return ""

    def trigger_shortcut_action(self, action_id: str, source_tab: Optional[CamTab] = None) -> None:
        tab = source_tab or self.active_cam_tab()
        action_id = str(action_id or "")
        previous_ids = {"previous_image_left", "previous_image_up", "previous_image_page", "previous_image_backspace"}
        next_ids = {"next_image_right", "next_image_down", "next_image_page", "next_image_space"}

        if action_id in previous_ids:
            if tab is not None: tab.previous_image()
            return
        if action_id in next_ids:
            if tab is not None: tab.next_image()
            return
        if action_id == "first_image":
            if tab is not None: tab.jump_first()
            return
        if action_id == "last_image":
            if tab is not None: tab.jump_last()
            return
        if action_id == "fit_viewer":
            if tab is not None: tab.viewer_fit()
            return
        if action_id == "focus_zoom_field":
            if tab is not None:
                tab.zoom_percent_edit.setFocus(); tab.zoom_percent_edit.selectAll()
            return
        if action_id == "exit_focus_mode":
            if tab is not None and tab.viewer_focus_mode: tab.set_focus_mode(False)
            return
        if action_id == "toggle_focus_mode":
            if tab is not None: tab.toggle_focus_mode()
            return
        if action_id == "toggle_compare":
            if tab is not None: tab.btn_compare_mode.toggle()
            return
        if action_id == "toggle_overlay":
            if tab is not None and tab.compare_enabled: tab.btn_overlay_mode.toggle()
            return
        if action_id == "open_drawings":
            if tab is not None: tab.open_drawing_tools()
            return
        if action_id == "open_screenshots":
            if tab is not None: tab.open_screenshot_library()
            return
        if action_id == "mark_done_next": self.mark_current_done_next(); return
        if action_id == "mark_fix_next": self.mark_current_fix_next(); return
        if action_id == "previous_reference": self.go_previous_reference(); return
        if action_id == "next_reference": self.go_next_reference(); return
        if action_id == "copy_path": self.copy_current_image_path(); return
        if action_id == "copy_file": self.copy_current_file_name(); return
        if action_id == "copy_reference": self.copy_current_reference(); return
        if action_id == "open_folder": self.open_current_image_folder(); return
        if action_id == "open_image": self.open_current_image_external(); return
        if action_id == "new_comparison": self.new_comparison(); return
        if action_id == "scan": self.run_scan(); return
        if action_id == "save_session": self.save_session_as(); return
        if action_id == "load_session": self.load_session_dialog(); return
        if action_id == "clear_cache": self.clear_cache(); return
        if action_id == "quit": self.close(); return
        if action_id == "undo_modification": self.undo_last_modification(); return
        if action_id == "redo_modification": self.redo_last_modification(); return

    def _build_ui(self) -> None:
        # V2.94 : la page principale ne réaffiche plus le chemin racine complet.
        # La racine est désormais centralisée dans la page de démarrage rapide afin
        # de gagner de la hauteur et d'éviter une longue ligne de texte permanente.
        self.root_edit.hide()
        self.btn_browse.hide()

        top_path_layout = QGridLayout()
        top_path_layout.setContentsMargins(0, 0, 0, 0)
        top_path_layout.setHorizontalSpacing(6)
        top_path_layout.setVerticalSpacing(4)
        top_path_layout.addWidget(self.btn_startup_quick, 0, 0)
        top_path_layout.addWidget(self.btn_scan, 0, 1)
        top_path_layout.addWidget(self.btn_save_session, 0, 2)
        top_path_layout.addWidget(self.btn_load_session, 0, 3)
        top_path_layout.addWidget(self.chk_recursive_refs, 1, 0, 1, 2)
        top_path_layout.addWidget(self.chk_main_only, 1, 2, 1, 2)
        top_path_layout.setColumnStretch(4, 1)

        data_group = QGroupBox("Références / dossiers")
        data_layout = QGridLayout(data_group)
        data_layout.setContentsMargins(8, 8, 8, 8)
        data_layout.setHorizontalSpacing(6)
        data_layout.setVerticalSpacing(2)
        self.btn_refs_popup.setText("Sélection refs")
        self.btn_tree_popup.setText("Arbre dossiers")
        self.btn_refs_popup.setMaximumWidth(130)
        self.btn_tree_popup.setMaximumWidth(120)
        self.refs_count_label.setMinimumWidth(52)
        self.tree_count_label.setMinimumWidth(80)
        data_layout.addWidget(self.btn_refs_popup, 0, 0)
        data_layout.addWidget(self.refs_count_label, 0, 1)
        data_layout.addWidget(self.btn_tree_popup, 0, 2)
        data_layout.addWidget(self.tree_count_label, 0, 3)
        data_layout.setColumnStretch(4, 1)

        self.perf_group = QGroupBox("Performance viewer")
        self.perf_group.setToolTip("Réglages de qualité/fluidité du viewer : taille max image affichée, préchargement et conservation zoom/pan.")
        perf_layout = QGridLayout(self.perf_group)
        perf_layout.addWidget(QLabel("Taille max affichée :"), 0, 0)
        perf_layout.addWidget(self.spin_preview_max, 0, 1)
        perf_layout.addWidget(QLabel("Préchargement ±"), 1, 0)
        perf_layout.addWidget(self.spin_preload_radius, 1, 1)
        perf_layout.addWidget(self.chk_global_preload, 2, 0, 1, 2)
        perf_layout.addWidget(self.chk_global_preserve, 3, 0, 1, 2)
        perf_layout.addWidget(self.btn_clear_cache, 4, 0, 1, 2)
        perf_layout.addWidget(self.cache_label, 5, 0, 1, 2)

        active_table_group = QGroupBox("Liste images / annotations - CAM actif")
        active_table_group.setStyleSheet(
            "QGroupBox { color: #eeeeee; border: 1px solid #343434; border-radius: 8px; margin-top: 8px; background-color: #181818; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }"
            "QPushButton { background-color: #2b2b2b; color: #eeeeee; border: 1px solid #505050; border-radius: 4px; padding: 5px 9px; }"
            "QPushButton:hover { background-color: #383838; border-color: #777777; }"
        )
        active_table_layout = QVBoxLayout(active_table_group)
        active_table_layout.setSpacing(6)

        workflow_layout = QHBoxLayout()
        workflow_layout.setContentsMargins(0, 0, 0, 0)
        workflow_layout.setSpacing(6)
        workflow_layout.addWidget(self.btn_done_next)
        workflow_layout.addWidget(self.btn_fix_next)
        workflow_layout.addWidget(self.btn_undo_modification)
        workflow_layout.addWidget(self.btn_redo_modification)
        workflow_layout.addStretch(1)

        active_table_layout.addLayout(workflow_layout)
        active_table_layout.addWidget(self.active_table_label)
        self.active_table_holder = QWidget()
        self.active_table_holder_layout = QVBoxLayout(self.active_table_holder)
        self.active_table_holder_layout.setContentsMargins(0, 0, 0, 0)
        self.active_table_holder_layout.addWidget(self.active_table_placeholder, 1)
        active_table_layout.addWidget(self.active_table_holder, 1)

        project_panel = QWidget()
        project_layout = QVBoxLayout(project_panel)
        project_layout.setContentsMargins(6, 6, 6, 6)
        project_layout.addLayout(top_path_layout)
        project_layout.addWidget(data_group)
        project_layout.addWidget(active_table_group, 1)
        project_layout.addWidget(self.summary_label)

        left_panel = QWidget()
        left_panel.setMinimumWidth(620)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        # V2.83 : la page principale n'est plus dans un système d'onglets.
        # Les raccourcis clavier sont déplacés dans le menu principal.
        left_layout.addWidget(project_panel, 1)

        self.tabs_placeholder = QLabel("Viewer détaché. Utilise le bouton \"Réattacher viewer\" pour le remettre dans l'interface principale.")
        self.tabs_placeholder.setAlignment(Qt.AlignCenter)
        self.tabs_placeholder.setStyleSheet("font-size: 16px; color: white; padding: 18px;")
        self.tabs_placeholder.hide()

        self.tabs_host = QWidget()
        self.tabs_host_layout = QVBoxLayout(self.tabs_host)
        self.tabs_host_layout.setContentsMargins(0, 0, 0, 0)
        self.tabs_host_layout.addWidget(self.tabs, 1)
        self.tabs_host_layout.addWidget(self.tabs_placeholder, 1)
        # V2.90 : métadonnées alignées au bord droit du viewer, avec largeur complète.
        self.tabs_host_layout.addWidget(self.current_metadata_label, 0)

        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.addWidget(left_panel)
        self.main_splitter.addWidget(self.tabs_host)
        self.main_splitter.setSizes([680, 870])

        self.setCentralWidget(self.main_splitter)

        self.btn_browse.clicked.connect(self.browse_root)
        self.btn_startup_quick.clicked.connect(self.show_start_help)
        self.btn_scan.clicked.connect(self.run_scan)
        self.btn_clear_cache.clicked.connect(self.clear_cache)
        self.btn_refs_popup.clicked.connect(self.open_refs_popup)
        self.btn_tree_popup.clicked.connect(self.open_tree_popup)
        self.btn_log_popup.clicked.connect(self.open_log_popup)
        self.btn_save_session.clicked.connect(self.save_session_as)
        self.btn_load_session.clicked.connect(self.load_session_dialog)
        self.btn_done_next.clicked.connect(self.mark_current_done_next)
        self.btn_fix_next.clicked.connect(self.mark_current_fix_next)
        self.btn_undo_modification.clicked.connect(self.undo_last_modification)
        self.btn_redo_modification.clicked.connect(self.redo_last_modification)
        self.btn_browse_sessions_path.clicked.connect(lambda: self.browse_path_setting(self.path_sessions_edit))
        self.btn_browse_autosave_path.clicked.connect(lambda: self.browse_path_setting(self.path_autosave_edit))
        self.btn_browse_backups_path.clicked.connect(lambda: self.browse_path_setting(self.path_backups_edit))
        self.btn_browse_exports_path.clicked.connect(lambda: self.browse_path_setting(self.path_exports_edit))
        self.btn_save_paths.clicked.connect(lambda: self.save_state(silent=False))
        self.status_filter_combo.currentTextChanged.connect(self.on_status_filter_changed)
        self.spin_expected_cams.valueChanged.connect(lambda _v: self.on_expected_cams_changed())
        self.btn_check_missing_cams.clicked.connect(self.show_missing_cams)
        self.btn_prev_ref.clicked.connect(self.go_previous_reference)
        self.btn_next_ref.clicked.connect(self.go_next_reference)
        self.btn_copy_path.clicked.connect(self.copy_current_image_path)
        self.btn_copy_file.clicked.connect(self.copy_current_file_name)
        self.btn_copy_ref.clicked.connect(self.copy_current_reference)
        self.btn_open_folder.clicked.connect(self.open_current_image_folder)
        self.btn_open_external.clicked.connect(self.open_current_image_external)

    def open_shortcuts_dialog(self) -> None:
        """Ouvre le mapping clavier depuis le menu principal."""
        if self.shortcuts_dialog is not None:
            self.shortcuts_dialog.show()
            self.shortcuts_dialog.raise_()
            self.shortcuts_dialog.activateWindow()
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Raccourcis clavier")
        dialog.resize(720, 760)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self._build_shortcuts_tab())
        dialog.finished.connect(lambda _code: setattr(self, "shortcuts_dialog", None))
        self.shortcuts_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("Fichier")

        new_comparison_action = QAction("Nouvelle comparaison", self)
        self.register_menu_shortcut_action("new_comparison", new_comparison_action)
        new_comparison_action.triggered.connect(self.new_comparison)
        file_menu.addAction(new_comparison_action)
        file_menu.addSeparator()

        scan_action = QAction("Scanner", self)
        self.register_menu_shortcut_action("scan", scan_action)
        scan_action.triggered.connect(self.run_scan)
        file_menu.addAction(scan_action)

        undo_action = QAction("Retour modification", self)
        self.register_menu_shortcut_action("undo_modification", undo_action)
        undo_action.triggered.connect(self.undo_last_modification)
        file_menu.addAction(undo_action)

        redo_action = QAction("Modification suivante", self)
        self.register_menu_shortcut_action("redo_modification", redo_action)
        redo_action.triggered.connect(self.redo_last_modification)
        file_menu.addAction(redo_action)

        file_menu.addSeparator()
        save_session_action = QAction("Sauver session projet...", self)
        self.register_menu_shortcut_action("save_session", save_session_action)
        save_session_action.triggered.connect(self.save_session_as)
        file_menu.addAction(save_session_action)

        load_session_action = QAction("Charger session projet...", self)
        self.register_menu_shortcut_action("load_session", load_session_action)
        load_session_action.triggered.connect(self.load_session_dialog)
        file_menu.addAction(load_session_action)

        self.recent_sessions_menu = file_menu.addMenu("Sessions récentes")
        self.update_recent_sessions_menu()

        file_menu.addSeparator()
        clear_cache_action = QAction("Vider cache images", self)
        self.register_menu_shortcut_action("clear_cache", clear_cache_action)
        clear_cache_action.triggered.connect(self.clear_cache)
        file_menu.addAction(clear_cache_action)

        file_menu.addSeparator()
        quit_action = QAction("Quitter", self)
        self.register_menu_shortcut_action("quit", quit_action)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        shortcuts_menu = self.menuBar().addMenu("Raccourcis clavier")
        shortcuts_action = QAction("Configurer les raccourcis...", self)
        shortcuts_action.triggered.connect(self.open_shortcuts_dialog)
        shortcuts_menu.addAction(shortcuts_action)

        paths_menu = self.menuBar().addMenu("Paramètres chemins")
        paths_group = QGroupBox("Chemins")
        paths_layout = QGridLayout(paths_group)
        paths_layout.addWidget(QLabel("Sessions :"), 0, 0)
        paths_layout.addWidget(self.path_sessions_edit, 0, 1)
        paths_layout.addWidget(self.btn_browse_sessions_path, 0, 2)
        paths_layout.addWidget(QLabel("Autosave / état :"), 1, 0)
        paths_layout.addWidget(self.path_autosave_edit, 1, 1)
        paths_layout.addWidget(self.btn_browse_autosave_path, 1, 2)
        paths_layout.addWidget(QLabel("Backups :"), 2, 0)
        paths_layout.addWidget(self.path_backups_edit, 2, 1)
        paths_layout.addWidget(self.btn_browse_backups_path, 2, 2)
        paths_layout.addWidget(QLabel("Exports :"), 3, 0)
        paths_layout.addWidget(self.path_exports_edit, 3, 1)
        paths_layout.addWidget(self.btn_browse_exports_path, 3, 2)
        paths_layout.addWidget(self.btn_save_paths, 4, 0, 1, 3)
        paths_action = QWidgetAction(self)
        paths_action.setDefaultWidget(paths_group)
        paths_menu.addAction(paths_action)

        image_settings_menu = self.menuBar().addMenu("Paramètres images")

        expected_group = QGroupBox("CAM attendues")
        expected_layout = QGridLayout(expected_group)
        expected_layout.addWidget(QLabel("Nombre :"), 0, 0)
        expected_layout.addWidget(self.spin_expected_cams, 0, 1)
        expected_layout.addWidget(self.btn_check_missing_cams, 1, 0, 1, 2)
        expected_action = QWidgetAction(self)
        expected_action.setDefaultWidget(expected_group)
        image_settings_menu.addAction(expected_action)

        image_settings_menu.addSeparator()
        perf_widget_action = QWidgetAction(self)
        perf_widget_action.setDefaultWidget(self.perf_group)
        image_settings_menu.addAction(perf_widget_action)

        # V2.90 : menu supérieur "Image active" supprimé.
        # Les mêmes actions sont disponibles par clic droit sur une ligne de la liste.

        help_menu = self.menuBar().addMenu("Aide")
        log_action = QAction("Afficher le log", self)
        log_action.triggered.connect(self.open_log_popup)
        help_menu.addAction(log_action)
        locations_action = QAction("Emplacements des données", self)
        locations_action.triggered.connect(self.show_data_locations)
        help_menu.addAction(locations_action)
        help_menu.addSeparator()
        about_action = QAction("À propos", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

        self.apply_shortcuts_to_menu_actions()

    def show_start_help(self) -> None:
        """Affiche la fenêtre de démarrage rapide, non bloquante et fermable."""
        if self.startup_dialog is None:
            self.startup_dialog = StartupDialog(self)
        self.startup_dialog.refresh_state()
        if hasattr(self.startup_dialog, "populate_folder_tree"):
            root_now = self.root_edit.text().strip().strip('"')
            if getattr(self.startup_dialog, "_folder_tree_root", "") != root_now or self.startup_dialog.folder_tree.topLevelItemCount() == 0:
                self.startup_dialog.populate_folder_tree()
        self.startup_dialog.show()
        # V2.97 : la page Démarrage rapide reste centrée.
        # Elle est plus haute, mais conserve la même largeur pour garder la mise en page stable.
        self._center_startup_dialog()
        self.startup_dialog.raise_()
        self.startup_dialog.activateWindow()

    def _center_startup_dialog(self) -> None:
        """Centre la fenêtre Démarrage rapide sur l'écran actif ou sur la fenêtre principale."""
        if self.startup_dialog is None:
            return
        try:
            self.startup_dialog.adjustSize()
            screen = self.screen() or self.startup_dialog.screen() or QApplication.primaryScreen()
            if screen is not None:
                geo = screen.availableGeometry()
                x = geo.x() + max(0, (geo.width() - self.startup_dialog.width()) // 2)
                y = geo.y() + max(0, (geo.height() - self.startup_dialog.height()) // 2)
                self.startup_dialog.move(x, y)
                return
            parent_geo = self.frameGeometry()
            x = parent_geo.x() + max(0, (parent_geo.width() - self.startup_dialog.width()) // 2)
            y = parent_geo.y() + max(0, (parent_geo.height() - self.startup_dialog.height()) // 2)
            self.startup_dialog.move(x, y)
        except Exception:
            pass

    def update_startup_dialog_state(self) -> None:
        if self.startup_dialog is not None:
            self.startup_dialog.refresh_state()

    def close_startup_dialog_after_scan(self) -> None:
        if self.startup_dialog is not None and self.startup_dialog.isVisible():
            self.startup_dialog.allow_close_after_scan()

    def new_comparison(self) -> None:
        """Réinitialise le projet courant sans fermer l'application."""
        if self._dirty_annotations:
            reply = QMessageBox.question(
                self,
                "Nouvelle comparaison",
                "Des annotations ont été modifiées. Continuer et nettoyer le projet courant ?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
        if self.viewer_detached:
            self.reattach_viewer()
        self.root_edit.clear()
        self.refs_edit.clear()
        self.scan_result = ImageScanResult()
        self.selected_img_dirs.clear()
        self.annotations.clear()
        self.drawings_by_path.clear()
        self.drawing_redo_by_path.clear()
        self._pending_drawings_manifest = []
        self._dirty_annotations = False
        self.global_status_filter = "Tous"
        if hasattr(self, "status_filter_combo"):
            self.status_filter_combo.blockSignals(True)
            self.status_filter_combo.setCurrentText("Tous")
            self.status_filter_combo.blockSignals(False)
        self.tree.clear()
        self.log_edit.clear()
        self.image_cache.clear()
        self.clear_tabs_only()
        self.summary_label.setText("Nouvelle comparaison prête")
        self.current_metadata_label.setText("Métadonnées : -")
        self.current_metadata_label.setToolTip("")
        self.update_refs_count_label()
        self.update_tree_count_label()
        self.update_log_count_label()
        self.update_validation_summary()
        self.save_state(silent=True)
        self.statusBar().showMessage("Nouvelle comparaison : chemin et liste nettoyés", 3500)
        self.show_start_help()

    def _configured_dir(self, edit: Optional[QLineEdit], fallback: Path) -> Path:
        try:
            text = edit.text().strip() if edit is not None else ""
            return Path(text).expanduser() if text else fallback
        except Exception:
            return fallback

    def sessions_dir_path(self) -> Path:
        return self._configured_dir(getattr(self, "path_sessions_edit", None), APP_ROOT_DIR / "sessions")

    def autosave_dir_path(self) -> Path:
        return self._configured_dir(getattr(self, "path_autosave_edit", None), APP_ROOT_DIR)

    def backups_dir_path(self) -> Path:
        return self._configured_dir(getattr(self, "path_backups_edit", None), APP_ROOT_DIR / "_png_comparator_backups")

    def exports_dir_path(self) -> Path:
        return self._configured_dir(getattr(self, "path_exports_edit", None), APP_ROOT_DIR / "exports")

    def state_file_path(self) -> Path:
        return self.autosave_dir_path() / ".png_comparator_v2_state.json"

    def session_recents_file_path(self) -> Path:
        return self.sessions_dir_path() / ".png_comparator_sessions_recent.json"

    def browse_path_setting(self, edit: QLineEdit) -> None:
        start = edit.text().strip() or str(APP_ROOT_DIR)
        path = QFileDialog.getExistingDirectory(self, "Choisir un chemin", start)
        if path:
            edit.setText(path)
            self.save_state(silent=True)
            self.statusBar().showMessage("Chemin mis à jour", 2500)

    def load_recent_sessions(self) -> List[str]:
        try:
            recents_file = self.session_recents_file_path() if hasattr(self, "session_recents_file_path") else SESSION_RECENTS_FILE
            if recents_file.exists():
                data = json.loads(recents_file.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return [str(p) for p in data if str(p).strip() and Path(str(p)).exists()][:MAX_RECENT_SESSIONS]
        except Exception:
            pass
        return []

    def save_recent_sessions(self) -> None:
        try:
            recents_file = self.session_recents_file_path() if hasattr(self, "session_recents_file_path") else SESSION_RECENTS_FILE
            recents_file.parent.mkdir(parents=True, exist_ok=True)
            recents_file.write_text(json.dumps(self.recent_sessions[:MAX_RECENT_SESSIONS], indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def add_recent_session(self, path: str) -> None:
        path = str(Path(path))
        self.recent_sessions = [p for p in self.recent_sessions if p != path and Path(p).exists()]
        self.recent_sessions.insert(0, path)
        self.recent_sessions = self.recent_sessions[:MAX_RECENT_SESSIONS]
        self.save_recent_sessions()
        self.update_recent_sessions_menu()

    def update_recent_sessions_menu(self) -> None:
        menu = getattr(self, "recent_sessions_menu", None)
        if menu is None:
            return
        menu.clear()
        valid = [p for p in self.recent_sessions if Path(p).exists()]
        self.recent_sessions = valid[:MAX_RECENT_SESSIONS]
        if not self.recent_sessions:
            empty_action = QAction("Aucune session récente", self)
            empty_action.setEnabled(False)
            menu.addAction(empty_action)
            return
        for session_path in self.recent_sessions:
            action = QAction(Path(session_path).name, self)
            action.setToolTip(session_path)
            action.triggered.connect(lambda checked=False, p=session_path: self.load_session_file(p))
            menu.addAction(action)
        menu.addSeparator()
        clear_action = QAction("Vider l'historique", self)
        clear_action.triggered.connect(self.clear_recent_sessions)
        menu.addAction(clear_action)

    def clear_recent_sessions(self) -> None:
        self.recent_sessions = []
        self.save_recent_sessions()
        self.update_recent_sessions_menu()
        self.save_state(silent=True)

    def _backup_file(self, path: Path) -> None:
        if not path.exists():
            return
        try:
            backup_dir = self.backups_dir_path() if hasattr(self, "backups_dir_path") else (path.parent / "_png_comparator_backups")
            backup_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = backup_dir / f"{path.stem}_{timestamp}{path.suffix}.bak"
            shutil.copy2(path, backup_path)
            backups = sorted(
                backup_dir.glob(f"{path.stem}_*{path.suffix}.bak"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            for old_backup in backups[MAX_BACKUPS_PER_FILE:]:
                try:
                    old_backup.unlink()
                except Exception:
                    pass
        except Exception:
            pass

    def write_json_with_backup(self, path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        new_text = json.dumps(data, indent=2, ensure_ascii=False)
        if path.exists():
            try:
                if path.read_text(encoding="utf-8") == new_text:
                    return
            except Exception:
                pass
        self._backup_file(path)
        path.write_text(new_text, encoding="utf-8")

    def _drawing_signature(self, item: DrawingItem) -> str:
        try:
            return json.dumps(item.to_dict(), sort_keys=True, ensure_ascii=False)
        except Exception:
            return f"{item.kind}|{item.color}|{item.width}|{item.ref_width}|{item.ref_height}|{item.points}"

    def _merge_drawings_into(self, target: Dict[str, List[DrawingItem]], path_key: str, items: Sequence[DrawingItem]) -> None:
        key = canonical_image_key(path_key)
        if not key or not items:
            return
        bucket = target.setdefault(key, [])
        seen = {self._drawing_signature(item) for item in bucket}
        for item in items:
            if item.kind in {"freehand", "line", "rect", "ellipse"}:
                if not item.points:
                    continue
            elif item.kind == "eraser_action":
                if not item.erased_items:
                    continue
            else:
                continue
            sig = self._drawing_signature(item)
            if sig in seen:
                continue
            bucket.append(item)
            seen.add(sig)

    def collect_drawings_manifest(self) -> List[dict]:
        """Sauvegarde renforcée des dessins avec métadonnées de rattachement.

        Le champ legacy `drawings` reste présent, mais ce manifeste permet de relier
        un dessin à la bonne image même si le chemin est recanonisé après un scan ou
        une session chargée depuis un autre contexte Windows/SharePoint.
        """
        drawings = self.collect_drawings_data()
        records_by_key = {canonical_image_key(r.path): r for r in getattr(self.scan_result, "records", [])}
        manifest: List[dict] = []
        for key, items_data in drawings.items():
            record = records_by_key.get(canonical_image_key(key))
            manifest.append({
                "schema": 2,
                "key": canonical_image_key(key),
                "path": record.path if record is not None else str(key),
                "file_name": record.file_name if record is not None else loose_path_basename(str(key)),
                "stem": record.stem if record is not None else Path(str(key)).stem,
                "ref": record.ref if record is not None else "",
                "cam_number": int(record.cam_number) if record is not None else 0,
                "cam_name": record.cam_name if record is not None else "",
                "items": items_data,
            })
        return manifest

    def relink_drawings_to_scan_records(self) -> None:
        """Réassocie les dessins chargés d'une session aux chemins du scan actif.

        Corrige les disparitions intermittentes dues aux clés de chemins qui ne sont
        pas strictement identiques entre une sauvegarde, un re-scan et un environnement
        cloud/Windows.
        """
        records = list(getattr(self.scan_result, "records", []))
        if not records and not self.drawings_by_path:
            return

        valid_keys = {canonical_image_key(r.path) for r in records}
        by_meta: Dict[Tuple[str, int, str], str] = {}
        by_name: Dict[str, List[str]] = {}
        for r in records:
            key = canonical_image_key(r.path)
            by_meta[(str(r.ref).upper(), int(r.cam_number), str(r.file_name).lower())] = key
            by_name.setdefault(str(r.file_name).lower(), []).append(key)

        remapped: Dict[str, List[DrawingItem]] = {}

        # 1) Dessins déjà présents en mémoire : conserver si la clé correspond,
        # sinon tenter un fallback par nom de fichier unique.
        for key, items in list(self.drawings_by_path.items()):
            canon = canonical_image_key(key)
            target_key = canon if canon in valid_keys else ""
            if not target_key:
                candidates = by_name.get(loose_path_basename(key), [])
                if len(candidates) == 1:
                    target_key = candidates[0]
            self._merge_drawings_into(remapped, target_key or canon, items)

        # 2) Manifeste enrichi : priorité au mapping ref+cam+nom fichier.
        for entry in getattr(self, "_pending_drawings_manifest", []):
            if not isinstance(entry, dict):
                continue
            items_raw = entry.get("items", [])
            if not isinstance(items_raw, list):
                continue
            items = [DrawingItem.from_dict(item) for item in items_raw if isinstance(item, dict)]
            items = [
                item for item in items
                if (item.kind in {"freehand", "line", "rect", "ellipse"} and item.points)
                or (item.kind == "eraser_action" and item.erased_items)
            ]
            file_name = str(entry.get("file_name") or loose_path_basename(str(entry.get("path") or entry.get("key") or ""))).lower()
            ref = str(entry.get("ref") or "").upper()
            try:
                cam_number = int(entry.get("cam_number") or 0)
            except Exception:
                cam_number = 0
            target_key = by_meta.get((ref, cam_number, file_name), "")
            if not target_key:
                stored_key = canonical_image_key(str(entry.get("path") or entry.get("key") or ""))
                if stored_key in valid_keys:
                    target_key = stored_key
            if not target_key:
                candidates = by_name.get(file_name, [])
                if len(candidates) == 1:
                    target_key = candidates[0]
            self._merge_drawings_into(remapped, target_key, items)

        self.drawings_by_path = {key: items for key, items in remapped.items() if key and items}
        self.drawing_redo_by_path = {}

    def collect_drawings_data(self) -> Dict[str, List[dict]]:
        """Collecte la mémoire centrale des dessins pour session/autosave.

        V2.73/V2.74 : toutes les clés sont canonisées et fusionnées sans doublons. Cela
        évite que des dessins disparaissent parce qu'un onglet, une session ou un
        scan utilise une variante de chemin différente.
        """
        combined: Dict[str, List[DrawingItem]] = {}

        # Source de vérité : mémoire centrale MainWindow.
        for path, items in getattr(self, "drawings_by_path", {}).items():
            self._merge_drawings_into(combined, canonical_image_key(str(path)), items)

        # Sécurité : si un onglet possède encore une référence locale, fusionner
        # sans écraser la mémoire centrale.
        for tab in getattr(self, "cam_tabs", {}).values():
            for viewer_name in ("viewer", "compare_viewer"):
                viewer = getattr(tab, viewer_name, None)
                if viewer is None:
                    continue
                for path, items in getattr(viewer, "drawings_by_path", {}).items():
                    self._merge_drawings_into(combined, canonical_image_key(str(path)), items)

        return {
            path: [
                item.to_dict()
                for item in items
                if (item.kind in {"freehand", "line", "rect", "ellipse"} and item.points)
                or (item.kind == "eraser_action" and item.erased_items)
            ]
            for path, items in combined.items()
            if items
        }

    def apply_pending_drawings_to_tab(self, tab: "CamTab") -> None:
        """Branche l'onglet sur la mémoire centrale des dessins."""
        tab.viewer.drawings_by_path = self.drawings_by_path
        tab.viewer.drawing_redo_by_path = self.drawing_redo_by_path
        tab.compare_viewer.drawings_by_path = self.drawings_by_path
        tab.compare_viewer.drawing_redo_by_path = self.drawing_redo_by_path
        tab.viewer.update()
        tab.compare_viewer.update()

    def collect_state_data(self) -> dict:
        detached_geometry = ""
        main_geometry = ""
        try:
            main_geometry = bytes(self.saveGeometry()).hex()
        except Exception:
            main_geometry = ""
        try:
            if self.detached_viewer_window is not None:
                detached_geometry = bytes(self.detached_viewer_window.saveGeometry()).hex()
        except Exception:
            detached_geometry = ""

        return {
            "app": APP_NAME,
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "root": self.root_edit.text().strip(),
            "refs": self.refs_edit.toPlainText(),
            "recursive_refs": self.chk_recursive_refs.isChecked(),
            "main_only": self.chk_main_only.isChecked(),
            "bg_colors": self.bg_colors,
            "active_bg_index": self.active_bg_index,
            "selected_img_dirs": sorted(self.selected_img_dirs),
            "annotations": {
                path: Annotation(ann.marked, normalize_status(ann.status), ann.comment).to_dict()
                for path, ann in self.annotations.items()
                if has_annotation_content(ann)
            },
            "drawings": self.collect_drawings_data(),
            "drawings_manifest": self.collect_drawings_manifest(),
            "preview_max_side": self.spin_preview_max.value(),
            "preload_radius": self.spin_preload_radius.value(),
            "global_preload": self.chk_global_preload.isChecked(),
            "global_preserve": self.chk_global_preserve.isChecked(),
            "global_status_filter": self.global_status_filter,
            "expected_cams": self.spin_expected_cams.value() if hasattr(self, "spin_expected_cams") else 0,
            "current_session_path": self.current_session_path or "",
            "recent_sessions": self.recent_sessions,
            "paths": {
                "sessions": self.path_sessions_edit.text().strip() if hasattr(self, "path_sessions_edit") else "",
                "autosave": self.path_autosave_edit.text().strip() if hasattr(self, "path_autosave_edit") else "",
                "backups": self.path_backups_edit.text().strip() if hasattr(self, "path_backups_edit") else "",
                "exports": self.path_exports_edit.text().strip() if hasattr(self, "path_exports_edit") else "",
            },
            "viewer_detached": self.viewer_detached,
            "main_window_geometry": main_geometry,
            "detached_window_geometry": detached_geometry or self._pending_detached_geometry_hex,
        }

    def apply_state_data(self, data: dict, restore_geometry: bool = False) -> None:
        paths = data.get("paths", {})
        if isinstance(paths, dict):
            if hasattr(self, "path_sessions_edit") and str(paths.get("sessions", "")).strip():
                self.path_sessions_edit.setText(str(paths.get("sessions", "")).strip())
            if hasattr(self, "path_autosave_edit") and str(paths.get("autosave", "")).strip():
                self.path_autosave_edit.setText(str(paths.get("autosave", "")).strip())
            if hasattr(self, "path_backups_edit") and str(paths.get("backups", "")).strip():
                self.path_backups_edit.setText(str(paths.get("backups", "")).strip())
            if hasattr(self, "path_exports_edit") and str(paths.get("exports", "")).strip():
                self.path_exports_edit.setText(str(paths.get("exports", "")).strip())

        self.root_edit.setText(str(data.get("root", "")))
        self.refs_edit.setPlainText(str(data.get("refs", "")))
        self.chk_recursive_refs.setChecked(bool(data.get("recursive_refs", True)))
        self.chk_main_only.setChecked(bool(data.get("main_only", True)))
        self.global_status_filter = str(data.get("global_status_filter", "Tous") or "Tous")
        if self.global_status_filter == "Non vérifiées":
            self.global_status_filter = "À contrôler"
        if hasattr(self, "status_filter_combo"):
            idx = self.status_filter_combo.findText(self.global_status_filter, Qt.MatchFixedString)
            self.status_filter_combo.setCurrentIndex(idx if idx >= 0 else 0)
        if hasattr(self, "spin_expected_cams"):
            expected_cams = int(data.get("expected_cams", 0) or 0)
            self.spin_expected_cams.setValue(max(self.spin_expected_cams.minimum(), min(self.spin_expected_cams.maximum(), expected_cams)))
        colors = data.get("bg_colors")
        if isinstance(colors, list) and len(colors) == 3:
            try:
                self.bg_colors = [tuple(int(v) for v in c[:3]) for c in colors]  # type: ignore[index]
            except Exception:
                self.bg_colors = list(DEFAULT_BG_COLORS)
        self.bg_colors[0] = DEFAULT_BG_COLORS[0]
        self.bg_colors[1] = (0, 0, 0)

        self.active_bg_index = int(data.get("active_bg_index", 0))
        if self.active_bg_index < 0 or self.active_bg_index > 2:
            self.active_bg_index = 0

        annotations_raw = data.get("annotations", {})
        if isinstance(annotations_raw, dict):
            self.annotations = {}
            for path_key, ann in annotations_raw.items():
                if not isinstance(ann, dict):
                    continue
                restored_ann = Annotation.from_dict(ann)
                restored_ann.status = normalize_status(restored_ann.status)
                if has_annotation_content(restored_ann):
                    self.annotations[str(path_key)] = restored_ann

        self.drawings_by_path = {}
        self.drawing_redo_by_path = {}
        self._pending_drawings_manifest = []

        drawings_manifest = data.get("drawings_manifest", [])
        if isinstance(drawings_manifest, list):
            for entry in drawings_manifest:
                if not isinstance(entry, dict):
                    continue
                self._pending_drawings_manifest.append(entry)
                items_raw = entry.get("items", [])
                if not isinstance(items_raw, list):
                    continue
                key_source = str(entry.get("path") or entry.get("key") or "")
                key = canonical_image_key(key_source)
                items = [DrawingItem.from_dict(item) for item in items_raw if isinstance(item, dict)]
                items = [item for item in items if item.points]
                self._merge_drawings_into(self.drawings_by_path, key, items)

        # Compatibilité avec les sessions V2.68-V2.73.
        drawings_raw = data.get("drawings", {})
        if isinstance(drawings_raw, dict):
            for path_key, items_raw in drawings_raw.items():
                if not isinstance(items_raw, list):
                    continue
                items = [DrawingItem.from_dict(item) for item in items_raw if isinstance(item, dict)]
                items = [item for item in items if item.points]
                self._merge_drawings_into(self.drawings_by_path, canonical_image_key(str(path_key)), items)

        selected = data.get("selected_img_dirs", [])
        if isinstance(selected, list):
            self.selected_img_dirs = {str(p) for p in selected}
            self._pending_session_selected_img_dirs = set(self.selected_img_dirs)

        preview_max = int(data.get("preview_max_side", DEFAULT_PREVIEW_MAX_SIDE))
        preview_max = max(self.spin_preview_max.minimum(), min(self.spin_preview_max.maximum(), preview_max))
        self.spin_preview_max.setValue(preview_max)
        self.image_cache.set_preview_max_side(preview_max)

        preload_radius = int(data.get("preload_radius", DEFAULT_PRELOAD_RADIUS))
        preload_radius = max(self.spin_preload_radius.minimum(), min(self.spin_preload_radius.maximum(), preload_radius))
        self.spin_preload_radius.setValue(preload_radius)

        self.chk_global_preload.setChecked(bool(data.get("global_preload", True)))
        self.chk_global_preserve.setChecked(bool(data.get("global_preserve", True)))

        recent = data.get("recent_sessions", [])
        if isinstance(recent, list):
            for session_path in reversed([str(p) for p in recent if str(p).strip()]):
                if Path(session_path).exists():
                    self.add_recent_session(session_path)

        self._pending_detached_geometry_hex = str(data.get("detached_window_geometry", "") or "")
        if restore_geometry:
            main_geometry = str(data.get("main_window_geometry", "") or "")
            if main_geometry:
                try:
                    self.restoreGeometry(QByteArray.fromHex(main_geometry.encode("ascii")))
                except Exception:
                    pass

    def save_session_as(self) -> None:
        start_dir = str(Path(self.current_session_path).parent) if self.current_session_path else str(self.sessions_dir_path())
        Path(start_dir).mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Sauver session projet",
            str(Path(start_dir) / "session_png_comparator.pngcomp.json"),
            "Session PNG Comparator (*.pngcomp.json);;JSON (*.json)",
        )
        if not path:
            return
        self.save_session_file(path)

    def save_session_file(self, path: str, silent: bool = False) -> None:
        session_path = Path(path)
        data = self.collect_state_data()
        data["current_session_path"] = str(session_path)
        try:
            self.write_json_with_backup(session_path, data)
            self.current_session_path = str(session_path)
            self.add_recent_session(str(session_path))
            self._dirty_annotations = False
            self.save_state(silent=True)
            if not silent:
                self.statusBar().showMessage(f"Session sauvegardée : {session_path}", 6000)
        except Exception as exc:
            if not silent:
                QMessageBox.warning(self, "Session impossible", f"Impossible de sauvegarder la session :\n{exc}")

    def load_session_dialog(self) -> None:
        start_dir = str(Path(self.current_session_path).parent) if self.current_session_path else str(self.sessions_dir_path())
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Charger session projet",
            start_dir,
            "Session PNG Comparator (*.pngcomp.json *.json);;Tous les fichiers (*.*)",
        )
        if path:
            self.load_session_file(path)

    def load_session_file(self, path: str) -> None:
        session_path = Path(path)
        try:
            data = json.loads(session_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Format session invalide")
        except Exception as exc:
            QMessageBox.warning(self, "Session invalide", f"Impossible de charger la session :\n{exc}")
            return

        self.current_session_path = str(session_path)
        self.add_recent_session(str(session_path))
        self.apply_state_data(data, restore_geometry=True)
        self.statusBar().showMessage(f"Session chargée : {session_path}", 5000)

        root = self.root_edit.text().strip().strip('"')
        if root and self.refs() and Path(root).exists():
            self.run_scan()
        else:
            self.clear_tabs_only()
            self.update_validation_summary()

    def autosave_current_work(self) -> None:
        # Sauvegarde légère et silencieuse. Le fichier session actif reçoit aussi un backup avant écriture.
        self.save_state(silent=True)
        if self.current_session_path:
            self.save_session_file(self.current_session_path, silent=True)

    def update_refs_count_label(self) -> None:
        count = len(self.refs())
        self.refs_count_label.setText(f"{count} réf")

    def update_tree_count_label(self) -> None:
        active = len(self.selected_img_dirs)
        total = len(self.scan_result.img_dirs)
        self.tree_count_label.setText(f"{active}/{total} dossier IMG")

    def update_log_count_label(self) -> None:
        text = self.log_edit.toPlainText().strip()
        count = 0 if not text else len(text.splitlines())
        self.log_count_label.setText(f"{count} ligne(s)")

    def open_refs_popup(self) -> None:
        """Ouvre la sélection native des références.

        V2.93 : la page de démarrage est le sélecteur hybride officiel :
        collage texte + explorateur récursif alimentent la même liste dynamique.
        """
        self.show_start_help()

    def open_tree_popup(self) -> None:
        if self.tree_popup_dialog is None:
            self.tree_popup_dialog = WidgetPopupDialog(
                "Arbre des dossiers trouvés / exclusion",
                self.tree,
                self,
                "Décoche les dossiers IMG à exclure. Les onglets CAM et la liste active se mettent à jour automatiquement.",
            )
            self.tree_popup_dialog.resize(980, 720)
        self.tree_popup_dialog.show()
        self.tree_popup_dialog.raise_()
        self.tree_popup_dialog.activateWindow()

    def open_log_popup(self) -> None:
        if self.log_popup_dialog is None:
            self.log_popup_dialog = WidgetPopupDialog(
                "Log",
                self.log_edit,
                self,
                "Historique du scan et messages de diagnostic.",
            )
            self.log_popup_dialog.resize(900, 620)
        self.log_popup_dialog.show()
        self.log_popup_dialog.raise_()
        self.log_popup_dialog.activateWindow()

    def clear_active_table_holder(self) -> None:
        while self.active_table_holder_layout.count():
            item = self.active_table_holder_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)

    def update_active_image_table(self, _index: int = -1) -> None:
        if not hasattr(self, "active_table_holder_layout"):
            return
        current = self.tabs.currentWidget()
        # V2.70 : une palette dessin ouverte sur un ancien onglet gardait parfois
        # le focus/outil sur l'ancien viewer. On ferme les palettes au changement CAM.
        for tab in getattr(self, "cam_tabs", {}).values():
            if tab is not current and getattr(tab, "drawing_dialog", None) is not None:
                try:
                    tab.drawing_dialog.close()
                except Exception:
                    pass
                tab.drawing_dialog = None
        self.clear_active_table_holder()
        if isinstance(current, CamTab):
            self.active_table_label.setText(f"CAM{current.cam_number} - {len(current.records)} image(s) affichée(s)")
            current.top_controls_widget.setParent(None)
            current.table.setParent(None)
            self.active_table_holder_layout.addWidget(current.top_controls_widget, 0)
            self.active_table_holder_layout.addWidget(current.table, 1)
            current.top_controls_widget.show()
            current.table.show()
            record = current.current_record()
            if record is not None:
                self.on_cam_current_image_changed(current.cam_number, record.ref, record.file_name, current.current_index + 1, len(current.records))
            else:
                self.on_cam_current_image_changed(current.cam_number, "", "", 0, len(current.records))
            self.update_current_metadata_label()
        else:
            self.active_table_label.setText("Aucune CAM active")
            self.active_table_holder_layout.addWidget(self.active_table_placeholder, 1)
            self.active_table_placeholder.show()
            self.on_cam_current_image_changed(0, "", "", 0, 0)
            self.update_current_metadata_label()

    def on_cam_current_image_changed(self, cam_number: int, ref: str, file_name: str, index: int, total: int) -> None:
        sender = self.sender()
        if isinstance(sender, CamTab) and sender is not self.tabs.currentWidget():
            return

        cam_text = f"CAM{cam_number}" if cam_number else ""
        if self.detached_viewer_window is not None:
            self.detached_viewer_window.update_current_info(cam_text, ref, file_name, index, total)
        if cam_number and ref:
            self.active_table_label.setText(f"{cam_text} - {index}/{total} - {ref}")
        self.update_current_metadata_label()

    def active_cam_tab(self) -> Optional[CamTab]:
        current = self.tabs.currentWidget()
        return current if isinstance(current, CamTab) else None


    def active_record(self) -> Optional[ImageRecord]:
        tab = self.active_cam_tab()
        return tab.current_record() if tab is not None else None

    def update_current_metadata_label(self) -> None:
        record = self.active_record()
        if record is None:
            self.current_metadata_label.setText("Métadonnées : -")
            self.current_metadata_label.setToolTip("")
            return
        original_size = None
        preview_size = None
        tab = self.active_cam_tab()
        if tab is not None and getattr(tab.viewer, "current_path", None) == record.path and tab.viewer.has_image():
            original_size = (int(getattr(tab.viewer, "original_image_width", 0)), int(getattr(tab.viewer, "original_image_height", 0)))
            preview_size = (tab.viewer.pixmap.width(), tab.viewer.pixmap.height()) if tab.viewer.pixmap is not None else None
        summary = image_metadata_summary_fast(record.path, original_size=original_size, preview_size=preview_size)
        self.current_metadata_label.setText(f"Métadonnées : {summary}")
        self.current_metadata_label.setToolTip(record.path)

    def copy_to_clipboard(self, text: str, label: str) -> None:
        if not text:
            return
        QApplication.clipboard().setText(text)
        self.statusBar().showMessage(f"{label} copié", 2000)

    def copy_current_image_path(self) -> None:
        record = self.active_record()
        if record is None:
            return
        self.copy_to_clipboard(record.path, "Chemin image")

    def copy_current_file_name(self) -> None:
        record = self.active_record()
        if record is None:
            return
        self.copy_to_clipboard(record.file_name, "Nom fichier")

    def copy_current_reference(self) -> None:
        record = self.active_record()
        if record is None:
            return
        self.copy_to_clipboard(record.ref, "Référence")

    def open_current_image_folder(self) -> None:
        record = self.active_record()
        if record is None:
            return
        if not reveal_in_file_manager(record.path):
            QMessageBox.warning(self, "Ouverture impossible", f"Impossible d'ouvrir le dossier :\n{record.path}")

    def open_current_image_external(self) -> None:
        record = self.active_record()
        if record is None:
            return
        if not open_path_default(record.path):
            QMessageBox.warning(self, "Ouverture impossible", f"Impossible d'ouvrir l'image :\n{record.path}")

    def go_reference(self, direction: int) -> None:
        tab = self.active_cam_tab()
        if tab is None or not tab.records:
            return
        if tab.current_index < 0:
            tab.select_row(0 if direction >= 0 else len(tab.records) - 1)
            return

        current_ref = tab.records[tab.current_index].ref
        if direction > 0:
            for idx in range(tab.current_index + 1, len(tab.records)):
                if tab.records[idx].ref != current_ref:
                    tab.select_row(idx)
                    return
            self.statusBar().showMessage("Dernière référence affichée pour ce CAM/filtre", 2000)
        else:
            for idx in range(tab.current_index - 1, -1, -1):
                if tab.records[idx].ref != current_ref:
                    # Reculer au premier item du bloc de référence précédent pour être cohérent.
                    target_ref = tab.records[idx].ref
                    first_idx = idx
                    while first_idx - 1 >= 0 and tab.records[first_idx - 1].ref == target_ref:
                        first_idx -= 1
                    tab.select_row(first_idx)
                    return
            self.statusBar().showMessage("Première référence affichée pour ce CAM/filtre", 2000)

    def go_previous_reference(self) -> None:
        self.go_reference(-1)

    def go_next_reference(self) -> None:
        self.go_reference(1)



    def _make_annotation_snapshot(self, cam: int, path: str, row: int, annotation: Annotation) -> dict:
        return {
            "cam": int(cam),
            "path": str(path),
            "row": int(row),
            "annotation": Annotation(annotation.marked, normalize_status(annotation.status), annotation.comment).to_dict(),
        }

    def _current_annotation_snapshot_for(self, cam: int, path: str, row: int = -1) -> dict:
        ann = self.annotations.get(path, Annotation())
        return self._make_annotation_snapshot(cam, path, row, ann)

    def push_annotation_undo_snapshot(self, cam: int, path: str, row: int, annotation_data: object) -> None:
        annotation = Annotation.from_dict(annotation_data if isinstance(annotation_data, dict) else {})
        self.modification_undo_stack.append(self._make_annotation_snapshot(cam, path, row, annotation))
        self.modification_undo_stack = self.modification_undo_stack[-80:]
        self.modification_redo_stack.clear()

    def push_current_modification_undo(self, tab: Optional[CamTab] = None) -> None:
        tab = tab or self.active_cam_tab()
        if tab is None:
            return
        record = tab.current_record()
        if record is None:
            return
        self.modification_undo_stack.append(self._current_annotation_snapshot_for(tab.cam_number, record.path, tab.current_index))
        self.modification_undo_stack = self.modification_undo_stack[-80:]
        self.modification_redo_stack.clear()

    def _restore_modification_snapshot(self, snapshot: dict) -> bool:
        cam = int(snapshot.get("cam", 0) or 0)
        path = str(snapshot.get("path", ""))
        row = int(snapshot.get("row", -1) or -1)
        annotation = Annotation.from_dict(snapshot.get("annotation", {}) if isinstance(snapshot.get("annotation", {}), dict) else {})
        tab = self.cam_tabs.get(cam) or self.active_cam_tab()
        if tab is None:
            self.statusBar().showMessage("Impossible : CAM introuvable", 3500)
            return False
        if tab is not self.active_cam_tab():
            tab_index = self.tabs.indexOf(tab)
            if tab_index >= 0:
                self.tabs.setCurrentIndex(tab_index)
        return tab.restore_annotation_snapshot(path, annotation, row)

    def undo_last_modification(self) -> None:
        if not self.modification_undo_stack:
            self.statusBar().showMessage("Aucune modification à annuler", 2500)
            return
        snapshot = self.modification_undo_stack.pop()
        cam = int(snapshot.get("cam", 0) or 0)
        path = str(snapshot.get("path", ""))
        row = int(snapshot.get("row", -1) or -1)
        self.modification_redo_stack.append(self._current_annotation_snapshot_for(cam, path, row))
        self.modification_redo_stack = self.modification_redo_stack[-80:]
        if self._restore_modification_snapshot(snapshot):
            self.update_validation_summary()
            self.save_state(silent=True)
            self.statusBar().showMessage("Dernière modification annulée", 2500)

    def redo_last_modification(self) -> None:
        if not self.modification_redo_stack:
            self.statusBar().showMessage("Aucune modification suivante", 2500)
            return
        snapshot = self.modification_redo_stack.pop()
        cam = int(snapshot.get("cam", 0) or 0)
        path = str(snapshot.get("path", ""))
        row = int(snapshot.get("row", -1) or -1)
        self.modification_undo_stack.append(self._current_annotation_snapshot_for(cam, path, row))
        self.modification_undo_stack = self.modification_undo_stack[-80:]
        if self._restore_modification_snapshot(snapshot):
            self.update_validation_summary()
            self.save_state(silent=True)
            self.statusBar().showMessage("Modification rétablie", 2500)

    def mark_current_done_next(self) -> None:
        tab = self.active_cam_tab()
        if tab is None:
            return
        self.push_current_modification_undo(tab)
        tab.set_current_status_and_comment("Terminé", "", go_next=True)
        self.update_validation_summary()
        self.save_state(silent=True)

    def mark_current_fix_next(self) -> None:
        tab = self.active_cam_tab()
        if tab is None:
            return
        record = tab.current_record()
        if record is None:
            return
        ann = self.annotations.get(record.path, Annotation())
        comment = ann.comment.strip()
        table_row = tab.table_row_for_record_index(tab.current_index) if tab.current_index >= 0 else -1
        if not comment:
            item = tab.table.item(table_row, 4) if table_row >= 0 else None
            if item is not None:
                comment = item.text().strip()
        if not comment:
            if table_row >= 0:
                tab.table.setCurrentCell(table_row, 4)
                item = tab.table.item(table_row, 4)
                if item is not None:
                    tab.table.editItem(item)
            QMessageBox.warning(
                self,
                "Commentaire requis",
                "Ajoute d'abord un commentaire dans la ligne active avant de marquer l'image À corriger.",
            )
            return
        self.push_current_modification_undo(tab)
        tab.set_current_status_and_comment("À corriger", "", go_next=True)
        self.update_validation_summary()
        self.save_state(silent=True)

    def on_status_filter_changed(self, value: str) -> None:
        self.global_status_filter = value or "Tous"
        for tab in self.cam_tabs.values():
            tab.set_status_filter(self.global_status_filter)
        self.update_active_image_table()
        self.update_validation_summary()
        self.save_state(silent=True)

    def on_expected_cams_changed(self) -> None:
        self.update_validation_summary()
        if self.scan_result.records:
            self.print_scan_summary(short=True)
        self.save_state(silent=True)

    def update_validation_summary(self) -> None:
        records = self.filtered_records()
        total = len(records)
        done = 0
        fix = 0
        unverified = 0
        for r in records:
            ann = self.annotations.get(r.path, Annotation())
            status = normalize_status(ann.status)
            if status == "Terminé":
                done += 1
            elif status == "À corriger":
                fix += 1
            elif ann.marked or ann.comment:
                # Image annotée mais sans statut final : on la compte encore comme non terminée.
                unverified += 1
            else:
                unverified += 1

        progress = int(round((done / total) * 100)) if total else 0
        self.validation_progress.setValue(progress)
        self.validation_progress.setFormat(f"Validation : {progress}%")
        self.validation_stats_label.setText(
            f"Images : {total} | Terminé : {done} | À corriger : {fix} | À contrôler : {unverified}"
        )

    def expected_cam_numbers(self) -> List[int]:
        count = self.spin_expected_cams.value() if hasattr(self, "spin_expected_cams") else 0
        if count <= 0:
            return []
        return list(range(1, count + 1))

    def missing_cam_map(self) -> Dict[str, List[int]]:
        expected = self.expected_cam_numbers()
        if not expected:
            return {}
        records = self.filtered_records()
        by_ref: Dict[str, Set[int]] = {ref: set() for ref in self.refs()}
        for r in records:
            by_ref.setdefault(r.ref, set()).add(r.cam_number)
        missing: Dict[str, List[int]] = {}
        for ref in self.refs():
            missing_for_ref = [cam for cam in expected if cam not in by_ref.get(ref, set())]
            if missing_for_ref:
                missing[ref] = missing_for_ref
        return missing

    def show_missing_cams(self) -> None:
        expected = self.expected_cam_numbers()
        if not expected:
            QMessageBox.information(self, "CAM attendues", "Renseigne un nombre de CAM attendues supérieur à 0.")
            return
        missing = self.missing_cam_map()
        if not missing:
            QMessageBox.information(self, "CAM manquantes", f"Aucune CAM manquante détectée pour CAM1 à CAM{expected[-1]}.")
            return

        lines = [f"CAM attendues : CAM1 à CAM{expected[-1]}", "", "Références avec CAM manquantes :"]
        for ref, cams in missing.items():
            lines.append(f"- {ref} : " + ", ".join(f"CAM{cam}" for cam in cams))
        QMessageBox.warning(self, "CAM manquantes", "\n".join(lines))

    def toggle_detached_viewer(self) -> None:
        if self.viewer_detached:
            self.reattach_viewer()
        else:
            self.detach_viewer()

    def detach_viewer(self) -> None:
        if self.viewer_detached:
            if self.detached_viewer_window is not None:
                self.detached_viewer_window.show()
                self.detached_viewer_window.raise_()
                self.detached_viewer_window.activateWindow()
            return

        if self.detached_viewer_window is None:
            self.detached_viewer_window = DetachedViewerWindow(self)
            self.detached_viewer_window.reattach_requested.connect(self.reattach_viewer)
            if self._pending_detached_geometry_hex:
                try:
                    self.detached_viewer_window.restoreGeometry(QByteArray.fromHex(self._pending_detached_geometry_hex.encode("ascii")))
                except Exception:
                    pass

        self.tabs_host_layout.removeWidget(self.tabs)
        self.tabs.setParent(None)
        self.detached_viewer_window.set_tabs_widget(self.tabs)
        self.viewer_detached = True
        self.btn_detach_tabs.setText("Réattacher viewer")
        for tab in self.cam_tabs.values():
            if hasattr(tab, "btn_detach_viewer"):
                tab.btn_detach_viewer.setText("Réattacher viewer")
        self.tabs_placeholder.hide()
        self.tabs_host.hide()
        if hasattr(self, "main_splitter"):
            self.main_splitter.setSizes([1, 0])

        current = self.tabs.currentWidget()
        if isinstance(current, CamTab):
            record = current.current_record()
            if record is not None:
                self.detached_viewer_window.update_current_info(f"CAM{current.cam_number}", record.ref, record.file_name, current.current_index + 1, len(current.records))

        self.detached_viewer_window.show()
        self.detached_viewer_window.raise_()
        self.detached_viewer_window.activateWindow()
        self.statusBar().showMessage("Viewer détaché dans une fenêtre flottante", 2500)

    def reattach_viewer(self) -> None:
        if not self.viewer_detached:
            return
        if self.detached_viewer_window is not None:
            self.detached_viewer_window.take_tabs_widget()
        self.tabs.setParent(None)
        self.tabs_host_layout.insertWidget(0, self.tabs, 1)
        self.tabs.show()
        self.tabs_host.show()
        if hasattr(self, "main_splitter"):
            self.main_splitter.setSizes([680, 870])
        self.viewer_detached = False
        self.btn_detach_tabs.setText("Détacher viewer")
        for tab in self.cam_tabs.values():
            if hasattr(tab, "btn_detach_viewer"):
                tab.btn_detach_viewer.setText("Détacher viewer")
        self.tabs_placeholder.hide()
        if self.detached_viewer_window is not None and not self._app_closing:
            self.detached_viewer_window.hide()
        self.statusBar().showMessage("Viewer réattaché à l'interface principale", 2500)

    def browse_root(self) -> None:
        start = self.root_edit.text().strip() or str(Path.home())
        path = QFileDialog.getExistingDirectory(self, "Choisir le chemin racine", start)
        if path:
            self.root_edit.setText(path)

    def refs(self) -> List[str]:
        lines = self.refs_edit.toPlainText().splitlines()
        refs: List[str] = []
        for line in lines:
            value = line.strip()
            if not value:
                continue
            parts = re.split(r"[;,\t]+", value)
            for part in parts:
                part = part.strip()
                if part and part not in refs:
                    refs.append(part)
        return refs

    def run_scan(self) -> bool:
        root_text = self.root_edit.text().strip().strip('"')
        refs = self.refs()

        if not root_text:
            QMessageBox.warning(self, "Chemin manquant", "Renseigne un chemin racine de recherche.")
            return False
        if not refs:
            QMessageBox.warning(self, "Liste manquante", "Colle au moins une référence dans la liste.")
            return False

        root = Path(root_text)
        if not root.exists() or not root.is_dir():
            QMessageBox.warning(self, "Chemin invalide", f"Le chemin n'existe pas ou n'est pas un dossier :\n{root}")
            return False

        self.clear_tabs_only()
        self.image_cache.clear()
        self.log_edit.clear()
        self.log(f"Scan lancé : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.log(f"Chemin racine : {root}")
        self.log(f"Références : {len(refs)}")

        recursive = self.chk_recursive_refs.isChecked()
        main_only = self.chk_main_only.isChecked()
        self.log(f"Mode recherche sous-dossiers : {'activé' if recursive else 'désactivé'}")
        self.log(f"Scan _MAIN_ only : {'activé' if main_only else 'désactivé'}")
        self.log(f"Qualité viewer max avant scan : {self.spin_preview_max.value()} px")

        progress = QProgressDialog("Scan en cours...", "Annuler", 0, 0, self)
        progress.setWindowModality(Qt.ApplicationModal)
        progress.setMinimumDuration(250)
        progress.setMinimumWidth(720)
        progress.show()
        QApplication.processEvents()

        progress_state = {"last_logged": 0}

        def on_scan_progress(path_text: str, checked_count: int) -> bool:
            progress.setLabelText(
                "Scan en cours...\n"
                f"Dossiers vérifiés : {checked_count}\n"
                f"Actuel : {path_text}"
            )
            if checked_count - progress_state["last_logged"] >= 100:
                progress_state["last_logged"] = checked_count
                self.log(f"Recherche sous-dossiers : {checked_count} dossiers vérifiés | {path_text}")
            QApplication.processEvents()
            return not progress.wasCanceled()

        try:
            scanner = ImageScanner(
                root=root,
                refs=refs,
                recursive_ref_search=recursive,
                contains_mode=False,
                main_only=main_only,
                progress_callback=on_scan_progress if recursive else None,
            )
            result = scanner.scan()
        finally:
            progress.close()

        if getattr(result, "cancelled", False):
            self.log("Scan annulé par l'utilisateur.")
            self.scan_result = result
            self.print_scan_summary()
            return False
        if getattr(result, "checked_dirs", 0):
            self.log(f"Recherche sous-dossiers terminée : {result.checked_dirs} dossiers vérifiés.")

        self.scan_result = result
        self.relink_drawings_to_scan_records()
        all_img_dirs = {str(p) for p in result.img_dirs}
        pending_selected = getattr(self, "_pending_session_selected_img_dirs", None)
        if pending_selected:
            restored = {str(p) for p in pending_selected if str(p) in all_img_dirs}
            self.selected_img_dirs = restored if restored else all_img_dirs
            self._pending_session_selected_img_dirs = None
        else:
            self.selected_img_dirs = all_img_dirs

        self.build_tree()
        self.rebuild_tabs()
        self.print_scan_summary()
        self.save_state(silent=True)
        self.close_startup_dialog_after_scan()
        self.show_cam_check_after_scan()
        return True

    def show_cam_check_after_scan(self) -> None:
        """Affiche un bilan informatif des CAM attendues juste après le scan."""
        expected = self.expected_cam_numbers() if hasattr(self, "spin_expected_cams") else []
        if not expected:
            return

        missing = self.missing_cam_map()
        if missing:
            self.log("Bilan CAM attendues après scan : CAM manquantes détectées.")
            lines = [f"CAM attendues : CAM1 à CAM{expected[-1]}", "", "Références avec CAM manquantes :"]
            for ref, cams in missing.items():
                cams_text = ", ".join(f"CAM{cam}" for cam in cams)
                lines.append(f"- {ref} : {cams_text}")
                self.log(f"CAM manquantes - {ref} : {cams_text}")
            QMessageBox.warning(self, "CAM manquantes", "\n".join(lines))
            return

        refs_count = len(self.refs())
        self.log(f"Bilan CAM attendues après scan : tout trouvé pour CAM1 à CAM{expected[-1]}.")
        QMessageBox.information(
            self,
            "CAM attendues",
            f"Toutes les CAM attendues ont été trouvées.\n\nCAM contrôlées : CAM1 à CAM{expected[-1]}\nRéférences contrôlées : {refs_count}",
        )

    def build_tree(self) -> None:
        self._building_tree = True
        self.tree.clear()

        for ref in self.refs():
            ref_item = QTreeWidgetItem([ref, ""])
            ref_item.setFlags(ref_item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
            ref_item.setCheckState(0, Qt.Checked)
            ref_item.setData(0, Qt.UserRole, {"type": "ref", "ref": ref})
            self.tree.addTopLevelItem(ref_item)

            ref_dirs = self.scan_result.ref_dirs.get(ref, [])
            if not ref_dirs:
                missing_item = QTreeWidgetItem(["Référence non trouvée", "0"])
                missing_item.setFlags(missing_item.flags() & ~Qt.ItemIsUserCheckable)
                missing_item.setForeground(0, QColor("red"))
                ref_item.addChild(missing_item)
                continue

            img_dirs = self.scan_result.img_dirs_by_ref.get(ref, [])
            if not img_dirs:
                no_img_item = QTreeWidgetItem(["Aucun dossier IMG* trouvé", "0"])
                no_img_item.setFlags(no_img_item.flags() & ~Qt.ItemIsUserCheckable)
                no_img_item.setForeground(0, QColor("orange"))
                ref_item.addChild(no_img_item)
                continue

            for img_dir in img_dirs:
                count = sum(1 for r in self.scan_result.records if r.ref == ref and r.img_dir == str(img_dir))
                label = str(img_dir)
                try:
                    label = str(img_dir.relative_to(Path(self.root_edit.text().strip().strip('"'))))
                except Exception:
                    pass

                child = QTreeWidgetItem([label, str(count)])
                child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
                child.setCheckState(0, Qt.Checked if str(img_dir) in self.selected_img_dirs else Qt.Unchecked)
                child.setToolTip(0, str(img_dir))
                child.setData(0, Qt.UserRole, {"type": "img_dir", "path": str(img_dir)})
                ref_item.addChild(child)

            ref_item.setExpanded(True)

        self.tree.resizeColumnToContents(1)
        self._building_tree = False
        self.update_tree_count_label()

    def on_tree_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._building_tree or column != 0:
            return

        data = item.data(0, Qt.UserRole)
        if isinstance(data, dict) and data.get("type") == "img_dir":
            path = data.get("path")
            if path:
                if item.checkState(0) == Qt.Checked:
                    self.selected_img_dirs.add(path)
                else:
                    self.selected_img_dirs.discard(path)
                self.rebuild_tabs()
                self.update_tree_count_label()
                self.print_scan_summary(short=True)
                self.save_state(silent=True)
        elif isinstance(data, dict) and data.get("type") == "ref":
            self.refresh_selected_dirs_from_tree()
            self.rebuild_tabs()
            self.update_tree_count_label()
            self.print_scan_summary(short=True)
            self.save_state(silent=True)

    def refresh_selected_dirs_from_tree(self) -> None:
        selected: Set[str] = set()
        for i in range(self.tree.topLevelItemCount()):
            ref_item = self.tree.topLevelItem(i)
            for j in range(ref_item.childCount()):
                child = ref_item.child(j)
                data = child.data(0, Qt.UserRole)
                if isinstance(data, dict) and data.get("type") == "img_dir" and child.checkState(0) == Qt.Checked:
                    selected.add(str(data.get("path")))
        self.selected_img_dirs = selected

    def filtered_records(self) -> List[ImageRecord]:
        return [r for r in self.scan_result.records if r.img_dir in self.selected_img_dirs]

    def clear_tabs_only(self) -> None:
        if hasattr(self, "active_table_holder_layout"):
            self.clear_active_table_holder()
            self.active_table_holder_layout.addWidget(self.active_table_placeholder, 1)
            self.active_table_placeholder.show()
            self.active_table_label.setText("Aucune CAM active")
        for tab in self.cam_tabs.values():
            tab.cleanup()
        self.tabs.clear()
        self.cam_tabs.clear()
        if hasattr(self, "validation_progress"):
            self.update_validation_summary()

    def rebuild_tabs(self) -> None:
        current_cam = None
        if self.tabs.currentWidget() is not None:
            for cam, tab in self.cam_tabs.items():
                if tab is self.tabs.currentWidget():
                    current_cam = cam
                    break

        # V2.70 : les dessins sont déjà dans self.drawings_by_path, partagé avec tous les onglets.
        # On ne les reconvertit plus au rebuild pour éviter toute perte ou duplication.

        self.clear_tabs_only()

        records = self.filtered_records()
        cams = sorted({r.cam_number for r in records})
        if not cams:
            empty = QLabel("Aucune image CAM trouvée avec la sélection actuelle.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("font-size: 18px; color: white;")
            self.tabs.addTab(empty, "Aucune CAM")
            self.update_active_image_table()
            self.update_validation_summary()
            return

        for cam in cams:
            cam_records = [r for r in records if r.cam_number == cam]
            tab = CamTab(
                cam_number=cam,
                records=cam_records,
                annotations=self.annotations,
                bg_colors=self.bg_colors,
                active_bg_index=self.active_bg_index,
                cache=self.image_cache,
                preload_radius=self.spin_preload_radius.value(),
                preload_enabled=self.chk_global_preload.isChecked(),
                preserve_view_enabled=self.chk_global_preserve.isChecked(),
                status_filter=self.global_status_filter,
            )
            tab.shortcut_provider = self
            tab.annotation_about_to_change.connect(self.push_annotation_undo_snapshot)
            tab.annotation_changed.connect(self.on_annotation_changed)
            tab.request_color_select.connect(self.on_bg_selected)
            tab.request_color_edit.connect(self.edit_bg_color)
            tab.request_status_message.connect(lambda msg: self.statusBar().showMessage(msg, 1800))
            tab.current_image_changed.connect(self.on_cam_current_image_changed)
            tab.request_detach_viewer.connect(self.toggle_detached_viewer)
            tab.viewer.drawing_changed.connect(self.on_drawing_changed)
            tab.compare_viewer.drawing_changed.connect(self.on_drawing_changed)
            self.apply_pending_drawings_to_tab(tab)
            self.cam_tabs[cam] = tab
            self.tabs.addTab(tab, f"CAM{cam} ({len(cam_records)})")

        if current_cam in self.cam_tabs:
            index = list(self.cam_tabs).index(current_cam)
            self.tabs.setCurrentIndex(index)
        self.update_active_image_table()
        self.update_validation_summary()

    def on_bg_selected(self, index: int) -> None:
        self.bg_colors[1] = (0, 0, 0)
        self.active_bg_index = index
        for tab in self.cam_tabs.values():
            tab.set_background_colors(self.bg_colors, self.active_bg_index)
        self.save_state(silent=True)

    def edit_bg_color(self, index: int) -> None:
        if index != 2:
            # Fond 1 et Fond 2 restent fixes. Pas de popup au clic droit.
            return
        current = tuple_to_color(self.bg_colors[index])
        color = QColorDialog.getColor(current, self, "Modifier Fond 3 custom")
        if not color.isValid():
            return
        self.bg_colors[1] = (0, 0, 0)
        self.bg_colors[2] = color_to_tuple(color)
        self.active_bg_index = 2
        for tab in self.cam_tabs.values():
            tab.set_background_colors(self.bg_colors, self.active_bg_index)
        self.save_state(silent=True)

    def on_annotation_changed(self) -> None:
        self._dirty_annotations = True
        self.update_validation_summary()
        self.statusBar().showMessage("Annotations modifiées - pense à sauver la session", 3000)

    def on_drawing_changed(self) -> None:
        self._dirty_annotations = True
        self.statusBar().showMessage("Dessins modifiés - sauvegarde auto en cours", 2200)
        if hasattr(self, "drawing_save_timer"):
            self.drawing_save_timer.start()

    def on_preview_size_changed(self, value: int) -> None:
        self.image_cache.set_preview_max_side(value)
        self.statusBar().showMessage("Taille max affichée modifiée : cache vidé", 3000)
        self.save_state(silent=True)

    def on_preload_radius_changed(self, value: int) -> None:
        for tab in self.cam_tabs.values():
            tab.set_preload_radius(value)
        self.save_state(silent=True)

    def on_global_preload_changed(self, enabled: bool) -> None:
        for tab in self.cam_tabs.values():
            tab.chk_preload.setChecked(enabled)
        self.save_state(silent=True)

    def on_global_preserve_changed(self, enabled: bool) -> None:
        for tab in self.cam_tabs.values():
            tab.set_preserve_view_enabled(enabled)
        self.save_state(silent=True)

    def on_cache_info_changed(self, preview_count: int, pending_count: int) -> None:
        self.cache_label.setText(f"Cache : {preview_count} image(s) | {pending_count} en attente")
        if pending_count > 0:
            self.statusBar().showMessage(f"Chargement image en arrière-plan : {pending_count} en attente", 1200)

    def clear_cache(self) -> None:
        self.image_cache.clear()
        self.statusBar().showMessage("Cache images vidé", 2500)

    def print_scan_summary(self, short: bool = False) -> None:
        records = self.filtered_records()
        cams = sorted({r.cam_number for r in records})
        img_dirs_count = len(self.selected_img_dirs)
        total_dirs = len(self.scan_result.img_dirs)

        missing = self.missing_cam_map() if hasattr(self, "spin_expected_cams") else {}
        missing_text = f" | Réfs avec CAM manquantes : {len(missing)}" if missing else ""
        self.summary_label.setText(
            f"Images actives : {len(records)} | CAM : {', '.join('CAM' + str(c) for c in cams) if cams else 'aucune'} | "
            f"Dossiers IMG actifs : {img_dirs_count}/{total_dirs}{missing_text}"
        )
        self.update_tree_count_label()
        self.update_validation_summary()

        if short:
            return

        self.log("--- Résumé scan ---")
        self.log(f"Dossiers références trouvés : {sum(len(v) for v in self.scan_result.ref_dirs.values())}")
        self.log(f"Dossiers IMG* trouvés : {len(self.scan_result.img_dirs)}")
        self.log(f"Images PNG avec CAMn : {len(self.scan_result.records)}")
        self.log(f"CAM détectées : {', '.join('CAM' + str(c) for c in self.scan_result.cams) if self.scan_result.cams else 'aucune'}")
        expected = self.expected_cam_numbers() if hasattr(self, "spin_expected_cams") else []
        if expected:
            missing = self.missing_cam_map()
            self.log(f"CAM attendues : CAM1 à CAM{expected[-1]}")
            if missing:
                self.log("CAM manquantes détectées :")
                for ref, cams_missing in missing.items():
                    self.log(f"  - {ref} : " + ", ".join(f"CAM{cam}" for cam in cams_missing))
            else:
                self.log("Aucune CAM manquante détectée.")

        if self.scan_result.missing_refs:
            self.log("Références non trouvées :")
            for ref in self.scan_result.missing_refs:
                self.log(f"  - {ref}")

        for warning in self.scan_result.warnings:
            self.log(f"Attention : {warning}")


    def log(self, message: str) -> None:
        self.log_edit.append(message)
        self.update_log_count_label()

    def show_data_locations(self) -> None:
        """Explique où le logiciel écrit ses fichiers persistants."""
        try:
            screenshots_dir = self.exports_dir_path() / "screenshots"
        except Exception:
            screenshots_dir = APP_ROOT_DIR / "exports" / "screenshots"
        lines = [
            "PNG Comparator écrit volontairement quelques fichiers pour retrouver ton dernier état.",
            "",
            f"Dossier du script / EXE : {APP_INSTALL_DIR}",
            f"Dossier data actif : {APP_ROOT_DIR}",
            "",
            f"État auto chargé au démarrage : {self.state_file_path()}",
            f"Pointeur d'état de secours : {STATE_FILE}",
            f"Sessions : {self.sessions_dir_path()}",
            f"Sessions récentes : {self.session_recents_file_path()}",
            f"Autosave / état : {self.autosave_dir_path()}",
            f"Backups : {self.backups_dir_path()}",
            f"Exports : {self.exports_dir_path()}",
            f"Screenshots : {screenshots_dir}",
            "",
            "Si le dossier du programme n'est pas writable, les données vont dans AppData/PNGComparator.",
            "En EXE onefile, _MEIxxxxx est seulement un dossier temporaire PyInstaller : l'app ne doit pas y sauvegarder tes données.",
        ]
        QMessageBox.information(self, "Emplacements des données", "\n".join(lines))

    def show_about(self) -> None:
        QMessageBox.information(
            self,
            "À propos",
            "PNG Comparator V3.01 ALPHA CLEANUP\n\n"
            "Outil de contrôle/comparaison de rendus PNG par références, dossiers IMG* et CAM dynamiques.\n\n"
            "Version pré-alpha audit/cleanup : navigation cohérente avec le tri, filtres optimisés et nettoyage code mort.\n\n"
            "Les raccourcis ne sont plus listés ici : ils sont consultables et modifiables via le menu Raccourcis clavier.",
        )

    def load_state(self) -> None:
        candidates = []
        try:
            candidates.append(self.state_file_path())
        except Exception:
            pass
        candidates.extend([STATE_FILE, LEGACY_STATE_FILE])
        path = next((p for p in candidates if p.exists()), candidates[0] if candidates else STATE_FILE)
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return
        except Exception:
            return

        self.current_session_path = str(data.get("current_session_path", "") or "")
        recent = data.get("recent_sessions", [])
        if isinstance(recent, list):
            self.recent_sessions = [str(p) for p in recent if str(p).strip() and Path(str(p)).exists()][:MAX_RECENT_SESSIONS]
            self.update_recent_sessions_menu()
        self.apply_state_data(data, restore_geometry=True)

    def save_state(self, silent: bool = False) -> None:
        data = self.collect_state_data()
        data["current_session_path"] = self.current_session_path or ""
        data["recent_sessions"] = self.recent_sessions
        try:
            state_path = self.state_file_path()
            self.write_json_with_backup(state_path, data)
            # On garde aussi un petit pointeur d'état à côté de l'application.
            # Ainsi, si tu déplaces le chemin autosave, le prochain lancement peut
            # quand même retrouver tes chemins configurés.
            try:
                if state_path.resolve() != STATE_FILE.resolve():
                    self.write_json_with_backup(STATE_FILE, data)
            except Exception:
                pass
            self._dirty_annotations = False
            if not silent:
                self.statusBar().showMessage(f"Sauvegardé : {state_path}", 5000)
        except Exception as exc:
            if not silent:
                QMessageBox.warning(self, "Sauvegarde impossible", f"Impossible de sauvegarder l'état :\n{exc}")

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._dirty_annotations:
            reply = QMessageBox.question(
                self,
                "Annotations non sauvegardées",
                "Des annotations ont été modifiées. Sauvegarder avant de quitter ?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Yes,
            )
            if reply == QMessageBox.Cancel:
                event.ignore()
                return
            if reply == QMessageBox.Yes:
                self.save_state(silent=True)
        else:
            self.save_state(silent=True)

        if self.current_session_path:
            self.save_session_file(self.current_session_path, silent=True)

        self._app_closing = True
        if self.startup_dialog is not None:
            self.startup_dialog.hide()
        if self.detached_viewer_window is not None:
            self.detached_viewer_window.suppress_reattach = True
            self.detached_viewer_window.hide()

        self.clear_tabs_only()
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)

    if "Fusion" in QStyleFactory.keys():
        app.setStyle("Fusion")

    app.setStyleSheet(CHECKBOX_VISUAL_STYLE)

    window = MainWindow()
    # V2.97 : lancement direct de la fenêtre principale en plein espace de travail.
    # showMaximized garde la barre de titre/menu Windows, contrairement au vrai fullscreen.
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

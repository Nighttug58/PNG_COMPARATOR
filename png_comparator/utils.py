from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from PySide6.QtCore import QUrl
from PySide6.QtGui import QColor, QDesktopServices


def canonical_image_key(path: str) -> str:
    """Clé stable pour relier dessins/sessions aux images sans lecture disque."""
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


def image_border_color_for_background(color: QColor) -> QColor:
    """Couleur de bordure toujours visible sur le fond du viewer."""
    red, green, blue = color.red(), color.green(), color.blue()
    if red > 235 and green > 235 and blue > 235:
        return QColor(0, 0, 0)
    if red < 20 and green < 20 and blue < 20:
        return QColor(255, 255, 255)
    return QColor(255 - red, 255 - green, 255 - blue)


def wildcard_text_match(pattern: str, *values: str) -> bool:
    """Filtre custom simple : * agit comme joker sur le texte fourni."""
    raw = pattern.strip()
    if not raw:
        return True

    haystack = " | ".join(str(value) for value in values if value).upper()
    parts = [part.strip() for part in re.split(r"[;,\n]+", raw) if part.strip()]
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
    """Métadonnées rapides sans relire lourdement le PNG dans le thread UI."""
    file_path = Path(path)
    try:
        stat = file_path.stat()
        size_text = human_file_size(int(stat.st_size))
        modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        size_text = "-"
        modified = "-"

    original_w, original_h = original_size or (0, 0)
    preview_w, preview_h = preview_size or (0, 0)
    if original_w > 0 and original_h > 0:
        dim_text = f"Dimensions : {original_w} × {original_h} px"
    else:
        dim_text = "Dimensions : en attente du chargement"

    preview_text = (
        f"Aperçu : {preview_w} × {preview_h} px"
        if preview_w > 0 and preview_h > 0
        else "Aperçu : -"
    )
    return f"{dim_text} | {preview_text} | Poids : {size_text} | Modifié : {modified}"


def open_path_default(path: str) -> bool:
    """Ouvre un fichier/dossier avec l'application par défaut du système."""
    try:
        file_path = Path(path)
        if sys.platform.startswith("win") and hasattr(os, "startfile"):
            os.startfile(str(file_path))  # type: ignore[attr-defined]
            return True
        return QDesktopServices.openUrl(QUrl.fromLocalFile(str(file_path)))
    except Exception:
        return False


def reveal_in_file_manager(path: str) -> bool:
    """Ouvre le dossier de l'image, avec sélection du fichier sous Windows."""
    try:
        file_path = Path(path)
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", "/select,", str(file_path)])
            return True
        return QDesktopServices.openUrl(QUrl.fromLocalFile(str(file_path.parent)))
    except Exception:
        return False

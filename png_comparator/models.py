from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class ImageRecord:
    """Une image PNG détectée par le scanner."""

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
class ViewerState:
    """État de caméra partagé entre viewers comparés."""

    fit_mode: bool = True
    scale: float = 1.0
    center_norm_x: float = 0.5
    center_norm_y: float = 0.5
    display_width: int = 0
    display_height: int = 0


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
        return sorted(set(all_dirs), key=lambda path: str(path).lower())

    @property
    def cams(self) -> List[int]:
        return sorted({record.cam_number for record in self.records})

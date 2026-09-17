from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple


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
        if self.erased_items:
            data["erased_items"] = [item.to_dict() for item in self.erased_items]
        return data

    @staticmethod
    def from_dict(data: dict) -> "DrawingItem":
        points_raw = data.get("points", []) if isinstance(data, dict) else []
        points: List[Tuple[float, float]] = []
        if isinstance(points_raw, list):
            for point in points_raw:
                try:
                    if isinstance(point, (list, tuple)) and len(point) >= 2:
                        points.append((float(point[0]), float(point[1])))
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
            erased_items = [
                item
                for item in erased_items
                if item.kind in {"freehand", "line", "rect", "ellipse"} and item.points
            ]

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
        return sorted(set(all_dirs), key=lambda path: str(path).lower())

    @property
    def cams(self) -> List[int]:
        return sorted({record.cam_number for record in self.records})

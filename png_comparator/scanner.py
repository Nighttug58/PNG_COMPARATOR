from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from .models import ImageRecord, ImageScanResult


CAM_RE = re.compile(r"CAM[\s_\-.]*(\d+)", re.IGNORECASE)
TOKEN_SPLIT_RE = re.compile(r"[\s_\-.()\[\]{}]+")


class ImageScanner:
    """Scan disque : références -> dossiers IMG* -> PNG contenant CAMn."""

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
        self.refs = [ref.strip() for ref in refs if ref.strip()]
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

            result.img_dirs_by_ref[ref] = sorted(set(img_dirs_for_ref), key=lambda path: str(path).lower())

        result.records.sort(
            key=lambda record: (
                record.cam_number,
                record.ref.lower(),
                record.file_name.lower(),
                record.path.lower(),
            )
        )
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
                with os.scandir(current) as iterator:
                    entries = list(iterator)
            except (PermissionError, OSError):
                continue

            dirs_to_add: List[Path] = []
            for entry in entries:
                try:
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                except (PermissionError, OSError):
                    continue
                if entry.name in self.SKIP_DIR_NAMES:
                    continue
                child = Path(entry.path)
                self.checked_dirs += 1
                if not self._notify_progress(child):
                    self.cancelled = True
                    return
                yield child
                dirs_to_add.append(child)

            dirs_to_add.sort(key=lambda path: path.name.lower(), reverse=True)
            stack.extend(dirs_to_add)

    def _find_reference_dirs_indexed(self) -> Dict[str, List[Path]]:
        result: Dict[str, List[Path]] = {ref: [] for ref in self.refs}
        refs_lower = {ref.lower(): ref for ref in self.refs}
        refs_pairs = [(ref, ref.lower()) for ref in self.refs]

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
            result[ref] = sorted(set(result[ref]), key=lambda path: str(path).lower())
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
            with os.scandir(self.root) as iterator:
                for entry in iterator:
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

        return sorted(candidates, key=lambda path: str(path).lower())

    def _find_img_dirs(self, ref_dir: Path) -> List[Path]:
        dirs: List[Path] = []
        for path in self._iter_dirs_fast(ref_dir):
            if self.cancelled:
                break
            if path.name.upper().startswith("IMG"):
                dirs.append(path)
        return sorted(set(dirs), key=lambda path: str(path).lower())

    @staticmethod
    def _find_pngs_in_dir(img_dir: Path) -> List[Path]:
        pngs: List[Path] = []
        try:
            for path in img_dir.iterdir():
                if path.is_file() and path.suffix.lower() == ".png":
                    pngs.append(path)
        except (PermissionError, OSError):
            pass
        return sorted(pngs, key=lambda path: path.name.lower())

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
    """Détecte les tags utiles situés après CAMn dans le nom de fichier."""
    match = CAM_RE.search(stem)
    if not match:
        return []

    suffix = stem[match.end():]
    after_tokens = [
        token.strip().upper()
        for token in TOKEN_SPLIT_RE.split(suffix.lstrip(" _-.()[]{}"))
        if token.strip()
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

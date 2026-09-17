from __future__ import annotations

from collections import OrderedDict
from typing import Optional, Sequence, Set, Tuple

from PySide6.QtCore import QObject, QRunnable, QSize, QThreadPool, QTimer, Signal, Slot
from PySide6.QtGui import QImage, QImageReader
from PySide6.QtWidgets import QApplication


DEFAULT_PREVIEW_MAX_SIDE = 2200


def image_cache_key(path: str, preview_max_side: int) -> str:
    """Clé du cache mémoire, basée sur le chemin et la taille Preview max."""
    return f"{preview_max_side}::{path}"


class ImageLoadSignals(QObject):
    loaded = Signal(str, int, QImage, int, int)
    failed = Signal(str, int, str)


class ImageLoadTask(QRunnable):
    """Worker de chargement image. Charge du QImage, jamais de QPixmap hors thread UI."""

    def __init__(self, path: str, preview_max_side: int) -> None:
        super().__init__()
        self.path = path
        self.preview_max_side = int(preview_max_side)
        self.signals = ImageLoadSignals()
        self.setAutoDelete(True)

    def _can_emit(self) -> bool:
        try:
            app = QApplication.instance()
            if app is None or QApplication.closingDown():
                return False
        except Exception:
            return True
        return True

    def _emit_loaded_safe(self, image: QImage, original_w: int, original_h: int) -> None:
        if not self._can_emit():
            return
        try:
            self.signals.loaded.emit(
                self.path,
                self.preview_max_side,
                image,
                original_w,
                original_h,
            )
        except RuntimeError:
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
                width = size.width()
                height = size.height()
                if max(width, height) > max_side:
                    scale = max_side / float(max(width, height))
                    scaled_size = QSize(
                        max(1, int(width * scale)),
                        max(1, int(height * scale)),
                    )
                    reader.setScaledSize(scaled_size)

            image = reader.read()
            if image.isNull():
                self._emit_failed_safe(reader.errorString() or "Lecture impossible")
                return

            image = image.convertToFormat(QImage.Format_ARGB32_Premultiplied)
            self._emit_loaded_safe(image, original_w, original_h)
        except RuntimeError:
            return


class ImageMemoryCache(QObject):
    """Cache mémoire LRU + chargement asynchrone."""

    image_ready = Signal(str, QImage, int, int)
    image_failed = Signal(str, str)
    cache_info_changed = Signal(int, int)

    def __init__(
        self,
        preview_max_side: int = DEFAULT_PREVIEW_MAX_SIDE,
        parent: Optional[QObject] = None,
    ) -> None:
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
        """Vide le cache et invalide les workers déjà lancés.

        Les QRunnable ne sont pas interrompus brutalement. Leur clé est toutefois
        retirée de ``pending`` ; les callbacks tardifs sont donc ignorés dans
        ``_on_loaded`` / ``_on_failed`` et ne peuvent pas repeupler le cache.
        """
        self.preview_cache.clear()
        self.pending.clear()
        self.emit_cache_info()

    def request(self, path: str) -> None:
        if not path:
            return
        key = image_cache_key(path, self.preview_max_side)

        if key in self.preview_cache:
            image, original_w, original_h = self.preview_cache.pop(key)
            self.preview_cache[key] = (image, original_w, original_h)
            QTimer.singleShot(
                0,
                lambda p=path, img=image, w=original_w, h=original_h: self.image_ready.emit(p, img, w, h),
            )
            return

        if key in self.pending:
            return

        self.pending.add(key)
        task = ImageLoadTask(path=path, preview_max_side=self.preview_max_side)
        task.signals.loaded.connect(self._on_loaded)
        task.signals.failed.connect(self._on_failed)
        self.pool.start(task)
        self.emit_cache_info()

    @Slot(str, int, QImage, int, int)
    def _on_loaded(
        self,
        path: str,
        preview_max_side: int,
        image: QImage,
        original_w: int,
        original_h: int,
    ) -> None:
        key = image_cache_key(path, preview_max_side)
        if key not in self.pending:
            # Worker obsolète : cache vidé ou requête invalidée depuis son départ.
            self.emit_cache_info()
            return
        self.pending.discard(key)

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
        if key not in self.pending:
            self.emit_cache_info()
            return
        self.pending.discard(key)
        self.image_failed.emit(path, error)
        self.emit_cache_info()

    def prefetch(self, paths: Sequence[str]) -> None:
        for path in paths:
            self.request(path)

    def emit_cache_info(self) -> None:
        self.cache_info_changed.emit(len(self.preview_cache), len(self.pending))

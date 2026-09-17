from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QMainWindow, QPushButton, QSizePolicy, QVBoxLayout, QWidget


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

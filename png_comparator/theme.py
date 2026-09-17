from __future__ import annotations

import ctypes
import sys

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory, QWidget


DARK_STYLESHEET = """
QWidget {
    background-color: #1e1e1e;
    color: #e8e8e8;
}
QMainWindow, QDialog {
    background-color: #1e1e1e;
}
QMenuBar, QMenu {
    background-color: #252525;
    color: #eeeeee;
}
QMenuBar::item:selected, QMenu::item:selected {
    background-color: #3a3a3a;
}
QToolTip {
    color: #f0f0f0;
    background-color: #2b2b2b;
    border: 1px solid #555555;
}
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox, QTableWidget, QTreeWidget {
    background-color: #191919;
    color: #eeeeee;
    border: 1px solid #444444;
    selection-background-color: #4a4a4a;
    selection-color: #ffffff;
}
QHeaderView::section {
    background-color: #292929;
    color: #eeeeee;
    border: 1px solid #414141;
    padding: 5px;
}
QPushButton, QToolButton {
    background-color: #343434;
    color: #eeeeee;
    border: 1px solid #505050;
    border-radius: 4px;
    padding: 5px 8px;
}
QPushButton:hover, QToolButton:hover {
    background-color: #414141;
    border-color: #666666;
}
QPushButton:pressed, QToolButton:pressed {
    background-color: #292929;
}
QPushButton:disabled, QToolButton:disabled {
    color: #777777;
    background-color: #292929;
    border-color: #383838;
}
QGroupBox {
    border: 1px solid #3f3f3f;
    border-radius: 5px;
    margin-top: 8px;
    padding-top: 8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}
QTabWidget::pane {
    border: 1px solid #3d3d3d;
    background-color: #1e1e1e;
}
QTabBar::tab {
    background-color: #292929;
    color: #dcdcdc;
    padding: 6px 12px;
    border: 1px solid #3b3b3b;
}
QTabBar::tab:selected {
    background-color: #3a3a3a;
    color: #ffffff;
}
QScrollBar:vertical, QScrollBar:horizontal {
    background-color: #202020;
    border: none;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background-color: #555555;
    min-height: 20px;
    min-width: 20px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
    background-color: #666666;
}
QStatusBar {
    background-color: #202020;
    color: #dddddd;
}
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
QCheckBox::indicator:checked {
    border: 2px solid #ff8686;
    background-color: #d13c3c;
}
"""


def build_dark_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(30, 30, 30))
    palette.setColor(QPalette.WindowText, QColor(232, 232, 232))
    palette.setColor(QPalette.Base, QColor(24, 24, 24))
    palette.setColor(QPalette.AlternateBase, QColor(36, 36, 36))
    palette.setColor(QPalette.ToolTipBase, QColor(43, 43, 43))
    palette.setColor(QPalette.ToolTipText, QColor(240, 240, 240))
    palette.setColor(QPalette.Text, QColor(232, 232, 232))
    palette.setColor(QPalette.Button, QColor(52, 52, 52))
    palette.setColor(QPalette.ButtonText, QColor(238, 238, 238))
    palette.setColor(QPalette.BrightText, QColor(255, 100, 100))
    palette.setColor(QPalette.Highlight, QColor(74, 74, 74))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    palette.setColor(QPalette.PlaceholderText, QColor(145, 145, 145))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(110, 110, 110))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(110, 110, 110))
    return palette


def apply_application_dark_theme(app: QApplication) -> None:
    """Force un rendu sombre Qt indépendamment du thème de l'OS."""
    if "Fusion" in QStyleFactory.keys():
        app.setStyle("Fusion")
    app.setPalette(build_dark_palette())
    app.setStyleSheet(DARK_STYLESHEET)


def apply_windows_dark_titlebar(widget: QWidget) -> None:
    """Force la barre de titre Windows sombre quand DWM le permet.

    Windows 10/11 utilisent selon la build l'attribut 19 ou 20.
    En dehors de Windows, la fonction est volontairement sans effet.
    """
    if not sys.platform.startswith("win"):
        return
    try:
        hwnd = int(widget.winId())
        value = ctypes.c_int(1)
        dwmapi = ctypes.windll.dwmapi
        applied = False
        for attribute in (20, 19):
            try:
                result = dwmapi.DwmSetWindowAttribute(
                    ctypes.c_void_p(hwnd),
                    ctypes.c_uint(attribute),
                    ctypes.byref(value),
                    ctypes.sizeof(value),
                )
                if result == 0:
                    applied = True
                    break
            except Exception:
                continue
        if applied:
            try:
                ctypes.windll.uxtheme.SetWindowTheme(
                    ctypes.c_void_p(hwnd),
                    ctypes.c_wchar_p("DarkMode_Explorer"),
                    None,
                )
            except Exception:
                pass
    except Exception:
        pass

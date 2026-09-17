from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QComboBox, QLineEdit, QStyle, QStyledItemDelegate, QWidget

from ..status import STATUS_CHOICES, normalize_status, status_text_color


class NoWheelComboBox(QComboBox):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.ClickFocus)

    def wheelEvent(self, event) -> None:  # type: ignore[override]
        event.ignore()


class StatusComboDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index) -> None:  # type: ignore[override]
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

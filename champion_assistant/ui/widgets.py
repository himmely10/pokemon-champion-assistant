from pathlib import Path

from PIL.ImageQt import ImageQt
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QScrollArea

from ..data.storage import TYPE_NAMES

TYPE_COLORS = {
    "normal": "#737d89", "fire": "#cf6839", "water": "#397dc3", "electric": "#a98a16",
    "grass": "#3d9265", "ice": "#398f9c", "fighting": "#b25356", "poison": "#9662ae",
    "ground": "#aa7542", "flying": "#7779bd", "psychic": "#c25b85", "bug": "#849438",
    "rock": "#978652", "ghost": "#7662a3", "dragon": "#5b6fc1", "dark": "#66606a",
    "steel": "#698891", "fairy": "#bd6b9b",
}


def label(text="", object_name=None):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    widget.setMinimumHeight(19)
    if object_name:
        widget.setObjectName(object_name)
    return widget


def type_badge(kind):
    widget = label(TYPE_NAMES.get(kind, "属性缺失"))
    widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
    widget.setStyleSheet(f"background:{TYPE_COLORS.get(kind, '#737d89')};color:white;border-radius:10px;padding:4px 13px;font-weight:600;")
    widget.setFixedHeight(28)
    return widget


class PanelScrollArea(QScrollArea):
    """Fit the panel to available space; scroll only below its usable minimum."""

    def resizeEvent(self, event):
        super().resizeEvent(event)
        panel = self.widget()
        if panel:
            width=max(self.viewport().width(), panel.minimumWidth())
            wrapped_height=panel.layout().totalHeightForWidth(width) if panel.layout() else -1
            panel.resize(width, max(self.viewport().height(), panel.minimumHeight(),
                                    panel.minimumSizeHint().height(), wrapped_height))


class DropPreview(QFrame):
    fileDropped = Signal(str)
    openRequested = Signal()
    rejected = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("DropPreview")
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName('游戏截图输入区；按回车选择图片')
        self.setFixedHeight(68)
        self.image = None
        self.layout = QVBoxLayout(self)
        self.display = label("拖入完整游戏截图\n或双击选择图片", "DropHint")
        self.display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.display)

    @staticmethod
    def supported(mime):
        urls = mime.urls() if mime.hasUrls() else []
        return (len(urls) == 1 and urls[0].isLocalFile()
                and Path(urls[0].toLocalFile()).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"})

    def dragEnterEvent(self, event):
        if self.supported(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if self.supported(event.mimeData()):
            event.acceptProposedAction()
            self.fileDropped.emit(event.mimeData().urls()[0].toLocalFile())
        else:
            self.rejected.emit("一次请拖入一张本地 PNG、JPG、WebP 或 BMP 截图。")

    def mouseDoubleClickEvent(self, event):
        self.openRequested.emit()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.openRequested.emit()
            event.accept()
        else:
            super().keyPressEvent(event)

    def set_image(self, image):
        self.image = QPixmap.fromImage(ImageQt(image))
        self.update_preview()

    def clear_image(self):
        self.image = None
        self.display.clear()
        self.display.setText("拖入完整游戏截图\n或双击选择图片")

    def update_preview(self):
        if self.image:
            self.display.setPixmap(self.image.scaled(self.display.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_preview()

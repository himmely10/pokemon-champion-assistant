"""Render the original vector mark into Windows multi-resolution icon resources."""
from io import BytesIO
from pathlib import Path
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtGui import QImage, QPainter
from PySide6.QtCore import Qt, QBuffer, QIODevice
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def main():
    app = QApplication.instance() or QApplication([])
    brand = ROOT / 'assets/branding'
    rendered = QImage(256, 256, QImage.Format.Format_ARGB32)
    rendered.fill(Qt.GlobalColor.transparent)
    painter = QPainter(rendered)
    QSvgRenderer(str(brand / 'app.svg')).render(painter)
    painter.end()
    stream = QBuffer()
    stream.open(QIODevice.OpenModeFlag.WriteOnly)
    rendered.save(stream, 'PNG')
    image = Image.open(BytesIO(bytes(stream.data())))
    image.save(brand / 'app.ico', sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])


if __name__ == '__main__':
    main()

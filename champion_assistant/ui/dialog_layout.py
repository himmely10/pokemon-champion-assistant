"""Initial dialog sizing within the current display's usable area."""
from PySide6.QtCore import Qt

def fit_dialog(dialog, width, height):
    dialog.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
    area = dialog.screen().availableGeometry()
    dialog.resize(min(width, max(320, area.width()-48)),
                  min(height, max(320, area.height()-64)))

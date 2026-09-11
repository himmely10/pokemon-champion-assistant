"""Initial dialog sizing within the current display's usable area."""

def fit_dialog(dialog, width, height):
    area = dialog.screen().availableGeometry()
    dialog.resize(min(width, max(320, area.width()-48)),
                  min(height, max(320, area.height()-64)))

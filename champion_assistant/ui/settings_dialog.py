"""Product settings hub for the desktop shell."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from .dialog_layout import fit_dialog
from .widgets import label


class SettingsDialog(QDialog):
    """Expose existing application services through one discoverable settings UI."""

    themeChanged = Signal(bool)
    obsRequested = Signal()
    updateRequested = Signal()
    guideRequested = Signal()
    dataDirectoryRequested = Signal()
    diagnosticsRequested = Signal()

    def __init__(self, dark=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置 · Champion Lab")
        self.setModal(False)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 20, 22, 20)
        outer.setSpacing(14)

        heading = label("设置", "SettingsTitle")
        outer.addWidget(heading)
        outer.addWidget(label("连接、资料和界面偏好均保存在本机；OBS 密码不会写入设置文件。", "Muted"))

        appearance = self._card("外观与辅助功能")
        appearance_layout = appearance.layout()
        theme_row = QHBoxLayout()
        theme_text = QVBoxLayout()
        theme_text.addWidget(QLabel("深色主题"))
        theme_text.addWidget(label("适合长时间对战与采集环境", "Muted"))
        theme_row.addLayout(theme_text, 1)
        self.dark_toggle = QCheckBox("启用")
        self.dark_toggle.setChecked(bool(dark))
        self.dark_toggle.toggled.connect(self.themeChanged.emit)
        theme_row.addWidget(self.dark_toggle)
        appearance_layout.addLayout(theme_row)
        density_row = QHBoxLayout()
        density_row.addWidget(QLabel("界面密度"))
        density_row.addStretch()
        self.density = QComboBox()
        self.density.addItems(["紧凑（推荐）", "舒适"])
        self.density.setEnabled(False)
        self.density.setToolTip("舒适密度将在后续版本开放；当前桌面布局会自动适配窗口。")
        density_row.addWidget(self.density)
        appearance_layout.addLayout(density_row)
        outer.addWidget(appearance)

        services = self._card("连接与资料")
        grid = QGridLayout()
        self.obs_button = QPushButton("配置 OBS 采集")
        self.obs_button.clicked.connect(self.obsRequested.emit)
        self.update_button = QPushButton("检查资料更新")
        self.update_button.clicked.connect(self.updateRequested.emit)
        self.guide_button = QPushButton("重新打开使用引导")
        self.guide_button.clicked.connect(self.guideRequested.emit)
        self.data_button = QPushButton("打开本地数据目录")
        self.data_button.clicked.connect(self.dataDirectoryRequested.emit)
        grid.addWidget(self.obs_button, 0, 0)
        grid.addWidget(self.update_button, 0, 1)
        grid.addWidget(self.guide_button, 1, 0)
        grid.addWidget(self.data_button, 1, 1)
        services.layout().addLayout(grid)
        outer.addWidget(services)

        diagnostics = self._card("诊断与隐私")
        diagnostics.layout().addWidget(label("诊断摘要只包含版本、资料位置与连接状态，不包含截图原图或 OBS 密码。", "Muted"))
        self.diagnostics_button = QPushButton("复制诊断摘要")
        self.diagnostics_button.clicked.connect(self.diagnosticsRequested.emit)
        diagnostics.layout().addWidget(self.diagnostics_button)
        outer.addWidget(diagnostics)
        outer.addStretch()

        footer = QHBoxLayout()
        self.status = label("所有设置立即生效。", "Muted")
        footer.addWidget(self.status, 1)
        close_button = QPushButton("完成")
        close_button.setObjectName("Primary")
        close_button.clicked.connect(self.accept)
        footer.addWidget(close_button)
        outer.addLayout(footer)
        fit_dialog(self, 680, 690)

    @staticmethod
    def _card(title):
        card = QFrame()
        card.setObjectName("SettingsCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(label(title, "SettingsSection"))
        return card

    def set_dark(self, dark):
        self.dark_toggle.blockSignals(True)
        self.dark_toggle.setChecked(bool(dark))
        self.dark_toggle.blockSignals(False)

    def show_status(self, text):
        self.status.setText(text)

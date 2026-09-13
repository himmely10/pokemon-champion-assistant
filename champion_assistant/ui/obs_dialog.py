from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLineEdit,
                              QMessageBox, QPushButton, QSpinBox, QVBoxLayout)

from .widgets import label
from ..capture.obs import local_obs_settings
from .dialog_layout import fit_dialog


class ObsDialog(QDialog):
    connectRequested = Signal(object)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("连接 OBS · 选择 Switch 画面")
        self.setMinimumWidth(510)
        fit_dialog(self, 590, 580)
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.addWidget(label("在 OBS 中打开「工具 → WebSocket 服务器设置」，启用服务器。选择 Switch 视频采集源可避免场景边框影响识别。"))
        form = QFormLayout()
        self.host = QLineEdit(settings.get("host", "localhost"))
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(settings.get("port", 4455))
        self.password = QLineEdit(settings.get("password", ""))
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("本次运行使用，不保存密码")
        form.addRow("服务器地址", self.host)
        form.addRow("端口", self.port)
        form.addRow("密码", self.password)
        layout.addLayout(form)
        self.local_button = QPushButton("读取本机 OBS 设置")
        self.local_button.setToolTip("读取本机 OBS 的端口和密码，仅在本次运行使用；不会修改 OBS 设置。")
        self.local_button.clicked.connect(self.read_local)
        layout.addWidget(self.local_button)
        self.connect_button = QPushButton("连接并读取采集源")
        self.connect_button.clicked.connect(self.request_sources)
        layout.addWidget(self.connect_button)
        self.sources = QComboBox()
        self.sources.setMinimumContentsLength(25)
        if settings.get("source"):
            self.sources.addItem(settings["source"], settings["source"])
        layout.addWidget(self.sources)
        self.status = label("连接只读取源列表和截图，不会切换场景或开始推流。", "Muted")
        layout.addWidget(self.status)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("使用此采集源")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(settings.get("source")))
        layout.addWidget(self.buttons)

    def read_local(self):
        settings = local_obs_settings(include_password=True)
        if not settings:
            self.status.setText("没有找到标准安装位置的 OBS 设置；便携版或远程 OBS 请手动填写。")
            return
        self.host.setText(settings["host"])
        self.port.setValue(settings["port"])
        self.password.setText(settings["password"])
        self.status.setText("本机设置已读取，密码仅在内存使用。请点击连接。" if settings["enabled"] else
                            "本机 OBS 尚未启用 WebSocket。请先在 OBS 工具菜单中勾选启用并应用，再点击连接。")

    def settings(self):
        return {"host": self.host.text().strip() or "localhost", "port": self.port.value(),
                "password": self.password.text(), "source": self.sources.currentData() or ""}

    def request_sources(self):
        self.set_busy(True)
        self.status.setText("正在连接 OBS…")
        self.connectRequested.emit(self.settings())

    def set_busy(self, busy):
        self.connect_button.setEnabled(not busy)
        for widget in (self.local_button, self.host, self.port, self.password):
            widget.setEnabled(not busy)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(not busy and self.sources.count() > 0)

    def show_sources(self, result, error):
        previous = self.sources.currentData()
        self.sources.clear()
        if error:
            self.status.setText(error)
        else:
            for source in result["sources"]:
                self.sources.addItem(f"{source['kind']} · {source['name']}", source["name"])
            if self.sources.findData(previous) >= 0:
                self.sources.setCurrentIndex(self.sources.findData(previous))
            self.status.setText(f"OBS {result['version']} 连接已验证，请选择包含完整游戏画面的源。" if result['sources'] else
                                '连接已验证，但没有采集源。请在 OBS「来源」添加视频采集设备，然后重新连接读取。')
            if result['sources']:
                previous_notice = getattr(self, 'notice_box', None)
                if previous_notice is not None:
                    previous_notice.close()
                self.notice_box = QMessageBox(QMessageBox.Icon.Information, 'OBS 连接成功',
                    f"已连接 OBS {result['version']}，读取到 {len(result['sources'])} 个可用来源。请选择 Switch 画面后确认。",
                    QMessageBox.StandardButton.Ok, self)
                self.notice_box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
                self.notice_box.open()
        self.set_busy(False)

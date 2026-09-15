"""Skippable first-run routes. OBS credentials are entered only in ObsDialog."""
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QScrollArea, QWidget, QFileDialog

from ..data.storage import read_json, save_json
from ..paths import app_paths, migrate_legacy
from .dialog_layout import fit_dialog
from .widgets import label


def needs_onboarding(settings_path):
    try:
        return read_json(Path(settings_path)).get('onboarding_version', 0) < 1
    except (OSError, ValueError, AttributeError):
        return True


class OnboardingDialog(QDialog):
    imageRequested = Signal()
    obsRequested = Signal()

    def __init__(self, settings_path, parent=None):
        super().__init__(parent)
        self.settings_path = Path(settings_path)
        self.route = None
        self.setWindowTitle('开始使用 · Champion 对战工作台')
        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 20, 22, 20)
        outer.setSpacing(14)
        outer.addWidget(label('准备好第一场分析', 'OnboardingTitle'))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        content = QVBoxLayout(body)
        content.setContentsMargins(4, 8, 4, 8)
        content.addWidget(label('选择一种输入方式。资料可以离线查阅，我方能力按预存队伍计算。', 'OnboardingBody'))
        self.image_button = QPushButton('从图片开始 · 无需 OBS')
        self.obs_button = QPushButton('连接 OBS · 采集 Switch 画面')
        self.image_button.clicked.connect(lambda: self.choose('image'))
        self.obs_button.clicked.connect(lambda: self.choose('obs'))
        content.addWidget(self.image_button)
        content.addWidget(self.obs_button)
        self.instructions = label('你也可以先跳过；主界面的「使用引导」可随时重新打开。', 'OnboardingBody')
        content.addWidget(self.instructions)
        content.addStretch()
        self.import_button = QPushButton('导入旧版本的队伍与设置…')
        self.import_button.clicked.connect(self.import_legacy)
        content.addWidget(self.import_button)
        self.notice = label('', 'Muted')
        content.addWidget(self.notice)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        footer = QHBoxLayout()
        self.skip_button = QPushButton('暂时跳过')
        self.skip_button.clicked.connect(lambda: self.finish('skipped'))
        footer.addWidget(self.skip_button)
        footer.addStretch()
        self.start_button = QPushButton('请选择输入方式')
        self.start_button.setObjectName('Primary')
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(lambda: self.finish(self.route))
        footer.addWidget(self.start_button)
        outer.addLayout(footer)
        fit_dialog(self, 670, 540)

    def choose(self, route):
        self.route = route
        self.start_button.setEnabled(True)
        if route == 'image':
            self.instructions.setText('1. 准备完整 16:9 对战选队截图。\n2. 点击下方选择图片，或稍后拖入主界面。\n3. 检查右侧六只对手；待确认位置可以手动修正。\n4. 在「我方队伍配置」选择预存队伍，再打开双向伤害。')
            self.start_button.setText('选择图片')
        else:
            self.instructions.setText('1. 将 Switch 通过采集卡接入 OBS「视频采集设备」来源。\n2. OBS 工具 → WebSocket 服务器设置：启用并应用。\n3. 打开连接设置，填写地址、端口和密码；密码只在本次运行使用。\n4. 连接成功后选择完整游戏画面的来源，再点击「从 OBS 截图并识别」。')
            self.start_button.setText('打开 OBS 连接设置')

    def finish(self, route):
        try:
            settings = read_json(self.settings_path) if self.settings_path.exists() else {}
            settings.pop('password', None)
            settings.update(onboarding_version=1, onboarding_route=route)
            save_json(self.settings_path, settings)
        except (OSError, ValueError, AttributeError):
            # A read-only settings folder must not prevent first use.
            self.notice.setText('本次可以继续使用，但无法保存引导状态。')
        self.accept()
        if route == 'image':
            self.imageRequested.emit()
        elif route == 'obs':
            self.obsRequested.emit()

    def import_legacy(self):
        directory = QFileDialog.getExistingDirectory(self, '选择旧版项目根目录（包含 user_data）')
        if not directory:
            return
        try:
            result = migrate_legacy(directory, app_paths())
            self.notice.setText('已导入：' + ('、'.join(result['imported']) or '无新数据') +
                                '；已存在的数据保持不变。重新打开队伍配置查看；连接设置在下次启动载入。')
        except Exception:
            self.notice.setText('旧数据导入失败，原文件已保留。请检查选择的目录与文件权限。')

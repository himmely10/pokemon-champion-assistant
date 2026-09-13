"""A single background updater shared by manual actions and the in-app clock."""
import json
from pathlib import Path
import sys

from PySide6.QtCore import QObject, QProcess, QTimer, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QProgressBar, QPushButton, QVBoxLayout)

from ..data.storage import read_json, save_json
from ..data.update_service import UpdateService
from ..paths import app_paths
from ..version import __version__


class UpdateController(QObject):
    statusChanged = Signal(str)
    updated = Signal()
    busyChanged = Signal(bool)

    def __init__(self, root, settings_path, parent=None):
        super().__init__(parent)
        self.root, self.settings_path = Path(root), Path(settings_path)
        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(app_paths().resources))
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._error)
        self.timer = QTimer(self)
        self.timer.setInterval(3600000)
        self.timer.timeout.connect(lambda: self.run('sync', automatic=True))
        self.initial_timer = QTimer(self)
        self.initial_timer.setSingleShot(True)
        self.initial_timer.timeout.connect(lambda: self.run('sync', automatic=True))
        self.cancelled = False
        self.last_result = {}

    def settings(self):
        try:
            value = read_json(self.settings_path).get('updates', {})
            hours = value.get('hours', 24)
            return {'channel': str(value.get('channel', '')), 'hours': hours if hours in (0, 24, 72, 168) else 24}
        except (OSError, ValueError, AttributeError):
            return {'channel': '', 'hours': 24}

    def save_settings(self, channel, hours):
        from urllib.parse import urlparse
        parsed = urlparse(channel.strip())
        if channel.strip() and (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password):
            raise ValueError('请输入无用户名或密码的 HTTPS 资料渠道地址。')
        try:
            saved = read_json(self.settings_path)
        except (OSError, ValueError):
            saved = {}
        saved['updates'] = {'channel': channel.strip(), 'hours': hours}
        save_json(self.settings_path, saved)

    def start(self):
        self.timer.start()
        self.initial_timer.start(1200)

    def run(self, operation, package=None, automatic=False):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            return False
        settings = self.settings()
        if automatic and not settings['hours']:
            return False
        if automatic and not settings['channel']:
            self.statusChanged.emit('尚未配置资料渠道，可在更新中心导入本地资料包。')
            return False
        args = ['--update-worker', '--root', str(self.root), '--operation', operation,
                '--channel', settings['channel'], '--hours', str(settings['hours'])]
        if automatic:
            args += ['--if-due']
        if package:
            args += ['--package', str(package)]
        if getattr(sys, 'frozen', False):
            program = str(Path(sys.executable).with_name('ChampionWorker.exe'))
        else:
            program = sys.executable
            args = ['-X', 'utf8', str(app_paths().resource('launch_assistant.py')), *args]
        self.cancelled = False
        self.busyChanged.emit(True)
        self.statusChanged.emit('正在处理资料，请稍候；当前分析保持原版本。')
        self.process.start(program, args)
        return True

    def _finished(self, code, status):
        output = bytes(self.process.readAllStandardOutput()).decode('utf-8', errors='replace')
        self.process.readAllStandardError()
        try:
            if self.cancelled:
                result = {'status': 'cancelled', 'message': '已取消更新，当前分析保持原版本。'}
            else:
                result = json.loads(output)
            labels = {'current': '已经是最新资料。', 'available': '发现新资料，点击“更新资料”下载。',
                      'not_due': '资料尚未到检查时间。', 'valid': '当前资料校验通过。'}
            self.last_result = result
            self.statusChanged.emit(result.get('message') or labels.get(result['status'], result['status']))
            if result['status'] == 'updated':
                self.updated.emit()
        except (ValueError, KeyError, TypeError):
            self.statusChanged.emit('更新任务失败，原资料保留；可重试或导入本地资料包。')
        self.busyChanged.emit(False)

    def _error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.statusChanged.emit('无法启动内置更新组件，请重新安装完整版本。')
            self.busyChanged.emit(False)

    def cancel(self):
        self.cancelled = True
        self.process.kill()

    def stop(self):
        self.timer.stop()
        self.initial_timer.stop()
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.cancel()
            self.process.waitForFinished(1500)


class UpdateDialog(QDialog):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle('资料更新中心')
        self.resize(760, 440)
        layout = QVBoxLayout(self)
        intro = QLabel('资料与采用率更新后，下次分析使用新版本。个人队伍不受影响。')
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.version = QLabel()
        self.version.setWordWrap(True)
        layout.addWidget(self.version)
        program = QPushButton(f'程序 v{__version__} · 查看安装包发布页')
        program.setToolTip('在浏览器中打开项目 Releases；私有仓库需要相应访问权限。')
        program.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(
            'https://github.com/himmely10/pokemon-champion-assistant/releases')))
        layout.addWidget(program)
        form = QFormLayout()
        settings = controller.settings()
        self.channel = QLineEdit(settings['channel'])
        self.channel.setPlaceholderText('维护者提供的 HTTPS channel.json 地址')
        self.interval = QComboBox()
        for name, hours in [('每天', 24), ('每三天', 72), ('每周', 168), ('关闭自动检查', 0)]:
            self.interval.addItem(name, hours)
        self.interval.setCurrentIndex(self.interval.findData(settings['hours']))
        form.addRow('资料渠道', self.channel)
        form.addRow('软件运行时自动检查', self.interval)
        layout.addLayout(form)
        self.status_label = QLabel('可先导入本地资料包；程序版本升级通过安装新版完成。')
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)
        layout.addStretch()
        buttons = QHBoxLayout()
        self.actions = []
        for title, operation in [('检查更新', 'check'), ('更新资料', 'sync'), ('校验', 'validate'), ('恢复上一版', 'rollback')]:
            button = QPushButton(title)
            button.clicked.connect(lambda checked=False, op=operation: self.run(op))
            buttons.addWidget(button)
            self.actions.append(button)
        import_button = QPushButton('导入资料包')
        import_button.clicked.connect(self.import_package)
        buttons.addWidget(import_button)
        self.actions.append(import_button)
        layout.addLayout(buttons)
        self.bundled_button = QPushButton('采用当前软件附带的离线资料')
        self.bundled_button.setToolTip('主动切换为此安装版附带的资料；可能早于已下载资料，之后可恢复上一版。个人队伍不变。')
        self.bundled_button.setVisible(app_paths().resource('pokemon/baseline.zip').is_file())
        self.bundled_button.clicked.connect(lambda: controller.run('import', app_paths().resource('pokemon/baseline.zip')))
        self.actions.append(self.bundled_button)
        layout.addWidget(self.bundled_button)
        footer = QHBoxLayout()
        save = QPushButton('保存设置')
        save.clicked.connect(self.save)
        cancel = QPushButton('取消更新')
        cancel.clicked.connect(controller.cancel)
        close = QPushButton('关闭')
        close.clicked.connect(self.close)
        for button in (save, cancel, close):
            footer.addWidget(button)
        layout.addLayout(footer)
        controller.statusChanged.connect(self.status_label.setText)
        controller.busyChanged.connect(self.set_busy)
        controller.updated.connect(self.refresh)
        self.refresh()

    def refresh(self):
        from datetime import datetime
        state = UpdateService(self.controller.root).state
        version = state.get('installed') or '随软件提供的资料'
        moment = state.get('installed_at')
        stamp = datetime.fromtimestamp(moment).strftime('%Y-%m-%d %H:%M') if moment else '尚无更新记录'
        checked = state.get('checked_at')
        checked_stamp = datetime.fromtimestamp(checked).strftime('%Y-%m-%d %H:%M') if checked else '尚未检查'
        self.version.setText(f'已下载版本：{version}\n更新时间：{stamp} · 最近检查：{checked_stamp}\n活动分析仍显示其原资料版本。')

    def set_busy(self, busy):
        self.progress.setVisible(busy)
        for button in self.actions:
            button.setEnabled(not busy)
        if not busy:
            self.refresh()

    def save(self):
        try:
            self.controller.save_settings(self.channel.text(), self.interval.currentData())
            self.status_label.setText('更新设置已保存。')
            return True
        except ValueError as exc:
            self.status_label.setText(str(exc))
            return False

    def run(self, operation):
        if self.save():
            self.controller.run(operation)

    def import_package(self):
        path, _ = QFileDialog.getOpenFileName(self, '导入公共资料包', '', '资料包 (*.zip)')
        if path:
            self.controller.run('import', path)

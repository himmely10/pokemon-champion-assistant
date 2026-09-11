"""Run the shared daily-check script while the desktop app is open."""
import json
from pathlib import Path
import sys
import sysconfig

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

ROOT = Path(__file__).resolve().parents[2]


def updater_command(usage_dir):
    # Windows venv launchers create another process. Start the actual interpreter
    # with this environment's packages, so killing QProcess stops the updater itself.
    executable = getattr(sys, "_base_executable", sys.executable)
    bootstrap = "import site,sys,runpy;site.addsitedir(sys.argv.pop(1));runpy.run_path(sys.argv.pop(1),run_name='__main__')"
    return executable, ["-X", "utf8", "-c", bootstrap, sysconfig.get_path("purelib"),
                        str(ROOT / "scripts/update_usage_data.py"), "--data-dir", str(usage_dir), "--if-due", "--json"]


class UsageUpdater(QObject):
    updated = Signal()
    statusChanged = Signal(str)

    def __init__(self, usage_dir, parent=None, command_factory=updater_command):
        super().__init__(parent)
        self.usage_dir = Path(usage_dir)
        self.command_factory = command_factory
        self.stopping = False
        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(ROOT))
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._error)
        self.timer = QTimer(self)
        self.timer.setInterval(60 * 60 * 1000)
        self.timer.timeout.connect(self.check)
        self.initial_timer = QTimer(self)
        self.initial_timer.setSingleShot(True)
        self.initial_timer.timeout.connect(self.check)

    def start(self):
        self.stopping = False
        self.timer.start()
        self.initial_timer.start(1000)

    def check(self):
        if self.stopping or self.process.state() != QProcess.ProcessState.NotRunning:
            return
        program, arguments = self.command_factory(self.usage_dir)
        self.statusChanged.emit("正在后台检查采用率更新…")
        self.process.start(program, arguments)

    def _finished(self, exit_code, exit_status):
        output = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self.process.readAllStandardError()  # Error summaries stay generic; no traceback in the UI.
        if self.stopping:
            return
        try:
            if exit_status != QProcess.ExitStatus.NormalExit or exit_code not in (0, 2):
                raise ValueError("update failed")
            result = json.loads(output)
            status = result["status"]
            if status not in {"updated", "partial", "not_due"}:
                raise ValueError("unexpected update result")
        except (ValueError, KeyError, TypeError):
            self.statusChanged.emit("采用率更新失败，继续使用缓存；软件运行期间约 1 小时后重试。")
            return
        if status == "not_due":
            self.statusChanged.emit("采用率已检查：距上次成功更新不足 24 小时。")
        else:
            self.updated.emit()
            self.statusChanged.emit("采用率已自动更新。" if status == "updated" else
                                    "采用率部分更新；失败项保留缓存，约 1 小时后重试。")

    def _error(self, error):
        if not self.stopping and error == QProcess.ProcessError.FailedToStart:
            self.statusChanged.emit("更新脚本无法启动，继续使用缓存；请检查 Python 环境。")

    def stop(self):
        self.stopping = True
        self.timer.stop()
        self.initial_timer.stop()
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()
            self.process.waitForFinished(1000)

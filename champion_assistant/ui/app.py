import argparse
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from .main_window import MainWindow, ROOT
from .usage_updater import UsageUpdater


def main(argv=None):
    parser = argparse.ArgumentParser(description="宝可梦对战资料台：拖入截图或通过 OBS 识别对手。")
    parser.add_argument("image", nargs="?", type=Path, help="启动后识别指定截图")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "pokemon")
    parser.add_argument("--layout", type=Path, help="自定义六槽位识别布局 JSON")
    args = parser.parse_args(argv)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("Pokemon Champion Assistant")
    try:
        window = MainWindow(args.data_dir, args.layout, report_path=ROOT / "artifacts/desktop/last_result.json")
    except Exception as exc:
        QMessageBox.critical(None, "资料台启动失败", f"无法读取本地资料：{exc}\n请运行自动更新脚本的 validate 检查。")
        return 1
    window.show()
    window.usage_updater = UsageUpdater(window.catalog.usage_dir, window)
    window.usage_updater.updated.connect(window.refresh_usage_view)
    window.usage_updater.statusChanged.connect(window.usage_update_label.setText)
    app.aboutToQuit.connect(window.usage_updater.stop)
    window.usage_updater.start()
    if args.image:
        QTimer.singleShot(0, lambda: window.open_image(str(args.image)))
    return app.exec()

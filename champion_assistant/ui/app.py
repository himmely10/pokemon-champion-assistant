import argparse
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QIcon

from ..paths import app_paths


def _run_legacy(app, args, paths):
    """Keep the former native interface available for diagnostics and image args."""
    from PySide6.QtCore import QTimer
    from .main_window import MainWindow
    from .onboarding import needs_onboarding
    from .theme import STYLE
    from .update_dialog import UpdateController, UpdateDialog

    app.setStyleSheet(STYLE)
    window = MainWindow(args.data_dir or paths.data, args.layout, report_path=paths.cache / 'last_result.json')
    area = window.screen().availableGeometry()
    window.resize(min(window.width(), area.width() - 24), min(window.height(), area.height() - 48))
    window.show()
    window.usage_updater = UpdateController(window.data_dir, window.settings_path, window)
    window.usage_updater.updated.connect(window.refresh_usage_view)
    window.usage_updater.statusChanged.connect(window.usage_update_label.setText)
    app.aboutToQuit.connect(window.usage_updater.stop)
    window.usage_updater.start()
    window.update_dialog = UpdateDialog(window.usage_updater, window)
    window.updateRequested.connect(window.update_dialog.show)
    update_action = window.menuBar().addAction('资料更新')
    update_action.triggered.connect(window.update_dialog.show)
    if args.image:
        QTimer.singleShot(0, lambda: window.open_image(str(args.image)))
    elif needs_onboarding(window.settings_path):
        QTimer.singleShot(0, window.open_onboarding)
    return app.exec()


def main(argv=None):
    parser = argparse.ArgumentParser(description="宝可梦对战资料台：拖入截图或通过 OBS 识别对手。")
    parser.add_argument("image", nargs="?", type=Path, help="启动后识别指定截图")
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--layout", type=Path, help="自定义六槽位识别布局 JSON")
    parser.add_argument("--port", type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument("--static-root", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--legacy-ui", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("Pokemon Champion Assistant")
    try:
        paths = app_paths().ensure()
        app.setWindowIcon(QIcon(str(paths.resource('assets/branding/app.ico'))))
        if args.legacy_ui or args.image:
            return _run_legacy(app, args, paths)
        from .web_window import WebDesktopWindow
        window = WebDesktopWindow(
            data_dir=args.data_dir or paths.data,
            layout_path=args.layout,
            static_root=args.static_root,
            port=args.port,
        )
    except Exception as exc:
        QMessageBox.critical(None, "资料台启动失败", f"无法读取本地资料：{exc}\n请运行自动更新脚本的 validate 检查。")
        return 1
    window.show()
    return app.exec()

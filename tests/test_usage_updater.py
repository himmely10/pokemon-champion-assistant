import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QProcess
import pytest

from champion_assistant.data.storage import digest, json_bytes, now, save_json
from champion_assistant.ui.usage_updater import UsageUpdater


def python_command(code):
    return lambda _: (getattr(sys, "_base_executable", sys.executable), ["-X", "utf8", "-c", code])


def test_app_runs_real_shared_script_and_skips_fresh_data(qtbot, tmp_path):
    data = json_bytes({"schema_version": 1, "features_version": 2, "format": "double", "season": "m-6",
                       "fetched_at": now(), "pokemon": {}, "errors": {}})
    (tmp_path / "snapshot.json").write_bytes(data)
    save_json(tmp_path / "current.json", {"file": "snapshot.json", "sha256": digest(data)})
    updater = UsageUpdater(tmp_path)
    messages, changes = [], []
    updater.statusChanged.connect(messages.append)
    updater.updated.connect(lambda: changes.append(True))
    updater.start()
    qtbot.waitUntil(lambda: any("不足 24 小时" in text for text in messages), timeout=10000)
    assert updater.timer.isActive() and updater.timer.interval() == 3600000
    assert changes == []
    updater.stop()


@pytest.mark.parametrize("status,exit_code,expected,changed", [
    ("updated", 0, "已自动更新", True), ("partial", 2, "部分更新", True),
    ("bad-response", 0, "更新失败", False), ("updated", 1, "更新失败", False)])
def test_completion_refreshes_only_successful_snapshots(qtbot, tmp_path, status, exit_code, expected, changed):
    updater = UsageUpdater(tmp_path, command_factory=python_command(
        f"import json;print(json.dumps({{'status':{status!r}}}));raise SystemExit({exit_code})"))
    messages, changes = [], []
    updater.statusChanged.connect(messages.append)
    updater.updated.connect(lambda: changes.append(True))
    updater.check()
    qtbot.waitUntil(lambda: any(expected in text for text in messages), timeout=10000)
    assert bool(changes) == changed
    updater.stop()


def test_reentry_and_close_stop_owned_process(qtbot, tmp_path):
    updater = UsageUpdater(tmp_path, command_factory=python_command("import time;time.sleep(30)"))
    updater.check()
    qtbot.waitUntil(lambda: updater.process.state() == QProcess.ProcessState.Running)
    pid = updater.process.processId()
    updater.check()
    assert updater.process.processId() == pid
    updater.stop()
    assert updater.process.state() == QProcess.ProcessState.NotRunning
    assert not updater.timer.isActive() and not updater.initial_timer.isActive()


def test_background_refresh_keeps_selected_opponent_and_context(qtbot, tmp_path):
    from champion_assistant.ui.main_window import MainWindow
    window = MainWindow(settings_path=tmp_path / "settings.json")
    qtbot.addWidget(window)
    record = window.catalog.record_for_name("烈咬陆鲨")
    window.show_record(record, context="对手槽位 5 · 识别结果")
    context = window.context_label.text()
    window.move_search.setText("守住")
    window.refresh_usage_view()
    assert window.selected_record is record and window.context_label.text() == context
    assert window.move_search.text() == "守住"
    assert window.status_table.rowCount() == 1
    window.close()

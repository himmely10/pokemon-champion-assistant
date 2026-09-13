import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QProcess
from champion_assistant.ui.update_dialog import UpdateController, UpdateDialog


def test_settings_preserve_obs_and_disable_auto(qtbot, tmp_path):
    settings = tmp_path / 'ui.json'
    settings.write_text(json.dumps({'host': 'localhost', 'source': 'Switch'}))
    controller = UpdateController(tmp_path / 'data', settings)
    controller.save_settings('', 0)
    saved = json.loads(settings.read_text())
    assert saved['source'] == 'Switch'
    assert controller.run('sync', automatic=True) is False
    dialog = UpdateDialog(controller)
    qtbot.addWidget(dialog)
    assert dialog.interval.currentData() == 0
    assert '本地资料包' in dialog.status_label.text()


def test_background_cli_failure_is_visible_and_reusable(qtbot, tmp_path):
    controller = UpdateController(tmp_path / 'data', tmp_path / 'ui.json')
    messages = []
    controller.statusChanged.connect(messages.append)
    with qtbot.waitSignal(controller.busyChanged, check_params_cb=lambda busy: not busy, timeout=15000):
        assert controller.run('check')
        assert not controller.run('check')
    assert controller.last_result['status'] == 'unconfigured'
    assert controller.process.state() == QProcess.ProcessState.NotRunning
    assert any('未配置' in text for text in messages)
    controller.stop()


def test_bundled_data_requires_explicit_adoption(qtbot, tmp_path, monkeypatch):
    from types import SimpleNamespace
    from PySide6.QtCore import Qt
    import champion_assistant.ui.update_dialog as module
    controller = UpdateController(tmp_path / 'user-data', tmp_path / 'ui.json')
    package = tmp_path / 'pokemon/baseline.zip'
    package.parent.mkdir()
    package.write_bytes(b'button test; package validation is exercised separately')
    monkeypatch.setattr(module, 'app_paths', lambda: SimpleNamespace(resource=lambda name: tmp_path / name))
    calls = []
    monkeypatch.setattr(controller, 'run', lambda *args: calls.append(args))
    dialog = UpdateDialog(controller)
    qtbot.addWidget(dialog)
    dialog.show()
    assert not calls
    qtbot.mouseClick(dialog.bundled_button, Qt.MouseButton.LeftButton)
    assert calls == [('import', package)]

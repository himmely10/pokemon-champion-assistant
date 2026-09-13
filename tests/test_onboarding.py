import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialogButtonBox

from champion_assistant.data.storage import save_json, read_json
from champion_assistant.ui.onboarding import OnboardingDialog, needs_onboarding
from champion_assistant.ui.obs_dialog import ObsDialog
from champion_assistant.ui.widgets import DropPreview


@pytest.mark.parametrize('route', ['image', 'obs', 'skipped'])
def test_first_run_routes_are_skippable_and_preserve_other_settings(qtbot, tmp_path, route):
    path = tmp_path / 'settings.json'
    save_json(path, {'update_interval_hours': 72, 'host': 'localhost', 'password': 'do-not-persist'})
    assert needs_onboarding(path)
    dialog = OnboardingDialog(path)
    qtbot.addWidget(dialog)
    emitted = []
    dialog.imageRequested.connect(lambda: emitted.append('image'))
    dialog.obsRequested.connect(lambda: emitted.append('obs'))
    dialog.show()
    if route == 'skipped':
        qtbot.mouseClick(dialog.skip_button, Qt.MouseButton.LeftButton)
    else:
        qtbot.mouseClick(dialog.image_button if route == 'image' else dialog.obs_button, Qt.MouseButton.LeftButton)
        assert dialog.start_button.isEnabled()
        qtbot.mouseClick(dialog.start_button, Qt.MouseButton.LeftButton)
    assert emitted == ([] if route == 'skipped' else [route])
    assert not needs_onboarding(path)
    settings = read_json(path)
    assert settings['update_interval_hours'] == 72
    assert 'password' not in settings
    # Completing the guide doesn't remove the option to open it again.
    reopened = OnboardingDialog(path)
    qtbot.addWidget(reopened)
    reopened.show()
    assert reopened.image_button.isEnabled()


def test_picture_route_does_not_require_obs(qtbot, tmp_path):
    dialog = OnboardingDialog(tmp_path / 'settings.json')
    qtbot.addWidget(dialog)
    dialog.choose('image')
    assert '无需 OBS' in dialog.image_button.text()
    assert '密码' not in dialog.instructions.text()


def test_preview_keyboard_opens_file_chooser(qtbot):
    widget = DropPreview()
    qtbot.addWidget(widget)
    widget.show()
    with qtbot.waitSignal(widget.openRequested):
        qtbot.keyClick(widget, Qt.Key.Key_Return)


def test_obs_empty_sources_and_failure_have_next_steps(qtbot):
    dialog = ObsDialog({})
    qtbot.addWidget(dialog)
    dialog.show_sources({'version': '32', 'sources': []}, '')
    assert '添加视频采集设备' in dialog.status.text()
    assert not dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
    dialog.show_sources(None, '认证失败，请检查 OBS 密码。')
    assert '检查 OBS 密码' in dialog.status.text()
    assert dialog.connect_button.isEnabled()
    dialog.show_sources({'version': '32', 'sources': [{'kind': '源', 'name': 'Switch'}]}, '')
    assert dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
    assert dialog.notice_box.windowTitle() == 'OBS 连接成功'


def test_small_onboarding_keeps_action_footer_visible(qtbot, tmp_path):
    dialog = OnboardingDialog(tmp_path / 'settings.json')
    qtbot.addWidget(dialog)
    dialog.choose('obs')
    dialog.resize(620, 340)
    dialog.show()
    qtbot.waitUntil(dialog.isVisible)
    assert dialog.start_button.mapTo(dialog, dialog.start_button.rect().bottomRight()).y() < dialog.height()
    assert dialog.skip_button.isVisible()

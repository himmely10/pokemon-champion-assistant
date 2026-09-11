"""Real image/Qt integration plus read-only OBS protocol and reference contracts."""
import base64
import io
import os
from pathlib import Path
from threading import Event

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
pytest.importorskip("PySide6")
from PySide6.QtCore import QObject, Signal, Slot, Qt, QMimeData, QPointF, QUrl
from PySide6.QtGui import QDropEvent, QFontDatabase

from champion_assistant.capture.obs import CaptureError, ObsCapture, decode_screenshot
from champion_assistant.data.moves import accuracy_label, move_tooltip, power_label
from champion_assistant.data.references import ReferenceCatalog
from champion_assistant.data.storage import read_json
from champion_assistant.ui.main_window import MainWindow, ROOT


@pytest.fixture(scope="module")
def catalog():
    return ReferenceCatalog(ROOT / "pokemon")


def test_mega_family_and_move_semantics(catalog):
    for name, expected in [("喷火龙", {"charizard", "mega-charizard-x", "mega-charizard-y"}),
                           ("烈咬陆鲨", {"garchomp", "mega-garchomp", "mega-garchomp-z"})]:
        record = catalog.record_for_name(name)
        family = catalog.form_family(record)
        assert {r["opgg_key"] for r in family} == expected
        assert catalog.form_family(family[-1]) == family
    assert catalog.display_name(catalog.record_for_name("来悲粗茶")) == "来悲粗茶"
    assert catalog.display_name(catalog.record_for_name("彩粉蝶")) == "彩粉蝶"
    unlinked = next(r for r in catalog.records if not r.get("opgg_key"))
    assert catalog.form_family(unlinked) == [unlinked]
    damage, status, notice = catalog.learnset(catalog.record_for_name("烈咬陆鲨"))
    assert damage and status and "双打" in notice
    assert all(m["category"] != "status" and m["isAvailable"] for m in damage)
    assert all(m["category"] == "status" and m["isAvailable"] for m in status)
    earthquake = next(m for m in damage if m["key"] == "earthquake")
    assert power_label(earthquake) == "100" and accuracy_label(earthquake) == "100%"
    assert power_label({"category": "physical", "power": None}) == "特殊"
    assert accuracy_label({"accuracy": None}) == "—"
    assert accuracy_label({}) == "未知"
    assert "&lt;img" in move_tooltip({**earthquake, "description": "<img src=x>"})


@pytest.fixture
def png_data():
    stream = io.BytesIO()
    Image.new("RGB", (1280, 720), "green").save(stream, "PNG")
    return "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode()


def test_obs_read_only_requests_and_cleanup(png_data):
    calls, clients = [], []
    class Client:
        def __init__(self, **settings):
            assert settings["timeout"] == 5
            self.closed = False
            clients.append(self)
        def send(self, name, data=None, raw=False):
            assert raw
            calls.append((name, data))
            return {"GetVersion": {"availableRequests": ["GetSourceScreenshot"], "obsVersion": "32"},
                    "GetInputList": {"inputs": [{"inputName": "Switch"}]},
                    "GetSceneList": {"scenes": [{"sceneName": "游戏"}]},
                    "GetSourceScreenshot": {"imageData": png_data}}[name]
        def disconnect(self):
            self.closed = True
    capture = ObsCapture(Client)
    assert capture.sources({})["sources"] == [{"name": "Switch", "kind": "源"}, {"name": "游戏", "kind": "场景"}]
    assert capture.screenshot({"source": "Switch"}).size == (1280, 720)
    assert calls[-1] == ("GetSourceScreenshot", {"sourceName": "Switch", "imageFormat": "png"})
    assert all(c.closed for c in clients)
    assert {name for name, _ in calls} <= {"GetVersion", "GetInputList", "GetSceneList", "GetSourceScreenshot"}


@pytest.mark.parametrize("data", [None, "bad", "data:image/png;base64,!!", "data:image/png;base64,YmFk"])
def test_obs_rejects_bad_images(data):
    with pytest.raises(CaptureError):
        decode_screenshot(data)


def test_obs_errors_hide_credentials_and_close():
    clients = []
    class Client:
        def __init__(self, **settings):
            self.closed = False
            clients.append(self)
        def send(self, *args, **kwargs):
            raise RuntimeError("secret-password")
        def disconnect(self):
            self.closed = True
    with pytest.raises(CaptureError) as error:
        ObsCapture(Client).sources({"password": "secret-password"})
    assert "secret-password" not in str(error.value)
    assert clients[0].closed


@pytest.fixture
def window(qtbot, tmp_path):
    # Qt's offscreen backend has no Windows font enumeration.
    if not QFontDatabase.families():
        for font in ("msyh.ttc", "msyhbd.ttc", "consola.ttf"):
            QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + font)
    widget = MainWindow(settings_path=tmp_path / "settings.json")
    qtbot.addWidget(widget)
    widget.show()
    yield widget
    qtbot.waitUntil(lambda: not widget.busy, timeout=45000)
    widget.close()


def test_ui_mega_preview_move_click_search_and_tooltip(window, qtbot):
    window.show_record(window.catalog.record_for_name("喷火龙"))
    assert window.stats_table.columnCount() == 4
    assert window.stats_table.item(6, 1).text() == "100"
    window.select_form_column(2)
    assert window.selected_record["opgg_key"] == "mega-charizard-x"
    assert window.opponents == []  # Preview does not invent a recognized Mega.
    window.move_search.setText("守住")
    assert window.damage_table.rowCount() == 0 and window.status_table.rowCount() == 1
    item = window.status_table.item(0, 0)
    assert "守住" in item.toolTip()
    qtbot.mouseClick(window.status_table.viewport(), Qt.MouseButton.LeftButton,
                     pos=window.status_table.visualItemRect(item).center())
    assert window.move_title.text() == "守住"
    assert window.metric_values["威力"].text() == "—"
    assert window.move_effect.text() == item.data(Qt.ItemDataRole.UserRole)["description"]


def test_drag_image_recognition_and_new_input_clears_previous(window, qtbot):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(ROOT / "例子.png"))])
    drop = QDropEvent(QPointF(20, 20), Qt.DropAction.CopyAction, mime,
                      Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    window.preview.dropEvent(drop)
    assert drop.isAccepted() and window.busy
    qtbot.waitUntil(lambda: not window.busy, timeout=45000)
    assert window.last_result is not None, window.status_label.text()
    assert [r["name"] for r in window.opponents] == ["苍炎刃鬼", "风妖精", "巨金怪", "来悲粗茶", "烈咬陆鲨", "姆克鹰"]
    window.team_list.setCurrentRow(4)
    assert window.stats_table.columnCount() == 4
    window.pokemon_search.setCurrentText("喷火龙")
    window.correct_slot()
    assert window.opponents[4]["name"] == "喷火龙" and window.opponents[4]["manual"]
    window.open_image(str(ROOT / "不存在.png"))
    assert window.opponents == [] and window.preview.image is None
    qtbot.waitUntil(lambda: not window.busy, timeout=5000)
    assert window.last_result is None and "无法打开" in window.status_label.text()


def test_cancel_discards_late_result(qtbot, tmp_path):
    class DeferredWorker(QObject):
        finished = Signal(int, str, object, str)
        def __init__(self, *args):
            super().__init__()
            self.cancelled = Event()
        @Slot(int, str, object)
        def run(self, *args):
            pass
    widget = MainWindow(settings_path=tmp_path / "settings.json", worker_factory=DeferredWorker)
    qtbot.addWidget(widget)
    widget.open_image("unused.png")
    revision = widget.revision
    widget.cancel()
    widget._finished(revision, "file", {"should_not_be_read": True}, "")
    assert not widget.busy and widget.last_result is None
    assert widget.status_label.text() == "操作已取消。"
    widget.close()


def test_obs_password_is_only_in_memory(window):
    window.configure_obs()
    dialog = window.obs_dialog
    dialog.password.setText("never-write-this")
    dialog.show_sources({"sources": [{"name": "Switch", "kind": "源"}], "version": "32"}, "")
    dialog.accept()
    saved = read_json(window.settings_path)
    assert saved == {"host": "localhost", "port": 4455, "source": "Switch"}
    assert window.obs_settings["password"] == "never-write-this"


def test_small_window_uses_scroll_and_keeps_stats_separate(window, qtbot):
    window.show_record(window.catalog.record_for_name("烈咬陆鲨"))
    window.resize(1100, 790)
    qtbot.wait(30)
    assert window.reference_tabs.geometry().bottom() < window.form_note.geometry().top()
    assert window.form_note.geometry().bottom() < window.move_search.parentWidget().height()
    assert window.splitter.widget(1).verticalScrollBar().maximum() > 0


def test_speed_table_matches_user_reference_and_comparison(window):
    window.show_record(window.catalog.record_for_name("大狃拉"))
    assert [window.speed_table.item(r, 1).text() for r in range(6)] == ["283", "189", "258", "172", "140", "126"]
    window.speed_compare.setCurrentText("烈咬陆鲨")
    assert window.speed_table.columnCount() == 3
    assert window.speed_table.item(1, 2).text() == "169"
    assert window.opponents == []


def test_local_obs_import_does_not_persist_password(window, monkeypatch):
    monkeypatch.setattr("champion_assistant.ui.obs_dialog.local_obs_settings", lambda **kwargs: {
        "host": "127.0.0.1", "port": 4466, "password": "private-local-password", "enabled": False})
    window.configure_obs()
    dialog = window.obs_dialog
    dialog.read_local()
    assert dialog.port.value() == 4466 and "尚未启用" in dialog.status.text()
    assert dialog.password.text() == "private-local-password"
    assert not window.settings_path.exists()
    dialog.reject()

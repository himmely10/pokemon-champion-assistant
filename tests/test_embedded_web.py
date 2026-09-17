import http.client
import os
import socket
from threading import Thread

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --no-sandbox")

from PySide6.QtCore import QUrl
from PySide6.QtWebEngineCore import QWebEnginePage

from champion_assistant.ui.web_window import ChampionWebPage, EmbeddedWebHost, WebDesktopWindow
from champion_assistant.webapp import WebServices, create_server


def test_embedded_web_host_owns_and_stops_local_service(tmp_path):
    static = tmp_path / "web"
    static.mkdir()
    (static / "index.html").write_text("<title>Champion Lab</title>", encoding="utf-8")
    services = WebServices(
        teams_path=tmp_path / "teams.sqlite3",
        settings_path=tmp_path / "settings.json",
    )
    host = EmbeddedWebHost(port=0, static_root=static, services=services)

    url = host.start()
    connection = http.client.HTTPConnection("127.0.0.1", host.port, timeout=5)
    connection.request("GET", "/api/health")
    response = connection.getresponse()
    assert response.status == 200
    assert url == f"http://127.0.0.1:{host.port}"
    response.read()
    connection.close()

    owned_thread = host._thread
    host.stop()
    assert host.running is False
    assert not owned_thread.is_alive()
    with pytest.raises(OSError):
        http.client.HTTPConnection("127.0.0.1", host.port, timeout=1).connect()


def test_borrowed_service_does_not_build_duplicate_services(tmp_path):
    static = tmp_path / "web"
    static.mkdir()
    (static / "index.html").write_text("<title>Champion Lab</title>", encoding="utf-8")
    existing_services = WebServices(
        teams_path=tmp_path / "existing.sqlite3",
        settings_path=tmp_path / "existing.json",
    )
    server = create_server(port=0, static_root=static, services=existing_services)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    calls = []
    host = EmbeddedWebHost(
        port=server.server_port,
        static_root=static,
        services_factory=lambda: calls.append(True),
    )
    try:
        assert host.start() == f"http://127.0.0.1:{server.server_port}"
        assert host.running is True
        assert calls == []
        host.stop()
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        connection.request("GET", "/api/health")
        assert connection.getresponse().status == 200
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_other_program_on_requested_port_reports_collision(tmp_path):
    with socket.socket() as blocker:
        blocker.bind(("127.0.0.1", 0))
        blocker.listen()
        host = EmbeddedWebHost(port=blocker.getsockname()[1], static_root=tmp_path)
        with pytest.raises(RuntimeError, match="端口.*已被其他程序占用"):
            host.start()


def test_default_zero_port_gives_each_desktop_window_its_own_host(tmp_path):
    static = tmp_path / "web"
    static.mkdir()
    (static / "index.html").write_text("<title>Champion Lab</title>", encoding="utf-8")
    services = WebServices(
        teams_path=tmp_path / "teams.sqlite3",
        settings_path=tmp_path / "settings.json",
    )
    first = EmbeddedWebHost(port=0, static_root=static, services=services)
    second = EmbeddedWebHost(port=0, static_root=static, services=services)
    try:
        first.start()
        second.start()
        assert first.port != second.port
        first.stop()
        assert second.running
    finally:
        first.stop()
        second.stop()


def test_desktop_window_loads_page_and_stops_its_server(qtbot, tmp_path):
    static = tmp_path / "web"
    static.mkdir()
    (static / "index.html").write_text("<title>Champion Lab</title>", encoding="utf-8")
    services = WebServices(
        teams_path=tmp_path / "teams.sqlite3",
        settings_path=tmp_path / "settings.json",
    )
    window = WebDesktopWindow(static_root=static, port=0, services=services)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(lambda: window.web_view.title() == "Champion Lab", timeout=20000)
    port = window.host.port
    assert window.centralWidget() is window.web_view
    assert window.web_view.url().host() == "127.0.0.1"
    window.close()
    assert not window.host.running
    with pytest.raises(OSError):
        http.client.HTTPConnection("127.0.0.1", port, timeout=1).connect()


def test_desktop_navigation_keeps_local_routes_and_rejects_file_urls(qtbot):
    page = ChampionWebPage()
    navigation = QWebEnginePage.NavigationType.NavigationTypeLinkClicked
    assert page.acceptNavigationRequest(QUrl("http://127.0.0.1:32145/team"), navigation, True)
    assert not page.acceptNavigationRequest(QUrl("file:///C:/Windows/win.ini"), navigation, True)

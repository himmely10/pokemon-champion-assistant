"""Native single-window shell for the local Champion Lab web application."""
from __future__ import annotations

from pathlib import Path
from threading import Thread

from PySide6.QtCore import QUrl
from PySide6.QtGui import QColor, QDesktopServices, QIcon
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QMainWindow

from ..paths import app_paths
from ..version import __version__
from ..webapp import DEFAULT_PORT, WebServices, create_server, is_champion_lab_running


class EmbeddedWebHost:
    """Own a loopback HTTP server for the lifetime of one desktop window."""

    def __init__(self, *, port=DEFAULT_PORT, static_root=None, services=None,
                 services_factory=None):
        self.requested_port = int(port)
        self.static_root = Path(static_root) if static_root else None
        self.services = services
        self.services_factory = services_factory
        self.port = self.requested_port
        self._server = None
        self._thread = None
        self._borrowed = False

    @property
    def running(self):
        if self._borrowed:
            return is_champion_lab_running(self.port)
        return bool(self._thread and self._thread.is_alive())

    def start(self):
        if self.running:
            return self.url
        if self._try_borrow_requested_port():
            return self.url
        try:
            self._server = create_server(
                port=self.requested_port,
                static_root=self.static_root,
                services=self.services,
                services_factory=self.services_factory,
            )
        except OSError as exc:
            if self._try_borrow_requested_port():
                return self.url
            raise RuntimeError(
                f"无法启动本地界面：端口 {self.requested_port} 已被其他程序占用。"
            ) from exc
        self.port = self._server.server_port
        self._thread = Thread(
            target=self._server.serve_forever,
            name="champion-lab-web",
            daemon=True,
        )
        self._thread.start()
        return self.url

    def _try_borrow_requested_port(self):
        if not self.requested_port or not is_champion_lab_running(self.requested_port):
            return False
        self.port = self.requested_port
        self._borrowed = True
        return True

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}"

    def stop(self):
        server, thread = self._server, self._thread
        self._server = None
        self._thread = None
        self._borrowed = False
        if server is None:
            return
        server.shutdown()
        server.server_close()
        if thread:
            thread.join(timeout=3)


class ChampionWebPage(QWebEnginePage):
    """Keep application routes in-window and send external links to the browser."""

    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        host = url.host().lower()
        if not is_main_frame:
            return True
        if url.scheme() in {"http", "https"} and host in {"127.0.0.1", "localhost"}:
            return True
        if url.scheme() in {"http", "https"}:
            QDesktopServices.openUrl(url)
        return False


class WebDesktopWindow(QMainWindow):
    """Display the React workspace as the only desktop application surface."""

    def __init__(self, *, data_dir=None, layout_path=None, static_root=None,
                 port=0, services=None):
        super().__init__()
        paths = app_paths().ensure()
        services_factory = None if services is not None else lambda: WebServices(
            data_dir=data_dir or paths.data,
            layout_path=layout_path,
        )
        self.host = EmbeddedWebHost(
            port=port,
            static_root=static_root,
            services=services,
            services_factory=services_factory,
        )
        url = self.host.start()

        self.setWindowTitle(f"Champion Lab 对战工作台 · v{__version__}")
        self.setWindowIcon(QIcon(str(paths.resource("assets/branding/app.ico"))))
        self.setMinimumSize(960, 680)
        self.resize(1500, 940)

        self.web_view = QWebEngineView(self)
        page = ChampionWebPage(self.web_view)
        page.setBackgroundColor(QColor("#0c1525"))
        self.web_view.setPage(page)
        self.web_view.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalStorageEnabled, True
        )
        self.setCentralWidget(self.web_view)
        self.web_view.setUrl(QUrl(url))

    def closeEvent(self, event):
        self.web_view.stop()
        self.host.stop()
        event.accept()

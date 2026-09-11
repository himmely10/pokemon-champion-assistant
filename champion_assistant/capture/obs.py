"""Read-only OBS WebSocket v5 operations; every client belongs to its calling worker."""
from __future__ import annotations

import base64
import binascii
import io
import json
import logging
import os
from pathlib import Path
import socket

from PIL import Image


class CaptureError(ValueError):
    pass


def local_obs_settings(path=None, *, include_password=False):
    """Read the standard OBS profile without changing OBS or persisting its password."""
    path = Path(path) if path else Path(os.environ.get("APPDATA", "")) / "obs-studio/plugin_config/obs-websocket/config.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        port = raw.get("server_port", 4455)
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("invalid port")
        result = {"host": "127.0.0.1", "port": port, "enabled": raw.get("server_enabled") is True,
                  "auth_required": raw.get("auth_required") is True}
        if include_password:
            result["password"] = raw.get("server_password", "") if result["auth_required"] else ""
        return result
    except (OSError, ValueError):
        return None


def decode_screenshot(data):
    prefix = "data:image/png;base64,"
    if not isinstance(data, str) or not data.startswith(prefix) or len(data) > 60_000_000:
        raise CaptureError("OBS 未返回有效的 PNG 截图。请选择实际的视频源或游戏场景。")
    try:
        content = base64.b64decode(data[len(prefix):], validate=True)
        with Image.open(io.BytesIO(content)) as image:
            if image.format != "PNG" or image.width * image.height > 40_000_000:
                raise CaptureError("截图格式或尺寸不受支持。")
            image.load()
            return image.convert("RGB")
    except (OSError, ValueError, binascii.Error) as exc:
        raise CaptureError("OBS 截图无法解码，请检查采集源是否有画面。") from exc


def load_image(path):
    try:
        with Image.open(path) as image:
            if image.width * image.height > 40_000_000:
                raise CaptureError("图片尺寸过大，请使用完整的游戏截图。")
            image.load()
            return image.convert("RGB")
    except OSError as exc:
        raise CaptureError("无法打开图片，请选择 PNG、JPG、WebP 或 BMP 文件。") from exc


class ObsCapture:
    def __init__(self, factory=None):
        self.factory = factory

    def _client(self, settings):
        if self.factory is None:
            import obsws_python
            # This SDK logs the password at INFO; do not propagate its connection logs.
            logging.getLogger("obsws_python").setLevel(logging.CRITICAL)
            factory = obsws_python.ReqClient
        else:
            factory = self.factory
        host = settings.get("host", "localhost").strip()
        if host.lower() == "localhost":
            host = "127.0.0.1"
        if not host or "/" in host or "://" in host:
            raise CaptureError("地址只填写主机名或 IP，例如 127.0.0.1；不要填写 ws:// 或端口。")
        return factory(host=host, port=int(settings.get("port", 4455)),
                       password=settings.get("password", ""), timeout=5)

    def _execute(self, settings, operation):
        client = None
        try:
            client = self._client(settings)
            version = client.send("GetVersion", raw=True)
            if "GetSourceScreenshot" not in version.get("availableRequests", []):
                raise CaptureError("OBS 不支持源截图，请使用启用 WebSocket v5 的 OBS 版本。")
            return operation(client, version)
        except CaptureError:
            raise
        except ConnectionRefusedError as exc:
            raise CaptureError("OBS 端口拒绝连接。打开 OBS 并不会自动启用 WebSocket：请在「工具 → WebSocket 服务器设置」勾选启用并应用，核对端口。") from exc
        except socket.gaierror as exc:
            raise CaptureError("无法解析 OBS 主机名。同机连接请用 127.0.0.1，端口单独填写。") from exc
        except Exception as exc:
            from obsws_python.error import OBSSDKRequestError, OBSSDKTimeoutError
            from websocket import WebSocketTimeoutException
            if isinstance(exc, (TimeoutError, OBSSDKTimeoutError, WebSocketTimeoutException)):
                message = "OBS 请求超时。请核对地址、端口和网络连接；视频源卡住时可重试。"
            elif isinstance(exc, OBSSDKRequestError):
                message = f"OBS 已连接，但请求失败（代码 {exc.code}）。请重新读取源列表，选择有画面的视频采集设备。"
            elif "authentication" in str(exc).lower() or "identify client" in str(exc).lower():
                message = "已到达 OBS，但密码验证失败。请填写 WebSocket 服务器密码，或点击「读取本机 OBS 设置」。"
            else:
                message = "OBS 连接失败。请核对服务器开关、地址、端口及密码；可点击「读取本机 OBS 设置」重新载入。"
            raise CaptureError(message) from exc
        finally:
            if client is not None:
                try:
                    client.disconnect()
                except Exception:
                    pass

    def sources(self, settings):
        def operation(client, version):
            inputs = client.send("GetInputList", raw=True).get("inputs", [])
            scenes = client.send("GetSceneList", raw=True).get("scenes", [])
            audio_kinds = {"wasapi_input_capture", "wasapi_output_capture", "wasapi_process_output_capture", "pulse_input_capture", "pulse_output_capture", "coreaudio_input_capture", "coreaudio_output_capture"}
            sources = [{"name": r["inputName"], "kind": "源"} for r in inputs if r.get("inputKind") not in audio_kinds]
            sources += [{"name": r["sceneName"], "kind": "场景"} for r in scenes]
            return {"sources": sources, "version": version.get("obsVersion", "未知")}
        return self._execute(settings, operation)

    def screenshot(self, settings):
        source = settings.get("source", "").strip()
        if not source:
            raise CaptureError("请先连接 OBS 并选择 Switch 采集源。")
        def operation(client, version):
            data = client.send("GetSourceScreenshot", {"sourceName": source, "imageFormat": "png"}, raw=True)
            return decode_screenshot(data.get("imageData"))
        return self._execute(settings, operation)

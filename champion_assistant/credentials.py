"""Current-user protected storage for local application credentials."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path


class CredentialStoreError(OSError):
    """Raised when a credential cannot be protected for the current OS user."""


class _DataBlob(ctypes.Structure):
    _fields_ = (("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_byte)))


def _input_blob(value: bytes):
    buffer = ctypes.create_string_buffer(value)
    blob = _DataBlob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    return blob, buffer


def _crypt32():
    if os.name != "nt":
        raise CredentialStoreError("当前系统不支持 Windows 用户凭据加密。")
    return ctypes.windll.crypt32, ctypes.windll.kernel32


def _protect(value: bytes) -> bytes:
    crypt32, kernel32 = _crypt32()
    source, source_buffer = _input_blob(value)
    output = _DataBlob()
    if not crypt32.CryptProtectData(
        ctypes.byref(source), "Champion Lab OBS", None, None, None, 0x01, ctypes.byref(output)
    ):
        raise CredentialStoreError(str(ctypes.WinError()))
    del source_buffer  # keep the backing buffer alive through the native call
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel32.LocalFree(output.data)


def _unprotect(value: bytes) -> bytes:
    crypt32, kernel32 = _crypt32()
    source, source_buffer = _input_blob(value)
    output = _DataBlob()
    if not crypt32.CryptUnprotectData(
        ctypes.byref(source), None, None, None, None, 0x01, ctypes.byref(output)
    ):
        raise CredentialStoreError(str(ctypes.WinError()))
    del source_buffer
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel32.LocalFree(output.data)


class ObsPasswordStore:
    """Persist an OBS password as a DPAPI blob scoped to the current Windows user."""

    HEADER = b"PCA-OBS-DPAPI\x01"

    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> str:
        if not self.path.is_file():
            return ""
        try:
            payload = self.path.read_bytes()
            if not payload.startswith(self.HEADER):
                return ""
            return _unprotect(payload[len(self.HEADER):]).decode("utf-8")
        except (OSError, UnicodeError, CredentialStoreError):
            return ""

    def save(self, password: str) -> None:
        if not isinstance(password, str) or not password:
            raise CredentialStoreError("不能保存空的 OBS 密码。")
        protected = self.HEADER + _protect(password.encode("utf-8"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        try:
            temporary.write_bytes(protected)
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)

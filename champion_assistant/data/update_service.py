"""Install validated public-data packages without altering player data or live analyses."""
from __future__ import annotations
import json
import hashlib
from pathlib import Path
import re
import tempfile
from threading import Event
import time
from urllib.parse import urlparse
import zipfile

import requests

from .storage import atomic_bytes, confined, digest, read_json, save_json, update_lock, validate_bundle
from ..damage import RULE_VERSION

MAX_DOWNLOAD = 512 * 1024 * 1024
MAX_EXTRACTED = 1024 * 1024 * 1024
SCHEMA = 1


def due(state, hours=24, *, now=None):
    if not hours:
        return False
    current = time.time() if now is None else now
    last = state.get('checked_at')
    failed = state.get('failed_at')
    if failed is not None:
        return current < failed or current - failed >= 3600
    return last is None or current < last or current - last >= hours * 3600


def read_package(archive, destination, cancelled=None):
    """Validate the entire archive before extracting into an updater-owned stage."""
    destination = Path(destination)
    with zipfile.ZipFile(archive) as z:
        entries = z.infolist()
        if len(entries) > 20000 or sum(i.file_size for i in entries) > MAX_EXTRACTED:
            raise ValueError('资料包解压大小超过限制')
        if any(i.file_size > 128 * 1024 * 1024 for i in entries):
            raise ValueError('资料包单文件超过限制')
        names = [i.filename for i in entries if not i.is_dir()]
        if len({n.casefold() for n in names}) != len(names) or 'package.json' not in names:
            raise ValueError('资料包清单缺失或路径重复')
        if z.getinfo('package.json').file_size > 1024 * 1024:
            raise ValueError('资料包清单超过限制')
        meta = json.loads(z.read('package.json'))
        if meta.get('schema_version') != SCHEMA or not isinstance(meta.get('files'), dict):
            raise ValueError('不支持的资料包版本')
        if meta.get('rule_version', RULE_VERSION) != RULE_VERSION:
            raise ValueError('资料包要求其他伤害规则版本，请先升级程序')
        catalog_id = meta.get('catalog_id', '')
        if not re.fullmatch(r'data-[a-z0-9-]{1,75}', catalog_id):
            raise ValueError('资料版本标识无效')
        if set(names) != set(meta['files']) | {'package.json'}:
            raise ValueError('资料包内容与清单不一致')
        for name, checksum in meta['files'].items():
            confined(destination, name)
            if not (name.startswith('_versions/' + catalog_id + '/') or name.startswith('_usage/snapshots/')):
                raise ValueError('资料包包含非公共资料目录')
            if Path(name).suffix.lower() not in {'.json', '.png', '.sqlite'}:
                raise ValueError('资料包包含不允许的文件类型')
            if not isinstance(checksum, str) or not re.fullmatch('[a-f0-9]{64}', checksum):
                raise ValueError('资料文件摘要无效')
            if cancelled and cancelled.is_set():
                raise ValueError('用户取消更新')
            content = z.read(name)
            if digest(content) != checksum:
                raise ValueError('资料文件校验失败：' + name)
            atomic_bytes(confined(destination, name), content)
    validate_bundle(destination / '_versions' / catalog_id)
    return meta


class UpdateService:
    def __init__(self, root, channel='', *, cancelled=None, progress=lambda message: None, http=None):
        self.root = Path(root).resolve()
        self.channel = channel.strip()
        self.cancelled = cancelled or Event()
        self.progress = progress
        self.http = http or requests.Session()
        self.control = self.root / '_updates'
        self.control.mkdir(parents=True, exist_ok=True)

    @property
    def state(self):
        try:
            return read_json(self.control / 'state.json')
        except (OSError, ValueError):
            return {}

    def _record(self, **values):
        save_json(self.control / 'state.json', {**self.state, **values})

    def _cancel(self):
        if self.cancelled.is_set():
            raise ValueError('用户取消更新')

    def _chunks(self, url, maximum):
        parsed = urlparse(url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('更新渠道必须是无凭据的 HTTPS 地址')
        size = 0
        with self.http.get(url, stream=True, timeout=(10, 30)) as response:
            response.raise_for_status()
            if urlparse(response.url).scheme != 'https':
                raise ValueError('更新渠道重定向不安全')
            for chunk in response.iter_content(128 * 1024):
                self._cancel()
                size += len(chunk)
                if size > maximum:
                    raise ValueError('下载大小超过限制')
                yield chunk

    def _download(self, url, maximum):
        return b''.join(self._chunks(url, maximum))

    def _download_package(self, url, path, expected):
        checksum = hashlib.sha256()
        with Path(path).open('wb') as stream:
            for chunk in self._chunks(url, MAX_DOWNLOAD):
                stream.write(chunk)
                checksum.update(chunk)
        if checksum.hexdigest() != expected:
            raise ValueError('下载资料包摘要不一致')

    def check(self, *, if_due=False, hours=24):
        with update_lock(self.control):
            return self._check(if_due=if_due, hours=hours)

    def _check(self, *, if_due=False, hours=24):
        self._cancel()
        if if_due and not due(self.state, hours):
            return {'status': 'not_due'}
        if not self.channel:
            return {'status': 'unconfigured', 'message': '未配置在线资料渠道，可导入本地资料包。'}
        try:
            self.progress('正在检查资料版本…')
            manifest = json.loads(self._download(self.channel, 1024 * 1024))
            if manifest.get('schema_version') != SCHEMA:
                raise ValueError('不支持的渠道清单')
            for field in ('version', 'url', 'sha256'):
                if not isinstance(manifest.get(field), str) or not manifest[field]:
                    raise ValueError('渠道清单不完整')
            if not re.fullmatch('[a-f0-9]{64}', manifest['sha256']):
                raise ValueError('渠道摘要无效')
            self._record(checked_at=time.time(), failed_at=None, available=manifest)
            status = 'current' if self.state.get('installed') == manifest['version'] else 'available'
            return {'status': status, 'manifest': manifest}
        except Exception:
            self._record(failed_at=time.time())
            raise

    def sync(self, *, if_due=False, hours=24):
        with update_lock(self.control):
            return self._sync(if_due=if_due, hours=hours)

    def _sync(self, *, if_due=False, hours=24):
        result = self._check(if_due=if_due, hours=hours)
        if result['status'] != 'available':
            return result
        meta = result['manifest']
        try:
            self.progress('正在下载资料包…')
            with tempfile.TemporaryDirectory(prefix='download-', dir=self.control) as temp:
                path = Path(temp) / 'package.zip'
                self._download_package(meta['url'], path, meta['sha256'])
                return self._install(path, version=meta['version'])
        except Exception:
            self._record(failed_at=time.time())
            raise

    def install(self, archive, *, version=None):
        self._cancel()
        with update_lock(self.control):
            return self._install(archive, version=version)

    def _install(self, archive, *, version=None):
        from .snapshot import publish_release
        self.progress('正在校验资料，当前分析保持原版本…')
        with tempfile.TemporaryDirectory(prefix='install-', dir=self.control) as temp:
            stage = Path(temp)
            meta = read_package(archive, stage, self.cancelled)
            if version is not None and version != meta.get('version'):
                raise ValueError('渠道版本与资料包版本不一致，未切换资料')
            self._cancel()
            catalog_id = meta['catalog_id']
            target = confined(self.root, '_versions/' + catalog_id)
            if target.exists():
                validate_bundle(target)
                if digest((target / 'manifest.json').read_bytes()) != digest((stage / '_versions' / catalog_id / 'manifest.json').read_bytes()):
                    raise ValueError('相同版本 ID 的内容不一致')
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                (stage / '_versions' / catalog_id).rename(target)
            for name in meta['files']:
                if name.startswith('_usage/'):
                    dest = confined(self.root, name)
                    content = confined(stage, name).read_bytes()
                    if dest.exists() and digest(dest.read_bytes()) != digest(content):
                        raise ValueError('已存在的采用率版本内容冲突')
                    atomic_bytes(dest, content)
            self._cancel()
            # Publication is short and cannot be cancelled halfway through.
            release = publish_release(self.root, catalog_id=catalog_id, usage_pointer=meta.get('usage_pointer', {}))
            self._record(installed=version or meta.get('version') or catalog_id, installed_at=time.time(), failed_at=None)
            return {'status': 'updated', 'release': release, 'message': '资料已就绪，下次分析使用新版本。'}

    def validate(self):
        from .snapshot import SnapshotManager
        value = SnapshotManager(self.root).candidate()
        return {'status': 'valid', 'snapshot': value.snapshot_id}

    def rollback(self):
        from .snapshot import rollback_release
        with update_lock(self.control):
            result = rollback_release(self.root)
            self._record(installed=None)
            return {'status': 'updated', 'release': result, 'message': '已恢复上一有效资料，下次分析生效。'}

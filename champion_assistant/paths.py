"""Resolve immutable application resources separately from writable player data."""
from __future__ import annotations

from dataclasses import dataclass
from contextlib import closing
from pathlib import Path
import json
import os
import shutil
import sqlite3
import sys
import uuid


@dataclass(frozen=True)
class AppPaths:
    resources: Path
    user: Path
    cache: Path
    installed: bool = False

    def resource(self, relative):
        root = self.resources.resolve()
        result = (root / relative).resolve()
        if not result.is_relative_to(root):
            raise ValueError('程序资源路径越界')
        return result

    @property
    def teams(self):
        return self.user / 'teams.sqlite3'

    @property
    def settings(self):
        return self.user / 'local_ui.json' if self.installed else self.resources / 'config/local_ui.json'

    @property
    def data(self):
        return (self.user if self.installed else self.resources) / 'pokemon'

    def ensure(self):
        self.user.mkdir(parents=True, exist_ok=True)
        self.cache.mkdir(parents=True, exist_ok=True)
        if self.installed and not self.data.exists():
            # An interrupted bootstrap never exposes a half-copied baseline.
            temp = self.user / ('baseline-' + uuid.uuid4().hex)
            try:
                shutil.copytree(self.resource('pokemon'), temp)
                from .data.storage import resolve_dataset
                resolve_dataset(temp)
                try:
                    temp.rename(self.data)
                except FileExistsError:
                    pass  # Another app instance completed the same bootstrap.
            finally:
                if temp.exists() and temp.resolve().is_relative_to(self.user.resolve()):
                    shutil.rmtree(temp)
        return self


def app_paths():
    installed = bool(getattr(sys, 'frozen', False))
    resources = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    override = os.environ.get('CHAMPION_USER_DIR')
    if installed:
        from PySide6.QtCore import QStandardPaths
        base = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation))
        cache = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericCacheLocation))
        user = Path(override) if override else base / 'PokemonChampionAssistant'
        return AppPaths(resources, user, user / 'cache' if override else cache / 'PokemonChampionAssistant', True)
    user = Path(override) if override else resources / 'user_data'
    return AppPaths(resources, user, resources / 'artifacts/desktop')


def node_executable():
    paths = app_paths()
    bundled = paths.resource('runtime/node.exe')
    if bundled.is_file():
        return str(bundled)
    if not paths.installed:
        node = shutil.which('node')
        if node:
            return node
    raise ValueError('缺少内置 Node 伤害计算组件，请重新安装完整版本。')


def migrate_legacy(source, paths=None):
    """Import without deleting sources or overwriting existing personal data."""
    paths = paths or app_paths()
    source = Path(source).resolve()
    paths.user.mkdir(parents=True, exist_ok=True)
    result = {'imported': [], 'existing': []}
    for name, old, target in (
        ('teams', source / 'user_data/teams.sqlite3', paths.teams),
        ('settings', source / 'config/local_ui.json', paths.settings),
    ):
        if not old.exists():
            continue
        if target.exists():
            result['existing'].append(name)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(target.name + '.' + uuid.uuid4().hex + '.import')
        try:
            if name == 'teams':
                with closing(sqlite3.connect(old.as_uri() + '?mode=ro', uri=True)) as src, closing(sqlite3.connect(temp)) as dst:
                    src.backup(dst)
                    if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                        raise ValueError('旧队伍库校验失败，未导入。')
                    if dst.execute('PRAGMA user_version').fetchone()[0] not in (0, 1):
                        raise ValueError('旧队伍库版本不兼容，未导入。')
            else:
                data = json.loads(old.read_text(encoding='utf-8'))
                if not isinstance(data, dict):
                    raise ValueError('旧设置格式无效')
                if isinstance(data.get('obs'), dict):
                    data['obs'].pop('password', None)
                data.pop('password', None)
                temp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            # Keep a recovery copy; Windows rename refuses a racing existing target.
            shutil.copy2(temp, temp.with_suffix('.backup'))
            if target.exists():
                result['existing'].append(name)
            else:
                temp.rename(target)
                result['imported'].append(name)
        finally:
            temp.unlink(missing_ok=True)
    return result

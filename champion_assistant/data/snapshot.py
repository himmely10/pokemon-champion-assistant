"""Atomic reference releases and strong, process-local analysis version leases."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
import weakref
from threading import RLock

from .references import ReferenceCatalog
from .storage import confined, digest, json_bytes, read_json, resolve_dataset, save_json, validate_bundle
from .usage import load_usage_snapshot
from ..damage import RULE_VERSION
from ..recognition import DEFAULT_LAYOUT, ALGORITHM_VERSION

_readers = weakref.WeakValueDictionary()
_reader_lock = RLock()


def _lease(snapshot):
    with _reader_lock:
        _readers[id(snapshot)] = snapshot
    return snapshot


def _version_token(descriptor, layout_hash):
    return digest(json_bytes({'release': descriptor, 'layout': layout_hash, 'rules': RULE_VERSION,
                              'recognition_algorithm': ALGORITHM_VERSION}))


@dataclass(eq=False)
class AnalysisSnapshot:
    token: str
    descriptor: dict
    catalog: ReferenceCatalog
    layout_path: Path
    layout_hash: str

    @property
    def data_dir(self):
        return self.catalog.root

    @property
    def snapshot_id(self):
        return self.token


def _legacy_descriptor(root):
    static = resolve_dataset(root)
    manifest = static / 'manifest.json'
    catalog = {'path': static.relative_to(root).as_posix() or '.',
               'bundle_id': static.name if manifest.exists() else 'legacy',
               'manifest_sha256': digest(manifest.read_bytes()) if manifest.exists() else None}
    usage_path = root / '_usage/current.json'
    return {'schema_version': 1, 'catalog': catalog,
            'usage': read_json(usage_path) if usage_path.exists() else None,
            'rule_version': RULE_VERSION}


def _load_descriptor(root, descriptor, layout_path):
    if descriptor.get('schema_version') != 1:
        raise ValueError('分析资料组合 schema 不受支持；保留上次分析。')
    if descriptor.get('rule_version') != RULE_VERSION:
        raise ValueError('资料组合与当前伤害规则版本不兼容；保留上次分析。')
    static_info = descriptor['catalog']
    static = root if static_info['path'] == '.' else confined(root, static_info['path'])
    manifest_path = static / 'manifest.json'
    if manifest_path.exists() and not static_info.get('manifest_sha256'):
        raise ValueError('资料组合缺少静态清单校验信息。')
    if not manifest_path.exists() and static_info.get('bundle_id') != 'legacy':
        raise ValueError('资料组合缺少静态清单。')
    if static_info.get('manifest_sha256'):
        if digest(manifest_path.read_bytes()) != static_info['manifest_sha256']:
            raise ValueError('组合中的静态资料清单校验失败。')
        manifest = read_json(manifest_path)
        if manifest.get('bundle_id') != static_info['bundle_id']:
            raise ValueError('组合中的静态资料身份不符。')
        if manifest.get('rule_version', RULE_VERSION) != RULE_VERSION:
            raise ValueError('静态资料与当前规则版本不兼容。')
        if manifest.get('reference_schema', 1) != 1:
            raise ValueError('静态资料 schema 不受支持。')
        validate_bundle(static)
    usage_info = descriptor.get('usage')
    usage = {}
    if usage_info:
        relative = usage_info.get('database_file') or usage_info['file']
        checksum = usage_info.get('database_sha256') if usage_info.get('database_file') else usage_info['sha256']
        path = confined(root / '_usage', relative)
        if digest(path.read_bytes()) != checksum:
            raise ValueError('组合中的采用率快照校验失败。')
        usage = load_usage_snapshot(path)
        if usage_info.get('database_file'):
            evidence = confined(root / '_usage', usage_info['file'])
            if digest(evidence.read_bytes()) != usage_info['sha256']:
                raise ValueError('采用率来源快照校验失败。')
            if load_usage_snapshot(evidence) != usage:
                raise ValueError('采用率数据库与来源快照不一致。')
        if usage.get('schema_version') != 1 or usage.get('format') != 'double':
            raise ValueError('采用率快照 schema 或对战模式不兼容。')
        compatible = usage_info.get('catalog_id')
        if compatible and compatible != static_info['bundle_id']:
            raise ValueError('采用率快照与静态资料版本不兼容。')
    catalog = ReferenceCatalog(static, usage_dir=root / '_usage', usage_snapshot=usage)
    layout_hash = digest(layout_path.read_bytes())
    token = _version_token(descriptor, layout_hash)
    catalog.snapshot_token = token
    snapshot = AnalysisSnapshot(token, deepcopy(descriptor), catalog, layout_path, layout_hash)
    return _lease(snapshot)


class SnapshotManager:
    def __init__(self, root, layout_path=None):
        self.root = Path(root).resolve()
        self.layout_path = Path(layout_path or DEFAULT_LAYOUT)
        self.current = None
        self._catalogs = weakref.WeakValueDictionary()

    def candidate(self):
        # One read of the combination pointer; component current files are ignored
        # once a release exists. A failed candidate never mutates current.
        pointer = self.root / 'release.json'
        descriptor = read_json(pointer) if pointer.exists() else _legacy_descriptor(self.root)
        layout_hash = digest(self.layout_path.read_bytes())
        token = _version_token(descriptor, layout_hash)
        catalog = self._catalogs.get(token)
        if catalog is not None:
            # Each analysis owns a separate lease even when validated immutable
            # catalog data is reused. Closed old windows can release their version.
            snapshot = AnalysisSnapshot(token, deepcopy(descriptor), catalog, self.layout_path, layout_hash)
            return _lease(snapshot)
        candidate = _load_descriptor(self.root, descriptor, self.layout_path)
        self._catalogs[candidate.token] = candidate.catalog
        return candidate

    def initial(self):
        try:
            return self.candidate()
        except (OSError, ValueError, KeyError):
            pointer = read_json(self.root / 'release.json')
            for release_id in reversed(pointer.get('history', [])):
                try:
                    descriptor = read_json(confined(self.root, f'_releases/{release_id}.json'))
                    result = _load_descriptor(self.root, descriptor, self.layout_path)
                    result.catalog.usage_error = '最新组合不可用，启动时恢复上一有效资料组合。'
                    return result
                except (OSError, ValueError, KeyError):
                    continue
            raise ValueError('没有可读取的有效资料组合，请回滚或重新导入资料包。')


def publish_release(root, catalog_id=None, usage_pointer=None, *, layout_path=None):
    """Validate both components before one atomic pointer replacement.

    UpdateService owns the updater lock; this method does not take a nested lock.
    Existing analyses own their old snapshot and are unaffected by publication.
    """
    root = Path(root).resolve()
    old = read_json(root / 'release.json') if (root / 'release.json').exists() else None
    legacy = _legacy_descriptor(root) if not old else None
    descriptor = ({key: deepcopy(old[key]) for key in ('schema_version', 'catalog', 'usage', 'rule_version')}
                  if old else deepcopy(legacy))
    if catalog_id is not None:
        static = confined(root, f'_versions/{catalog_id}')
        descriptor['catalog'] = {'path': static.relative_to(root).as_posix(), 'bundle_id': catalog_id,
                                 'manifest_sha256': digest((static / 'manifest.json').read_bytes())}
    if usage_pointer is not None:
        descriptor['usage'] = deepcopy(usage_pointer)
    _load_descriptor(root, descriptor, Path(layout_path or DEFAULT_LAYOUT))
    release_id = 'release-' + digest(json_bytes(descriptor))[:24]
    if old and old.get('release_id') == release_id:
        return old
    history = list(old.get('history', [])) if old else []
    if old and old.get('release_id'):
        history.append(old['release_id'])
    elif not old:
        # First upgrade must retain the valid JSON-era combination, even though
        # it did not previously have a release.json/history entry.
        try:
            _load_descriptor(root, legacy, Path(layout_path or DEFAULT_LAYOUT))
        except (OSError, ValueError, KeyError):
            pass
        else:
            previous_id = 'release-' + digest(json_bytes(legacy))[:24]
            if previous_id != release_id:
                legacy.update(release_id=previous_id, history=[])
                save_json(confined(root, f'_releases/{previous_id}.json'), legacy)
                history.append(previous_id)
    descriptor.update(release_id=release_id, history=list(dict.fromkeys(history)))
    save_json(confined(root, f'_releases/{release_id}.json'), descriptor)
    save_json(root / 'release.json', descriptor)
    return descriptor


def rollback_release(root, *, layout_path=None):
    root = Path(root).resolve()
    current = read_json(root / 'release.json')
    for release_id in reversed(current.get('history', [])):
        try:
            candidate = read_json(confined(root, f'_releases/{release_id}.json'))
            _load_descriptor(root, candidate, Path(layout_path or DEFAULT_LAYOUT))
        except (OSError, ValueError, KeyError):
            continue
        save_json(root / 'release.json', candidate)
        return candidate
    raise ValueError('没有可恢复的有效资料组合。')


def leased_paths():
    """Cleanup callers must keep these live-reader paths plus current/previous releases.

    No automatic deletion is performed here; inability to remove a Windows-open
    version is harmless and cleanup can retry after the last reader is gone.
    """
    paths = set()
    with _reader_lock:
        readers = list(_readers.values())
    for snapshot in readers:
        paths.add(snapshot.data_dir.resolve())
        usage = snapshot.descriptor.get('usage')
        if usage:
            paths.add(confined(snapshot.catalog.usage_dir, usage.get('database_file') or usage['file']))
    return paths

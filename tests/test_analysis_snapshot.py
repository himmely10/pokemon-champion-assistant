"""Analysis versions remain pinned until a complete new result is accepted."""
import json
import os
from copy import deepcopy

import pytest
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from champion_assistant.data.snapshot import SnapshotManager, publish_release, rollback_release, leased_paths
from champion_assistant.data.storage import save_json, read_json, digest, make_bundle, publish
from champion_assistant.recognition import PROJECT_ROOT


def test_initial_snapshot_pins_usage_without_reloading(monkeypatch):
    manager = SnapshotManager(PROJECT_ROOT / 'pokemon')
    snapshot = manager.candidate()
    original = deepcopy(snapshot.catalog.usage)
    monkeypatch.setattr('champion_assistant.data.references.load_usage', lambda _: {'changed': True})
    snapshot.catalog.reload_usage()
    assert snapshot.catalog.usage == original
    assert snapshot.token and snapshot.catalog.snapshot_token == snapshot.token


def test_incompatible_release_does_not_replace_current(tmp_path):
    manager = SnapshotManager(PROJECT_ROOT / 'pokemon')
    old = manager.candidate()
    manager.current = old
    manager.root = tmp_path
    save_json(tmp_path / 'release.json', {'schema_version': 999})
    with pytest.raises(ValueError):
        manager.candidate()
    assert manager.current is old


@pytest.fixture
def releases(tmp_path):
    record = {'name': '巨钳螳螂', 'directory': '巨钳螳螂', 'record_id': 'opgg:scizor',
              'species_name': '巨钳螳螂', 'source_slug': 'scizor', 'opgg_key': 'scizor',
              'dex_number': 212, 'types': ['bug', 'steel'], 'images': {}, 'recognition_ready': False,
              'base_stats': dict(zip(('hp', 'attack', 'defense', 'special_attack', 'special_defense', 'speed'),
                                     (70, 130, 100, 55, 80, 65))), 'base_stat_total': 500}
    bundles = []
    usage = []
    for number in (1, 2):
        index = {'schema_version': 1, 'pokemon': [record], 'species_count': 1, 'form_count': 1, 'generated_at': str(number)}
        bundle = make_bundle(tmp_path, index, tmp_path, {'groups': []})
        bundles.append(bundle)
        path = tmp_path / '_usage/snapshots' / f'usage-{number}.json'
        save_json(path, {'schema_version': 1, 'format': 'double', 'season': f'm-{number}', 'pokemon': {}})
        usage.append({'file': f'snapshots/usage-{number}.json', 'sha256': digest(path.read_bytes())})
    publish(tmp_path, bundles[0])
    save_json(tmp_path / '_usage/current.json', usage[0])
    return tmp_path, bundles, usage


def test_atomic_combination_ignores_component_pointer_races_and_rolls_back(releases):
    root, bundles, usage = releases
    first = publish_release(root, bundles[0].name, usage[0])
    manager = SnapshotManager(root)
    old = manager.candidate()
    manager.current = old
    publish(root, bundles[1])
    save_json(root / '_usage/current.json', usage[1])
    between = manager.candidate()
    assert between.token == old.token
    assert between.catalog.usage['season'] == 'm-1'
    second = publish_release(root, bundles[1].name, usage[1])
    new = manager.candidate()
    assert new.catalog.bundle_id == bundles[1].name
    assert new.catalog.usage['season'] == 'm-2'
    assert old.catalog.bundle_id == bundles[0].name and old.catalog.usage['season'] == 'm-1'
    assert manager.current is old
    assert old.data_dir in leased_paths()
    assert second['history'] == [first['release_id']]
    assert rollback_release(root)['release_id'] == first['release_id']
    assert manager.candidate().token == old.token


@pytest.mark.parametrize('defect', ['hash', 'schema', 'rule', 'missing', 'usage'])
def test_bad_candidate_keeps_pointer_and_old_reader(releases, defect):
    root, bundles, usage = releases
    first = publish_release(root, bundles[0].name, usage[0])
    manager = SnapshotManager(root)
    old = manager.candidate()
    bad = deepcopy(first)
    if defect == 'hash': bad['catalog']['manifest_sha256'] = '0' * 64
    elif defect == 'schema': bad['schema_version'] = 2
    elif defect == 'rule': bad['rule_version'] = 'incompatible'
    elif defect == 'missing': bad['catalog']['path'] = '_versions/absent'
    else: bad['usage']['sha256'] = '0' * 64
    save_json(root / 'release.json', bad)
    with pytest.raises((ValueError, OSError)):
        manager.candidate()
    assert old.catalog.usage['season'] == 'm-1'


def test_failed_publication_never_activates_broken_usage(releases):
    root, bundles, usage = releases
    publish_release(root, bundles[0].name, usage[0])
    original = (root / 'release.json').read_bytes()
    with pytest.raises(ValueError):
        publish_release(root, bundles[1].name, {**usage[1], 'sha256': 'bad'})
    assert (root / 'release.json').read_bytes() == original


def test_initial_recovers_previous_valid_combination(releases):
    root, bundles, usage = releases
    publish_release(root, bundles[0].name, usage[0])
    latest = publish_release(root, bundles[1].name, usage[1])
    latest['schema_version'] = 99
    save_json(root / 'release.json', latest)
    restored = SnapshotManager(root).initial()
    assert restored.catalog.bundle_id == bundles[0].name
    assert '恢复' in restored.catalog.usage_error


def test_first_upgrade_can_rollback_to_legacy_json(releases):
    root, bundles, usage = releases
    published = publish_release(root, bundles[1].name, usage[1])
    assert len(published['history']) == 1
    rollback_release(root)
    restored = SnapshotManager(root).candidate()
    assert restored.catalog.bundle_id == bundles[0].name
    assert restored.catalog.usage['season'] == 'm-1'


def test_same_version_reuses_validation_but_has_independent_lease(releases, monkeypatch):
    root, _, _ = releases
    manager = SnapshotManager(root)
    first = manager.candidate()
    monkeypatch.setattr('champion_assistant.data.snapshot._load_descriptor',
                        lambda *args: pytest.fail('unchanged version was revalidated'))
    second = manager.candidate()
    assert second is not first and second.catalog is first.catalog
    assert second.token == first.token


def test_last_reader_releases_old_version_lease(releases):
    import gc
    root, bundles, usage = releases
    publish_release(root, bundles[0].name, usage[0])
    manager = SnapshotManager(root)
    old = manager.candidate()
    publish_release(root, bundles[1].name, usage[1])
    current = manager.candidate()
    assert old.data_dir in leased_paths()
    del old
    gc.collect()
    assert bundles[0] not in leased_paths()
    assert current.data_dir in leased_paths()


def test_unmapped_form_keeps_reference_and_only_blocks_its_damage(releases):
    from champion_assistant.damage import DamageService
    root, bundles, usage = releases
    record = read_json(bundles[0] / 'index.json')['pokemon'][0]
    future = {**record, 'name': '测试未来形态', 'directory': '测试未来形态',
              'record_id': 'opgg:future-form', 'source_slug': 'future-form', 'opgg_key': 'future-form'}
    bundle = make_bundle(root, {'schema_version': 1, 'pokemon': [record, future],
                               'species_count': 1, 'form_count': 2}, root, {'groups': []})
    publish_release(root, bundle.name, usage[0])
    catalog = SnapshotManager(root).candidate().catalog
    service = DamageService(catalog)
    assert catalog.record_for_name(future['name'])['base_stats'] == record['base_stats']
    assert service.species(record) == 'Scizor'
    with pytest.raises(ValueError, match='尚未映射'):
        service.species(future)


@pytest.fixture
def snapshot_window(qtbot, releases, tmp_path):
    from threading import Event
    from PySide6.QtCore import QObject, Signal, Slot
    from champion_assistant.ui.main_window import MainWindow
    class DeferredWorker(QObject):
        finished = Signal(int, str, object, str)
        def __init__(self, *args):
            super().__init__()
            self.cancelled = Event()
            self.root = args[0]
        @Slot(int, str, object)
        def run(self, *args):
            pass
    root, bundles, usage = releases
    publish_release(root, bundles[0].name, usage[0])
    window = MainWindow(root, settings_path=tmp_path / 'settings.json', worker_factory=DeferredWorker)
    window.damage_teams = lambda catalog=None: []
    qtbot.addWidget(window)
    yield window
    window.busy = False
    window.close()


def result_for(snapshot):
    from PIL import Image
    return {'snapshot': snapshot, 'image': Image.new('RGB', (1600, 900)),
            'recognition': {'snapshot_token': snapshot.token, 'recognized_count': 6,
                            'elapsed_seconds': 0.01,
                            'opponent': [{'slot': i + 1, 'status': 'recognized', 'name': '巨钳螳螂'}
                                         for i in range(6)]}}


def test_ui_switches_complete_result_and_old_damage_window_stays_pinned(snapshot_window, releases):
    window = snapshot_window
    root, bundles, usage = releases
    old = window.snapshot
    window.show_record(old.catalog.record_for_name('巨钳螳螂'))
    window.open_damage()
    old_dialog = window.damage_dialog
    publish_release(root, bundles[1].name, usage[1])
    window.refresh_usage_view()
    assert window.catalog is old.catalog and old_dialog.service.catalog is old.catalog
    window.open_image('new.png')
    new = SnapshotManager(root).candidate()
    window._finished(window.revision, 'file', result_for(new), '')
    assert window.snapshot is new
    assert window.catalog.usage['season'] == 'm-2'
    assert old_dialog.service.catalog.usage['season'] == 'm-1'
    assert window.damage_dialog is None
    window.open_damage()
    assert window.damage_dialog is not old_dialog
    assert window.damage_dialog.service.catalog is new.catalog
    assert window.worker.root == root


def test_quick_second_image_discards_old_result_without_clearing_current(snapshot_window, releases):
    window = snapshot_window
    original = window.snapshot
    window.open_image('first.png')
    first = window.revision
    window.open_image('second.png')
    window._finished(first, 'file', result_for(original), '')
    second = window.revision
    assert second > first and window.busy
    window._finished(first, 'file', result_for(original), '')
    assert window.busy and window.last_result is None
    window._finished(second, 'file', result_for(original), '')
    assert not window.busy and window.last_result['snapshot_token'] == original.token


def test_worker_publishes_matching_snapshot_and_preserves_old_on_candidate_error(releases, monkeypatch):
    from PIL import Image
    from champion_assistant.ui.worker import AnalysisWorker
    root, bundles, usage = releases
    publish_release(root, bundles[0].name, usage[0])
    class Recognizer:
        def __init__(self, data_dir, layout_path):
            self.root = data_dir
        def recognize(self, image):
            return {'opponent': [], 'recognized_count': 0}, image, []
    monkeypatch.setattr('champion_assistant.ui.worker.OpponentRecognizer', Recognizer)
    monkeypatch.setattr('champion_assistant.ui.worker.load_image', lambda _: Image.new('RGB', (1600, 900)))
    worker = AnalysisWorker(root)
    results = []
    worker.finished.connect(lambda *args: results.append(args))
    worker.run(1, 'file', 'sample.png')
    old = worker.snapshots.current
    assert results[-1][2]['recognition']['snapshot_token'] == old.token
    broken = read_json(root / 'release.json')
    broken['rule_version'] = 'bad'
    save_json(root / 'release.json', broken)
    worker.run(2, 'file', 'sample.png')
    assert results[-1][2] is None and results[-1][3]
    assert worker.snapshots.current is old


def test_publication_during_capture_only_affects_next_analysis(releases, monkeypatch):
    from PIL import Image
    from champion_assistant.ui.worker import AnalysisWorker
    root, bundles, usage = releases
    publish_release(root, bundles[0].name, usage[0])
    class Recognizer:
        def __init__(self, *args): pass
        def recognize(self, image): return {}, image, []
    class Obs:
        def screenshot(self, payload):
            publish_release(root, bundles[1].name, usage[1])
            return Image.new('RGB', (1600, 900))
    monkeypatch.setattr('champion_assistant.ui.worker.OpponentRecognizer', Recognizer)
    worker = AnalysisWorker(root, obs=Obs())
    worker.run(1, 'obs', {})
    assert worker.snapshots.current.catalog.bundle_id == bundles[0].name
    assert worker.snapshots.current.catalog.usage['season'] == 'm-1'
    worker.run(2, 'obs', {})
    assert worker.snapshots.current.catalog.bundle_id == bundles[1].name
    assert worker.snapshots.current.catalog.usage['season'] == 'm-2'

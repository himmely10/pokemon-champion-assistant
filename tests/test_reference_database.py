"""SQLite publication contracts, including exact semantics and immutable readers."""
import copy
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from champion_assistant.data.sqlite_catalog import (
    build_catalog_database, build_usage_database, read_catalog_database,
    read_usage_database, validate_catalog_database, validate_usage_database,
)
from champion_assistant.data.storage import read_json, resolve_dataset
from champion_assistant.paths import app_paths


@pytest.fixture
def facts():
    record = {'record_id': 'opgg:scizor', 'name': '巨钳螳螂', 'directory': '巨钳螳螂',
              'dex_number': 212, 'species_name': '巨钳螳螂', 'source_slug': 'scizor',
              'opgg_key': 'scizor', 'types': ['bug', 'steel'],
              'base_stats': dict(zip(('hp', 'attack', 'defense', 'special_attack', 'special_defense', 'speed'), (70, 130, 100, 55, 80, 65))),
              'base_stat_total': 500, 'images': {}, 'recognition_ready': False}
    index = {'pokemon': [record], 'species_count': 1, 'form_count': 1}
    source = [{'key': 'scizor', 'moves': ['bullet-punch'], 'abilities': ['technician']}]
    moves = {'bullet-punch': {'key': 'bullet-punch', 'name': '子弹拳', 'category': 'physical',
                             'type': 'steel', 'power': 40, 'accuracy': None, 'description': '先制攻击', 'isAvailable': True}}
    return index, source, moves, {'groups': []}


def test_exact_catalog_roundtrip_and_readonly_threads(tmp_path, facts):
    path = tmp_path / 'catalog.sqlite'
    build_catalog_database(path, *facts)
    expected = {'index': facts[0], 'source': facts[1], 'moves': facts[2], 'policy': facts[3]}
    assert read_catalog_database(path) == expected
    with ThreadPoolExecutor(2) as pool:
        assert list(pool.map(read_catalog_database, [path, path])) == [expected, expected]
    with pytest.raises(ValueError, match='存在'):
        build_catalog_database(path, *facts)
    assert read_catalog_database(path) == expected


@pytest.mark.parametrize('defect', ['duplicate', 'missing_type', 'missing_move', 'bad_mega'])
def test_reject_incomplete_domain(tmp_path, facts, defect):
    index, source, moves, policy = copy.deepcopy(facts)
    if defect == 'duplicate': index['pokemon'].append(copy.deepcopy(index['pokemon'][0]))
    if defect == 'missing_type': index['pokemon'][0]['types'] = []
    if defect == 'missing_move': source[0]['moves'].append('not-found')
    if defect == 'bad_mega': index['pokemon'][0]['mega_form_ids'] = ['absent']
    with pytest.raises(ValueError):
        build_catalog_database(tmp_path / 'catalog.sqlite', index, source, moves, policy)
    assert not (tmp_path / 'catalog.sqlite').exists()


def test_usage_null_rate_and_independent_spreads(tmp_path):
    snapshot = {'schema_version': 1, 'format': 'double', 'season': 'm-6', 'pokemon': {
        'scizor': {'pokemon_key': 'scizor', 'statistics_key': 'scizor', 'season': 'm-6', 'format': 'double',
                   'moves': {'bullet-punch': None}, 'training': [{'points': dict(zip(
                       ('hp', 'attack', 'defense', 'special_attack', 'special_defense', 'speed'), (2,32,0,0,0,32))),
                       'usage_percent': 14.6}], 'natures': [{'key': 'adamant', 'usage_percent': 40}]}}}
    path = tmp_path / 'usage.sqlite'
    build_usage_database(path, snapshot)
    assert read_usage_database(path) == snapshot
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT usage_percent FROM usage_moves').fetchone()[0] is None
        conn.execute('PRAGMA user_version=99')
    with pytest.raises(ValueError, match='schema'):
        validate_usage_database(path)


def test_corrupt_and_inconsistent_database_rejected(tmp_path, facts):
    path = tmp_path / 'catalog.sqlite'
    path.write_bytes(b'not sqlite')
    with pytest.raises(ValueError): validate_catalog_database(path)
    path.unlink()
    build_catalog_database(path, *facts)
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE form_types SET type='fire'")
    with pytest.raises(ValueError): validate_catalog_database(path)


def test_real_full_catalog_equivalence(tmp_path):
    root = resolve_dataset(app_paths().resource('pokemon'))
    facts = (read_json(root/'index.json'), read_json(root/'source_catalog.json'),
             read_json(root/'moves.json'), read_json(root/'recognition_identity_groups.json'))
    path = tmp_path/'catalog.sqlite'
    counts = build_catalog_database(path, *facts)
    result = read_catalog_database(path)
    assert result == dict(zip(('index', 'source', 'moves', 'policy'), facts))
    assert counts['forms'] == len(facts[0]['pokemon'])
    assert counts['pending_assets'] > 0


def test_real_usage_equivalence(tmp_path):
    from champion_assistant.data.usage import load_usage
    snapshot = load_usage(app_paths().resource('pokemon/_usage'))
    path = tmp_path/'usage.sqlite'
    counts = build_usage_database(path, snapshot)
    assert read_usage_database(path) == snapshot
    assert counts['entries'] == len(snapshot['pokemon'])
    assert counts['spreads'] > 0


def test_sql_authority_and_fixed_usage(tmp_path, facts):
    from champion_assistant.data.references import ReferenceCatalog
    from champion_assistant.data.storage import save_json
    build_catalog_database(tmp_path/'catalog.sqlite', *facts)
    # No manifest here: a direct database test. JSON evidence is deliberately stale.
    save_json(tmp_path/'index.json', {'pokemon': []})
    usage = {'pokemon': {}}
    catalog = ReferenceCatalog(tmp_path, usage_snapshot=usage)
    assert catalog.record_for_name('巨钳螳螂')['base_stats']['speed'] == 65
    usage['pokemon']['unexpected'] = {}
    catalog.reload_usage()
    assert catalog.usage == {'pokemon': {}}
    damaging, status, _ = catalog.learnset(catalog.records[0])
    assert len(damaging) == 1 and not status
    assert damaging[0]['usage_percent'] is None


def test_two_readers_and_new_build_do_not_mutate_old(tmp_path, facts):
    old, new = tmp_path/'old.sqlite', tmp_path/'new.sqlite'
    build_catalog_database(old, *facts)
    before = old.read_bytes()
    changed = copy.deepcopy(facts)
    changed[0]['pokemon'][0]['base_stats']['speed'] += 1
    changed[0]['pokemon'][0]['base_stat_total'] += 1
    with ThreadPoolExecutor(3) as pool:
        readers = [pool.submit(read_catalog_database, old) for _ in range(2)]
        builder = pool.submit(build_catalog_database, new, *changed)
        assert all(f.result()['index'] == facts[0] for f in readers)
        builder.result()
    assert old.read_bytes() == before
    assert read_catalog_database(new)['index'] == changed[0]


def test_foreign_key_and_same_name_identity(tmp_path, facts):
    index, source, moves, policy = copy.deepcopy(facts)
    other = copy.deepcopy(index['pokemon'][0])
    other['record_id'] = 'other-source:212'
    other['directory'] = 'other'
    index['pokemon'].append(other)
    index['form_count'] = 2
    path = tmp_path/'catalog.sqlite'
    build_catalog_database(path, index, source, moves, policy)
    assert len(read_catalog_database(path)['index']['pokemon']) == 2
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE form_types SET form_id='missing' WHERE form_id='opgg:scizor'")
    with pytest.raises(ValueError, match='外键'):
        validate_catalog_database(path)

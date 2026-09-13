"""Immutable, validated SQLite projections of the collected reference facts.

Entity payloads retain source fields verbatim; relational columns provide stable IDs,
indexes and integrity checks. They are checked against those payloads at publication.
Readers use a new read-only connection per operation, never a shared connection.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import sqlite3
import uuid

from .storage import STAT_KEYS, TYPE_NAMES, json_bytes

SCHEMA_VERSION = 1
STATS = ('hp', 'attack', 'defense', 'special_attack', 'special_defense', 'speed')

CATALOG_SCHEMA = {
    'metadata': 'key TEXT PRIMARY KEY, payload TEXT NOT NULL',
    'species': 'id INTEGER PRIMARY KEY, name TEXT NOT NULL',
    'source_forms': 'id TEXT PRIMARY KEY, ordinal INTEGER UNIQUE, payload TEXT NOT NULL',
    'forms': 'id TEXT PRIMARY KEY, ordinal INTEGER UNIQUE, species_id INTEGER NOT NULL REFERENCES species(id), source_id TEXT REFERENCES source_forms(id), name TEXT NOT NULL, hp INTEGER, attack INTEGER, defense INTEGER, special_attack INTEGER, special_defense INTEGER, speed INTEGER, payload TEXT NOT NULL',
    'form_types': 'form_id TEXT REFERENCES forms(id), ordinal INTEGER, type TEXT NOT NULL, PRIMARY KEY(form_id, ordinal)',
    'mega_forms': 'base_id TEXT REFERENCES forms(id), mega_id TEXT REFERENCES forms(id), ordinal INTEGER, PRIMARY KEY(base_id, mega_id)',
    'moves': 'id TEXT PRIMARY KEY, type TEXT NOT NULL, category TEXT NOT NULL, power INTEGER, accuracy INTEGER, payload TEXT NOT NULL',
    'learnsets': 'source_id TEXT REFERENCES source_forms(id), move_id TEXT REFERENCES moves(id), ordinal INTEGER, banned INTEGER NOT NULL, PRIMARY KEY(source_id, move_id)',
    'abilities': 'id TEXT PRIMARY KEY, name TEXT, description TEXT',
    'source_abilities': 'source_id TEXT REFERENCES source_forms(id), ability_id TEXT REFERENCES abilities(id), ordinal INTEGER, PRIMARY KEY(source_id, ability_id)',
    'items': 'id TEXT PRIMARY KEY, name TEXT, description TEXT',
    'form_items': 'form_id TEXT REFERENCES forms(id), item_id TEXT REFERENCES items(id), PRIMARY KEY(form_id, item_id)',
    'assets': 'form_id TEXT REFERENCES forms(id), variant TEXT, path TEXT NOT NULL, sha256 TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(form_id, variant)',
    'recognition_groups': 'id INTEGER PRIMARY KEY, name TEXT NOT NULL, payload TEXT NOT NULL',
    'recognition_members': 'group_id INTEGER REFERENCES recognition_groups(id), source_slug TEXT, PRIMARY KEY(group_id, source_slug)',
    'provenance': 'form_id TEXT REFERENCES forms(id), field TEXT, payload TEXT NOT NULL, PRIMARY KEY(form_id, field)',
}
USAGE_SCHEMA = {
    'metadata': 'key TEXT PRIMARY KEY, payload TEXT NOT NULL',
    'usage_entries': 'id TEXT PRIMARY KEY, statistics_id TEXT, season TEXT NOT NULL, format TEXT NOT NULL, payload TEXT NOT NULL',
    'usage_moves': 'entry_id TEXT REFERENCES usage_entries(id), move_id TEXT, usage_percent REAL, PRIMARY KEY(entry_id, move_id)',
    'usage_spreads': 'entry_id TEXT REFERENCES usage_entries(id), ordinal INTEGER, hp INTEGER, attack INTEGER, defense INTEGER, special_attack INTEGER, special_defense INTEGER, speed INTEGER, usage_percent REAL, payload TEXT NOT NULL, PRIMARY KEY(entry_id, ordinal)',
    'usage_natures': 'entry_id TEXT REFERENCES usage_entries(id), ordinal INTEGER, payload TEXT NOT NULL, PRIMARY KEY(entry_id, ordinal)',
}


def encoded(value):
    return json_bytes(value).decode('utf-8')


def _catalog_rows(index, source, moves, policy):
    rows = {table: [] for table in CATALOG_SCHEMA}
    rows['metadata'] = [('index', encoded({k: v for k, v in index.items() if k != 'pokemon'})),
                        ('policy', encoded(policy))]
    records = index['pokemon']
    ids = [r.get('record_id', r['directory']) for r in records]
    source_ids = [s['key'] for s in source]
    if not records or len(set(ids)) != len(ids) or len(set(source_ids)) != len(source_ids):
        raise ValueError('重复或空的稳定 ID')
    if index['form_count'] != len(records) or index['species_count'] != len({r['dex_number'] for r in records}):
        raise ValueError('资料计数不符')
    species, abilities, items = {}, set(), set()
    for ordinal, raw in enumerate(source):
        rows['source_forms'].append((raw['key'], ordinal, encoded(raw)))
        for pos, key in enumerate(dict.fromkeys(raw.get('moves', []) + raw.get('bannedMoves', []))):
            if key not in moves: raise ValueError(f'招式资料缺失：{raw["key"]}/{key}')
            rows['learnsets'].append((raw['key'], key, pos, int(key in raw.get('bannedMoves', []))))
        for pos, key in enumerate(dict.fromkeys(raw.get('abilities', []))):
            abilities.add(key)
            rows['source_abilities'].append((raw['key'], key, pos))
    for ordinal, (identifier, record) in enumerate(zip(ids, records)):
        stats, types = record['base_stats'], record.get('types')
        if set(stats) != STAT_KEYS or any(type(v) is not int or not 0 < v <= 255 for v in stats.values()):
            raise ValueError('种族值无效')
        if record['base_stat_total'] != sum(stats.values()): raise ValueError('种族值总和不符')
        explicitly_unknown = types is None and record.get('types_ready') is False and not record.get('opgg_key')
        if not explicitly_unknown and (not isinstance(types, list) or not 1 <= len(types) <= 2 or any(t not in TYPE_NAMES for t in types)):
            raise ValueError(f'属性资料缺失或无效：{record["name"]}')
        species.setdefault(record['dex_number'], record['species_name'])
        source_id = record.get('opgg_key')
        if source_id and source_id not in source_ids: raise ValueError(f'形态来源缺失：{source_id}')
        rows['forms'].append((identifier, ordinal, record['dex_number'], source_id, record['name'],
                              *(stats[k] for k in STATS), encoded(record)))
        rows['form_types'] += [(identifier, pos, value) for pos, value in enumerate(types or [])]
        for pos, mega in enumerate(record.get('mega_form_ids', [])):
            if mega not in ids or mega == identifier: raise ValueError('Mega 形态外键无效')
            rows['mega_forms'].append((identifier, mega, pos))
        for variant, asset in record['images'].items():
            if variant not in ('normal', 'shiny'): raise ValueError('图标版本无效')
            rows['assets'].append((identifier, variant, f"{record['directory']}/{asset['file']}", asset['sha256'], encoded(asset)))
        for key, value in record.items():
            if key.endswith('_source'): rows['provenance'].append((identifier, key, encoded(value)))
        item = record.get('mega_item')
        if item:
            if not isinstance(item, str): raise ValueError('道具 ID 无效')
            items.add(item)
            rows['form_items'].append((identifier, item))
    rows['species'] = list(species.items())
    rows['abilities'] = [(key, None, None) for key in sorted(abilities)]
    rows['items'] = [(key, None, None) for key in sorted(items)]
    for key, move in moves.items():
        if move.get('key') != key or move.get('type') not in TYPE_NAMES or move.get('category') not in ('physical', 'special', 'status'):
            raise ValueError(f'招式身份／属性／类别无效：{key}')
        for field in ('power', 'accuracy'):
            if move.get(field) is not None and (type(move[field]) is not int or not 0 <= move[field] <= 1000):
                raise ValueError('招式数值无效')
        rows['moves'].append((key, move['type'], move['category'], move.get('power'), move.get('accuracy'), encoded(move)))
    seen_slugs = set()
    for ordinal, group in enumerate(policy['groups']):
        rows['recognition_groups'].append((ordinal, group['name'], encoded(group)))
        for slug in group['source_slugs']:
            if slug in seen_slugs: raise ValueError('外观分组身份重复')
            seen_slugs.add(slug)
            rows['recognition_members'].append((ordinal, slug))
    return rows


def _rate(value):
    if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 100):
        raise ValueError('采用率无效')
    return value


def _usage_rows(snapshot):
    if snapshot.get('schema_version') != 1 or snapshot.get('format') not in ('double', 'single'):
        raise ValueError('采用率 schema／模式无效')
    rows = {table: [] for table in USAGE_SCHEMA}
    rows['metadata'] = [('snapshot', encoded({k:v for k,v in snapshot.items() if k != 'pokemon'}))]
    for key, entry in snapshot['pokemon'].items():
        if entry['pokemon_key'] != key or entry['format'] != snapshot['format'] or entry['season'] != snapshot['season']:
            raise ValueError('采用率身份／赛季／模式不符')
        rows['usage_entries'].append((key, entry.get('statistics_key'), entry['season'], entry['format'], encoded(entry)))
        rows['usage_moves'] += [(key, move, _rate(rate)) for move, rate in entry.get('moves', {}).items()]
        seen = set()
        for pos, spread in enumerate(entry.get('training', [])):
            points = spread['points']
            if set(points) != STAT_KEYS or any(type(v) is not int or not 0 <= v <= 32 for v in points.values()) or sum(points.values()) > 66:
                raise ValueError('培养点分配无效')
            values = tuple(points[s] for s in STATS)
            if values in seen: raise ValueError('培养点分配重复')
            seen.add(values)
            rows['usage_spreads'].append((key, pos, *values, _rate(spread.get('usage_percent')), encoded(spread)))
        for pos, nature in enumerate(entry.get('natures', [])):
            _rate(nature.get('usage_percent'))
            rows['usage_natures'].append((key, pos, encoded(nature)))
    return rows


def _connect(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro&immutable=1', uri=True)


def _build(path, schema, rows, kind):
    path = Path(path)
    if path.exists(): raise ValueError(f'数据库已存在，不允许原地更新：{path}')
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    connection = None
    try:
        with sqlite3.connect(temp) as connection:
            # Foreign keys can be inserted in any order but must be valid on commit.
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
            connection.execute(f'PRAGMA application_id={1128811841 if kind == "catalog" else 1128813907}')
            for table, columns in schema.items(): connection.execute(f'CREATE TABLE {table} ({columns})')
            connection.execute('BEGIN')
            connection.execute('PRAGMA defer_foreign_keys=ON')
            for table, values in rows.items():
                if values: connection.executemany(f'INSERT INTO {table} VALUES ({",".join("?" for _ in values[0])})', values)
            if kind == 'catalog':
                connection.execute('CREATE INDEX form_source ON forms(source_id)')
                connection.execute('CREATE INDEX form_name ON forms(name)')
            else:
                connection.execute('CREATE INDEX usage_identity ON usage_entries(statistics_id, season, format)')
        connection.close()
        _validate(temp, kind)
        # Windows rename refuses an existing target; no overwrite of a live reader.
        temp.rename(path)
    except sqlite3.Error as exc:
        raise ValueError(f'数据库构建失败：{exc}') from exc
    finally:
        if connection: connection.close()
        if temp.exists(): temp.unlink()


def _read(connection, kind):
    meta = {k: json.loads(v) for k,v in connection.execute('SELECT * FROM metadata')}
    if kind == 'catalog':
        records = [json.loads(r[0]) for r in connection.execute('SELECT payload FROM forms ORDER BY ordinal')]
        return {'index': {**meta['index'], 'pokemon': records},
                'source': [json.loads(r[0]) for r in connection.execute('SELECT payload FROM source_forms ORDER BY ordinal')],
                'moves': {k: json.loads(p) for k,p in connection.execute('SELECT id,payload FROM moves')}, 'policy': meta['policy']}
    return {**meta['snapshot'], 'pokemon': {k: json.loads(p) for k,p in connection.execute('SELECT id,payload FROM usage_entries')}}


def _validate(path, kind):
    connection = None
    try:
        connection = _connect(path)
        if connection.execute('PRAGMA user_version').fetchone()[0] != SCHEMA_VERSION:
            raise ValueError('不支持的 SQLite schema')
        expected_id = 1128811841 if kind == 'catalog' else 1128813907
        if connection.execute('PRAGMA application_id').fetchone()[0] != expected_id:
            raise ValueError('SQLite 数据库类型不符')
        if connection.execute('PRAGMA integrity_check').fetchall() != [('ok',)] or connection.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('数据库完整性／外键校验失败')
        result = _read(connection, kind)
        expected = _catalog_rows(**result) if kind == 'catalog' else _usage_rows(result)
        for table, values in expected.items():
            actual = list(connection.execute(f'SELECT * FROM {table}'))
            if len(actual) != len(values) or set(actual) != set(values):
                raise ValueError(f'数据库领域投影不一致：{table}')
        return result
    except (sqlite3.Error, KeyError, TypeError) as exc:
        raise ValueError(f'数据库校验失败：{exc}') from exc
    finally:
        if connection: connection.close()


def build_catalog_database(path, index, source, moves, policy):
    _build(path, CATALOG_SCHEMA, _catalog_rows(index, source, moves, policy), 'catalog')
    return validate_catalog_database(path)


def validate_catalog_database(path):
    result = _validate(path, 'catalog')
    records = result['index']['pokemon']
    return {'forms': len(records), 'species': len({r['dex_number'] for r in records}),
            'moves': len(result['moves']), 'source_forms': len(result['source']),
            'images': sum(len(r['images']) for r in records),
            'pending_assets': sum(not r.get('recognition_ready', bool(r['images'])) for r in records)}


def build_usage_database(path, snapshot):
    _build(path, USAGE_SCHEMA, _usage_rows(snapshot), 'usage')
    return validate_usage_database(path)


def validate_usage_database(path):
    result = _validate(path, 'usage')
    return {'entries': len(result['pokemon']), 'moves': sum(len(e.get('moves', {})) for e in result['pokemon'].values()),
            'spreads': sum(len(e.get('training', [])) for e in result['pokemon'].values())}


def read_catalog_database(path):
    return _validate(path, 'catalog')


def read_usage_database(path):
    return _validate(path, 'usage')

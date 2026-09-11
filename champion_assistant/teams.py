"""Team-scoped builds and an all-or-nothing roster gate. No species-global fallback."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from .data.storage import read_json

STATS = {'hp': 'HP', 'attack': '攻击', 'defense': '防御',
         'special_attack': '特攻', 'special_defense': '特防', 'speed': '速度'}
OPTIONS_PATH = Path(__file__).resolve().parents[1] / 'config/team_build_options.json'


def blank_member(identity=None):
    return {'identity': identity, 'points': dict.fromkeys(STATS), 'nature': None,
            'ability': None, 'item': None, 'moves': [None] * 4}


class TeamRules:
    def __init__(self, catalog):
        self.catalog = catalog
        self.options = read_json(OPTIONS_PATH)

    def identity(self, record):
        # Only explicitly approved cosmetic aliases collapse. Mega/battle forms stay distinct.
        cosmetic = self.catalog.cosmetic_names.get(record['source_slug'])
        return 'cosmetic:' + cosmetic if cosmetic else record.get('record_id', record['directory'])

    def choices(self):
        return [(name, self.identity(r)) for name, r in self.catalog.search_records()]

    def record(self, identity):
        return next((r for r in self.catalog.records if self.identity(r) == identity), None)

    def name(self, identity):
        r = self.record(identity)
        return self.catalog.display_name(r) if r else (identity or '未知')

    def move_keys(self, identity):
        r = self.record(identity)
        if not r:
            return []
        damage, status, _ = self.catalog.learnset(r)
        return [m['key'] for m in damage + status]

    def ability_keys(self, identity):
        r = self.record(identity)
        return self.catalog.source.get(r.get('opgg_key'), {}).get('abilities', []) if r else []

    def validate(self, team):
        if not isinstance(team.get('name'), str) or not 1 <= len(team['name'].strip()) <= 80:
            raise ValueError('队伍名称须为 1–80 个字符。')
        members = team.get('members', [])
        mode = team.get('registration')
        if mode not in ('full', 'partial') or not isinstance(members, list):
            raise ValueError('登记模式无效。')
        if (mode == 'full' and len(members) != 6) or (mode == 'partial' and not 1 <= len(members) <= 5):
            raise ValueError('完整队伍必须登记六只；部分登记须明确选择，且登记一至五只。')
        identities = [m.get('identity') for m in members]
        if len(set(identities)) != len(identities):
            raise ValueError('同一队伍不能重复登记相同身份。')
        for member in members:
            identity = member.get('identity')
            if not self.record(identity):
                raise ValueError('宝可梦身份不在当前资料中，请重新确认。')
            points = member.get('points', {})
            if set(points) != set(STATS):
                raise ValueError('培养点必须包含六项能力，未填项保存为未知。')
            cap = self.options['point_rules']
            if any(v is not None and (type(v) is not int or not 0 <= v <= cap['per_stat']) for v in points.values()):
                raise ValueError(f"单项培养点须为 0–{cap['per_stat']} 或未知。")
            if sum(v for v in points.values() if v is not None) > cap['total']:
                raise ValueError(f"培养点总和不能超过 {cap['total']}。")
            if member.get('nature') is not None and member['nature'] not in self.options['natures']:
                raise ValueError('性格无效。')
            if member.get('ability') is not None and member['ability'] not in self.ability_keys(identity):
                raise ValueError('特性不属于该宝可梦形态。')
            if member.get('item') is not None and member['item'] != 'none' and member['item'] not in self.options['items']:
                raise ValueError('道具无效。')
            moves = member.get('moves')
            if not isinstance(moves, list) or len(moves) != 4:
                raise ValueError('必须保留四个招式槽位，允许未知。')
            known = [m for m in moves if m is not None]
            if len(set(known)) != len(known) or any(m not in self.move_keys(identity) for m in known):
                raise ValueError('四招不能重复，且必须属于当前形态的可用招式池。')


def match_team(team, observed, rules):
    """Return zero builds on any gate failure; unknown extra slots allowed only in partial mode.

    Observations use identity=None for unknown, ambiguous=True for an unresolved form,
    and item=None (unreadable), 'none' (visibly empty), or an exact item key.
    """
    def rejected(reason):
        return {'matched': False, 'reason': reason, 'builds': {}, 'team_id': None, 'revision': None}
    try:
        rules.validate(team)
    except (ValueError, TypeError, KeyError) as exc:
        return rejected(f'预存配置需要修正：{exc}')
    if len(observed) != 6:
        return rejected('当前我方阵容必须保留六个槽位。')
    if any(o.get('ambiguous') for o in observed):
        return rejected('当前阵容存在未确认的形态，整队配置未引用。')
    known = [o.get('identity') for o in observed if o.get('identity')]
    if len(known) != len(set(known)):
        return rejected('当前阵容存在重复身份，无法唯一对应槽位。')
    if any(not rules.record(i) for i in known):
        return rejected('当前阵容包含未知资料身份。')
    expected = {m['identity'] for m in team['members']}
    if team['registration'] == 'full' and set(known) != expected:
        return rejected(f'完整队伍仅匹配 {len(expected.intersection(known))}/6，整队配置未引用。')
    if not expected.issubset(known):
        return rejected(f'部分登记仅匹配 {len(expected.intersection(known))}/{len(expected)}，整队配置未引用。')
    builds = {}
    for member in team['members']:
        slot = next(i for i, o in enumerate(observed) if o.get('identity') == member['identity'])
        item = observed[slot].get('item')
        if item is not None and member['item'] is not None and item != member['item']:
            return rejected(f'第 {slot + 1} 槽道具与预存队伍冲突，整队配置未引用。')
        builds[slot] = deepcopy(member)
    return {'matched': True, 'reason': f'整队校验通过，引用 {len(builds)} 只已登记成员。',
            'builds': builds, 'team_id': team['id'], 'revision': team['revision']}


class TeamStore:
    """SQLite transactions and optimistic revisions protect independent teams and editors."""
    def __init__(self, path, rules):
        self.path, self.rules = Path(path), rules
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                raise ValueError('队伍数据库版本不兼容；原文件已保留。')
            db.execute('CREATE TABLE IF NOT EXISTS teams (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL)')
            db.execute('PRAGMA user_version=1')

    def connect(self):
        from contextlib import closing
        return closing(sqlite3.connect(self.path, timeout=5))

    def list(self):
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute('SELECT payload FROM teams ORDER BY rowid')]

    def save(self, team):
        self.rules.validate(team)
        saved = deepcopy(team)
        saved['name'] = saved['name'].strip()
        saved['schema_version'] = 1
        saved['dataset_id'] = self.rules.catalog.bundle_id
        saved['point_rules'] = deepcopy(self.rules.options['point_rules'])
        saved['id'] = saved.get('id') or uuid4().hex
        old_revision = saved.get('revision', 0)
        saved['revision'] = old_revision + 1
        with self.connect() as db, db:
            if old_revision:
                cursor = db.execute('UPDATE teams SET revision=?, payload=? WHERE id=? AND revision=?',
                                    (saved['revision'], json.dumps(saved, ensure_ascii=False), saved['id'], old_revision))
                if cursor.rowcount != 1:
                    raise ValueError('该队伍已被其他窗口更新或删除，请重新载入后编辑。')
            else:
                db.execute('INSERT INTO teams VALUES (?,?,?)', (saved['id'], 1, json.dumps(saved, ensure_ascii=False)))
        return saved

    def delete(self, team):
        with self.connect() as db, db:
            if db.execute('DELETE FROM teams WHERE id=? AND revision=?', (team['id'], team['revision'])).rowcount != 1:
                raise ValueError('队伍版本已变化，请重新载入。')

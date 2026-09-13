"""Champions scenario adapter for explicitly selected saved-team builds."""
from copy import deepcopy
import json
from pathlib import Path
import re
import shutil
import subprocess

from .teams import STATS, TeamRules, blank_member
from .data.storage import read_json
from .battle_effects import engine_side

from .paths import app_paths, node_executable

ROOT = app_paths().resources
ENGINE = ROOT/'damage_engine'
STAT_IDS = dict(zip(STATS, ('hp', 'atk', 'def', 'spa', 'spd', 'spe')))
RULE_VERSION = 'champions-e7fd7e5-single-target-v1'


def identifier(text):
    return re.sub('[^a-z0-9]', '', text.lower())


def battle_defaults():
    return {'hp': 0, 'status': '', 'boosts': dict.fromkeys(list(STATS)[1:], 0),
            'ability_on': False, 'allies_fainted': 0, 'reflect': False, 'light_screen': False,
            'protected': False, 'helping_hand': False, 'friend_guard': False, 'tailwind': False,
            'aurora_veil': False}


class DamageService:
    def __init__(self, catalog):
        self.catalog, self.rules = catalog, TeamRules(catalog)
        self.meta = read_json(ENGINE/'catalog.json')
        self.lookups = {k: {v['id']: v for v in values} for k, values in self.meta.items()}

    def speed(self, member, battle, environment):
        """Exact vendored speed calculation; incomplete builds remain unavailable."""
        try:
            job = {'kind':'speed', 'attacker':self.prepare(member,battle),
                   'field':{'weather':environment.get('weather') or None,
                            'terrain':environment.get('terrain') or None,
                            'attackerSide':engine_side(battle)}}
            return self.execute([job])[0]
        except (ValueError,KeyError,TypeError) as exc:
            return {'status':'unavailable','reason':str(exc)}

    def species(self, record):
        key = record.get('opgg_key') or record['source_slug']
        aliases = {'indeedee-male': 'indeedee', 'indeedee-female': 'indeedeef',
                   'basculegion-male': 'basculegion', 'basculegion-female': 'basculegionf',
                   'meowstic-male': 'meowstic', 'meowstic-female': 'meowsticf',
                   'aegislash-shield': 'aegislash', 'gourgeist-average': 'gourgeist'}
        if key.startswith('mega-'):
            parts = key[5:].split('-')
            key = parts[0] + '-mega' + (('-' + '-'.join(parts[1:])) if len(parts) > 1 else '')
        key = aliases.get(key, key)
        result = self.lookups['species'].get(identifier(key))
        if not result:
            raise ValueError('该形态尚未映射到 Champions 规则快照')
        return result['name']

    def prepare(self, member, battle):
        # A deliberate manual "no ability" scenario is distinct from unknown.
        check = deepcopy(member)
        if check.get('ability') == '__none__': check['ability'] = None
        self.rules.validate({'name':'情景', 'registration':'partial', 'members':[check]})
        if any(v is None for v in member['points'].values()):
            missing='、'.join(STATS[k] for k,v in member['points'].items() if v is None)
            raise ValueError(f'培养点有未知项：{missing}，请明确填写；未知不会当作 0')
        if member['nature'] is None or member['ability'] is None or member['item'] is None:
            missing='、'.join(name for key,name in [('nature','性格'),('ability','特性'),('item','道具')] if member[key] is None)
            raise ValueError(f'{missing}尚未确认；请补全或明确选择无道具／无特性效果假设')
        record = self.rules.record(member['identity'])
        name = self.species(record)
        member = deepcopy(member)
        if member['ability'] == 'trace':
            copied = battle.get('copied_ability')
            if not copied:
                raise ValueError('复制：请选择实际复制到的特性，或明确选择未触发；也可选择 Mega 形态使用妖精皮肤')
            if copied != '__none__' and copied not in self.rules.options['abilities']:
                raise ValueError('复制到的特性无效')
            member['ability'] = copied
        if member['ability'] in {'trace','receiver','power-of-alchemy','protean','libero','color-change','imposter'}:
            raise ValueError('暂不支持该复制／属性变化特性；可另选“无特性效果”作为简化假设')
        if member['item'] == 'metronome':
            raise ValueError('节拍器道具需要连续使用次数，本版暂未提供该输入')
        def translated(group, key):
            result = self.lookups[group].get(identifier(key))
            if not result: raise ValueError(f'规则快照中缺少 {key}')
            return result['name']
        options = {
            'evs': {STAT_IDS[k]: v for k, v in member['points'].items()},
            'nature': translated('natures', member['nature']),
            'ability': '(No Ability)' if member['ability'] == '__none__' else translated('abilities', member['ability']),
            'item': '' if member['item'] == 'none' else translated('items', member['item']),
            'status': battle['status'], 'abilityOn': battle['ability_on'],
            'alliesFainted': battle['allies_fainted'],
            'boosts': {STAT_IDS[k]: v for k, v in battle['boosts'].items()}}
        max_hp = record['base_stats']['hp'] + member['points']['hp'] + 75
        if record['base_stats']['hp'] == 1: max_hp = 1
        if type(battle['hp']) is not int or not 0 <= battle['hp'] <= max_hp:
            raise ValueError(f'当前 HP 须为 1–{max_hp}，0 代表明确的满 HP 情景')
        if battle['status'] not in ('', 'brn', 'par', 'psn', 'tox', 'slp', 'frz'):
            raise ValueError('异常状态无效')
        if any(type(v) is not int or not -6 <= v <= 6 for v in battle['boosts'].values()):
            raise ValueError('能力等级须为 -6 至 +6')
        if type(battle['allies_fainted']) is not int or not 0 <= battle['allies_fainted'] <= 5:
            raise ValueError('已倒下同伴数须为 0–5')
        options['curHP'] = battle['hp'] or max_hp
        return {'name':name, 'options':options, 'baseStats':{STAT_IDS[k]:v for k,v in record['base_stats'].items()},
                'types':[t.title() for t in record['types']]}

    def battle_form(self, member, identity):
        """Derive a battle-only Mega build without changing saved team identity or investment."""
        result = deepcopy(member)
        if identity == member['identity']:return result
        base = self.rules.record(member['identity'])
        family = self.catalog.form_family(base)
        record = next((r for r in family if self.rules.identity(r) == identity), None)
        if not record or not record.get('opgg_key', '').startswith('mega-'):
            raise ValueError('只能从预存形态切换为同一家族的 Mega 形态')
        stone = self.lookups['items'].get(identifier(member['item'] or ''), {})
        if self.species(record) not in stone.get('megaStone', {}).values():
            raise ValueError(f"{self.catalog.display_name(record)}：预存道具不是对应进化石，请到队伍配置修改")
        abilities = self.rules.ability_keys(identity)
        if len(abilities) != 1:raise ValueError('Mega 特性资料不唯一或缺失')
        result.update(identity=identity, ability=abilities[0])
        return result

    def readiness(self, member):
        """Run the same bounded local calculation path to expose save-time limitations."""
        record = self.rules.record(member['identity'])
        scene = self.comparison_presets(record)[0]
        rows, jobs = self.jobs(member, battle_defaults(), [scene],
            {'weather':'', 'terrain':'', 'targets':2, 'critical':False}, common=False)
        warnings = []
        try:self.prepare(member, battle_defaults())
        except (ValueError, KeyError) as exc:warnings.append(str(exc))
        try:results = self.execute(jobs)
        except ValueError as exc:return [str(exc)]
        for row, result in zip(rows, results):
            if result['status'] == 'unavailable':
                name = row['move']['name'] if row['move'] else '未填写招式'
                if result['reason'] not in warnings:warnings.append(f"{name}：{result['reason']}")
        return warnings

    def common_moves(self, record, limit=8, *, damage_only=False):
        damage, status, _ = self.catalog.learnset(record)
        return [m['key'] for m in sorted(damage + ([] if damage_only else status),
            key=lambda m: -(m['usage_percent'] if m['usage_percent'] is not None else -1))
                if m['usage_percent'] is not None][:limit]

    def presets(self, record):
        physical = record['base_stats']['attack'] >= record['base_stats']['special_attack']
        configs = [
            ('高速输出假设', {'hp':2, 'attack' if physical else 'special_attack':32, 'speed':32}, 'jolly' if physical else 'timid'),
            ('满 HP＋物耐假设', {'hp':32, 'defense':32, 'special_defense':2}, 'impish' if physical else 'bold'),
            ('满 HP＋特耐假设', {'hp':32, 'special_defense':32, 'defense':2}, 'careful' if physical else 'calm')]
        result = []
        for label, points, nature in configs:
            member = blank_member(self.rules.identity(record))
            member.update(points={k:points.get(k,0) for k in STATS}, nature=nature, ability='__none__', item='none')
            moves = self.common_moves(record, 4)
            member['moves'] = moves + [None]*(4-len(moves))
            result.append({'name':label, 'member':member, 'battle':battle_defaults()})
        return result

    def jobs(self, own, own_battle, scenarios, environment, *, common=True):
        if type(environment['targets']) is not int or environment['targets'] not in (1,2):
            raise ValueError('有效目标数须选择一个或至少两个')
        if not 1 <= len(scenarios) <= 12:
            raise ValueError('需要一至十二个独立情景')
        if environment['weather'] not in ('', 'Sun', 'Rain', 'Sand', 'Snow') or environment['terrain'] not in ('', 'Electric', 'Grassy', 'Misty', 'Psychic'):
            raise ValueError('天气或场地无效')
        rows, jobs = [], []
        def side(b):
            return engine_side(b)
        for scenario_index,scenario in enumerate(scenarios):
            enemy, enemy_battle = scenario['member'], scenario['battle']
            record = self.rules.record(enemy['identity'])
            incoming = self.common_moves(record, damage_only=True) if common else [
                key for key in enemy['moves'] if self.catalog.moves.get(key, {}).get('category') != 'status']
            for direction, attacker, defender, ab, db, moves in [
                ('我方 → 对手', own, enemy, own_battle, enemy_battle, own['moves']),
                ('对手 → 我方', enemy, own, enemy_battle, own_battle, (incoming or [None]) if common else incoming)]:
                if scenario.get('direction') and scenario['direction'] != direction:continue
                for key in moves:
                    move = self.catalog.moves.get(key)
                    job = {}
                    try:
                        if not move: raise ValueError('招式未填写或暂无双打采用率；可改用手动四招')
                        if key not in self.rules.move_keys(attacker['identity']): raise ValueError('招式不在该形态当前可用招式池')
                        engine_move = self.lookups['moves'].get(identifier(key))
                        if engine_move and (move['type'].title() != engine_move.get('type')
                            or move['category'].title() != engine_move.get('category')
                            or (move.get('power') is not None and move['power'] > 0 and move['power'] != engine_move.get('basePower'))):
                            raise ValueError('招式资料与规则快照不同，需核对更新后再计算')
                        job = {'attacker':self.prepare(attacker, ab), 'defender':self.prepare(defender, db), 'move':key,
                               'charge_boost_included':ab.get('charge_boost_included'),
                               'critical':environment['critical'], 'field':{'gameType':'Doubles',
                               'weather':environment['weather'] or None, 'terrain':environment['terrain'] or None,
                               'isSingleTarget':environment['targets'] == 1, 'attackerSide':side(ab), 'defenderSide':side(db)}}
                    except (ValueError, KeyError, TypeError) as exc:
                        job = {'error':str(exc)}
                    # Status moves have no direct damage, regardless of missing offensive stats.
                    if move and move['category'] == 'status' and key in self.rules.move_keys(attacker['identity']):
                        job = {'statusMove':True}
                    rows.append({'scenario':scenario['name'], 'scenario_index':scenario_index, 'direction':direction, 'move':move,
                                 'enemy':deepcopy(enemy), 'enemy_battle':deepcopy(enemy_battle)})
                    jobs.append(job)
        return rows, jobs

    def comparison_presets(self,record):
        """Separate durability and offense benchmarks; observed spreads do not imply joint builds."""
        usage=(self.catalog.usage or {}).get('pokemon',{}).get(record.get('opgg_key'),{})
        nature='hardy'
        for observed in sorted(usage.get('natures',[]),key=lambda n:-n['usage_percent']):
            found=next((key for key,n in self.rules.options['natures'].items()
                        if n['name']==observed['name']),None)
            if found:nature=found;break
        result=[]
        def add(name,points,nat,direction,rate=None):
            member=blank_member(self.rules.identity(record))
            member.update(points={k:points.get(k,0) for k in STATS},nature=nat,ability='__none__',item='none')
            if record.get('opgg_key','').startswith('mega-'):
                abilities=self.rules.ability_keys(member['identity'])
                if len(abilities)==1:member['ability']=abilities[0]
                stone=next((key for key in self.rules.options['items'] if self.species(record) in
                    self.lookups['items'].get(identifier(key),{}).get('megaStone',{}).values()),None)
                if stone:member['item']=stone
            moves=self.common_moves(record,4);member['moves']=moves+[None]*(4-len(moves))
            result.append({'name':name,'member':member,'battle':battle_defaults(),
                           'direction':direction,'spread_usage':rate})
        for direction in ['我方 → 对手','对手 → 我方']:
            if direction=='我方 → 对手':
                add('零耐久投入',{},'hardy',direction)
                add('满 HP＋物防',{'hp':32,'defense':32,'special_defense':2},'impish',direction)
                add('满 HP＋特防',{'hp':32,'special_defense':32,'defense':2},'calm',direction)
            else:
                add('零输出投入',{},'hardy',direction)
                add('满物攻',{'hp':2,'attack':32,'speed':32},'adamant',direction)
                add('满特攻',{'hp':2,'special_attack':32,'speed':32},'modest',direction)
            for i,spread in enumerate(sorted(usage.get('training',[]),key=lambda s:-s['usage_percent'])[:3],1):
                add(f'常用分配 {i}',spread['points'],nature,direction,spread['usage_percent'])
        return result

    def execute(self, jobs):
        node = node_executable()
        try:
            result = subprocess.run([node, str(ENGINE/'bridge.cjs')], input=json.dumps(jobs, ensure_ascii=False),
                encoding='utf-8', capture_output=True, timeout=25, cwd=ENGINE,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess,'CREATE_NO_WINDOW') else 0)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError('伤害引擎未启动或超时，请检查 Node.js 和 damage_engine；旧结果已撤下') from exc
        if result.returncode:
            raise ValueError('本地伤害引擎执行失败：' + result.stderr[:250])
        output = json.loads(result.stdout)
        if len(output) != len(jobs): raise ValueError('伤害引擎结果数量不一致')
        return output

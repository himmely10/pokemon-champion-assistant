"""Offline packaged-runtime smoke checks, with a machine-readable local report."""
from __future__ import annotations
import argparse
import json
import os
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from .paths import app_paths, node_executable


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--image', type=Path)
    parser.add_argument('--ability', type=Path)
    parser.add_argument('--status', type=Path)
    parser.add_argument('--exercise-user-store', action='store_true',
                        help='Requires an explicit CHAMPION_USER_DIR; creates an upgrade-test team there')
    args = parser.parse_args(argv)
    report = {'frozen': bool(getattr(sys, 'frozen', False)), 'checks': {}}
    start = time.perf_counter()
    try:
        paths = app_paths().ensure()
        from .data.snapshot import SnapshotManager
        from .teams import TeamRules, TeamStore, blank_member, STATS
        from .damage import DamageService, battle_defaults
        catalog = SnapshotManager(paths.data).initial().catalog
        report['checks']['catalog'] = {'forms': len(catalog.records), 'version': catalog.bundle_id}
        node = node_executable()
        report['checks']['node'] = subprocess.check_output([node, '--version'], text=True,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).strip()
        rules = TeamRules(catalog)
        with tempfile.TemporaryDirectory(prefix='champion-smoke-') as temp:
            store = TeamStore(Path(temp) / 'teams.sqlite3', rules)
            report['checks']['team_store'] = store.list() == []
        service = DamageService(catalog)
        def combatant(name, points, moves):
            member = blank_member(rules.identity(catalog.record_for_name(name)))
            member.update(points={key: points.get(key, 0) for key in STATS},
                          nature='hardy', ability='__none__', item='none', moves=moves)
            return member
        own = combatant('烈咬陆鲨', {'attack': 32}, ['earthquake', None, None, None])
        opponent = combatant('巨金怪', {'hp': 32}, ['meteor-mash', None, None, None])
        _, jobs = service.jobs(own, battle_defaults(),
            [{'name': '离线计算自检', 'member': opponent, 'battle': battle_defaults()}],
            {'weather': '', 'terrain': '', 'critical': False, 'targets': 2}, common=False)
        result = service.execute(jobs)
        if (result[0].get('minimum'), result[0].get('maximum')) != (102, 122):
            raise ValueError('内置伤害计算基准不符')
        report['checks']['damage_bridge'] = {'minimum': result[0]['minimum'], 'maximum': result[0]['maximum']}
        mega = next(record for record in catalog.records if record.get('opgg_key') == 'mega-charizard-x')
        defender = deepcopy(opponent)
        defender['identity'] = rules.identity(mega)
        defender['moves'] = ['flamethrower', None, None, None]
        _, mega_jobs = service.jobs(own, battle_defaults(),
            [{'name': 'Mega 自检', 'member': defender, 'battle': battle_defaults()}],
            {'weather': '', 'terrain': '', 'critical': False, 'targets': 2}, common=False)
        mega_result = service.execute(mega_jobs)[0]
        if mega_result.get('status') != 'ok' or mega_result.get('maximum', 0) <= 0:
            raise ValueError('Mega 形态离线计算失败')
        report['checks']['mega_damage'] = {key: mega_result[key] for key in ('minimum', 'maximum')}
        if args.exercise_user_store:
            if not os.environ.get('CHAMPION_USER_DIR'):
                raise ValueError('用户库演练必须指定独立 CHAMPION_USER_DIR')
            store = TeamStore(paths.teams, rules)
            teams = store.list()
            if not teams:
                entry = deepcopy(own)
                entry['ability'] = rules.ability_keys(entry['identity'])[0]
                entry['moves'] = rules.move_keys(entry['identity'])[:4]
                store.save({'name': '安装升级验收队伍', 'registration': 'partial', 'members': [entry]})
            from .data.storage import digest, json_bytes
            report['checks']['personal_team_fingerprint'] = digest(json_bytes(store.list()))
        if args.image:
            from .recognition import OpponentRecognizer
            from PIL import Image
            with Image.open(args.image) as image:
                recognition, _, _ = OpponentRecognizer(catalog.root).recognize(image)
            report['checks']['recognition'] = recognition
        if args.ability or args.status:
            if not (args.ability and args.status):
                raise ValueError('OCR 验证必须同时提供能力与状态截图')
            from .team_import import ScreenshotImporter
            result = ScreenshotImporter(rules).run(args.ability, args.status)
            report['checks']['ocr'] = result
        report['status'] = 'ok'
    except Exception as exc:
        report['status'], report['error'] = 'failed', str(exc)
    report['elapsed_seconds'] = round(time.perf_counter() - start, 3)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if report['status'] == 'ok' else 1

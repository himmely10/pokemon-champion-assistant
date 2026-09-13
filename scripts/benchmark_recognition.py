"""Repeatable local benchmark; timings never replace identity regression tests."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cv2
import numpy as np
from PIL import Image
from champion_assistant.recognition import OpponentRecognizer


def memory():
    """Process working set in bytes, without an extra runtime dependency."""
    if sys.platform != 'win32':
        return {'working_set_bytes': None, 'peak_working_set_bytes': None}
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('faults', wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ('peak', 'working', 'quota_peak_paged', 'quota_paged',
                'quota_peak_nonpaged', 'quota_nonpaged', 'pagefile', 'peak_pagefile')]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    query = ctypes.windll.psapi.GetProcessMemoryInfo
    query.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    if not query(wintypes.HANDLE(-1), ctypes.byref(counters), counters.cb):
        return {'working_set_bytes': None, 'peak_working_set_bytes': None}
    return {'working_set_bytes': counters.working, 'peak_working_set_bytes': counters.peak}


def environment():
    processor = platform.processor()
    if sys.platform == 'win32':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
                processor = winreg.QueryValueEx(key, 'ProcessorNameString')[0].strip()
        except OSError:
            pass
    return {'platform': platform.platform(), 'processor': processor, 'cpu_count': os.cpu_count(),
            'python': sys.version, 'opencv': cv2.__version__, 'numpy': np.__version__}


def benchmark_ocr(runs):
    from champion_assistant.team_import import ScreenshotImporter
    from champion_assistant.data.references import ReferenceCatalog
    from champion_assistant.teams import TeamRules
    rules = TeamRules(ReferenceCatalog(ROOT/'pokemon'))
    paths = [ROOT/'tests/fixtures/team_import'/f'{mode}.png' for mode in ('ability', 'status')]
    attempts, expected = [], None
    for _ in range(runs):
        started = time.perf_counter()
        importer = ScreenshotImporter(rules)
        ready = time.perf_counter()
        page_times, pages = [], []
        for mode, path in zip(('ability', 'status'), paths):
            tick = time.perf_counter()
            pages.append(importer.read_page(path, mode))
            page_times.append(time.perf_counter() - tick)
        fingerprint = hashlib.sha256(json.dumps(pages, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        if expected is None:
            expected = fingerprint
        attempts.append({'init_seconds': ready-started, 'page_seconds': page_times,
                         'total_seconds': time.perf_counter()-started,
                         'matches_first_result': fingerprint == expected, 'memory': memory()})
    return {'sample_sha256': [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths],
            'runs': runs, 'attempts': attempts,
            'note': '首轮包含 OCR 冷初始化；后续复用模型，每次均重新识别两张截图。正确性另由转录回归测试验证。'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=int, default=20)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'pokemon')
    parser.add_argument('--layout', type=Path, default=ROOT / 'config/opponent_team_preview.json')
    parser.add_argument('--label', default='current')
    parser.add_argument('--workers', type=int, choices=range(1, 7), help='探索线程数；默认使用识别器设置')
    parser.add_argument('--only-ocr', action='store_true')
    parser.add_argument('--ocr-runs', type=int, default=3)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error('--runs must be positive')
    if args.only_ocr:
        if args.ocr_runs < 2:
            parser.error('--ocr-runs must be at least 2 to measure reuse')
        report = {'label': args.label, 'environment': environment(), 'ocr': benchmark_ocr(args.ocr_runs)}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False), flush=True)
        return
    manifest = json.loads((ROOT / 'tests/fixtures/recognition/manifest.json').read_text(encoding='utf-8'))
    started = time.perf_counter()
    worker_options = {} if args.workers is None else {'workers': args.workers}
    engine = OpponentRecognizer(args.data_dir, args.layout, **worker_options)
    init_seconds = time.perf_counter() - started
    report = {'label': args.label, 'environment': environment(),
              'dataset_id': engine.dataset_id, 'layout_sha256': hashlib.sha256(args.layout.read_bytes()).hexdigest(),
              'index_sha256': hashlib.sha256((engine.data_dir / 'index.json').read_bytes()).hexdigest(),
              'template_count': len(engine.templates), 'init_seconds': init_seconds, 'samples': [],
              'template_bytes': getattr(engine, 'template_bytes', None), 'memory_after_init': memory(),
              'workers': getattr(engine, 'workers', 3), 'cache_key': getattr(engine, 'cache_key', None)}
    started = time.perf_counter()
    duplicate = OpponentRecognizer(args.data_dir, args.layout, **worker_options)
    report['repeat_init_seconds'] = time.perf_counter() - started
    report['repeat_init_cache_hit'] = getattr(duplicate, 'cache_hit', False)
    del duplicate
    for sample in manifest['screenshots']:
        path = ROOT / sample['path']
        started = time.perf_counter()
        with Image.open(path) as raw:
            image = raw.convert('RGB')
        decode_seconds = time.perf_counter() - started
        started = time.perf_counter()
        cold, _, _ = engine.recognize(image)
        first_seconds = time.perf_counter() - started
        report['algorithm_version'] = cold.get('algorithm_version', 'original')
        durations, outputs, phases = [], [], []
        for _ in range(args.runs):
            started = time.perf_counter()
            result, _, _ = engine.recognize(image)
            durations.append(time.perf_counter() - started)
            outputs.append([r['name'] for r in result['opponent']])
            phases.append(result.get('timings', {}))
        names = [r['name'] for r in cold['opponent']]
        entry = {'path': sample['path'], 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                 'decode_seconds': decode_seconds, 'first_recognition_seconds': first_seconds,
                 'runs': args.runs, 'warm_seconds': durations, 'median_seconds': statistics.median(durations),
                 'p95_seconds': float(np.percentile(durations, 95)), 'names': names,
                 'first_result': cold['opponent'],
                 'all_expected': names == sample['names'] and all(x == sample['names'] for x in outputs),
                 'phases': phases, 'memory_after_sample': memory()}
        entry['gate_passed'] = args.runs >= 20 and entry['all_expected'] and entry['median_seconds'] <= 2 and entry['p95_seconds'] <= 3
        report['samples'].append(entry)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({k: v for k, v in entry.items() if k not in ('warm_seconds', 'phases', 'first_result')}, ensure_ascii=False), flush=True)
    report['gate_passed'] = all(s['gate_passed'] for s in report['samples'])
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()

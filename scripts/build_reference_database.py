"""Build a derived, unactivated SQLite bundle from verified local source evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from champion_assistant.data.references import ReferenceCatalog
from champion_assistant.data.sqlite_catalog import read_catalog_database, validate_catalog_database, validate_usage_database
from champion_assistant.data.storage import make_bundle, read_json, resolve_dataset, validate_bundle, validate_index
from champion_assistant.data.usage import load_usage, write_usage_snapshot
from champion_assistant.paths import app_paths


def build_reference_bundle(source_root, output_root, usage_root=None):
    """No active pointer is changed; output is suitable for the release builder."""
    source = resolve_dataset(source_root)
    output = Path(output_root).resolve()
    if output == source or output.is_relative_to(source):
        raise ValueError('输出不能放在现有版本目录内')
    if (source/'manifest.json').exists(): validate_bundle(source)
    index = read_json(source/'index.json')
    if not (source/'manifest.json').exists(): validate_index(index, source)
    policy = read_json(source/'recognition_identity_groups.json')
    source_rows = read_json(source/'source_catalog.json')
    moves = read_json(source/'moves.json')
    if (source/'manifest.json').exists():
        names = read_json(source/'manifest.json')['files']
        extra = {name: (source/name).read_bytes() for name in names
                 if (name not in ('index.json', 'recognition_identity_groups.json', 'catalog.sqlite')
                     and '/' not in name) or name.startswith('_sources/')}
    else:
        extra = {name: (source/name).read_bytes() for name in ('source_catalog.json', 'moves.json')}
    # The condition above retains top-level source evidence only; never copy an
    # existing database, manifest, personal data, or an old member JSON as authority.
    extra.pop('catalog.sqlite', None)
    start = time.perf_counter()
    bundle = make_bundle(output, index, source, policy, extra, reference_database=True)
    elapsed = time.perf_counter()-start
    facts = read_catalog_database(bundle/'catalog.sqlite')
    if facts != {'index': index, 'source': source_rows, 'moves': moves, 'policy': policy}:
        raise ValueError('全量领域等价校验失败')
    usage = load_usage(usage_root) if usage_root is not None else None
    usage_result = None
    if usage is not None:
        relative = write_usage_snapshot(output/'_usage', usage)
        pointer = read_json(output/'_usage/current.json')
        usage_result = {**validate_usage_database(output/'_usage'/pointer['database_file']),
                        'file': relative, 'database_file': pointer['database_file'],
                        'database_sha256': pointer['database_sha256']}
    legacy = ReferenceCatalog(source, usage_snapshot=usage or {})
    sql = ReferenceCatalog(bundle, usage_snapshot=usage or {})
    for record in legacy.records:
        identifier = record.get('record_id', record['directory'])
        other = sql.by_id[identifier]
        if legacy.form_family(record) != sql.form_family(other) or legacy.learnset(record) != sql.learnset(other):
            raise ValueError(f'界面领域等价校验失败：{identifier}')
    return {'status': 'built_unactivated', 'source_bundle': source.name, 'bundle_path': str(bundle),
            'catalog': validate_catalog_database(bundle/'catalog.sqlite'), 'usage': usage_result,
            'equivalence': 'exact_all_fields_and_learnsets', 'build_seconds': round(elapsed, 3)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=app_paths().resource('pokemon'))
    parser.add_argument('--usage-dir', type=Path)
    parser.add_argument('--output-root', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = build_reference_bundle(args.data_dir, args.output_root, args.usage_dir)
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({'status': 'failed', 'error': str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

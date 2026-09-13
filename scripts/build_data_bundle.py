"""Build a reproducible offline/HTTPS data package and validate it with the client."""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import json
from pathlib import Path
import sys
import tempfile
from urllib.parse import quote, urlparse
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from champion_assistant.damage import RULE_VERSION
from champion_assistant.data.sqlite_catalog import build_catalog_database, validate_catalog_database
from champion_assistant.data.storage import (atomic_bytes, confined, digest, json_bytes, read_json,
                                           resolve_dataset, save_json, update_lock, validate_bundle, validate_index)
from champion_assistant.data.usage import load_usage, write_usage_snapshot
from champion_assistant.data.update_service import UpdateService
from champion_assistant.data.snapshot import SnapshotManager
from champion_assistant.paths import app_paths

VOLATILE_FIELDS = {'fetched_at', 'generated_at', 'checked_at'}


def _semantic(value):
    if isinstance(value, dict):
        return {key: _semantic(v) for key,v in value.items() if key not in VOLATILE_FIELDS}
    if isinstance(value, list): return [_semantic(v) for v in value]
    return value


def _base_url(value):
    if not value: return None
    parsed = urlparse(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('渠道必须是无凭据、无查询参数的 HTTPS 目录地址')
    return value.rstrip('/') + '/'


def _source_facts(source_root, usage_root):
    source = resolve_dataset(source_root)
    if (source/'manifest.json').exists(): validate_bundle(source)
    index = read_json(source/'index.json')
    if not (source/'manifest.json').exists(): validate_index(index, source)
    facts = {'index': index, 'source': read_json(source/'source_catalog.json'),
             'moves': read_json(source/'moves.json'), 'policy': read_json(source/'recognition_identity_groups.json')}
    if not facts['moves']: raise ValueError('缺少完整招式资料，不能发行空的 SQL 图鉴')
    usage = load_usage(usage_root)
    if not usage: raise ValueError('缺少双打采用率快照，不能发布不完整资料组合')
    pointer = read_json(Path(usage_root)/'current.json')
    if pointer.get('catalog_id') and pointer['catalog_id'] != source.name:
        raise ValueError('采用率绑定的图鉴版本与输入不兼容')
    unknown = set(usage['pokemon']) - {r['key'] for r in facts['source']}
    if unknown: raise ValueError('采用率包含图鉴外身份：' + ', '.join(sorted(unknown)))
    return source, facts, usage


def _static_package(stage, source, facts):
    """Allowlist public domain records, not a recursive copy of the project."""
    catalog = stage/'catalog'
    catalog.mkdir()
    index = facts['index']
    save_json(catalog/'index.json', index)
    save_json(catalog/'source_catalog.json', facts['source'])
    save_json(catalog/'moves.json', facts['moves'])
    save_json(catalog/'recognition_identity_groups.json', facts['policy'])
    for record in index['pokemon']:
        save_json(confined(catalog,f"{record['directory']}/{record['name']}.json"), record)
        for asset in record['images'].values():
            relative = f"{record['directory']}/{asset['file']}"
            atomic_bytes(confined(catalog,relative), confined(source,relative).read_bytes())
    build_catalog_database(catalog/'catalog.sqlite', **facts)
    files = {p.relative_to(catalog).as_posix(): digest(p.read_bytes()) for p in sorted(catalog.rglob('*')) if p.is_file()}
    identifier = 'data-' + digest(json_bytes(files))[:24]
    # Source time, not the wall clock: equal source snapshots produce equal bytes.
    save_json(catalog/'manifest.json', {'schema_version':1,'reference_schema':1,'bundle_id':identifier,
                                     'created_at':index.get('generated_at'), 'rule_version':RULE_VERSION,
                                     'files':files})
    validate_bundle(catalog)
    return identifier, catalog


def _write_zip(path, files, package):
    values = {**files, 'package.json':json_bytes(package)}
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for relative in sorted(values):
            info = zipfile.ZipInfo(relative, date_time=(1980,1,1,0,0,0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info,values[relative],compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)


def _channel(output, result, base_url):
    if base_url is None: return None
    path = output/'channel.json'
    save_json(path, {'schema_version':1,'version':result['version'],
                     'url':base_url+quote(Path(result['archive_path']).name),
                     'sha256':result['sha256'],'size':result['size'],'rule_version':RULE_VERSION,
                     'source_times':result['source_times'],'catalog_id':result['catalog_id'],
                     'season':result['season'],'format':'double'})
    return str(path)


def build_data_bundle(source_root, output_dir, *, usage_root=None, base_url=None):
    """Build, client-import-test, then write the local candidate channel last.

    Publication to a remote stable channel is deliberately a separate action.
    Retain output_dir/build-state.json and its ZIP across maintainer runs to skip
    collection-time-only changes without altering immutable source snapshots.
    """
    base_url = _base_url(base_url)
    source_root, output = Path(source_root).resolve(), Path(output_dir).resolve()
    if output == source_root or output.is_relative_to(source_root):
        raise ValueError('构建输出必须独立于来源资料目录')
    usage_root = Path(usage_root) if usage_root is not None else source_root/'_usage'
    source, facts, usage = _source_facts(source_root,usage_root)
    semantic_id = digest(json_bytes(_semantic({'facts':facts,'usage':usage,'rule_version':RULE_VERSION})))
    output.mkdir(parents=True,exist_ok=True)
    with update_lock(output):
        state_path = output/'build-state.json'
        if state_path.exists():
            previous=read_json(state_path)
            if previous.get('semantic_id')==semantic_id:
                archive=confined(output,previous['archive_name'])
                if archive.exists() and digest(archive.read_bytes())==previous['sha256']:
                    result={**previous,'status':'unchanged','archive_path':str(archive)}
                    result['channel_path']=_channel(output,result,base_url)
                    save_json(output/'latest-build.json',{**result,'latest_checked_source_times':{
                        'catalog_generated_at':facts['index'].get('generated_at'),'usage_fetched_at':usage.get('fetched_at')}})
                    return result
        # Do not nest the client's own install stage below a potentially long
        # output directory (Windows path length limits apply before packaging).
        with tempfile.TemporaryDirectory(prefix='pca-data-') as temp:
            stage=Path(temp)
            catalog_id,catalog=_static_package(stage,source,facts)
            write_usage_snapshot(stage/'usage',usage)
            usage_pointer=read_json(stage/'usage/current.json')
            usage_pointer['catalog_id']=catalog_id
            files={f'_versions/{catalog_id}/{p.relative_to(catalog).as_posix()}':p.read_bytes()
                   for p in catalog.rglob('*') if p.is_file()}
            for field in ('file','database_file'):
                relative=usage_pointer[field]
                files['_usage/'+relative]=confined(stage/'usage',relative).read_bytes()
            source_times={'catalog_generated_at':facts['index'].get('generated_at'),
                          'usage_fetched_at':usage.get('fetched_at'),
                          'usage_source_updated_at':usage.get('ranking_updated_at')}
            # Physical identity covers precise timestamps/evidence. semantic_id
            # is solely the skip key; independent changed bytes never reuse an ID.
            content_id=digest(json_bytes({name:digest(content) for name,content in files.items()}))
            version='references-'+content_id[:24]
            package={'schema_version':1,'version':version,'catalog_id':catalog_id,
                     'usage_pointer':usage_pointer,'rule_version':RULE_VERSION,'source_times':source_times,
                     'files':{name:digest(content) for name,content in files.items()}}
            archive_name=version+'.zip'
            staged_zip=stage/archive_name
            _write_zip(staged_zip,files,package)
            # Exercise the actual installation and snapshot reader before exposure.
            installed=stage/'installed'
            UpdateService(installed).install(staged_zip)
            snapshot=SnapshotManager(installed).candidate()
            actual=snapshot.catalog
            if (actual.index!=facts['index'] or list(actual.source.values())!=facts['source']
                    or actual.moves!=facts['moves'] or actual.usage!=usage):
                raise ValueError('客户端导入后的资料与来源不一致')
            del snapshot,actual
            content=staged_zip.read_bytes()
            archive=output/archive_name
            if archive.exists() and archive.read_bytes()!=content:
                raise ValueError('同一发行身份存在不同内容，拒绝覆盖')
            if not archive.exists(): atomic_bytes(archive,content)
            result={'status':'built','semantic_id':semantic_id,'version':version,'archive_name':archive_name,
                    'archive_path':str(archive),'sha256':digest(content),'size':len(content),
                    'catalog_id':catalog_id,'source_times':source_times,'season':usage['season'],
                    'catalog':validate_catalog_database(catalog/'catalog.sqlite'),
                    'usage_entries':len(usage['pokemon']), 'stale_entries':sorted(usage.get('errors',{})),
                    'client_roundtrip':'passed'}
            save_json(state_path,result)
            # This is a LOCAL candidate manifest; no network publication is done.
            result['channel_path']=_channel(output,result,base_url)
            save_json(output/'latest-build.json',result)
            return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',type=Path,default=app_paths().resource('pokemon'))
    parser.add_argument('--usage-dir',type=Path)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--base-url',help='最终包的无凭据 HTTPS 目录；未填则仅生成离线包')
    args=parser.parse_args(argv)
    try:
        with redirect_stdout(sys.stderr):
            result=build_data_bundle(args.data_dir,args.output_dir,usage_root=args.usage_dir,base_url=args.base_url)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (ValueError,OSError,KeyError) as exc:
        print(json.dumps({'status':'failed','error':str(exc)},ensure_ascii=False))
        return 1


if __name__=='__main__': raise SystemExit(main())

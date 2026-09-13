"""Maintainer package reproducibility and the real client installation contract."""
import copy
from pathlib import Path
import zipfile

import pytest

from scripts.build_data_bundle import build_data_bundle
from champion_assistant.data.storage import save_json, json_bytes, digest, read_json
from champion_assistant.data.update_service import UpdateService
from champion_assistant.data.snapshot import SnapshotManager


@pytest.fixture
def local_source(tmp_path):
    root = tmp_path/'source'
    record = {'record_id': 'opgg:scizor', 'name': '巨钳螳螂', 'directory': '巨钳螳螂',
              'dex_number': 212, 'species_name': '巨钳螳螂', 'source_slug': 'scizor',
              'opgg_key': 'scizor', 'types': ['bug', 'steel'],
              'base_stats': dict(zip(('hp','attack','defense','special_attack','special_defense','speed'), (70,130,100,55,80,65))),
              'base_stat_total': 500, 'images': {}, 'recognition_ready': False}
    save_json(root/'index.json', {'pokemon':[record], 'species_count':1, 'form_count':1,
                               'generated_at':'2026-09-10T00:00:00+00:00'})
    save_json(root/'source_catalog.json', [{'key':'scizor','moves':['bullet-punch'],'abilities':['technician']}])
    save_json(root/'moves.json', {'bullet-punch':{'key':'bullet-punch','name':'子弹拳','type':'steel',
                                              'category':'physical','power':40,'accuracy':100,'description':'先制攻击','isAvailable':True}})
    save_json(root/'recognition_identity_groups.json', {'groups':[]})
    snapshot = {'schema_version':1,'format':'double','season':'m-6','fetched_at':'2026-09-10T00:00:00+00:00',
                'pokemon': {'scizor':{'pokemon_key':'scizor','statistics_key':'scizor','format':'double','season':'m-6',
                                     'source_updated_at':'2026-09-09','fetched_at':'2026-09-10T00:00:00+00:00',
                                     'moves':{'bullet-punch':98.2}}},'errors':{}}
    save_usage(root, snapshot)
    return root, snapshot


def save_usage(root, snapshot):
    data=json_bytes(snapshot)
    relative='snapshots/usage-'+digest(data)[:24]+'.json'
    save_json(root/'_usage'/relative,snapshot)
    save_json(root/'_usage/current.json',{'file':relative,'sha256':digest(data)})


def test_offline_archive_roundtrip_and_no_private_files(tmp_path,local_source):
    source, expected = local_source
    save_json(source/'user_data/teams.db.json',{'secret':'never package'})
    save_json(source/'local_ui.json',{'password':'never package'})
    result=build_data_bundle(source,tmp_path/'output',usage_root=source/'_usage')
    assert result['status']=='built' and result['channel_path'] is None
    with zipfile.ZipFile(result['archive_path']) as z:
        names=z.namelist()
        assert any(n.endswith('/catalog.sqlite') for n in names)
        assert any(n.endswith('/usage.sqlite') for n in names)
        assert not any('user_data' in n or 'local_ui' in n for n in names)
        assert set(Path(n).suffix for n in names) <= {'.json','.sqlite','.png'}
    assert UpdateService(tmp_path/'installed').install(result['archive_path'])['status']=='updated'
    catalog=SnapshotManager(tmp_path/'installed').candidate().catalog
    assert catalog.records == read_json(source/'index.json')['pokemon']
    assert catalog.usage == expected


def test_byte_reproducible_and_source_not_mutated(tmp_path,local_source):
    source,_=local_source
    before={str(p.relative_to(source)):p.read_bytes() for p in source.rglob('*') if p.is_file()}
    first=build_data_bundle(source,tmp_path/'one',usage_root=source/'_usage')
    second=build_data_bundle(source,tmp_path/'two',usage_root=source/'_usage')
    assert first['sha256']==second['sha256']
    assert Path(first['archive_path']).read_bytes()==Path(second['archive_path']).read_bytes()
    assert before=={str(p.relative_to(source)):p.read_bytes() for p in source.rglob('*') if p.is_file()}


def test_collection_time_only_reuses_existing_artifact(tmp_path,local_source):
    source,usage=local_source
    first=build_data_bundle(source,tmp_path/'out',usage_root=source/'_usage')
    changed=copy.deepcopy(usage)
    changed['fetched_at']=changed['pokemon']['scizor']['fetched_at']='2026-09-11T00:00:00+00:00'
    save_usage(source,changed)
    second=build_data_bundle(source,tmp_path/'out',usage_root=source/'_usage')
    assert second['status']=='unchanged'
    assert second['sha256']==first['sha256'] and second['version']==first['version']
    changed['season']=changed['pokemon']['scizor']['season']='m-7'
    save_usage(source,changed)
    third=build_data_bundle(source,tmp_path/'out',usage_root=source/'_usage')
    assert third['status']=='built' and third['version']!=first['version']


def test_channel_is_last_and_failed_input_preserves_it(tmp_path,local_source):
    source,_=local_source
    out=tmp_path/'out'
    result=build_data_bundle(source,out,usage_root=source/'_usage',base_url='https://example.test/data/')
    channel=read_json(result['channel_path'])
    assert channel['url'].startswith('https://example.test/data/')
    assert channel['sha256']==digest(Path(result['archive_path']).read_bytes())
    before=(out/'channel.json').read_bytes()
    save_json(source/'moves.json',{})
    with pytest.raises(ValueError): build_data_bundle(source,out,usage_root=source/'_usage',base_url='https://example.test/data/')
    assert (out/'channel.json').read_bytes()==before


@pytest.mark.parametrize('url',['http://example.test','https://token@example.test','file:///x'])
def test_reject_unsafe_channel(tmp_path,local_source,url):
    source,_=local_source
    with pytest.raises(ValueError): build_data_bundle(source,tmp_path/'out',usage_root=source/'_usage',base_url=url)


def test_interrupted_output_write_never_advances_channel(tmp_path,local_source,monkeypatch):
    from scripts import build_data_bundle as builder
    source,usage=local_source
    output=tmp_path/'out'
    build_data_bundle(source,output,usage_root=source/'_usage',base_url='https://example.test/data')
    previous=(output/'channel.json').read_bytes()
    previous_state=(output/'build-state.json').read_bytes()
    changed=copy.deepcopy(usage)
    changed['pokemon']['scizor']['moves']['bullet-punch']=97.1
    changed['errors']={'scizor':'using retained source row'}
    save_usage(source,changed)
    original=builder.atomic_bytes
    def interrupted(path,data):
        if Path(path).parent==output and Path(path).suffix=='.zip':
            raise OSError('simulated interrupted artifact write')
        return original(path,data)
    monkeypatch.setattr(builder,'atomic_bytes',interrupted)
    with pytest.raises(OSError): build_data_bundle(source,output,usage_root=source/'_usage',base_url='https://example.test/data')
    assert (output/'channel.json').read_bytes()==previous
    assert (output/'build-state.json').read_bytes()==previous_state
    monkeypatch.setattr(builder,'atomic_bytes',original)
    result=build_data_bundle(source,output,usage_root=source/'_usage')
    assert result['stale_entries']==['scizor']


def test_incompatible_usage_identity_rejected(tmp_path,local_source):
    source,usage=local_source
    changed=copy.deepcopy(usage)
    changed['pokemon']['absent']=changed['pokemon'].pop('scizor')
    changed['pokemon']['absent']['pokemon_key']='absent'
    save_usage(source,changed)
    with pytest.raises(ValueError,match='图鉴外身份'):
        build_data_bundle(source,tmp_path/'out',usage_root=source/'_usage')

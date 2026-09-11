from copy import deepcopy
import gzip
import pytest
from champion_assistant.data.references import ReferenceCatalog
from champion_assistant.data.storage import json_bytes,digest,save_json
from champion_assistant.data.usage import action_result,parse_detail,reparse_usage_cache,load_usage
from champion_assistant.damage import DamageService,battle_defaults
from champion_assistant.type_matchups import type_matchups
from pathlib import Path

RAW=Path('docs/research/2026-09-11-usage-speed/double-garchomp.rsc')


def test_hex_training_and_separate_nature_statistics():
    payload=action_result(RAW.read_bytes())
    payload['detailData']['doubleDetail']['training']=[{'spread':'10-14-00-00-00-1e','usagePercent':3.1}]
    entry=parse_detail(payload,'garchomp','m-6')
    assert list(entry['training'][0]['points'].values())==[16,20,0,0,0,30]
    assert entry['training'][0]['usage_percent']==3.1
    assert entry['natures'] and 'nature' not in entry['training'][0]


@pytest.mark.parametrize('spread,rate',[
    ('10-14-00-00-1e',4),('GG-00-00-00-00-00',4),('21-00-00-00-00-00',4),
    ('20-20-03-00-00-00',4),('00-00-00-00-00-00',101),('00-00-00-00-00-00',float('nan'))])
def test_training_validation(spread,rate):
    payload=action_result(RAW.read_bytes())
    payload['detailData']['doubleDetail']['training']=[{'spread':spread,'usagePercent':rate}]
    with pytest.raises(ValueError):parse_detail(payload,'garchomp','m-6')


def test_cache_upgrade_preserves_age_and_explicit_query(tmp_path):
    entry=parse_detail(action_result(RAW.read_bytes()),'garchomp','m-6')
    expected=deepcopy(entry);entry.pop('training');entry.pop('natures')
    snapshot={'schema_version':1,'format':'double','season':'m-6','fetched_at':'2026-09-01T00:00:00+00:00','pokemon':{'garchomp':entry},'errors':{}}
    data=json_bytes(snapshot);checksum=digest(data)
    (tmp_path/'snapshot.json').write_bytes(data)
    save_json(tmp_path/'current.json',{'file':'snapshot.json','sha256':checksum})
    cache=tmp_path/'cache/responses';cache.mkdir(parents=True)
    args={'lang':'zh-cn','format':'double','season':'m-6','pokemonKey':'garchomp'}
    key=digest(json_bytes({'name':'getPokemonTierRankedBattleDetail','args':args}))
    (cache/f'{key}.gz').write_bytes(gzip.compress(RAW.read_bytes()))
    assert reparse_usage_cache(tmp_path)['entries']==1
    updated=load_usage(tmp_path)
    assert updated['fetched_at']==snapshot['fetched_at']
    assert updated['pokemon']['garchomp']['training']==expected['training']
    assert updated['pokemon']['garchomp']['fetched_at']==entry['fetched_at']


def test_direction_benchmarks_and_usage_are_not_joint_builds():
    service=DamageService(ReferenceCatalog('pokemon'))
    record=service.catalog.record_for_name('大狃拉')
    scenes=service.comparison_presets(record)
    outgoing=[s for s in scenes if s['direction']=='我方 → 对手']
    incoming=[s for s in scenes if s['direction']=='对手 → 我方']
    assert len(outgoing)==len(incoming)==6
    assert not any(outgoing[0]['member']['points'].values()) and outgoing[0]['member']['nature']=='hardy'
    assert outgoing[1]['member']['points']['hp']==outgoing[1]['member']['points']['defense']==32
    assert service.rules.options['natures'][outgoing[1]['member']['nature']]['increased']=='defense'
    assert outgoing[2]['member']['points']['special_defense']==32
    assert incoming[1]['member']['points']['attack']==32 and incoming[1]['member']['nature']=='adamant'
    assert incoming[2]['member']['points']['special_attack']==32 and incoming[2]['member']['nature']=='modest'
    assert outgoing[3]['spread_usage'] is not None
    for scene in scenes:
        assert sum(scene['member']['points'].values())<=66
        assert scene['member']['ability']=='__none__' and scene['member']['item']=='none'
    own=service.presets(service.catalog.record_for_name('烈咬陆鲨'))[0]['member']
    rows,jobs=service.jobs(own,battle_defaults(),scenes,{'weather':'','terrain':'','targets':2,'critical':False})
    for row in rows:assert scenes[row['scenario_index']]['direction']==row['direction']
    assert len(jobs)==6*4+6*8


def test_type_matchups_against_user_reference_and_mega():
    sneasler=type_matchups(['fighting','poison'])
    assert dict(sneasler['weakness'])=={'psychic':4,'ground':2,'flying':2}
    assert dict(sneasler['resistance'])=={'bug':.25,'grass':.5,'fighting':.5,'poison':.5,'rock':.5,'dark':.5}
    assert sneasler['immune']==[]
    base=type_matchups(['fire','flying']);mega=type_matchups(['fire','dragon'])
    assert ('ground',0) in base['immune'] and ('ground',2) in mega['weakness']
    assert ('rock',4) in base['weakness'] and ('rock',2) in mega['weakness']
    assert type_matchups([]) is None

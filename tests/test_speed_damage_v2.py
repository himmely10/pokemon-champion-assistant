from copy import deepcopy
from test_damage import service, pair, member
from champion_assistant.damage import battle_defaults
from champion_assistant.speed import reference_speed

def test_reference_conditions():
    assert reference_speed(120,32,11,True,stage=1,tailwind=True)==849
    assert reference_speed(120,ability='unburden',ability_on=True)==280
    assert reference_speed(120,ability='swift-swim',weather='Rain')==280

def test_saved_speed(service):
    m=member(service); b=battle_defaults(); b['boosts']['speed']=1;b['tailwind']=True
    assert service.speed(m,b,{'weather':'','terrain':''})['speed']==366
    m['points']['speed']=None
    assert service.speed(m,b,{'weather':'','terrain':''})['status']=='unavailable'

def test_saved_speed_defaults_to_no_weather_or_terrain(service):
    m=member(service); b=battle_defaults()
    assert service.speed(m,b,{}) == service.speed(m,b,{'weather':'','terrain':''})

def test_multihit_per_hit_effects(service):
    _,_,jobs=pair(service);j=jobs[0];j['move']='icicle-spear'
    j['defender']['options']['ability']='Stamina'
    r=service.execute([j])[0]
    assert r['status']=='ok',r
    assert [s['hits'] for s in r['multi_hit']['scenarios']]==[2,3,4,5]
    assert r['multi_hit']['scenarios'][0]['maximum'] < 2*r['multi_hit']['single']['maximum']

def test_charge_explicit_and_no_double_count(service):
    _,_,jobs=pair(service);j=jobs[0];j['move']='electro-shot'
    assert service.execute([j])[0]['status']=='unavailable'
    j['charge_boost_included']=False
    first=service.execute([j])[0]
    j['attacker']['options']['boosts']['spa']=1;j['charge_boost_included']=True
    second=service.execute([j])[0]
    assert first['status']==second['status']=='ok'
    assert first['rolls']==second['rolls']

def test_boosts_are_applied_to_correct_direction(service):
    _,_,jobs=pair(service)
    base=service.execute([jobs[0]])[0]
    boosted=deepcopy(jobs[0]);boosted['attacker']['options']['boosts']['atk']=2
    defended=deepcopy(jobs[0]);defended['defender']['options']['boosts']['def']=2
    attack,defense=service.execute([boosted,defended])
    assert attack['minimum']>base['maximum']
    assert defense['maximum']<base['minimum']

def test_charge_limits_and_contrary(service):
    _,_,jobs=pair(service);j=jobs[0];j['move']='electro-shot';j['charge_boost_included']=True
    for ability in ['(No Ability)','Contrary']:
        for stage in [-6,6]:
            j['attacker']['options']['ability']=ability
            j['attacker']['options']['boosts']['spa']=stage
            result=service.execute([j])[0]
            assert result['status']=='ok',result
            assert result['details']['attackBoost']==stage

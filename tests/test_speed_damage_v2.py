from copy import deepcopy
from pathlib import Path
from test_damage import service, pair, member
from champion_assistant.damage import battle_defaults, identifier
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

def test_aura_guard_only_halves_physical_contact_and_fur_coat_halves_physical(service):
    _,_,jobs=pair(service)
    template=jobs[0]

    def result(move, ability='(No Ability)'):
        job=deepcopy(template);job['move']=move;job['defender']['options']['ability']=ability
        return service.execute([job])[0]

    physical_contact=result('close-combat')
    guarded=result('close-combat','Aura Guard')
    assert guarded['maximum']<physical_contact['maximum']
    assert guarded['details']['defenderAbility']=='Aura Guard'
    assert result('draining-kiss','Aura Guard')['rolls']==result('draining-kiss')['rolls']
    assert result('earthquake','Aura Guard')['rolls']==result('earthquake')['rolls']

    coated=result('earthquake','Fur Coat')
    assert coated['maximum']<result('earthquake')['maximum']
    assert coated['details']['defenderAbility']=='Fur Coat'
    assert result('psychic','Fur Coat')['rolls']==result('psychic')['rolls']

    fluffy=result('close-combat','Fluffy')
    assert fluffy['maximum']<physical_contact['maximum']
    assert result('psychic','Fluffy')['rolls']==result('psychic')['rolls']
    assert result('flamethrower','Fluffy')['minimum']>result('flamethrower')['minimum']


def test_offensive_abilities_only_boost_matching_moves(service):
    _,_,jobs=pair(service)
    template=jobs[0]

    def result(move, ability='(No Ability)'):
        job=deepcopy(template);job['move']=move;job['attacker']['options']['ability']=ability
        return service.execute([job])[0]

    assert result('close-combat','Tough Claws')['minimum']>result('close-combat')['minimum']
    assert result('earthquake','Tough Claws')['rolls']==result('earthquake')['rolls']
    assert result('crunch','Strong Jaw')['minimum']>result('crunch')['minimum']
    assert result('psychic','Strong Jaw')['rolls']==result('psychic')['rolls']
    assert result('hyper-voice','Pixilate')['minimum']>result('hyper-voice')['minimum']


def test_low_hp_abilities_can_be_confirmed_or_derived_from_current_hp(service):
    _,_,jobs=pair(service)
    base=deepcopy(jobs[0]);base['move']='flamethrower'
    normal=service.execute([base])[0]
    confirmed=deepcopy(base)
    confirmed['attacker']['options'].update(ability='Blaze',abilityOn=True)
    low_hp=deepcopy(base)
    low_hp['attacker']['options'].update(ability='Blaze',abilityOn=False,curHP=1)
    confirmed_result,low_hp_result=service.execute([confirmed,low_hp])
    assert confirmed_result['minimum']>normal['minimum']
    assert low_hp_result['rolls']==confirmed_result['rolls']

def test_current_direct_damage_ability_inventory_is_wired_to_champions_engine(service):
    keys={
        'adaptability','aerilate','analytic','aura-guard','blaze','dragonize','dry-skin',
        'electromorphosis','fairy-aura','filter','fire-mane','fluffy','friend-guard',
        'fur-coat','guts','heatproof','huge-power','hustle','iron-fist','marvel-scale',
        'mega-launcher','minus','multiscale','overgrow','parental-bond','piercing-drill',
        'pixilate','plus','punk-rock','pure-power','purifying-salt','reckless',
        'refrigerate','rivalry','sand-force','sharpness','sheer-force','sniper',
        'solar-power','solid-rock','stakeout','steely-spirit','strong-jaw',
        'supreme-overlord','swarm','technician','thick-fat','torrent','tough-claws',
        'unseen-fist','water-bubble'}
    holders={key for record in service.catalog.records
             for key in service.rules.ability_keys(service.rules.identity(record))}
    assert keys<=holders
    mechanics=''.join((Path(__file__).parents[1]/path).read_text(encoding='utf-8') for path in (
        'damage_engine/vendor/smogon-calc/src/mechanics/champions.ts',
        'damage_engine/vendor/smogon-calc/src/mechanics/util.ts'))
    for key in keys:
        engine=service.lookups['abilities'].get(identifier(key))
        assert engine, key
        # Fairy Aura is generated from the move type instead of appearing as a literal.
        assert engine['name'] in mechanics or key=='fairy-aura', key

def test_charge_limits_and_contrary(service):
    _,_,jobs=pair(service);j=jobs[0];j['move']='electro-shot';j['charge_boost_included']=True
    for ability in ['(No Ability)','Contrary']:
        for stage in [-6,6]:
            j['attacker']['options']['ability']=ability
            j['attacker']['options']['boosts']['spa']=stage
            result=service.execute([j])[0]
            assert result['status']=='ok',result
            assert result['details']['attackBoost']==stage

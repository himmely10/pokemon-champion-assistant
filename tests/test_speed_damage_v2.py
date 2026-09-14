from copy import deepcopy
from pathlib import Path
import pytest
from test_damage import service, pair, member
from champion_assistant.damage import battle_defaults, identifier
from champion_assistant.speed import reference_speed
from champion_assistant.ability_conditions import (ABILITY_TRIGGER_LABELS, effective_accuracy,
                                                    effective_priority)

def test_reference_conditions():
    assert reference_speed(120,32,11,True,stage=1,tailwind=True)==849
    assert reference_speed(120,ability='unburden',ability_on=True)==280
    assert reference_speed(120,ability='swift-swim',weather='Rain')==280
    assert reference_speed(120,ability='chlorophyll')==140
    assert reference_speed(120,ability='chlorophyll',ability_on=True)==280
    assert reference_speed(120,ability='quick-feet',ability_on=True)==210
    assert reference_speed(120,ability='protosynthesis',ability_on=True)==210


def test_scene_dependent_abilities_explain_their_trigger():
    expected={
        'chlorophyll':'大晴天', 'swift-swim':'下雨', 'sand-rush':'沙暴',
        'slush-rush':'下雪', 'surge-surfer':'电气场地', 'quick-feet':'异常状态',
        'protosynthesis':'驱劲能量', 'quark-drive':'电气场地',
        'solar-power':'大晴天', 'sand-force':'沙暴', 'guts':'异常状态',
        'marvel-scale':'异常状态', 'grass-pelt':'青草场地',
        'multiscale':'满 HP', 'merciless':'中毒', 'rivalry':'同性'}
    for ability,condition in expected.items():
        assert condition in ABILITY_TRIGGER_LABELS[ability]


def test_accuracy_abilities_and_weather_conditions(service):
    attacker=member(service);defender=member(service)
    ab,db=battle_defaults(),battle_defaults()
    sleep=service.catalog.moves['sleep-powder']
    physical=service.catalog.moves['earthquake']
    defender['ability']='sand-veil'
    assert effective_accuracy(sleep,attacker,defender,ab,db,{'weather':'Sand'}) == {
        'percent':60.0,'notes':['沙隐 ×0.8']}
    assert effective_accuracy(sleep,attacker,defender,ab,db,{'weather':''})['percent']==75
    db['ability_on']=True
    assert effective_accuracy(sleep,attacker,defender,ab,db,{'weather':''})['percent']==60
    defender['ability']='__none__';db['ability_on']=False
    attacker['ability']='compound-eyes'
    assert effective_accuracy(sleep,attacker,defender,ab,db,{})['percent']==97.5
    attacker['ability']='hustle'
    assert effective_accuracy(physical,attacker,defender,ab,db,{})['percent']==80
    defender['ability']='no-guard'
    assert effective_accuracy(sleep,attacker,defender,ab,db,{})['percent']==100


def test_dynamic_priority_conditions(service):
    grassy=service.catalog.moves['grassy-glide']
    brave_bird=service.catalog.moves['brave-bird']
    tailwind=service.catalog.moves['tailwind']
    state=battle_defaults()
    rillaboom=member(service,'轰擂金刚猩')
    talonflame=member(service,'烈箭鹰')
    whimsicott=member(service,'风妖精')
    talonflame['ability']='gale-wings';whimsicott['ability']='prankster'
    assert effective_priority(grassy,rillaboom,state,{'terrain':''})['current']==0
    boosted=effective_priority(grassy,rillaboom,state,{'terrain':'Grassy'})
    assert boosted['current']==1 and '青草场地' in boosted['notes'][0]
    assert effective_priority(brave_bird,talonflame,state,{},full_hp=True)['current']==1
    assert effective_priority(brave_bird,talonflame,state,{},full_hp=False)['current']==0
    prankster=effective_priority(tailwind,whimsicott,state,{})
    assert prankster['current']==1 and '恶作剧之心' in prankster['notes'][0]


def test_prankster_status_move_is_ineffective_only_when_targeting_dark(service):
    attacker=member(service,'风妖精',moves=['taunt','tailwind',None,None])
    attacker['ability']='prankster'
    defender=member(service,'长毛巨魔',moves=[None]*4)
    rows,jobs=service.jobs(attacker,battle_defaults(),[{'name':'恶属性目标','member':defender,'battle':battle_defaults()}],
        {'weather':'','terrain':'','critical':False,'targets':2},common=False)
    results=service.execute(jobs)
    assert results[0]['status']=='status_move' and '对恶属性目标无效' in results[0]['reason']
    assert results[1]['status']=='status_move' and '对恶属性目标无效' not in results[1]['reason']
    assert rows[0]['priority']['current']==1


def test_grassy_glide_dynamic_priority_is_blocked_by_armor_tail(service):
    _,_,jobs=pair(service);job=jobs[0];job['move']='grassy-glide'
    job['field']['terrain']='Grassy'
    normal=service.execute([deepcopy(job)])[0]
    job['defender']['options']['ability']='Armor Tail'
    blocked=service.execute([job])[0]
    assert normal['maximum']>0 and blocked['maximum']==0

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


@pytest.mark.parametrize('ability,move,side',[
    ('Solar Power','flamethrower','attacker'),
    ('Sand Force','earthquake','attacker'),
    ('Guts','close-combat','attacker'),
    ('Marvel Scale','earthquake','defender'),
    ('Grass Pelt','earthquake','defender'),
])
def test_scene_ability_checkbox_forces_damage_condition(service,ability,move,side):
    _,_,jobs=pair(service);base=deepcopy(jobs[0]);base['move']=move
    subject=base[side]['options'];subject.update(ability=ability,abilityOn=False)
    inactive=service.execute([base])[0]
    subject['abilityOn']=True
    active=service.execute([base])[0]
    assert active['status']==inactive['status']=='ok'
    if side=='attacker':assert active['minimum']>inactive['minimum']
    else:assert active['maximum']<inactive['maximum']


def test_multiscale_checkbox_can_confirm_full_hp_condition(service):
    _,_,jobs=pair(service);job=deepcopy(jobs[0])
    defender=job['defender']['options'];defender.update(
        ability='Multiscale',curHP=job['defender']['baseStats']['hp'] + 74,abilityOn=False)
    inactive=service.execute([job])[0]
    defender['abilityOn']=True
    active=service.execute([job])[0]
    assert active['maximum']<inactive['maximum']

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

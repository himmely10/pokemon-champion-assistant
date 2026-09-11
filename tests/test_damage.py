"""Hand-worked damage fixtures, in-game stat observations and scenario boundaries."""
from copy import deepcopy
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest

from champion_assistant.damage import DamageService, battle_defaults, STAT_IDS
from champion_assistant.data.references import ReferenceCatalog
from champion_assistant.teams import STATS, blank_member


@pytest.fixture(scope='module')
def service():return DamageService(ReferenceCatalog('pokemon'))


def member(service, name='烈咬陆鲨', points=None, nature='hardy', moves=None):
    record=service.catalog.record_for_name(name)
    m=blank_member(service.rules.identity(record))
    m.update(points={k:(points or {}).get(k,0) for k in STATS},nature=nature,ability='__none__',item='none',
             moves=moves or ['earthquake','dragon-claw','protect','rock-slide'])
    return m


def pair(service, *, targets=2, reflect=False, burn=False, move='earthquake'):
    a=member(service,points={'attack':32})
    a['moves']=[move,None,None,None]
    d=member(service,'巨金怪',{'hp':32},moves=['meteor-mash',None,None,None])
    ab,db=battle_defaults(),battle_defaults()
    ab['status']='brn' if burn else '';db['reflect']=reflect
    env={'weather':'','terrain':'','critical':False,'targets':targets}
    rows,jobs=service.jobs(a,ab,[{'name':'独立基准','member':d,'battle':db}],env,common=False)
    return service.execute(jobs),rows,jobs


@pytest.mark.parametrize('targets,reflect,burn,expected',[
    (2,False,False,(102,122)), (1,False,False,(138,164)),
    (2,True,False,(68,81)), (1,True,False,(92,109)), (2,False,True,(51,61))])
def test_hand_calculated_ground_stab_doubles(service,targets,reflect,burn,expected):
    # Level 50, Atk=182, Def=150, BP=100 => base 55. Spread rounds to 41.
    # Random 85..100, STAB 1.5 (ties down), type 2, then doubles screen 2732/4096.
    output,_,_=pair(service,targets=targets,reflect=reflect,burn=burn)
    r=output[0]
    assert r['status']=='ok',r
    assert (r['minimum'],r['maximum'])==expected
    assert len(r['rolls'])==16 and r['max_hp']==187
    assert r['percent_max']==pytest.approx(expected[1]/187*100)


def test_hand_calculated_special_and_sun(service):
    # Charizard SpA 129, Venusaur SpD 120: base 44 (sun 66), STAB, 2x weakness.
    a=member(service,'喷火龙',moves=['flamethrower',None,None,None])
    d=member(service,'妙蛙花',moves=[None]*4)
    for weather,expected in [('',(110,132)),('Sun',(168,198))]:
        rows,jobs=service.jobs(a,battle_defaults(),[{'name':'特攻基准','member':d,'battle':battle_defaults()}],
            {'weather':weather,'terrain':'','critical':False,'targets':2},common=False)
        r=service.execute(jobs)[0]
        assert (r['minimum'],r['maximum'])==expected,r


def test_immunity_status_unsupported_and_reverse_direction(service):
    output,rows,jobs=pair(service)
    assert output[4]['attacker_stats']['atk']==155 and output[4]['defender_stats']['def']==115
    assert (output[4]['minimum'],output[4]['maximum'])==(69,82)
    assert rows[4]['direction']=='对手 → 我方'
    a=member(service,points={'attack':32})
    d=member(service,'烈箭鹰',moves=[None]*4)
    _,jobs=service.jobs(a,battle_defaults(),[{'name':'免疫','member':d,'battle':battle_defaults()}],
        {'weather':'','terrain':'','critical':False,'targets':2},common=False)
    result=service.execute(jobs)
    assert result[0]['status']=='ok' and result[0]['maximum']==0
    assert result[2]['status']=='status_move'
    _,_,jobs=pair(service)
    jobs[0]['move']='bullet-seed'
    assert service.execute(jobs)[0]['status']=='unavailable'


@pytest.mark.parametrize('field', ['points','ability','nature','item'])
def test_unknown_build_fields_never_become_defaults(service,field):
    a=member(service)
    if field=='points':a['points']['hp']=None
    else:a[field]=None
    with pytest.raises(ValueError):service.prepare(a,battle_defaults())


def test_snapshot_stat_mismatch_and_current_hp(service):
    _,_,jobs=pair(service)
    jobs[0]['attacker']['baseStats']['atk']+=1
    assert service.execute(jobs)[0]['status']=='unavailable'
    a=member(service)
    state=battle_defaults();state['hp']=100
    assert service.prepare(a,state)['options']['curHP']==100
    state['hp']=999
    with pytest.raises(ValueError):service.prepare(a,state)


def test_independent_spreads_and_usage_selection(service):
    own=member(service,points={'attack':32})
    record=service.catalog.record_for_name('巨金怪')
    presets=service.presets(record)
    rows,jobs=service.jobs(own,battle_defaults(),presets,{'weather':'','terrain':'','critical':False,'targets':2})
    results=service.execute(jobs)
    outputs=[r for row,r in zip(rows,results) if row['direction']=='我方 → 对手' and row['move']['key']=='earthquake']
    assert len(outputs)==3
    assert len({(r['max_hp'],r['minimum'],r['maximum']) for r in outputs})==3
    assert all(row['move']['key'] in service.common_moves(record, damage_only=True) for row in rows if row['direction']=='对手 → 我方')


def test_stats_against_user_status_screenshot(service):
    observed=[('沙奈朵',[0,0,2,32,0,32],'modest',[143,76,87,194,135,132]),
        ('爱管侍（雌性的样子）',[32,0,32,0,2,0],'relaxed',[177,75,128,115,127,94]),
        ('煤炭龟',[32,0,0,32,2,0],'quiet',[177,105,160,150,92,36]),
        ('大狃拉',[2,32,0,0,0,32],'jolly',[157,182,80,54,100,189]),
        ('炽焰咆哮虎',[29,32,3,0,2,0],'brave',[199,183,113,100,112,72]),
        ('幽尾玄鱼（雄性的样子）',[0,32,1,0,1,32],'jolly',[195,164,86,90,96,143])]
    jobs=[]
    for name,points,nature,expected in observed:
        m=member(service,name,dict(zip(STATS,points)),nature,moves=[None]*4)
        p=service.prepare(m,battle_defaults())
        jobs.append({'attacker':p,'defender':p,'move':'earthquake','critical':False,'field':{'gameType':'Doubles'}})
    for r,(_,_,_,expected) in zip(service.execute(jobs),observed):
        assert r['status']=='ok',r
        assert [r['attacker_stats'][k] for k in STAT_IDS.values()]==expected


def test_mega_types_are_not_borrowed_from_base(service):
    a=member(service,points={'attack':32})
    record=next(r for r in service.catalog.records if r.get('opgg_key')=='mega-charizard-x')
    x=member(service,service.catalog.display_name(record),moves=[None]*4)
    if not x['identity']:pytest.fail('missing Mega identity')
    scenarios=[{'name':'X','member':x,'battle':battle_defaults()}]
    _,jobs=service.jobs(a,battle_defaults(),scenarios,{'weather':'','terrain':'','critical':False,'targets':2},common=False)
    assert service.execute(jobs)[0]['maximum']>0  # Mega X loses Flying immunity.


@pytest.mark.parametrize('condition,expected',[
    ('orb',(133,159)),('boost',(152,182)),
    ('help',(152,182)),('crit',(152,182)),('protect',(0,0))])
def test_explicit_modifiers_against_hand_baseline(service,condition,expected):
    # Same 55 base / 41 spread baseline. 1.5 Atk or BP => base 82 / spread 61.
    # Crit rounds 41*1.5 to 61. Life Orb uses final 5324/4096 with pokeRound.
    _,_,jobs=pair(service)
    job=jobs[0]
    if condition=='orb':job['attacker']['options']['item']='Life Orb'
    if condition=='boost':job['attacker']['options']['boosts']['atk']=1
    if condition=='help':job['field']['attackerSide']['isHelpingHand']=True
    if condition=='crit':job['critical']=True
    if condition=='protect':job['field']['defenderSide']['isProtected']=True
    r=service.execute([job])[0]
    assert r['status']=='ok',r
    assert (r['minimum'],r['maximum'])==expected


def test_special_move_guards_and_fixed_damage(service):
    _,_,jobs=pair(service)
    for move in ['counter','super-fang','fissure','meteor-beam']:
        jobs[0]['move']=move
        assert service.execute(jobs[:1])[0]['status']=='unavailable'
    jobs[0]['move']='seismic-toss'
    r=service.execute(jobs[:1])[0]
    assert r['status']=='ok' and r['minimum']==r['maximum']==50
    # Choice Band is absent from the pinned Champions item roster; never ignore it.
    jobs[0]['attacker']['options']['item']='Choice Band'
    assert service.execute(jobs[:1])[0]['status']=='unavailable'

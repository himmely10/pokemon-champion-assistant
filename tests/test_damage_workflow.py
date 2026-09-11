"""Battle-only Mega/Trace choices, auto refresh and accessible team saving."""
from copy import deepcopy
from threading import Event
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QInputDialog, QMessageBox, QPushButton
from champion_assistant.data.references import ReferenceCatalog
from champion_assistant.damage import DamageService, battle_defaults
from champion_assistant.teams import TeamStore
from champion_assistant.ui.damage_dialog import DamageDialog
from champion_assistant.ui.team_dialog import TeamDialog, select


@pytest.fixture(scope='module')
def service():return DamageService(ReferenceCatalog('pokemon'))


@pytest.fixture
def team(service,tmp_path):
    own=service.presets(service.catalog.record_for_name('沙奈朵'))[0]['member']
    own.update(points=dict(hp=0,attack=0,defense=2,special_attack=32,special_defense=0,speed=28),
               nature='modest',ability='trace',item='gardevoirite',
               moves=['hyper-voice','expanding-force','trick-room','protect'])
    store=TeamStore(tmp_path/'teams.db',service.rules)
    store.save({'name':'沙奈朵队','registration':'partial','members':[own]})
    return store


def mega(service,key):
    return service.rules.identity(next(r for r in service.catalog.records if r.get('opgg_key')==key))


def test_trace_requires_explicit_state_and_mega_uses_pixilate(service,team):
    original=team.list()[0]['members'][0];own=deepcopy(original)
    with pytest.raises(ValueError,match='复制'):service.prepare(own,battle_defaults())
    b={**battle_defaults(),'copied_ability':'__none__'}
    assert service.prepare(own,b)['options']['ability']=='(No Ability)'
    b['copied_ability']='levitate'
    assert service.prepare(own,b)['options']['ability']=='Levitate'
    evolved=service.battle_form(own,mega(service,'mega-gardevoir'))
    p=service.prepare(evolved,battle_defaults())
    assert p['options']['ability']=='Pixilate' and p['baseStats']['spa']==165
    assert own==original and evolved['points']==original['points']
    target=service.comparison_presets(service.catalog.record_for_name('耿鬼'))[0]
    env={'weather':'','terrain':'','critical':False,'targets':2}
    _,jobs=service.jobs(own,{**b,'copied_ability':'__none__'},[target],env)
    normal=service.execute(jobs)[0]
    _,jobs=service.jobs(evolved,battle_defaults(),[target],env)
    result=service.execute(jobs)[0]
    assert normal['maximum']==0  # Ordinary Normal Hyper Voice cannot hit Ghost.
    assert result['status']=='ok' and result['minimum']>0
    assert result['attacker_stats']['spa']==238
    own['item']='none'
    with pytest.raises(ValueError,match='进化石'):service.battle_form(own,mega(service,'mega-gardevoir'))
    with pytest.raises(ValueError,match='同一家族'):service.battle_form(original,mega(service,'mega-charizard-x'))


def test_incoming_excludes_status_for_common_and_manual(service,team):
    own=team.list()[0]['members'][0]
    scenes=service.comparison_presets(service.catalog.record_for_name('巨金怪'))
    env={'weather':'','terrain':'','critical':False,'targets':2}
    for common in (True,False):
        rows,_=service.jobs(own,battle_defaults(),scenes,env,common=common)
        assert all(r['move']['category']!='status' for r in rows if r['direction']=='对手 → 我方' and r['move'])
    only_status=deepcopy(scenes[-1])
    only_status['member']['moves']=['protect']*4
    rows,_=service.jobs(own,battle_defaults(),[only_status],env,common=False)
    assert not rows  # No misleading unknown-move row when every selected move is status.
    preset=service.comparison_presets(service.rules.record(mega(service,'mega-gardevoir')))[0]
    assert preset['member']['ability']=='pixilate' and preset['member']['item']=='gardevoirite'


def test_auto_calculation_and_form_choices_preserve_saved_team(qtbot,service,team):
    before=deepcopy(team.list())
    d=DamageDialog(service.catalog,team.list,lambda:None);qtbot.addWidget(d)
    select(d.saved_team,before[0]['id']);d.set_target(service.catalog.record_for_name('耿鬼'))
    d.show()
    qtbot.waitUntil(lambda:bool(d.rows),timeout=15000)
    assert '复制' in d.table.item(0,1).toolTip()
    select(d.copied_ability,'__none__')
    qtbot.waitUntil(lambda:bool(d.rows) and d.rows[0]['status']=='ok',timeout=15000)
    assert d.rows[0]['maximum']==0
    select(d.own_form,mega(service,'mega-gardevoir'))
    qtbot.waitUntil(lambda:bool(d.rows) and d.rows[0]['status']=='ok',timeout=15000)
    assert d.rows[0]['minimum']>0
    select(d.enemy_form,mega(service,'mega-gengar'))
    qtbot.waitUntil(lambda:bool(d.rows),timeout=15000)
    assert d.last_request['scenarios'][0]['member']['identity']==mega(service,'mega-gengar')
    d.tabs.setCurrentIndex(2);d.weather.setCurrentIndex(1)
    qtbot.waitUntil(lambda:bool(d.rows),timeout=15000)
    assert d.tabs.currentIndex()==2  # Auto update never steals the settings tab.
    assert not any(b.text()=='计算伤害对照' for b in d.findChildren(QPushButton))
    assert team.list()==before
    d.close()


def test_auto_change_during_worker_uses_latest_state(qtbot,service,team):
    d=DamageDialog(service.catalog,team.list,lambda:None);qtbot.addWidget(d)
    select(d.saved_team,team.list()[0]['id']);d.set_target(service.catalog.record_for_name('巨金怪'))
    select(d.own_form,mega(service,'mega-gardevoir'))
    started,release=Event(),Event();execute=d.service.execute
    def delayed(jobs):
        started.set();assert release.wait(5);return execute(jobs)
    d.service.execute=delayed;d.show()
    try:
        qtbot.waitUntil(started.is_set,timeout=3000)
        d.weather.setCurrentIndex(1)
        qtbot.wait(450)  # Debounce expires while the previous worker is still busy.
    finally:release.set()
    qtbot.waitUntil(lambda:bool(d.rows),timeout=15000)
    assert d.last_request['environment']['weather']=='Sun'
    d.close()


def test_save_warning_rename_and_visible_footer(qtbot,service,team,monkeypatch):
    d=TeamDialog(service.catalog,team.path);qtbot.addWidget(d)
    d.load_team(team.list()[0]);d.resize(900,600);d.show();qtbot.wait(30)
    pos=d.save_button.mapTo(d,QPoint(0,0))
    assert pos.y()+d.save_button.height()<=d.height()
    assert d.save_button.visibleRegion().boundingRect().height()==d.save_button.height()
    monkeypatch.setattr(QInputDialog,'getText',lambda *a,**k:('我的空间队',True))
    d.rename_team();assert d.dirty
    assert team.list()[0]['name']=='沙奈朵队'
    d.save_team()
    assert team.list()[0]['name']=='我的空间队'
    assert d.warning_box.icon()==QMessageBox.Icon.Warning
    assert '沙奈朵' in d.warning_box.text() and '复制' in d.warning_box.text()
    d.warning_box.accept();d.close()


def test_spread_header_hover_and_click_show_actual_points(qtbot,service,team):
    d=DamageDialog(service.catalog,team.list,lambda:None);qtbot.addWidget(d)
    select(d.saved_team,team.list()[0]['id']);d.set_target(service.catalog.record_for_name('大狃拉'))
    select(d.own_form,mega(service,'mega-gardevoir'))
    d.calculate();qtbot.waitUntil(lambda:d.worker is None,timeout=15000)
    for table in (d.table,d.incoming_table):
        col=next(i for i in range(1,table.columnCount()) if table.horizontalHeaderItem(i).text().startswith('常用分配 1'))
        tip=table.horizontalHeaderItem(col).toolTip()
        direction='我方 → 对手' if table is d.table else '对手 → 我方'
        scene=next(s for s in d.last_request['scenarios'] if s['direction']==direction and s['name']=='常用分配 1')
        for key,label in [('hp','HP'),('attack','攻击'),('defense','防御'),('special_attack','特攻'),('special_defense','特防'),('speed','速度')]:
            assert f"{label}：{scene['member']['points'][key]}" in tip
        assert '不代表与性格的联合概率' in tip
        table.horizontalHeader().sectionClicked.emit(col)
        assert '常用分配 1' in d.detail.toPlainText()
        assert '对手配置（本列假设）' in d.detail.toPlainText()
        assert '培养点' in d.detail.toPlainText()
    revision=d.revision;old_height=d.table.rowHeight(0)
    select(d.zoom,150)
    assert d.table.rowHeight(0)>old_height and d.revision==revision
    assert d.detail.font().pixelSize()>=22
    d.show();d.toggle_fullscreen();qtbot.wait(450)
    assert d.worker is None and d.revision==revision
    assert '常用分配 1' in d.detail.toPlainText()
    d.toggle_fullscreen();d.close()


def test_resizable_detail_and_fullscreen_exit(qtbot,service,team):
    from PySide6.QtCore import Qt
    d=DamageDialog(service.catalog,team.list,lambda:None);qtbot.addWidget(d)
    d.resize(1280,900);d.show();qtbot.wait(30)
    before=d.result_splitter.sizes()
    d.result_splitter.moveSplitter(before[0]-70,1)
    assert d.result_splitter.sizes()[1]>before[1]
    assert d.detail.maximumHeight()>1000
    assert d.windowFlags() & Qt.WindowType.WindowMaximizeButtonHint
    d.showMaximized();qtbot.wait(20)
    d.toggle_fullscreen();assert d.isFullScreen()
    qtbot.keyClick(d,Qt.Key.Key_Escape)
    assert not d.isFullScreen() and d.isMaximized() and d.isVisible()
    d.close()

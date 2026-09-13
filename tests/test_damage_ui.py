"""Saved-team selection, revisions and real local damage engine output."""
from copy import deepcopy
from threading import Event
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest

from champion_assistant.data.references import ReferenceCatalog
from champion_assistant.damage import DamageService
from champion_assistant.teams import TeamStore
from champion_assistant.ui.damage_dialog import DamageDialog
from champion_assistant.ui.team_dialog import TeamDialog, select


@pytest.fixture(scope='module')
def service():return DamageService(ReferenceCatalog('pokemon'))


@pytest.fixture
def store(service,tmp_path):
    store=TeamStore(tmp_path/'teams.db',service.rules)
    own=service.presets(service.catalog.record_for_name('烈咬陆鲨'))[0]['member']
    own['ability']='rough-skin'
    own['moves']=['earthquake','dragon-claw','protect','rock-slide']
    store.save({'name':'测试队伍 A','registration':'partial','members':[own]})
    return store


def configure(dialog,service):
    select(dialog.saved_team,dialog.list_teams()[0]['id'])
    dialog.set_target(service.catalog.record_for_name('巨金怪'))


def test_support_effects_auto_calculate_grouping_and_details(qtbot,service,store):
    from PySide6.QtWidgets import QGroupBox
    d=DamageDialog(service.catalog,store.list,lambda:None);qtbot.addWidget(d)
    configure(d,service);d.show()
    qtbot.waitUntil(lambda:bool(d.rows) and d.worker is None,timeout=15000)
    base=d.rows[0]['maximum']
    assert not d.own_battle.flags['helping_hand'].isChecked()
    assert {'进攻辅助 · 此方','防守保护 · 此方','速度条件 · 此方'} <= {
        box.title() for box in d.own_battle.findChildren(QGroupBox)}
    d.own_battle.flags['helping_hand'].setChecked(True)
    qtbot.waitUntil(lambda:bool(d.rows) and d.worker is None,timeout=15000)
    assert d.rows[0]['maximum']>base
    d.show_detail(0)
    assert '本次受到帮助 · 已启用 / 本招适用' in d.detail.toPlainText()
    incoming=next(i for i,row in enumerate(d.rows) if row['direction']=='对手 → 我方')
    d.show_detail(incoming)
    assert '本招忽略' in d.detail.toPlainText() and '帮助只作用于攻击方' in d.detail.toPlainText()
    d.own_battle.flags['helping_hand'].setChecked(False)
    qtbot.waitUntil(lambda:bool(d.rows) and d.worker is None,timeout=15000)
    assert d.rows[0]['maximum']==base
    d.pages[0].battle.flags['aurora_veil'].setChecked(True)
    qtbot.waitUntil(lambda:bool(d.rows) and d.worker is None,timeout=15000)
    assert d.rows[0]['maximum']<base
    d.show_detail(0);assert '极光幕 · 已启用 / 本招适用' in d.detail.toPlainText()
    assert all(row['move']['category']!='status' for row in d.rows if row['direction']=='对手 → 我方' and row['move'])


def test_real_bidirectional_results_and_input_revoke(qtbot,service,store):
    d=DamageDialog(service.catalog,store.list,lambda:None)
    qtbot.addWidget(d)
    assert d.selected_team is None  # Selection is explicit, never inferred from species.
    configure(d,service)
    assert not d.own.isEnabled()
    d.calculate();qtbot.waitUntil(lambda:d.worker is None,timeout=15000)
    assert d.tabs.currentIndex()==0 and d.table.rowCount()==4
    assert d.incoming_table.rowCount()==8
    assert '地震' in d.table.item(0,0).text()
    assert '零耐久投入' in d.table.horizontalHeaderItem(1).text()
    assert '满物攻' in d.incoming_table.horizontalHeaderItem(2).text()
    assert {'我方 → 对手','对手 → 我方'}=={r['direction'] for r in d.rows}
    assert any(r['status']=='ok' for r in d.rows)
    assert '测试队伍 A' in d.results_note.text()
    assert '培养点' in d.detail.toPlainText() and '独立随机结果' in d.detail.toPlainText()
    d.tabs.setCurrentIndex(1)
    assert '对手 → 我方' in d.detail.toPlainText()
    assert d.table.item(0,0).toolTip()
    assert '冰 4×' in d.own_matchups.text()
    d.pages[0].battle.boosts['defense'].setValue(1)
    assert not d.rows and d.table.rowCount()==0 and not d.detail.toPlainText()
    d.set_target(None)
    assert not d.pages
    d.calculate();assert d.worker is None


@pytest.mark.parametrize('change',['weather','usage','saved_revision','deleted'])
def test_late_result_is_discarded(qtbot,service,store,monkeypatch,change):
    d=DamageDialog(service.catalog,store.list,lambda:None)
    qtbot.addWidget(d);configure(d,service)
    started,release=Event(),Event()
    execute=d.service.execute
    def delayed(jobs):
        started.set();assert release.wait(5)
        return execute(jobs)
    d.service.execute=delayed
    try:
        d.calculate();qtbot.waitUntil(started.is_set)
        if change=='weather':d.weather.setCurrentIndex(1)
        elif change=='usage':
            usage=deepcopy(d.service.catalog.usage)
            usage['pokemon']['metagross']['fetched_at']='new snapshot'
            monkeypatch.setattr(d.service.catalog,'usage',usage)
        elif change=='saved_revision':store.save(store.list()[0])
        else:store.delete(store.list()[0])
    finally:release.set()
    qtbot.waitUntil(lambda:d.worker is None,timeout=15000)
    assert not d.rows and d.table.rowCount()==0


def test_saved_build_used_without_observations_and_save_refreshes(qtbot,service,store):
    team=TeamDialog(service.catalog,store.path);qtbot.addWidget(team)
    saved=store.list()[0];team.load_team(saved)
    d=DamageDialog(service.catalog,store.list,lambda:None);qtbot.addWidget(d)
    team.savedTeamsChanged.connect(d.refresh_teams)
    configure(d,service)
    assert not team.result['builds']
    assert d.snapshot()['team']['id']==saved['id']
    d.calculate();qtbot.waitUntil(lambda:d.worker is None,timeout=15000)
    assert any(r['status']=='ok' for r in d.rows)
    # Unsaved edits are never used. Only save changes the persisted calculation inputs.
    team.editors[0].points['attack'].setValue(0)
    assert d.snapshot()['own']['points']['attack']==32
    assert d.rows
    team.save_team()
    assert not d.rows and d.snapshot()['own']['points']['attack']==0
    assert not team.result['builds']
    # Deletion must clear the choice, even if another team contains the same species.
    another=store.list()[0];another.pop('id');another.pop('revision');another['name']='队伍 B'
    store.save(another)
    store.delete(next(t for t in store.list() if t['id']==saved['id']))
    d.refresh_teams()
    assert d.selected_team is None and d.own.read() is None
    with pytest.raises(ValueError,match='选择预存队伍'):d.snapshot()


def test_same_species_in_different_teams_never_share_builds(qtbot,service,store):
    first=store.list()[0]
    second=deepcopy(first);second.pop('id');second.pop('revision')
    second['name']='队伍 B';second['members'][0]['points']['attack']=0
    second=store.save(second)
    d=DamageDialog(service.catalog,store.list,lambda:None);qtbot.addWidget(d)
    d.set_target(service.catalog.record_for_name('巨金怪'))
    select(d.saved_team,first['id']);assert d.snapshot()['own']['points']['attack']==32
    d.own_battle.hp.setValue(12)
    select(d.saved_team,second['id']);assert d.snapshot()['own']['points']['attack']==0
    assert d.own_battle.hp.value()==0
    d.clear_session()
    assert d.selected_team['id']==second['id'] and d.own.read()==second['members'][0]
    assert not d.pages


def test_no_saved_team_and_read_error(qtbot,service):
    d=DamageDialog(service.catalog,lambda:[],lambda:None);qtbot.addWidget(d)
    d.set_target(service.catalog.record_for_name('巨金怪'))
    d.calculate();assert d.worker is None
    assert '选择预存队伍' in d.status.text()
    def broken():raise OSError('unavailable')
    d.list_teams=broken;d.refresh_teams()
    assert '读取失败' in d.team_note.text() and d.own.read() is None


def test_training_refresh_and_edited_usage_labels(qtbot,service,store,monkeypatch):
    d=DamageDialog(service.catalog,store.list,lambda:None);qtbot.addWidget(d);configure(d,service)
    d.pages[3].editor.points['hp'].setValue(0)
    scene=d.snapshot()['scenarios'][3]
    assert scene['spread_usage'] is None and '已调整' in scene['name']
    d.refresh_statistics()
    assert d.pages[3].editor.points['hp'].value()==0  # No statistical change: retain manual input.
    usage=deepcopy(d.service.catalog.usage)
    usage['pokemon']['metagross']['training'][0]['points']=dict.fromkeys(scene['member']['points'],0)
    monkeypatch.setattr(d.service.catalog,'usage',usage)
    with pytest.raises(ValueError,match='培养点统计已更新'):d.snapshot()
    d.refresh_statistics()
    assert not any(d.pages[3].editor.read()['points'].values())
    assert d.snapshot()['scenarios'][3]['spread_usage'] is not None


def test_missing_scenario_nature_is_visible_without_render_error(qtbot,service,store):
    d=DamageDialog(service.catalog,store.list,lambda:None);qtbot.addWidget(d);configure(d,service)
    select(d.pages[0].editor.nature,None)
    d.calculate();qtbot.waitUntil(lambda:d.worker is None,timeout=15000)
    assert '未知性格' in d.table.horizontalHeaderItem(1).text()
    assert '暂不可计算' in d.table.item(0,1).text()


def test_main_window_target_and_new_capture_preserve_saved_team(qtbot,service,store,tmp_path,monkeypatch):
    from PySide6.QtCore import QObject,Signal,Slot
    from champion_assistant.ui.main_window import MainWindow
    class Worker(QObject):
        finished=Signal(int,str,object,str)
        def __init__(self,*args):
            super().__init__();self.cancelled=Event()
        @Slot(int,str,object)
        def run(self,revision,operation,payload):
            self.finished.emit(revision,operation,None,'测试结束')
    w=MainWindow(settings_path=tmp_path/'ui.json',worker_factory=Worker)
    qtbot.addWidget(w);monkeypatch.setattr(w,'damage_teams',lambda catalog=None:store.list())
    try:
        w.opponents=[{'name':'巨金怪'}, {'name':'大狃拉'}]
        w._render_team();w.team_list.setCurrentRow(0)
        w.refresh_saved_team_selection()
        select(w.saved_team_selector,store.list()[0]['id'])
        assert '我方实配速度：' in w.saved_speed_label.text()
        assert '待确认' not in w.saved_speed_label.text()
        w.open_damage();d=w.damage_dialog
        assert len(d.pages)==12
        w.show_record(w.catalog.record_for_name('大狃拉'))
        assert '超能力 4×' in w.matchups.text()
        configure(d,service)
        w._show_empty_reference()
        # Reference clearing selects the unknown sixth slot; recognized roster remains available.
        assert not d.pages
        w.show_record(w.catalog.record_for_name('巨金怪'))
        assert len(d.pages)==12
        d.own_battle.hp.setValue(12)
        w.open_image('new.png')
        assert d.pages and d.own.read()==store.list()[0]['members'][0]
        assert d.own_battle.hp.value()==12
        qtbot.waitUntil(lambda:not w.busy)
    finally:w.close()

def test_battle_context_restricts_slots_and_defaults_saved_id(qtbot,service,store):
    team=store.list()[0]
    d=DamageDialog(service.catalog,store.list,lambda:None,team_id=team['id'],opponents=[service.catalog.record_for_name('巨金怪'),None])
    qtbot.addWidget(d)
    assert d.saved_team.currentData()==team['id']
    assert d.target.count()==6 and not d.target.isEditable()
    assert '未确认' in d.target.itemText(1)
    d.target.setCurrentIndex(1)
    assert not d.pages
    d.set_target(service.catalog.record_for_name('皮卡丘'))
    assert d.target.count()==6 and d.target.currentData() is None


def test_quick_enemy_stages_apply_to_every_scenario(qtbot,service,store):
    d=DamageDialog(service.catalog,store.list,lambda:None);qtbot.addWidget(d);configure(d,service)
    d.enemy_boosts['defense'].setValue(2)
    d.enemy_tailwind.setChecked(True)
    request=d.snapshot()
    assert all(p['battle']['boosts']['defense']==2 and p['battle']['tailwind'] for p in request['scenarios'])
    assert d.own.isHidden()


def test_mega_stone_conflict_requires_explicit_session_assumption(qtbot,service,store):
    member=service.presets(service.catalog.record_for_name('喷火龙'))[0]['member']
    member['item']='charizardite-x'
    member['ability']='blaze'
    team=store.save({'name':'Mega选择','registration':'partial','members':[member]})
    team=next(t for t in store.list() if t['name']=='Mega选择')
    d=DamageDialog(service.catalog,store.list,lambda:None,team_id=team['id']);qtbot.addWidget(d)
    select(d.own_form,service.rules.identity(service.catalog.record_for_name('超级喷火龙Y')))
    assert '⚠' in d.form_warning.text()
    with pytest.raises(ValueError):d.own_combat_member(member)
    d.assume_stone.setChecked(True)
    assert d.own_combat_member(member)['item']=='charizardite-y'
    assert next(t for t in store.list() if t['id']==team['id'])['members'][0]['item']=='charizardite-x'

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
    assert any(row['move']['category']=='status' for row in d.rows if row['direction']=='对手 → 我方' and row['move'])


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
    assert d.own_battle.hp.value()==100
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
    assert '性格尚未确认' in d.table.item(0,1).text()
    assert '性格尚未确认' in d.status.text()


def test_alolan_persian_manual_correction_calculates(qtbot,service,store):
    d=DamageDialog(service.catalog,store.list,lambda:None);qtbot.addWidget(d)
    select(d.saved_team,store.list()[0]['id'])
    d.set_target(service.catalog.record_for_name('猫老大（阿罗拉）'))
    d.calculate();qtbot.waitUntil(lambda:d.worker is None,timeout=15000)
    assert any(r['status']=='ok' for r in d.rows)
    assert all('该形态尚未映射' not in r.get('reason','') for r in d.rows)


def test_enemy_scene_ability_shows_condition_and_checkbox(qtbot,service,store):
    d=DamageDialog(service.catalog,store.list,lambda:None);qtbot.addWidget(d)
    d.show()
    select(d.saved_team,store.list()[0]['id'])
    d.set_target(service.catalog.record_for_name('妙蛙花'))
    select(d.enemy_ability_choice,'chlorophyll')
    assert d.enemy_ability.isVisible()
    assert d.enemy_ability.isEnabled()
    assert '叶绿素' in d.enemy_ability.text() and '大晴天' in d.enemy_ability.text()
    d.enemy_ability.setChecked(True)
    assert all(page.battle.flags['ability_on'].isChecked() for page in d.pages)
    assert '极速 290' in d.speed_summary.text()


def test_sand_veil_displays_effective_accuracy_for_damage_and_status_moves(qtbot,service,store):
    venusaur=service.presets(service.catalog.record_for_name('妙蛙花'))[0]['member']
    venusaur.update(ability='overgrow',item='none',moves=['sludge-bomb','sleep-powder','protect','leaf-storm'])
    team=store.save({'name':'命中率测试队','registration':'partial','members':[venusaur]})
    d=DamageDialog(service.catalog,store.list,lambda:None);qtbot.addWidget(d);d.show()
    select(d.saved_team,team['id'])
    d.set_target(service.catalog.record_for_name('烈咬陆鲨'))
    select(d.enemy_ability_choice,'sand-veil')
    assert '沙暴' in d.enemy_ability.text() and '命中率×0.8' in d.enemy_ability.text()
    d.enemy_ability.setChecked(True)
    assert d.weather.currentData()=='Sand'
    select(d.weather,'Sun');assert not d.enemy_ability.isChecked()
    select(d.weather,'Sand');assert d.enemy_ability.isChecked()
    d.calculate();qtbot.waitUntil(lambda:d.worker is None,timeout=15000)
    assert '命中 80% · 沙隐 ×0.8' in d.table.item(0,1).text()

    # A status move still has no damage range, but its adjusted hit chance remains useful.
    row=next(i for i in range(d.table.rowCount()) if '催眠粉' in d.table.item(i,0).text())
    assert '变化招式' in d.table.item(row,1).text()
    assert '命中 60% · 沙隐 ×0.8' in d.table.item(row,1).text()


def test_grassy_glide_priority_is_visible_and_scene_is_bidirectional(qtbot,service,store):
    own=service.presets(service.catalog.record_for_name('轰擂金刚猩'))[0]['member']
    own.update(ability='grassy-surge',item='none',moves=['grassy-glide','protect',None,None])
    team=store.save({'name':'先制度测试队','registration':'partial','members':[own]})
    d=DamageDialog(service.catalog,store.list,lambda:None);qtbot.addWidget(d);d.show()
    select(d.saved_team,team['id']);d.set_target(service.catalog.record_for_name('巨金怪'))
    select(d.terrain,'Grassy')
    d.calculate();qtbot.waitUntil(lambda:d.worker is None,timeout=15000)
    assert '先制 +0' in d.table.item(0,0).text()
    assert '先制 +1' in d.table.item(0,1).text() and '青草场地' in d.table.item(0,1).text()


def test_whimsicott_defaults_to_prankster_and_lists_common_status_moves(qtbot,service,store):
    d=DamageDialog(service.catalog,store.list,lambda:None);qtbot.addWidget(d);d.show()
    select(d.saved_team,store.list()[0]['id'])
    d.set_target(service.catalog.record_for_name('风妖精'))
    assert d.enemy_ability_choice.currentData()=='prankster'
    assert '恶作剧之心' in d.enemy_ability_choice.currentText()
    assert {'叶绿素','穿透','恶作剧之心'} <= {button.text() for button in d.enemy_ability_buttons.values()}
    assert d.enemy_ability_buttons['prankster'].isChecked()
    assert d.enemy_ability_buttons_widget.isVisible()
    d.calculate();qtbot.waitUntil(lambda:d.worker is None,timeout=15000)
    titles=[d.incoming_table.item(row,0).text() for row in range(d.incoming_table.rowCount())]
    assert any('顺风' in title for title in titles)
    assert any('再来一次' in title for title in titles)
    for name in ('顺风','再来一次'):
        row=next(i for i,title in enumerate(titles) if name in title)
        assert '先制 +1' in d.incoming_table.item(row,1).text()


def test_full_hp_condition_is_prominent_and_tracks_gale_wings(qtbot,service,store):
    own=service.presets(service.catalog.record_for_name('烈箭鹰'))[0]['member']
    own.update(ability='gale-wings',item='none',moves=['brave-bird','protect',None,None])
    team=store.save({'name':'疾风之翼测试队','registration':'partial','members':[own]})
    d=DamageDialog(service.catalog,store.list,lambda:None);qtbot.addWidget(d);d.show()
    select(d.saved_team,team['id']);d.set_target(service.catalog.record_for_name('巨金怪'))
    assert d.own_battle.hp.parentWidget() is d.quick_panel
    assert d.own_battle.flags['ability_on'].isChecked()
    d.own_battle.hp.setValue(99)
    assert not d.own_battle.flags['ability_on'].isChecked()
    d.calculate();qtbot.waitUntil(lambda:d.worker is None,timeout=15000)
    assert '先制 +0' in d.table.item(0,1).text()
    d.own_battle.hp.setValue(100)
    assert d.own_battle.flags['ability_on'].isChecked()


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


def test_enemy_ability_choice_and_fixed_mega_ability(qtbot,service,store):
    d=DamageDialog(service.catalog,store.list,lambda:None);qtbot.addWidget(d)
    select(d.saved_team,store.list()[0]['id'])
    d.set_target(service.catalog.record_for_name('猫老大（阿罗拉）'))
    assert d.enemy_ability_choice.isEnabled()
    assert d.enemy_ability_choice.findData('fur-coat')>=0
    select(d.enemy_ability_choice,'fur-coat')
    assert all(scene['member']['ability']=='fur-coat' for scene in d.snapshot()['scenarios'])
    assert '物理招式' in d.enemy_ability_note.text()
    assert d.enemy_ability.isHidden()  # 毛皮大衣始终生效，不需要第二个开关。

    d.set_target(service.catalog.record_for_name('大狃拉'))
    select(d.enemy_ability_choice,'unburden')
    assert not d.enemy_ability.isHidden() and '轻装已触发' in d.enemy_ability.text()
    assert all(not p.battle.flags['ability_on'].isHidden() for p in d.pages)

    d.set_target(service.catalog.record_for_name('超级路卡利欧Z'))
    assert not d.enemy_ability_choice.isEnabled()
    assert d.enemy_ability_choice.currentData()=='aura-guard'
    assert d.enemy_ability_choice.currentText()=='固定特性 · 波导防护'
    assert all(scene['member']['ability']=='aura-guard' for scene in d.snapshot()['scenarios'])
    assert '接触类物理招式' in d.enemy_ability_note.text()
    assert d.enemy_ability.isHidden()  # 波导防护固定生效。

    d.set_target(service.catalog.record_for_name('喷火龙'))
    assert not d.enemy_ability.isHidden()
    assert not d.enemy_ability.isEnabled()
    assert '选择猛火' in d.enemy_ability.text()
    select(d.enemy_ability_choice,'blaze')
    assert d.enemy_ability.isEnabled() and '猛火已触发' in d.enemy_ability.text()


def test_saved_blaze_build_shows_real_trigger_control(qtbot,service,store):
    member=service.presets(service.catalog.record_for_name('喷火龙'))[0]['member']
    member.update(ability='blaze',item='charizardite-y',
                  moves=['heat-wave','weather-ball','ancient-power','protect'])
    team=store.save({'name':'猛火队','registration':'partial','members':[member]})
    d=DamageDialog(service.catalog,store.list,lambda:None,team_id=team['id']);qtbot.addWidget(d)
    select(d.saved_team,team['id'])
    d.set_target(service.catalog.record_for_name('暴飞龙'))
    assert not d.own_battle.flags['ability_on'].isHidden()
    assert '猛火已触发' in d.own_battle.flags['ability_on'].text()
    d.own_battle.flags['ability_on'].setChecked(True)
    assert d.snapshot()['own_battle']['ability_on'] is True


@pytest.mark.parametrize(('saved_item','form_name','expected_item'), [
    ('charizardite-y','超级喷火龙X','charizardite-x'),
    ('charizardite-x','超级喷火龙Y','charizardite-y'),
])
def test_mega_form_uses_temporary_matching_stone(qtbot,service,store,saved_item,form_name,expected_item):
    member=service.presets(service.catalog.record_for_name('喷火龙'))[0]['member']
    member['item']=saved_item
    member['ability']='blaze'
    team=store.save({'name':'Mega选择','registration':'partial','members':[member]})
    team=next(t for t in store.list() if t['name']=='Mega选择')
    d=DamageDialog(service.catalog,store.list,lambda:None,team_id=team['id']);qtbot.addWidget(d)
    select(d.own_form,service.rules.identity(service.catalog.record_for_name(form_name)))
    assert '自动采用' in d.form_warning.text()
    assert d.own_combat_member(member)['item']==expected_item
    assert next(t for t in store.list() if t['id']==team['id'])['members'][0]['item']==saved_item

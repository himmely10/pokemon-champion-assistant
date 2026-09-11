"""Persistence, roster gate and Qt lifecycle regressions for team-scoped builds."""
from copy import deepcopy
import os
import sqlite3

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest

from champion_assistant.data.references import ReferenceCatalog
from champion_assistant.teams import TeamRules, TeamStore, blank_member, match_team


@pytest.fixture(scope='module')
def rules():
    return TeamRules(ReferenceCatalog('pokemon'))


@pytest.fixture
def full(rules):
    names = ['苍炎刃鬼', '风妖精', '巨金怪', '来悲粗茶', '烈咬陆鲨', '姆克鹰']
    members = [blank_member(rules.identity(rules.catalog.record_for_name(n))) for n in names]
    members[4].update(nature='jolly', ability='rough-skin', item='choice-scarf',
                      moves=['earthquake', 'protect', 'dragon-claw', 'rock-slide'])
    members[4]['points'].update(attack=32, speed=32, hp=2)
    return {'id': 'team-test', 'revision': 1, 'name': '顺风队', 'registration': 'full', 'members': members}


def observed(team):
    return [{'identity': m['identity'], 'item': None} for m in team['members']] + [
        {'identity': None, 'item': None} for _ in range(6 - len(team['members']))]


def test_full_gate_never_borrows_four_of_six(rules, full):
    obs = observed(full)
    obs[4]['identity'] = obs[5]['identity'] = None
    result = match_team(full, obs, rules)
    assert not result['matched'] and result['builds'] == {}
    assert '4/6' in result['reason']
    # Four configured builds do not change a six-member identity roster's mode.
    for member in full['members'][:4]:
        member['nature'] = 'jolly'
    assert not match_team(full, obs, rules)['builds']


def test_explicit_partial_requires_every_registered_member(rules, full):
    full.update(registration='partial', members=full['members'][:4])
    obs = observed(full)
    result = match_team(full, obs, rules)
    assert result['matched'] and set(result['builds']) == {0, 1, 2, 3}
    obs[3]['identity'] = None
    assert match_team(full, obs, rules)['builds'] == {}


def test_reorder_and_cross_team_isolation(rules, full, tmp_path):
    store = TeamStore(tmp_path / 'teams.db', rules)
    full.pop('id'); full.pop('revision')
    a = store.save(full)
    full['name'] = '另一队'
    full['members'][4]['points']['speed'] = 0
    b = store.save(full)
    reopened = TeamStore(store.path, rules).list()
    assert len(reopened) == 2 and a['id'] != b['id']
    obs = list(reversed(observed(a)))
    assert match_team(a, obs, rules)['builds'][1]['points']['speed'] == 32
    assert match_team(b, obs, rules)['builds'][1]['points']['speed'] == 0
    assert match_team(a, obs, rules)['builds'][0]['points']['hp'] is None
    result = match_team(a, obs, rules)
    result['builds'][1]['points']['speed'] = 1
    assert a['members'][4]['points']['speed'] == 32


@pytest.mark.parametrize('case', ['duplicate', 'ambiguous', 'item', 'none', 'missing', 'form'])
def test_gate_rejects_conflicts(rules, full, case):
    obs = observed(full)
    if case == 'duplicate': obs[5]['identity'] = obs[4]['identity']
    if case == 'ambiguous': obs[0]['ambiguous'] = True
    if case == 'item': obs[4]['item'] = 'life-orb'
    if case == 'none': obs[4]['item'] = 'none'
    if case == 'missing': obs.pop()
    if case == 'form': obs[4]['identity'] = rules.identity(rules.catalog.record_for_name('超级烈咬陆鲨'))
    assert not match_team(full, obs, rules)['builds']


def test_unknown_item_does_not_conflict_and_cosmetics_merge(rules, full):
    assert match_team(full, observed(full), rules)['matched']
    for cosmetic in ('来悲粗茶', '彩粉蝶'):
        records = [r for r in rules.catalog.records if rules.catalog.display_name(r) == cosmetic]
        assert len({rules.identity(r) for r in records}) == 1


@pytest.mark.parametrize('case', ['point_cap', 'budget', 'bool', 'duplicate_move', 'foreign_move', 'ability', 'nature', 'item', 'full_count', 'partial_count'])
def test_invalid_build_rejected_without_write(rules, full, tmp_path, case):
    store = TeamStore(tmp_path / 'teams.db', rules)
    m = full['members'][4]
    if case == 'point_cap': m['points']['speed'] = 33
    if case == 'budget': m['points']['defense'] = 1
    if case == 'bool': m['points']['speed'] = True
    if case == 'duplicate_move': m['moves'][1] = 'earthquake'
    if case == 'foreign_move': m['moves'][1] = 'spore'
    if case == 'ability': m['ability'] = 'prankster'
    if case == 'nature': m['nature'] = 'invalid'
    if case == 'item': m['item'] = 'invalid'
    if case == 'full_count': full['members'].pop()
    if case == 'partial_count': full['registration'] = 'partial'
    with pytest.raises(ValueError): store.save(full)
    assert store.list() == []


def test_revision_conflict_delete_and_future_schema_preserved(rules, full, tmp_path):
    path = tmp_path / 'teams.db'
    store = TeamStore(path, rules)
    full.pop('id'); full.pop('revision')
    a = store.save(full)
    b = store.save(a)
    with pytest.raises(ValueError): store.save(a)
    assert store.list() == [b]
    with pytest.raises(ValueError): store.delete(a)
    store.delete(b)
    assert store.list() == []
    with sqlite3.connect(path) as db: db.execute('PRAGMA user_version=99')
    before = path.read_bytes()
    with pytest.raises(ValueError): TeamStore(path, rules)
    assert path.read_bytes() == before


def test_editor_save_reopen_and_revoke(qtbot, rules, full, tmp_path):
    from champion_assistant.ui.team_dialog import TeamDialog, select
    dialog = TeamDialog(rules.catalog, tmp_path / 'teams.db')
    qtbot.addWidget(dialog)
    dialog.name.setText(full['name'])
    for editor, member in zip(dialog.editors, full['members']): editor.load(member)
    dialog.save_team()
    assert dialog.active and dialog.active['revision'] == 1
    # Choosing a saved team never populates the independent observations.
    assert not dialog.result['builds']
    for (pokemon, item), member in zip(dialog.observed, reversed(full['members'])):
        select(pokemon, member['identity'])
    assert dialog.result['matched'] and len(dialog.result['builds']) == 6
    assert '讲究围巾' in dialog.build_view.toPlainText()
    dialog.editors[4].points['speed'].setValue(0)
    assert not dialog.result['builds'] and not dialog.build_view.toPlainText()
    dialog.save_team()
    assert dialog.result['builds'][1]['points']['speed'] == 0
    dialog.reset_observed()
    assert not dialog.result['builds']
    dialog.load_team(dialog.store.list()[0])
    assert dialog.editors[4].points['speed'].value() == 0
    assert dialog.editors[0].points['hp'].value() == -1
    # A free-text search must revoke the old identity immediately.
    for (pokemon, _), member in zip(dialog.observed, full['members']): select(pokemon, member['identity'])
    assert dialog.result['matched']
    dialog.observed[0][0].setEditText('并未选择的文字')
    assert not dialog.result['builds']
    dialog.close()


def test_editor_identity_change_resets_build(qtbot, rules, full, tmp_path):
    from champion_assistant.ui.team_dialog import TeamDialog, select
    d = TeamDialog(rules.catalog, tmp_path / 'teams.db')
    qtbot.addWidget(d)
    d.editors[0].load(full['members'][4])
    select(d.editors[0].pokemon, full['members'][0]['identity'])
    member = d.editors[0].read()
    assert member['nature'] is None and member['item'] is None and member['moves'] == [None] * 4
    assert all(v is None for v in member['points'].values())
    d.dirty = False
    d.close()


def test_new_capture_revokes_current_roster(qtbot, rules, full, tmp_path):
    from threading import Event
    from PySide6.QtCore import QObject, Signal, Slot
    from champion_assistant.ui.main_window import MainWindow
    from champion_assistant.ui.team_dialog import TeamDialog, select
    class Worker(QObject):
        finished = Signal(int, str, object, str)
        def __init__(self, *args):
            super().__init__()
            self.cancelled = Event()
        @Slot(int, str, object)
        def run(self, revision, operation, payload):
            self.finished.emit(revision, operation, None, '测试结束')
    window = MainWindow(settings_path=tmp_path / 'ui.json', worker_factory=Worker)
    qtbot.addWidget(window)
    d = TeamDialog(rules.catalog, tmp_path / 'teams.db', window)
    window.team_dialog = d
    full.pop('id'); full.pop('revision')
    saved = d.store.save(full)
    d.load_team(saved)
    for (pokemon, _), member in zip(d.observed, saved['members']): select(pokemon, member['identity'])
    assert d.result['matched']
    window.open_image('new.png')
    assert not d.result['builds'] and all(p.currentData() is None for p, _ in d.observed)
    assert d.store.list()[0] == saved
    qtbot.waitUntil(lambda: not window.busy)
    window.close()

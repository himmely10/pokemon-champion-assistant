"""Real video screenshots, parsing failure gates, and draft-only Qt import lifecycle."""
from copy import deepcopy
import os
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
from PIL import Image

from champion_assistant.data.references import ReferenceCatalog
from champion_assistant.teams import TeamRules
from champion_assistant.team_import import ScreenshotImporter, cards, normalize, trim_name_whitespace

FIXTURES = Path(__file__).parent/'fixtures/team_import'


@pytest.fixture(scope='module')
def importer():
    pytest.importorskip('rapidocr')
    return ScreenshotImporter(TeamRules(ReferenceCatalog('pokemon')))


@pytest.fixture(scope='module')
def pages(importer):
    return [importer.read_page(FIXTURES/(mode+'.png'), mode) for mode in ('ability', 'status')]


def test_real_screenshots_all_fields(importer, pages):
    result = importer.combine(*pages)
    # Independently transcribed from the supplied screenshots, in slot order 1..6.
    expected = [
        ('gardevoir', [0,0,2,32,0,32], 'modest', 'trace', 'gardevoirite', ['hyper-voice','expanding-force','trick-room','protect']),
        ('indeedee-female', [32,0,32,0,2,0], 'relaxed', 'psychic-surge', 'rocky-helmet', ['trick-room','follow-me','helping-hand','psychic']),
        ('torkoal', [32,0,0,32,2,0], 'quiet', 'drought', 'charcoal', ['eruption','weather-ball','earth-power','protect']),
        ('sneasler', [2,32,0,0,0,32], 'jolly', 'poison-touch', 'focus-sash', ['fake-out','poison-jab','close-combat','feint']),
        ('incineroar', [29,32,3,0,2,0], 'brave', 'intimidate', 'life-orb', ['darkest-lariat','fake-out','close-combat','flare-blitz']),
        ('basculegion-male', [0,32,1,0,1,32], 'jolly', 'adaptability', 'choice-scarf', ['wave-crash','last-respects','aqua-jet','flip-turn'])]
    for member, (key, points, nature, ability, item, moves) in zip(result['draft']['members'], expected):
        assert importer.rules.record(member['identity'])['opgg_key'] == key
        assert list(member['points'].values()) == points
        assert [member['nature'], member['ability'], member['item'], member['moves']] == [nature, ability, item, moves]
    actual_stats = [[e['value'] for e in m['evidence']['panel_stats'].values()] for m in pages[1]['members']]
    assert actual_stats == [[143,76,87,194,135,132], [177,75,128,115,127,94], [177,105,160,150,92,36],
                            [157,182,80,54,100,189], [199,183,113,100,112,72], [195,164,86,90,96,143]]
    assert result['draft']['import_source']['review_required']
    assert any('0/O' in w for w in result['warnings'])
    assert 'id' not in result['draft'] and 'revision' not in result['draft']


@pytest.mark.parametrize('case', ['different_code', 'missing_code', 'different_identity', 'unknown_identity', 'wrong_page'])
def test_never_combine_different_or_unconfirmed_teams(importer, pages, case):
    a, s = deepcopy(pages)
    if case == 'different_code': s['team_code'] = 'AAAAAAAAAA'
    if case == 'missing_code': s['team_code'] = None
    if case == 'different_identity': s['members'][0]['member']['identity'] = s['members'][1]['member']['identity']
    if case == 'unknown_identity': a['members'][0]['member']['identity'] = None
    if case == 'wrong_page': s['mode'] = 'ability'
    with pytest.raises(ValueError): importer.combine(a, s)


def test_reject_blank_wrong_page_and_missing_card(importer):
    with pytest.raises(ValueError): cards(Image.new('RGB', (1920,1080), 'white'))
    with Image.open(FIXTURES/'ability.png') as image:
        with pytest.raises(ValueError): cards(image.crop((0,0,image.width,image.height//2)))
    with pytest.raises(ValueError, match='类型'): importer.read_page(FIXTURES/'status.png', 'ability')


def test_dictionary_does_not_silently_accept_fuzzy_names(importer):
    evidence = {'text': '大狂拉', 'score': .99}
    assert importer.resolve(evidence, [('大狃拉', 'sneasler')]) is None
    assert evidence['suggestions'] == ['大狃拉']
    assert normalize('ＤＤ金勾臂') == normalize('DD金勾臂')
    assert importer.identity({'text':'爱管侍', 'score':.99}, None) is None


def test_smaller_user_screenshots_recover_sneasler(importer):
    pair = [importer.read_page(FIXTURES/'smaller'/(mode+'.png'), mode) for mode in ('ability', 'status')]
    result = importer.combine(*pair)
    member = result['draft']['members'][3]
    assert importer.rules.record(member['identity'])['opgg_key'] == 'sneasler'
    assert member['nature'] == 'jolly' and member['ability'] == 'poison-touch'
    assert member['item'] == 'focus-sash'
    assert member['moves'] == ['fake-out','poison-jab','close-combat','feint']
    assert list(member['points'].values()) == [2,32,0,0,0,32]
    for page in pair:
        evidence = page['members'][3]['evidence']['name']
        assert evidence['recovery'] == 'tight_consensus'
        assert all(r['text'] == '大狃拉' for r in evidence['tight_reads'])


@pytest.mark.parametrize('readings', [
    [('大狃拉', .99), ('大狂拉', .99)],
    [('大狃拉', .99), ('大狃拉', .5)],
    [('大狂拉', .99), ('大狂拉', .99)]])
def test_tight_recovery_requires_agreement_and_exact_identity(importer, readings):
    evidence = {'text':'大狂拉', 'score':.99,
                'tight_reads':[{'text':text, 'score':score} for text, score in readings]}
    assert importer.resolve(evidence, [('大狃拉', 'sneasler')]) is None
    assert trim_name_whitespace(Image.new('RGB', (250,50), '#555599')) is None


def test_ui_review_and_draft_roundtrip(qtbot, importer, pages, tmp_path):
    from champion_assistant.ui.team_import_dialog import TeamImportDialog
    from champion_assistant.ui.team_dialog import TeamDialog
    d = TeamImportDialog(importer.rules)
    qtbot.addWidget(d)
    d.show_pages(pages)
    assert not d.use_button.isEnabled()
    d.use_draft()
    assert d.result_draft is None
    for code in d.codes: code.setText('FJR0CNH887')
    d.review.setChecked(True)
    d.use_draft()
    draft = d.result_draft['draft']
    assert draft['import_source']['team_code'] == 'FJR0CNH887'
    assert draft['import_source']['ability']['code_evidence']['text']  # Raw OCR evidence retained.
    editor = TeamDialog(importer.rules.catalog, tmp_path/'teams.db')
    qtbot.addWidget(editor)
    editor.load_team(draft, as_draft=True)
    assert editor.store.list() == [] and not editor.result['builds']
    assert all(p.currentData() is None for p, i in editor.observed)
    editor.save_team()
    assert editor.active['members'] == draft['members']
    assert editor.store.list()[0]['import_source'] == draft['import_source']
    editor.close()


def test_ui_new_file_and_identity_changes_revoke_review(qtbot, importer, pages):
    from champion_assistant.ui.team_import_dialog import TeamImportDialog
    d = TeamImportDialog(importer.rules)
    qtbot.addWidget(d)
    d.show_pages(pages)
    d.review.setChecked(True)
    d.table.cellWidget(0,0).setCurrentIndex(0)
    assert not d.review.isChecked()
    d.review.setChecked(True)
    d.use_draft()
    assert d.result_draft is None
    d.set_path('ability', FIXTURES/'ability.png')
    assert d.pages is None and not d.use_button.isEnabled()
    d.close()

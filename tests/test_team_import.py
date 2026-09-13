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
NEW_SCREENSHOTS = Path(__file__).resolve().parents[1] / '图片'


@pytest.fixture(scope='module')
def importer():
    pytest.importorskip('rapidocr')
    return ScreenshotImporter(TeamRules(ReferenceCatalog('pokemon')))


def test_ocr_models_shared_but_rules_and_results_are_not(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import champion_assistant.team_import as module
    calls = []
    def factory():
        calls.append(1)
        return object()
    monkeypatch.setattr(module, '_ocr_cached', None)
    monkeypatch.setattr(module, 'LocalOCR', factory)
    rules = [object() for _ in range(8)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        instances = list(pool.map(ScreenshotImporter, rules))
    assert calls == [1]
    assert all(x.ocr is instances[0].ocr for x in instances)
    assert [x.rules for x in instances] == rules


def test_ocr_initialization_failure_can_retry_and_bundle_change_reloads(monkeypatch, tmp_path):
    import champion_assistant.team_import as module
    from champion_assistant.paths import AppPaths
    monkeypatch.setattr(module, '_ocr_cached', None)
    calls = []
    def factory():
        calls.append(1)
        if len(calls) == 1:
            raise ValueError('missing model')
        return object()
    monkeypatch.setattr(module, 'LocalOCR', factory)
    with pytest.raises(ValueError, match='missing model'):
        module.shared_local_ocr()
    first = module.shared_local_ocr()
    assert module.shared_local_ocr() is first
    monkeypatch.setattr(module, 'app_paths', lambda: AppPaths(tmp_path, tmp_path, tmp_path, True))
    assert module.shared_local_ocr() is not first
    assert len(calls) == 3


def test_shared_ocr_serializes_inference_and_result_copy():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Lock
    from types import SimpleNamespace
    import time
    from champion_assistant.team_import import LocalOCR
    active = 0
    def engine(image, **kwargs):
        nonlocal active
        active += 1
        assert active == 1
        time.sleep(.005)
        active -= 1
        return SimpleNamespace(txts=[image], scores=[.99])
    ocr = object.__new__(LocalOCR)
    ocr._lock, ocr.engine = Lock(), engine
    with ThreadPoolExecutor(max_workers=4) as pool:
        outputs = list(pool.map(ocr.read, ['one', 'two', 'three', 'four']))
    assert outputs == [(text, .99) for text in ['one', 'two', 'three', 'four']]


@pytest.mark.parametrize('cancel_before_start', [True, False])
def test_ocr_worker_cancellation_never_returns_pages(qtbot, monkeypatch, cancel_before_start):
    import champion_assistant.ui.team_import_dialog as module
    cancelled = cancel_before_start
    calls = []
    class Importer:
        def __init__(self, rules):
            calls.append('init')
        def read_page(self, path, mode, progress):
            nonlocal cancelled
            if mode == 'status':
                cancelled = True
            return {'mode': mode}
    monkeypatch.setattr(module, 'ScreenshotImporter', Importer)
    worker = module.ImportWorker(object(), {'ability': 'a', 'status': 's'})
    monkeypatch.setattr(worker, 'isInterruptionRequested', lambda: cancelled)
    worker.run()
    assert worker.pages is None
    assert '取消' in worker.error
    assert calls == ([] if cancel_before_start else ['init'])


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


def test_new_replica_screenshots_all_fields(importer):
    # Independently transcribed from the user's two 3840x2160 replica-confirmation pages.
    pair = [importer.read_page(NEW_SCREENSHOTS / name, mode)
            for name, mode in [('能力2.png', 'ability'), ('状态2.png', 'status')]]
    assert [page['team_code'] for page in pair] == ['XVBSFRTM8W'] * 2
    result = importer.combine(*pair)
    expected = [
        ('golisopod', [32,5,0,0,29,0], 'adamant', 'emergency-exit', 'golisopite', ['sucker-punch','iron-head','leech-life','swords-dance']),
        ('grimmsnarl', [31,0,20,0,15,0], 'careful', 'prankster', 'light-clay', ['spirit-break','light-screen','parting-shot','reflect']),
        ('venusaur', [1,0,0,32,1,32], 'modest', 'chlorophyll', 'focus-sash', ['protect','sleep-powder','sludge-bomb','leaf-storm']),
        ('archaludon', [32,0,0,0,25,9], 'calm', 'stamina', 'leftovers', ['flash-cannon','dragon-pulse','electro-shot','protect']),
        ('pelipper', [32,0,10,1,21,2], 'bold', 'drizzle', 'sitrus-berry', ['weather-ball','hurricane','tailwind','wide-guard']),
        ('charizard', [12,0,14,8,0,32], 'timid', 'blaze', 'charizardite-y', ['heat-wave','weather-ball','ancient-power','protect'])]
    for member, (key, points, nature, ability, item, moves) in zip(result['draft']['members'], expected):
        assert importer.rules.record(member['identity'])['opgg_key'] == key
        assert list(member['points'].values()) == points
        assert [member['nature'], member['ability'], member['item'], member['moves']] == [nature, ability, item, moves]
    stats = [[e['value'] for e in m['evidence']['panel_stats'].values()] for m in pair[1]['members']]
    assert stats == [[182,165,160,72,139,60], [201,140,105,103,121,80], [156,91,103,167,121,132],
                     [197,112,150,145,121,114], [167,63,143,116,111,87], [165,93,112,137,105,167]]


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


def test_obs_capture_uses_ancestor_settings_and_previews_before_ocr(qtbot, monkeypatch):
    import champion_assistant.ui.team_import_dialog as module
    from PySide6.QtWidgets import QWidget, QPushButton
    parent = QWidget()
    parent.obs_settings = {'host': '127.0.0.1', 'port': 4455, 'password': 'secret', 'source': 'Switch'}
    middle = QWidget(parent)
    dialog = module.TeamImportDialog(object(), middle)
    qtbot.addWidget(parent)
    qtbot.addWidget(dialog)
    calls = []
    class Capture:
        def screenshot(self, settings):
            calls.append(dict(settings))
            return Image.new('RGB', (100, 60), 'purple')
    monkeypatch.setattr(module, 'ObsCapture', Capture)
    for mode in ('ability', 'status'):
        dialog.findChild(QPushButton, 'obs_' + mode).click()
        qtbot.waitUntil(lambda: dialog.obs_worker is None)
        assert Path(dialog.paths[mode]).is_file()
        assert not dialog.preview_labels[mode].pixmap().isNull()
    assert calls == [parent.obs_settings] * 2
    assert dialog.pages is None and dialog.worker is None
    assert not dialog.use_button.isEnabled()
    assert '核对' in dialog.status.text()
    dialog.close()


def test_obs_without_source_opens_selector_and_reads_sources_off_thread(qtbot, monkeypatch):
    import champion_assistant.ui.team_import_dialog as module
    monkeypatch.setattr(module, 'local_obs_settings', lambda **kwargs: {'host':'127.0.0.1', 'port':4456, 'password':'private'})
    class Capture:
        def sources(self, settings):
            assert settings['port'] == 4456
            return {'sources':[{'name':'Switch', 'kind':'源'}], 'version':'test'}
        def screenshot(self, settings):
            return Image.new('RGB', (100,60))
    monkeypatch.setattr(module, 'ObsCapture', Capture)
    dialog = module.TeamImportDialog(object())
    qtbot.addWidget(dialog)
    dialog.capture_obs('status')
    assert dialog.obs_dialog is not None
    dialog.obs_dialog.request_sources()
    qtbot.waitUntil(lambda: dialog.obs_worker is None)
    assert dialog.obs_dialog.sources.currentData() == 'Switch'
    dialog.obs_dialog.accept()
    qtbot.waitUntil(lambda: dialog.obs_worker is None)
    assert 'status' in dialog.paths and dialog.pages is None
    dialog.close()


def test_obs_worker_never_exposes_password_in_errors(qtbot, monkeypatch):
    import champion_assistant.ui.team_import_dialog as module
    class Capture:
        def screenshot(self, settings):
            raise RuntimeError('password=very-secret')
    monkeypatch.setattr(module, 'ObsCapture', Capture)
    worker = module.ObsImportWorker({'password':'very-secret'}, 'screenshot')
    worker.run()
    assert worker.error and 'very-secret' not in worker.error
    assert worker.settings == {}


def test_obs_close_waits_for_worker_and_discards_capture(qtbot, monkeypatch):
    import champion_assistant.ui.team_import_dialog as module
    from threading import Event
    release = Event()
    class Capture:
        def screenshot(self, settings):
            release.wait(2)
            return Image.new('RGB', (100,60))
    monkeypatch.setattr(module, 'ObsCapture', Capture)
    dialog = module.TeamImportDialog(object(), obs_settings={'source':'Switch'})
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.capture_obs('ability')
    dialog.close()
    assert dialog.closing and dialog.obs_worker is not None
    release.set()
    qtbot.waitUntil(lambda: dialog.obs_worker is None)
    assert not dialog.isVisible() and dialog.paths == {}

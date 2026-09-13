"""Cache invalidation and isolation, independent of the large real-image corpus."""
import json
from hashlib import sha256

import numpy as np
from PIL import Image
import pytest

import champion_assistant.recognition as recognition


@pytest.fixture
def dataset(tmp_path, monkeypatch):
    monkeypatch.setattr(recognition, '_template_cache', None)
    root = tmp_path / 'data'
    root.mkdir()
    (root/'icons').mkdir()
    pixels = np.random.default_rng(88).integers(0, 256, (32, 32, 4), dtype=np.uint8)
    pixels[:, :, 3] = 255
    Image.fromarray(pixels).save(root / 'icons/sprite.png')
    index = {'pokemon': [{'source_slug': 'test', 'name': '测试', 'species_name': '测试',
                         'dex_number': 1, 'directory': 'icons', 'images': {'normal': {
                         'file': 'sprite.png', 'sha256': sha256((root/'icons/sprite.png').read_bytes()).hexdigest()}}}]}
    (root/'index.json').write_text(json.dumps(index), encoding='utf-8')
    (root/'recognition_identity_groups.json').write_text('{"groups": []}', encoding='utf-8')
    layout = tmp_path/'layout.json'
    layout.write_text(json.dumps({'name': 'test', 'reference_size': [1600, 900],
        'slots': [[1320, 100+i*105, 1450, 195+i*105] for i in range(6)],
        'template_sizes': [32], 'min_score': .78, 'min_margin': .1}), encoding='utf-8')
    return root, layout, pixels


def test_bank_reused_but_each_image_and_result_are_independent(dataset):
    root, layout, pixels = dataset
    cold = recognition.OpponentRecognizer(root, layout)
    warm = recognition.OpponentRecognizer(root, layout)
    assert not cold.cache_hit and warm.cache_hit
    assert cold.templates is warm.templates
    assert cold.cache_key == warm.cache_key
    crop = Image.new('RGB', (130, 95), '#900030')
    crop.paste(Image.fromarray(pixels).convert('RGB'), (17, 9))
    result = cold.match_slot(crop)
    assert result == warm.match_slot(crop)
    assert result['name'] == '测试'
    result['form_candidates'].append('poison')
    result['candidates'][0]['form_candidates'].append('poison')
    assert warm.match_slot(crop)['form_candidates'] == ['测试']
    assert warm.match_slot(Image.new('RGB', crop.size))['name'] is None
    for foreground, alpha in warm.templates[0].prepared:
        assert not foreground.flags.writeable and not alpha.flags.writeable


@pytest.mark.parametrize('change', ['layout', 'policy', 'index', 'template', 'algorithm'])
def test_content_or_algorithm_change_invalidates_cache(dataset, monkeypatch, change):
    root, layout, pixels = dataset
    before = recognition.OpponentRecognizer(root, layout)
    if change == 'layout':
        value = json.loads(layout.read_text())
        value['template_sizes'] = [32, 40]
        layout.write_text(json.dumps(value), encoding='utf-8')
    elif change == 'policy':
        (root/'recognition_identity_groups.json').write_text(json.dumps({
            'groups': [{'name': '合并外观', 'source_slugs': ['test']}]}), encoding='utf-8')
    elif change in ('index', 'template'):
        index = json.loads((root/'index.json').read_text())
        index['revision'] = 2
        if change == 'template':
            pixels[10, 10, 0] ^= 255
            Image.fromarray(pixels).save(root/'icons/sprite.png')
            index['pokemon'][0]['images']['normal']['sha256'] = sha256((root/'icons/sprite.png').read_bytes()).hexdigest()
        (root/'index.json').write_text(json.dumps(index), encoding='utf-8')
    else:
        monkeypatch.setattr(recognition, 'ALGORITHM_VERSION', 'test-next')
    after = recognition.OpponentRecognizer(root, layout)
    assert not after.cache_hit
    assert before.cache_key != after.cache_key
    assert before.templates is not after.templates
    # The live old recognizer retains its complete old bank until it is released.
    assert before.templates[0].metadata['name'] == '测试'


def test_corrupt_source_cannot_be_hidden_by_a_cache_hit(dataset):
    root, layout, _ = dataset
    recognition.OpponentRecognizer(root, layout)
    (root/'icons/sprite.png').write_bytes(b'broken')
    with pytest.raises(ValueError, match='图标校验失败'):
        recognition.OpponentRecognizer(root, layout)


def test_new_dataset_root_never_reuses_legacy_bank(dataset, tmp_path):
    import shutil
    root, layout, _ = dataset
    before = recognition.OpponentRecognizer(root, layout)
    newer = tmp_path/'other-version'
    shutil.copytree(root, newer)
    after = recognition.OpponentRecognizer(newer, layout)
    assert before.cache_key != after.cache_key
    assert not after.cache_hit

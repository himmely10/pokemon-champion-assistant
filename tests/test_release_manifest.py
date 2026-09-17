"""Release resource integrity checks without packaging or image inference."""
import copy
from pathlib import Path

import pytest

from scripts.build_windows import validate_build_manifest, validate_web_dist
from champion_assistant.data.storage import digest, save_json


@pytest.fixture
def release_resources(tmp_path):
    names = ('runtime/node.exe','models/PP-OCRv6_det_small.onnx','models/PP-OCRv6_rec_small.onnx',
             'models/ch_ppocr_mobile_v2.0_cls_mobile.onnx','pokemon/release.json','pokemon/baseline.zip',
             'damage_engine/bridge.cjs','web/dist/index.html','web/dist/assets/app.js',
             'web/dist/assets/app.css')
    files = {}
    for name in names:
        path = tmp_path/name
        path.parent.mkdir(parents=True,exist_ok=True)
        content = ('''<script type="module" src="/assets/app.js"></script>
<link rel="stylesheet" href="/assets/app.css">''' if name.endswith('index.html')
                   else 'fixture:' + name).encode()
        path.write_bytes(content)
        files[name] = digest(content)
    manifest = {'schema_version':1,'version':'0.2.0','python':'3.13','node':'v22.0.0','files':files}
    save_json(tmp_path/'build-manifest.json',manifest)
    return tmp_path, manifest


def test_valid_resource_manifest_is_returned(release_resources):
    root, expected = release_resources
    assert validate_build_manifest(root) == expected


@pytest.mark.parametrize('defect',['changed_bytes','missing_file','missing_model_entry',
                                    'missing_web_entry','missing_web_asset','schema','traversal'])
def test_invalid_release_never_passes(release_resources,defect):
    root, manifest = release_resources
    manifest=copy.deepcopy(manifest)
    if defect=='changed_bytes': (root/'runtime/node.exe').write_bytes(b'changed')
    elif defect=='missing_file': (root/'models/PP-OCRv6_det_small.onnx').unlink()
    elif defect=='missing_model_entry': del manifest['files']['models/PP-OCRv6_rec_small.onnx']
    elif defect=='missing_web_entry': del manifest['files']['web/dist/index.html']
    elif defect=='missing_web_asset': (root/'web/dist/assets/app.js').unlink()
    elif defect=='schema': manifest['schema_version']=99
    else: manifest['files']['../outside']=digest(b'outside')
    save_json(root/'build-manifest.json',manifest)
    with pytest.raises((ValueError,OSError)):
        validate_build_manifest(root)


def test_integrity_check_does_not_modify_resources(release_resources):
    root,_=release_resources
    before={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    validate_build_manifest(root)
    assert before=={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_web_dist_requires_index_and_referenced_assets(tmp_path):
    dist = tmp_path / 'dist'
    (dist / 'assets').mkdir(parents=True)
    (dist / 'index.html').write_text(
        '<script type="module" src="/assets/app.js"></script>'
        '<link rel="stylesheet" href="/assets/app.css">', encoding='utf-8')
    with pytest.raises(ValueError, match='静态资源'):
        validate_web_dist(dist)
    (dist / 'assets/app.js').write_text('console.log("ok")', encoding='utf-8')
    (dist / 'assets/app.css').write_text('body{}', encoding='utf-8')
    assert validate_web_dist(dist) == {'assets/app.js', 'assets/app.css', 'index.html'}


def test_windows_helpers_hide_their_owned_console_windows():
    spec = (Path(__file__).parents[1] / 'packaging/assistant.spec').read_text(encoding='utf-8')
    assert "name='ChampionWorker'" in spec
    assert "name='ChampionLabWeb'" in spec
    assert spec.count("hide_console='hide-early'") == 2


def test_installer_exposes_one_product_entry_point():
    installer = (Path(__file__).parents[1] / 'packaging/installer.iss').read_text(encoding='utf-8')
    assert 'Name: "{group}\\{#AppName}"' in installer
    assert 'Champion Lab Web' not in installer
    assert 'ChampionWorker.exe' not in installer

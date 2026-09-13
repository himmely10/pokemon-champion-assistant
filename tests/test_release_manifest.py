"""Release resource integrity checks without packaging or image inference."""
import copy

import pytest

from scripts.build_windows import validate_build_manifest
from champion_assistant.data.storage import digest, save_json


@pytest.fixture
def release_resources(tmp_path):
    names = ('runtime/node.exe','models/PP-OCRv6_det_small.onnx','models/PP-OCRv6_rec_small.onnx',
             'models/ch_ppocr_mobile_v2.0_cls_mobile.onnx','pokemon/release.json','pokemon/baseline.zip','damage_engine/bridge.cjs')
    files = {}
    for name in names:
        path = tmp_path/name
        path.parent.mkdir(parents=True,exist_ok=True)
        content = ('fixture:' + name).encode()
        path.write_bytes(content)
        files[name] = digest(content)
    manifest = {'schema_version':1,'version':'0.2.0','python':'3.13','node':'v22.0.0','files':files}
    save_json(tmp_path/'build-manifest.json',manifest)
    return tmp_path, manifest


def test_valid_resource_manifest_is_returned(release_resources):
    root, expected = release_resources
    assert validate_build_manifest(root) == expected


@pytest.mark.parametrize('defect',['changed_bytes','missing_file','missing_model_entry','schema','traversal'])
def test_invalid_release_never_passes(release_resources,defect):
    root, manifest = release_resources
    manifest=copy.deepcopy(manifest)
    if defect=='changed_bytes': (root/'runtime/node.exe').write_bytes(b'changed')
    elif defect=='missing_file': (root/'models/PP-OCRv6_det_small.onnx').unlink()
    elif defect=='missing_model_entry': del manifest['files']['models/PP-OCRv6_rec_small.onnx']
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

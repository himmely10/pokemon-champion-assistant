"""Reproducible onedir build using only public resources and explicit runtimes."""
from __future__ import annotations
import argparse
import importlib.util
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from champion_assistant.data.storage import read_json, save_json, digest, confined
from champion_assistant.version import __version__

REQUIRED_RESOURCES = {'runtime/node.exe', 'models/PP-OCRv6_det_small.onnx',
    'models/PP-OCRv6_rec_small.onnx', 'models/ch_ppocr_mobile_v2.0_cls_mobile.onnx',
    'pokemon/release.json', 'pokemon/baseline.zip', 'damage_engine/bridge.cjs',
    'web/dist/index.html'}


def validate_web_dist(dist_dir):
    """Require the production HTML and every hashed JS/CSS asset it references."""
    root = Path(dist_dir)
    index = root / 'index.html'
    if not index.is_file():
        raise ValueError('网页生产构建缺少 web/dist/index.html')
    html = index.read_text(encoding='utf-8')
    references = set(re.findall(r'''(?:src|href)=["']/((?:assets)/[^"']+)["']''', html))
    if not references or not any(path.endswith('.js') for path in references) \
            or not any(path.endswith('.css') for path in references):
        raise ValueError('网页生产构建没有引用完整的 JavaScript/CSS 静态资源')
    for relative in references:
        if not confined(root, relative).is_file():
            raise ValueError('网页生产构建缺少静态资源：' + relative)
    return {'index.html', *references}


def build_web_dist():
    """Create reproducible browser assets before freezing application resources."""
    pnpm = shutil.which('pnpm')
    if not pnpm:
        raise ValueError('构建机需要 pnpm；最终用户无需安装。')
    web = ROOT / 'web'
    if not (web / 'node_modules').is_dir():
        raise ValueError('网页依赖尚未安装，请先在 web 目录运行 pnpm install --frozen-lockfile。')
    subprocess.run([pnpm, 'build'], cwd=web, check=True)
    validate_web_dist(web / 'dist')
    return web / 'dist'


def validate_build_manifest(resources_dir):
    root = Path(resources_dir)
    manifest = read_json(root / 'build-manifest.json')
    if manifest.get('schema_version') != 1 or not isinstance(manifest.get('files'), dict):
        raise ValueError('构建清单版本无效')
    if not REQUIRED_RESOURCES.issubset(manifest['files']):
        raise ValueError('构建资源不完整')
    web_files = {'web/dist/' + path for path in validate_web_dist(root / 'web/dist')}
    if not web_files.issubset(manifest['files']):
        raise ValueError('构建清单未覆盖网页静态资源')
    for relative, checksum in manifest['files'].items():
        file = confined(root, relative)
        if not file.is_file() or digest(file.read_bytes()) != checksum:
            raise ValueError('构建资源校验失败：' + relative)
    return manifest


def prepare_resources(data_dir=None):
    web_dist = build_web_dist()
    stage = ROOT / 'artifacts/build-resources'
    if stage.exists():
        if not stage.resolve().is_relative_to((ROOT / 'artifacts').resolve()):
            raise ValueError('构建目录越界')
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    (stage / 'config').mkdir()
    for path in (ROOT / 'config').glob('*.json'):
        if path.name != 'local_ui.json':
            shutil.copy2(path, stage / 'config' / path.name)
    source = Path(data_dir or ROOT / 'pokemon')
    from champion_assistant.data.snapshot import SnapshotManager
    snapshot = SnapshotManager(source).initial()
    if not (snapshot.catalog.root / 'catalog.sqlite').is_file():
        from scripts.build_data_bundle import build_data_bundle
        from champion_assistant.data.update_service import UpdateService
        package = build_data_bundle(source, ROOT / 'artifacts/bundled-data')
        source = ROOT / 'artifacts/converted-data'
        UpdateService(source).install(package['archive_path'])
        snapshot = SnapshotManager(source).initial()
    active = snapshot.catalog.root
    destination = stage / 'pokemon/_versions' / active.name
    shutil.copytree(active, destination)
    save_json(stage / 'pokemon/current.json', {'schema_version': 1, 'bundle_id': active.name,
        'manifest_sha256': digest((active / 'manifest.json').read_bytes())})
    descriptor = snapshot.descriptor.copy()
    descriptor['catalog'] = {**descriptor['catalog'], 'path': '_versions/' + active.name}
    descriptor.pop('history', None)
    save_json(stage / 'pokemon/release.json', descriptor)
    usage = source / '_usage'
    pointer = descriptor.get('usage')
    if pointer:
        for key in ('file', 'database_file'):
            if pointer.get(key):
                target = stage / 'pokemon/_usage' / pointer[key]
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(usage / pointer[key], target)
        save_json(stage / 'pokemon/_usage/current.json', pointer)
    # Keep an importable baseline with the program: existing users can explicitly
    # adopt it after an offline program upgrade without overwriting newer data.
    from scripts.build_data_bundle import build_data_bundle
    package = build_data_bundle(stage / 'pokemon', ROOT / 'artifacts/bundled-data')
    shutil.copy2(package['archive_path'], stage / 'pokemon/baseline.zip')
    shutil.copytree(ROOT / 'damage_engine', stage / 'damage_engine',
                    ignore=shutil.ignore_patterns('node_modules', '__pycache__'))
    shutil.copytree(web_dist, stage / 'web/dist')
    licenses = stage / 'licenses'
    licenses.mkdir()
    shutil.copy2(ROOT / 'THIRD_PARTY_NOTICES.md', licenses)
    shutil.copytree(ROOT / 'packaging/licenses', licenses / 'runtime')
    for distribution in importlib.metadata.distributions():
        for entry in distribution.files or []:
            if any(part.lower().startswith(('license', 'copying', 'notice')) for part in entry.parts):
                original = Path(distribution.locate_file(entry))
                if original.is_file():
                    target = licenses / distribution.metadata['Name'] / str(entry).replace('..', '_')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(original, target)
    for source_license in (Path(sys.base_prefix) / 'LICENSE.txt',):
        if source_license.is_file():
            shutil.copy2(source_license, licenses / ('Python-' + source_license.name))
    node = shutil.which('node')
    if not node:
        raise ValueError('构建机需要 Node；最终用户无需安装。')
    (stage / 'runtime').mkdir()
    shutil.copy2(node, stage / 'runtime/node.exe')
    rapidocr = importlib.util.find_spec('rapidocr')
    if rapidocr is None:
        raise ValueError('请安装 requirements-build.txt')
    models = Path(rapidocr.origin).parent / 'models'
    (stage / 'models').mkdir()
    for name in ('PP-OCRv6_det_small.onnx', 'PP-OCRv6_rec_small.onnx', 'ch_ppocr_mobile_v2.0_cls_mobile.onnx'):
        if not (models / name).is_file():
            raise ValueError('构建缺少 OCR 模型：' + name)
        shutil.copy2(models / name, stage / 'models' / name)
    manifest = {'schema_version': 1, 'version': __version__, 'python': sys.version, 'node': subprocess.check_output([node, '--version'], text=True).strip(),
                'files': {p.relative_to(stage).as_posix(): digest(p.read_bytes())
                          for p in stage.rglob('*') if p.is_file()}}
    (stage / 'build-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    validate_build_manifest(stage)
    return stage


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--data-dir', type=Path)
    args = parser.parse_args(argv)
    prepare_resources(args.data_dir)
    if not args.prepare_only:
        env = os.environ.copy()
        windows = Path(os.environ.get('SystemRoot', 'C:/Windows'))
        # Desktop toolchains may add unrelated DLL directories to PATH. Qt must
        # resolve the Windows ICU ABI, not a Poppler/Conda ICU with versioned exports.
        env['PATH'] = os.pathsep.join(map(str, [Path(sys.executable).parent, Path(sys.base_prefix), windows / 'System32', windows]))
        subprocess.run([sys.executable, '-m', 'PyInstaller', '--clean', '--noconfirm', '--distpath', str(ROOT / 'artifacts/dist'),
                        '--workpath', str(ROOT / 'artifacts/pyinstaller'), str(ROOT / 'packaging/assistant.spec')],
                       cwd=ROOT, check=True, env=env)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

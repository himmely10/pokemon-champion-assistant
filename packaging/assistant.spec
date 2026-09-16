# Build on Windows with the project environment; no user configuration is included.
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

root = Path(SPECPATH).parent
staged = root / 'artifacts/build-resources'
datas = [(str(staged / name), name) for name in ('config', 'pokemon', 'runtime', 'models', 'damage_engine', 'licenses', 'web')]
datas += [(str(staged / 'build-manifest.json'), '.')]
datas += collect_data_files('rapidocr', excludes=['models/*'])
brand = root / 'assets/branding'
if brand.exists():
    datas += [(str(brand), 'assets/branding')]
a = Analysis([str(root / 'launch_assistant.py')], pathex=[str(root)],
             datas=datas, binaries=[],
             hiddenimports=collect_submodules('rapidocr') + ['onnxruntime', 'champion_assistant.update_worker'],
             excludes=['torch', 'tensorflow', 'paddle', 'openvino', 'matplotlib', 'tkinter', 'IPython'],
             noarchive=False)
pyz = PYZ(a.pure)
icon = str(brand / 'app.ico') if (brand / 'app.ico').exists() else None
gui = EXE(pyz, a.scripts, [], exclude_binaries=True, name='PokemonChampionAssistant',
          console=False, icon=icon, upx=False)
worker = EXE(pyz, a.scripts, [], exclude_binaries=True, name='ChampionWorker',
             console=True, icon=icon, upx=False)
web = EXE(pyz, a.scripts, [], exclude_binaries=True, name='ChampionLabWeb',
          console=True, icon=icon, upx=False)
coll = COLLECT(gui, worker, web, a.binaries, a.datas, name='PokemonChampionAssistant', upx=False)

from pathlib import Path

from launch_assistant import executable_mode, prepare_frozen_qt


def test_installed_entry_points_default_to_the_single_window_shell():
    assert executable_mode(Path('C:/Program Files/ChampionLabWeb.exe'), frozen=True) == 'desktop'
    assert executable_mode(Path('C:/Program Files/ChampionWorker.exe'), frozen=True) == 'desktop'
    assert executable_mode(Path('C:/Program Files/PokemonChampionAssistant.exe'), frozen=True) == 'desktop'
    assert executable_mode(
        Path('C:/Program Files/ChampionLabWeb.exe'), frozen=True, argv=['--port', '32146']
    ) == 'web'
    assert executable_mode(
        Path('C:/Program Files/ChampionLabWeb.exe'), frozen=True, argv=['--port=32146']
    ) == 'web'
    assert executable_mode(Path('C:/repo/launch_assistant.py'), frozen=False) == 'desktop'


def test_frozen_qt_bootstrap_uses_executable_directory_and_restores_cwd(tmp_path, monkeypatch):
    executable_dir = tmp_path / 'installed'
    executable_dir.mkdir()
    original = tmp_path / 'caller'
    original.mkdir()
    monkeypatch.chdir(original)
    observed = []

    prepare_frozen_qt(
        executable_dir / 'ChampionWorker.exe',
        frozen=True,
        loader=lambda module: observed.append((module, Path.cwd())),
    )

    assert observed == [('PySide6.QtCore', executable_dir)]
    assert Path.cwd() == original

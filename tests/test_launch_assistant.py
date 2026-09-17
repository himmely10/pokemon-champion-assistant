from pathlib import Path

from launch_assistant import executable_mode


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

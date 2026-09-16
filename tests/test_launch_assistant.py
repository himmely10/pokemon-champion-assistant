from pathlib import Path

from launch_assistant import executable_mode


def test_frozen_web_executable_selects_web_mode():
    assert executable_mode(Path('C:/Program Files/ChampionLabWeb.exe'), frozen=True) == 'web'
    assert executable_mode(Path('C:/Program Files/PokemonChampionAssistant.exe'), frozen=True) == 'desktop'
    assert executable_mode(Path('C:/repo/launch_assistant.py'), frozen=False) == 'desktop'

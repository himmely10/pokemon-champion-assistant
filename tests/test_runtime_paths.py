"""Installed resources are read-only; personal data survives a safe import."""
import json
import sqlite3

import pytest

from champion_assistant.paths import AppPaths, migrate_legacy


def test_installed_paths_ignore_working_directory(tmp_path, monkeypatch):
    resources = tmp_path / '只读 程序'
    user = tmp_path / '个人 数据'
    monkeypatch.chdir(tmp_path)
    paths = AppPaths(resources, user, tmp_path / 'cache', installed=True)
    assert paths.teams == user / 'teams.sqlite3'
    assert paths.settings == user / 'local_ui.json'
    assert paths.data == user / 'pokemon'
    assert paths.resource('config/type_chart.json') == resources / 'config/type_chart.json'
    with pytest.raises(ValueError):
        paths.resource('../outside')


def test_legacy_import_preserves_source_and_refuses_conflict(tmp_path):
    source, target = tmp_path / '旧项目', tmp_path / '个人数据'
    (source / 'user_data').mkdir(parents=True)
    (source / 'config').mkdir()
    with sqlite3.connect(source / 'user_data/teams.sqlite3') as db:
        db.execute('CREATE TABLE teams (id TEXT, payload TEXT)')
        db.execute('INSERT INTO teams VALUES (?,?)', ('1', '我的队伍'))
    (source / 'config/local_ui.json').write_text(json.dumps({'zoom': 120}))
    paths = AppPaths(tmp_path / 'app', target, tmp_path / 'cache', installed=True)
    result = migrate_legacy(source, paths)
    assert result['imported'] == ['teams', 'settings']
    with sqlite3.connect(paths.teams) as db:
        assert db.execute('SELECT payload FROM teams').fetchone()[0] == '我的队伍'
    assert (source / 'user_data/teams.sqlite3').exists()
    assert migrate_legacy(source, paths)['imported'] == []


def test_corrupt_legacy_database_leaves_target_untouched(tmp_path):
    source = tmp_path / 'old'
    (source / 'user_data').mkdir(parents=True)
    (source / 'user_data/teams.sqlite3').write_bytes(b'not sqlite')
    paths = AppPaths(tmp_path / 'app', tmp_path / 'user', tmp_path / 'cache', installed=True)
    with pytest.raises((ValueError, sqlite3.DatabaseError)):
        migrate_legacy(source, paths)
    assert not paths.teams.exists()


def test_background_entry_uses_existing_due_contract(tmp_path, monkeypatch, capsys):
    from champion_assistant import update_worker
    def update(root, *, due_hours):
        assert root == tmp_path and due_hours == 24
        return {'status': 'not_due'}
    monkeypatch.setattr(update_worker, 'update_usage', update)
    assert update_worker.main(['--data-dir', str(tmp_path), '--if-due']) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'not_due'


def test_frozen_worker_json_is_portable_across_console_codepages(tmp_path, capsys):
    from champion_assistant import update_worker
    assert update_worker.main(['--root', str(tmp_path), '--operation', 'check']) == 0
    output = capsys.readouterr().out
    assert output.isascii()
    assert '未配置' in json.loads(output)['message']

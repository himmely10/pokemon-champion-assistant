import base64
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
from threading import Thread

import pytest
from PIL import Image

from champion_assistant import webapp
from champion_assistant.capture.obs import ObsCapture
from champion_assistant.teams import blank_member
from champion_assistant.webapp import ApiError, WebServices, create_server, is_champion_lab_running


class OtherLocalServiceHandler(BaseHTTPRequestHandler):
    server_version = "OtherLocalService/1"

    def do_GET(self):
        content = b'{"status":"ok"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, _format, *args):
        pass


@pytest.fixture(scope="module")
def services(tmp_path_factory):
    root = tmp_path_factory.mktemp("web-services")
    return WebServices(teams_path=root / "teams.sqlite3", settings_path=root / "settings.json")


def test_bootstrap_and_reference_use_real_catalog(services):
    result = services.bootstrap()
    assert result["app"]["api"] == "local"
    assert result["app"]["pokemon_forms"] == len(services.catalog.records)
    assert len(result["featured"]) == 12
    pokemon = result["featured"][0]
    detail = services.pokemon_detail(pokemon["id"])
    assert detail["name"] == pokemon["name"]
    assert detail["base_stats"]["speed"] == pokemon["speed"]
    assert services.sprite_path(pokemon["id"]).is_file()

    blastoise = next(item for item in result["featured"] if item["name"] == "水箭龟")
    mega_blastoise = next(item for item in result["featured"] if item["name"] == "超级水箭龟")
    assert blastoise["family_base"]["id"] == blastoise["id"]
    assert blastoise["is_battle_form"] is False
    assert mega_blastoise["family_base"]["id"] == blastoise["id"]
    assert mega_blastoise["family_base"]["name"] == "水箭龟"
    assert mega_blastoise["is_battle_form"] is True


def test_pokemon_search_pages_cover_the_entire_local_catalog(services):
    expected = len(services.catalog.search_records())
    pages = [services.search_pokemon("", limit=37, offset=offset)
             for offset in range(0, expected, 37)]
    found = [pokemon for page in pages for pokemon in page]
    assert len(found) == expected
    assert len({pokemon["id"] for pokemon in found}) == expected
    assert services.search_pokemon("", limit=37, offset=expected) == []
    with pytest.raises(ApiError, match="搜索起点无效"):
        services.search_pokemon("", offset=-1)


def test_settings_securely_persist_without_returning_obs_password(services):
    result = services.update_settings({
        "host": "127.0.0.1", "port": 4455, "source": "Switch", "password": "secret",
        "theme": "dark", "reduced_motion": True,
    })
    assert result["password_in_memory"] is True
    assert result["password_saved"] is True
    assert "password" not in result
    persisted = json.loads(services.settings_path.read_text(encoding="utf-8"))
    assert "password" not in persisted
    assert persisted["theme"] == "dark"

    # Clearing the browser password field must reuse the authenticated value.
    assert services._obs_settings({"password": ""})["password"] == "secret"


def test_obs_password_survives_local_service_restart(tmp_path):
    settings_path = tmp_path / "settings.json"
    first = WebServices(teams_path=tmp_path / "first.sqlite3", settings_path=settings_path)
    first.update_settings({"password": "restart-secret"})

    restarted = WebServices(teams_path=tmp_path / "second.sqlite3", settings_path=settings_path)
    assert restarted.public_settings()["password_saved"] is True
    assert restarted._obs_settings({})["password"] == "restart-secret"
    assert b"restart-secret" not in restarted.obs_password_store.path.read_bytes()

    cleared = restarted.update_settings({"clear_obs_password": True})
    assert cleared["password_saved"] is False
    assert cleared["password_in_memory"] is False
    assert not restarted.obs_password_store.path.exists()


def test_team_crud_and_quick_damage_use_saved_member(services):
    own_record = services.catalog.record_for_name("大狃拉")
    rival_record = services.catalog.record_for_name("烈咬陆鲨")
    member = services.damage.presets(own_record)[0]["member"]
    member["ability"] = services.rules.ability_keys(member["identity"])[0]
    saved = services.save_team({
        "id": "", "revision": 0, "name": "网页接口测试队",
        "registration": "partial", "members": [member],
    })
    assert saved["members"][0]["pokemon"]["name"] == "大狃拉"
    result = services.quick_damage({
        "own_id": member["identity"], "rival_id": services.rules.identity(rival_record),
        "own_member": saved["members"][0], "environment": {},
    })
    assert result["own"]["preset"] == "预存队伍配置"
    assert len(result["own_scenarios"]) == len(result["rival_scenarios"]) == 6
    assert [item["target_preset"] for item in result["own_scenarios"][:3]] == [
        "零耐久投入", "满 HP＋物防", "满 HP＋特防",
    ]
    assert [item["preset"] for item in result["rival_scenarios"][:3]] == [
        "零输出投入", "满物攻", "满特攻",
    ]
    assert all(item["spread_usage"] is not None for item in result["own_scenarios"][3:])
    assert any(move["status"] == "ok" and move["damage"][1] > 0 for move in result["own"]["moves"])
    assert services.delete_team(saved) == {"deleted": True}


def test_web_save_accepts_legacy_desktop_team_with_null_import_source(tmp_path):
    services = WebServices(teams_path=tmp_path / 'teams.sqlite3', settings_path=tmp_path / 'settings.json')
    identity = services.search_pokemon('', limit=1)[0]['id']
    legacy = services.store.save({
        'id': '', 'revision': 0, 'name': '旧桌面队伍', 'registration': 'partial',
        'members': [blank_member(identity)], 'import_source': None,
    })
    edited = services.save_team({**legacy, 'name': '网页编辑的旧队伍'})
    assert edited['id'] == legacy['id']
    assert edited['revision'] == legacy['revision'] + 1
    assert edited['name'] == '网页编辑的旧队伍'


def test_api_rejects_mismatched_member_and_non_loopback_bind(services):
    featured = services.search_pokemon("", limit=3)
    member = services.damage.presets(services._record(featured[0]["id"]))[0]["member"]
    with pytest.raises(ApiError, match="不一致"):
        services.quick_damage({
            "own_id": featured[1]["id"], "rival_id": featured[2]["id"],
            "own_member": member, "environment": {},
        })
    with pytest.raises(ValueError, match="回环"):
        create_server(host="0.0.0.0", services=services)


def test_web_server_rejects_a_second_listener_on_the_same_port(services):
    first = create_server(port=0, services=services)
    try:
        with pytest.raises(OSError):
            create_server(port=first.server_port, services=services)
    finally:
        first.server_close()


def test_running_server_probe_only_accepts_champion_lab(services, monkeypatch):
    server = create_server(port=0, services=services)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert is_champion_lab_running(server.server_port) is True
        assert is_champion_lab_running(server.server_port + 1) is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    foreign = ThreadingHTTPServer(("127.0.0.1", 0), OtherLocalServiceHandler)
    foreign_thread = Thread(target=foreign.serve_forever, daemon=True)
    foreign_thread.start()
    try:
        assert is_champion_lab_running(foreign.server_port) is False
        monkeypatch.setattr(webapp, "WebServices", lambda **_kwargs: services)
        with pytest.raises(SystemExit, match="其他程序占用"):
            webapp.main(["--port", str(foreign.server_port), "--no-browser"])
    finally:
        foreign.shutdown()
        foreign.server_close()
        foreign_thread.join(timeout=2)


def test_damage_options_and_full_battle_state_reuse_desktop_rules(services):
    own_record = services.catalog.record_for_name("沙奈朵")
    rival_record = services.catalog.record_for_name("风妖精")
    own_id = services.rules.identity(own_record)
    rival_id = services.rules.identity(rival_record)
    member = services.damage.presets(own_record)[0]["member"]
    member["ability"] = services.rules.ability_keys(own_id)[0]
    forms = services.catalog.form_family(own_record)
    mega = next(record for record in forms if record.get("opgg_key", "").startswith("mega-"))
    mega_id = services.rules.identity(mega)

    options = services.damage_options(rival_id)
    assert {effect["label"] for effect in options["support_effects"]} >= {"本次受到帮助", "光墙", "此方顺风"}
    assert any(ability["id"] == "prankster" for ability in options["abilities"])
    assert len(options["statuses"]) == 7

    own_battle = {"helping_hand": True, "tailwind": True, "boosts": {"speed": 1}}
    rival_battle = {"light_screen": True, "tailwind": True, "boosts": {"speed": 0}}
    result = services.quick_damage({
        "own_id": own_id,
        "own_form_id": mega_id,
        "own_member": member,
        "own_ability": services.rules.ability_keys(mega_id)[0],
        "rival_id": rival_id,
        "rival_ability": "prankster",
        "own_battle": own_battle,
        "rival_battle": rival_battle,
        "environment": {"weather": "", "terrain": "", "targets": 2, "critical": False},
    })
    assert result["own"]["attacker"]["id"] == mega_id
    assert result["speed_comparison"]["own"]["status"] == "ok"
    tiers = result["speed_comparison"]["tiers"]
    assert len(tiers) == 9
    assert [row["speed"] for row in tiers] == sorted(
        (row["speed"] for row in tiers), reverse=True,
    )
    assert [row["name"] for row in tiers].index("满速围巾") < [
        row["name"] for row in tiers
    ].index("极速")
    assert len([row for row in tiers if row["kind"] == "common"]) == 3
    assert all("relation" in row for row in result["speed_comparison"]["tiers"])
    effects = {effect["label"] for move in result["own"]["moves"] for effect in move["support_effects"]}
    assert "本次受到帮助" in effects
    assert any(move["priority"]["current"] is not None for move in result["own"]["moves"])


def test_web_battle_state_defaults_to_full_hp_percentage():
    assert WebServices._battle_state(None)["hp"] == 100
    assert WebServices._battle_state({"hp": 37})["hp"] == 37


def test_http_host_serves_spa_and_blocks_foreign_origin(services, tmp_path):
    (tmp_path / "index.html").write_text("<title>Champion Lab</title>", encoding="utf-8")
    server = create_server(port=0, static_root=tmp_path, services=services)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        connection.request("GET", "/api/health")
        response = connection.getresponse()
        assert response.status == 200
        assert json.loads(response.read())["status"] == "ok"
        body = json.dumps({"theme": "light"})
        connection.request("POST", "/api/settings", body, {
            "Content-Type": "application/json", "Content-Length": str(len(body)),
            "Origin": "https://example.com",
        })
        response = connection.getresponse()
        assert response.status == 403
        assert "非本机" in json.loads(response.read())["error"]
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def _team_import_test_image():
    output = BytesIO()
    Image.new('RGB', (32, 32), 'purple').save(output, format='PNG')
    return output.getvalue()


def _fake_team_import_page(services, mode):
    ids = [services.rules.identity(record) for record in services.catalog.records[:6]]
    return {
        'mode': mode, 'team_code': 'FJR0CNH887', 'code_evidence': {'text': 'ID FJR0CNH887', 'score': .95},
        'members': [
            {'slot': slot, 'member': blank_member(identity), 'evidence': {'name': {'text': 'test', 'score': .94}}, 'box': [1, 2, 3, 4]}
            for slot, identity in enumerate(ids, 1)
        ],
        'source': {'filename': 'secret-local-name.png', 'sha256': 'a' * 64, 'size': [32, 32]},
    }


def test_team_import_review_is_isolated_and_sanitized(tmp_path, monkeypatch):
    services = WebServices(teams_path=tmp_path / 'teams.sqlite3', settings_path=tmp_path / 'settings.json')
    existing_member = blank_member(services.rules.identity(services.catalog.records[6]))
    existing = services.save_team({'id': '', 'revision': 0, 'name': '旧队伍',
                                   'registration': 'partial', 'members': [existing_member]})
    monkeypatch.setattr('champion_assistant.team_import.shared_local_ocr', lambda: object())
    monkeypatch.setattr(webapp.ScreenshotImporter, 'read_page',
                        lambda self, path, mode: _fake_team_import_page(services, mode))
    image = _team_import_test_image()
    ability = services.team_import_recognize(image, 'ability')
    status = services.team_import_recognize(image, 'status')
    assert 'filename' not in ability['page']['source']
    assert services.teams() == [existing]
    ids = [item['member']['identity'] for item in ability['page']['members']]
    reviews = {'code': 'FJR0CNH887', 'identities': ids}
    request = {
        'ability_handle': ability['handle'], 'status_handle': status['handle'],
        'ability_review': reviews, 'status_review': reviews,
    }
    with pytest.raises(ApiError, match='复核'):
        services.team_import_combine({**request, 'ability_review': {**reviews, 'source': {'password': 'secret'}}})
    with pytest.raises(ApiError, match='一致'):
        services.team_import_combine({**request, 'status_review': {**reviews, 'code': 'ABCDEFGHIJ'}})
    with pytest.raises(ApiError, match='重复'):
        services.team_import_combine({**request, 'ability_review': {**reviews, 'identities': ids[:5] + [ids[0]]}})
    assert services.teams() == [existing]
    result = services.team_import_combine(request)
    assert result['draft']['id'] == '' and result['draft']['revision'] == 0
    assert len(result['draft']['members']) == 6
    assert 'secret-local-name' not in json.dumps(result)
    assert services.teams() == [existing]
    poisoned = {**result['draft'], 'screenshot': 'data:image/png;base64,EVIL', 'password': 'top-secret', 'import_source': {
        **result['draft']['import_source'], 'password': 'never-store', 'data_url': 'data:image/png;base64,AAAA',
        'ability': {**result['draft']['import_source']['ability'], 'source': {
            **result['draft']['import_source']['ability']['source'], 'filename': 'hidden.png'}}}}
    poisoned['members'][0]['screenshot'] = 'data:image/png;base64,MEMBER'
    saved = services.save_team(poisoned)
    persisted = json.dumps(saved, ensure_ascii=False)
    assert all(secret not in persisted for secret in ('never-store', 'top-secret', 'data:image', 'hidden.png'))
    assert len(services.teams()) == 2
    assert services.teams()[0] == existing


def test_team_import_identity_change_clears_dependent_build(tmp_path, monkeypatch):
    services = WebServices(teams_path=tmp_path / 'teams.sqlite3', settings_path=tmp_path / 'settings.json')
    monkeypatch.setattr('champion_assistant.team_import.shared_local_ocr', lambda: object())
    def read_page(self, path, mode):
        page = _fake_team_import_page(services, mode)
        if mode == 'ability':
            first = page['members'][0]['member']
            first['ability'] = services.rules.ability_keys(first['identity'])[0] if services.rules.ability_keys(first['identity']) else None
            first['moves'] = ['old-move'] * 4
        return page
    monkeypatch.setattr(webapp.ScreenshotImporter, 'read_page', read_page)
    ability = services.team_import_recognize(_team_import_test_image(), 'ability')
    status = services.team_import_recognize(_team_import_test_image(), 'status')
    ids = [item['member']['identity'] for item in ability['page']['members']]
    swapped = [ids[-1], *ids[1:-1], ids[0]]
    result = services.team_import_combine({
        'ability_handle': ability['handle'], 'status_handle': status['handle'],
        'ability_review': {'code': 'FJR0CNH887', 'identities': swapped},
        'status_review': {'code': 'FJR0CNH887', 'identities': swapped},
    })
    assert result['draft']['members'][0]['ability'] is None
    assert result['draft']['members'][0]['moves'] == [None] * 4
    assert result['draft']['import_source']['ability']['members'][0]['identity_corrected'] is True


def test_team_import_rejects_missing_stale_and_oversized_inputs(tmp_path, monkeypatch):
    services = WebServices(teams_path=tmp_path / 'teams.sqlite3', settings_path=tmp_path / 'settings.json')
    monkeypatch.setattr('champion_assistant.team_import.shared_local_ocr', lambda: object())
    monkeypatch.setattr(webapp.ScreenshotImporter, 'read_page',
                        lambda self, path, mode: _fake_team_import_page(services, mode))
    with pytest.raises(ApiError, match='25 MB'):
        services.team_import_recognize(b'', 'ability')
    with pytest.raises(ApiError, match='无法读取'):
        services.team_import_recognize(b'not an image', 'ability')
    oversized = BytesIO()
    Image.new('RGB', (6000, 6000), 'purple').save(oversized, format='PNG')
    with pytest.raises(ApiError, match='3000 万'):
        services.team_import_recognize(oversized.getvalue(), 'ability')
    ability = services.team_import_recognize(_team_import_test_image(), 'ability')
    status = services.team_import_recognize(_team_import_test_image(), 'status')
    ids = [item['member']['identity'] for item in ability['page']['members']]
    request = {'ability_handle': ability['handle'], 'status_handle': status['handle'],
               'ability_review': {'code': 'FJR0CNH887', 'identities': ids},
               'status_review': {'code': 'FJR0CNH887', 'identities': ids}}
    with services._team_import_lock:
        old = services._team_import_evidence[status['handle']]
        services._team_import_evidence[status['handle']] = (old[0] - webapp.TEAM_IMPORT_TTL - 1, old[1], old[2])
    with pytest.raises(ApiError, match='过期'):
        services.team_import_combine(request)


def test_team_import_obs_capture_reuses_password_without_echo(tmp_path):
    image = _team_import_test_image()
    data_url = 'data:image/png;base64,' + base64.b64encode(image).decode('ascii')
    class Obs:
        def screenshot_data_url(self, settings):
            assert settings['password'] == 'obs-private-password'
            assert settings['source'] == 'Switch'
            return data_url
    services = WebServices(teams_path=tmp_path / 'teams.sqlite3', settings_path=tmp_path / 'settings.json', obs=Obs())
    services.obs_password = 'obs-private-password'
    result = services.team_import_obs_capture({'source': 'Switch'})
    assert result == {'data_url': data_url}
    assert 'obs-private-password' not in json.dumps(result)


def test_obs_raw_screenshot_uses_existing_protocol_without_changing_old_capture():
    image = _team_import_test_image()
    data_url = 'data:image/png;base64,' + base64.b64encode(image).decode('ascii')
    calls = []
    class Client:
        def __init__(self, **settings):
            assert settings['password'] == 'private'
        def send(self, name, payload=None, *, raw=False):
            calls.append((name, payload))
            if name == 'GetVersion':
                return {'availableRequests': ['GetSourceScreenshot']}
            return {'imageData': data_url}
        def disconnect(self):
            pass
    obs = ObsCapture(factory=Client)
    settings = {'host': '127.0.0.1', 'port': 4455, 'password': 'private', 'source': 'Switch'}
    assert obs.screenshot_data_url(settings) == data_url
    assert obs.screenshot(settings).size == (32, 32)
    assert calls[1] == ('GetSourceScreenshot', {'sourceName': 'Switch', 'imageFormat': 'png'})


def test_team_import_http_route_rejects_foreign_origin_and_returns_no_store(tmp_path, monkeypatch):
    services = WebServices(teams_path=tmp_path / 'teams.sqlite3', settings_path=tmp_path / 'settings.json')
    monkeypatch.setattr('champion_assistant.team_import.shared_local_ocr', lambda: object())
    monkeypatch.setattr(webapp.ScreenshotImporter, 'read_page',
                        lambda self, path, mode: _fake_team_import_page(services, mode))
    server = create_server(port=0, static_root=tmp_path, services=services)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
        body = _team_import_test_image()
        path = '/api/team-import/recognize?mode=ability'
        connection.request('POST', path, body, {'Origin': 'https://example.com'})
        response = connection.getresponse()
        assert response.status == 403
        response.read()
        connection.request('POST', path, body, {'Origin': f'http://127.0.0.1:{server.server_port}'})
        response = connection.getresponse()
        assert response.status == 200
        assert response.getheader('Cache-Control') == 'no-store'
        result = json.loads(response.read())
        assert result['page']['mode'] == 'ability' and len(result['handle']) == 32
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)

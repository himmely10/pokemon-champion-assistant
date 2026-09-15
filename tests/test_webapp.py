import http.client
import json
from threading import Thread

import pytest

from champion_assistant.webapp import ApiError, WebServices, create_server


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
    assert any(move["status"] == "ok" and move["damage"][1] > 0 for move in result["own"]["moves"])
    assert services.delete_team(saved) == {"deleted": True}


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
    assert len(result["speed_comparison"]["tiers"]) == 6
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

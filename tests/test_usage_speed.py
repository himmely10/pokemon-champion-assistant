import copy
import json
from pathlib import Path

import pytest

from champion_assistant.data.references import ReferenceCatalog
from champion_assistant.damage import DamageService
from champion_assistant.data.storage import read_json, save_json, digest, json_bytes
from champion_assistant.data.usage import action_result, load_usage, move_order, parse_detail, update_usage
from champion_assistant.capture.obs import local_obs_settings, ObsCapture, CaptureError
from champion_assistant.speed import speed_lines, reference_speed

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "docs/research/2026-09-11-usage-speed"


def test_observed_public_double_action_and_lookup():
    payload = action_result((RESEARCH / "double-garchomp.rsc").read_bytes())
    entry = parse_detail(payload, "garchomp", "m-6")
    lookup = {m["id"]: m["key"] for m in payload["lookupData"]["moves"]}
    expected = {lookup[m["id"]]: m["usagePercent"] for m in payload["detailData"]["doubleDetail"]["moves"]}
    assert entry["moves"] == expected
    assert entry["format"] == "double" and entry["season"] == "m-6"
    # Generic win/lose move rates and singles must never feed the move-adoption column.
    assert entry["moves"]["protect"] > 70
    assert entry["moves"]["earthquake"] != payload["detailData"]["doubleDetail"]["win"]["moves"][0]["usagePercent"]


@pytest.mark.parametrize("kind", ["missing_double", "wrong_identity", "bad_rate", "unknown_move", "duplicate"])
def test_usage_rejects_corrupt_or_wrong_context(kind):
    payload = action_result((RESEARCH / "double-garchomp.rsc").read_bytes())
    detail = payload["detailData"]["doubleDetail"]
    if kind == "missing_double":
        payload["detailData"].pop("doubleDetail")
    elif kind == "wrong_identity":
        detail["pokemon"]["key"] = "sneasler"
    elif kind == "bad_rate":
        detail["moves"][0]["usagePercent"] = 101
    elif kind == "unknown_move":
        detail["moves"][0]["id"] = -999
    else:
        detail["moves"].append(detail["moves"][0])
    with pytest.raises(ValueError):
        parse_detail(payload, "garchomp", "m-6")


def test_missing_adoption_is_not_zero_and_power_sort_is_stable():
    moves = [{"name": "高威力未知率", "power": 150}, {"name": "已知零", "power": 40, "usage_percent": 0},
             {"name": "常用", "power": 50, "usage_percent": 70}, {"name": "变动威力", "power": None},
             {"name": "低威力未知率", "power": 30}]
    assert [m["name"] for m in sorted(moves, key=move_order)] == ["常用", "已知零", "高威力未知率", "低威力未知率", "变动威力"]


class FakeClient:
    season = "m-6"
    failures = set()
    def discover(self):
        return self.season
    def ranking(self, season):
        return {"createdAt": "fixture", "rankings": [{"key": "p" + str(i)} for i in range(5)]}
    def detail(self, season, row):
        if row["key"] in self.failures:
            raise ValueError("fixture failure")
        return {"pokemon_key": row["key"], "season": season, "format": "double", "moves": {"protect": 80}}


def test_usage_atomic_publish_due_and_failures(tmp_path):
    client = FakeClient()
    assert update_usage(tmp_path, client=client)["status"] == "updated"
    first = (tmp_path / "current.json").read_bytes()
    assert update_usage(tmp_path, due_hours=24, client=client)["status"] == "not_due"
    client.failures = {"p0"}
    assert update_usage(tmp_path, client=client)["status"] == "partial"
    assert load_usage(tmp_path)["pokemon"]["p0"]["moves"]["protect"] == 80
    before = (tmp_path / "current.json").read_bytes()
    client.failures = {"p0", "p1"}
    with pytest.raises(ValueError, match="20%"):
        update_usage(tmp_path, client=client)
    assert (tmp_path / "current.json").read_bytes() == before
    assert before != first
    client.failures = {"p0"}
    client.season = "m-7"
    update_usage(tmp_path, client=client)
    current = load_usage(tmp_path)
    assert current["season"] == "m-7" and "p0" not in current["pokemon"]


def test_snapshot_checksum_rejects_tampering(tmp_path):
    update_usage(tmp_path, client=FakeClient())
    pointer = read_json(tmp_path / "current.json")
    (tmp_path / pointer["file"]).write_text("{}")
    with pytest.raises(ValueError, match="校验"):
        load_usage(tmp_path)


def test_fresh_legacy_snapshot_gets_new_statistics_fields(tmp_path):
    update_usage(tmp_path,client=FakeClient())
    snapshot=load_usage(tmp_path)
    snapshot.pop('features_version')
    data=json_bytes(snapshot)
    (tmp_path/'legacy.json').write_bytes(data)
    save_json(tmp_path/'current.json',{'file':'legacy.json','sha256':digest(data)})
    assert update_usage(tmp_path,due_hours=24,client=FakeClient())['status']=='updated'
    assert load_usage(tmp_path)['features_version']==2


def test_mega_learnset_inherits_base_usage(tmp_path):
    catalog = ReferenceCatalog(ROOT / "pokemon", usage_dir=tmp_path)
    record = catalog.record_for_name("喷火龙")
    catalog.usage = {"pokemon": {record["opgg_key"]: {"moves": {"flamethrower": 90}}}}
    mega = catalog.form_family(record)[1]
    damage, status, notice = catalog.learnset(mega)
    assert damage and status and "常用分配和性格继承普通形态" in notice
    flamethrower = next(m for m in damage if m['key']=='flamethrower')
    assert flamethrower['usage_percent']==90
    assert any(m["usage_percent"] is None for m in damage + status)


@pytest.mark.parametrize('name', ['超级喷火龙X', '超级路卡利欧', '超级路卡利欧Z', '超级暴飞龙'])
def test_real_mega_forms_have_base_form_common_moves(name):
    catalog = ReferenceCatalog(ROOT / 'pokemon')
    record = catalog.record_for_name(name)
    service = DamageService(catalog)
    moves = service.common_moves(record, 4, damage_only=True)
    assert len(moves) == 4
    damage, _, notice = catalog.learnset(record)
    assert all(next(m for m in damage if m['key'] == key)['usage_percent'] is not None for key in moves)
    assert '继承普通形态' in notice


@pytest.mark.parametrize('name', ['超级大针蜂', '超级喷火龙X', '超级路卡利欧Z', '超级暴飞龙'])
def test_real_mega_forms_inherit_base_training_and_natures(name):
    catalog = ReferenceCatalog(ROOT / 'pokemon')
    record = catalog.record_for_name(name)
    usage, inherited_from = catalog.usage_for(record)
    assert inherited_from is not None
    assert usage['training'] and usage['natures']
    presets = DamageService(catalog).comparison_presets(record)
    common = [preset for preset in presets if preset['name'].startswith('常用分配')]
    assert len(common) == 6  # 三种分配分别用于攻、防两个方向。
    assert common[0]['spread_usage'] == usage['training'][0]['usage_percent']


def test_speed_user_screenshot_and_integer_floor():
    assert speed_lines(120) == [283, 189, 258, 172, 140, 126]
    assert speed_lines(102) == [253, 169, 231, 154, 122, 109]
    assert reference_speed(120, 32, 11, True) == (189 * 3) // 2
    assert reference_speed(120, 0, 9) == 126
    with pytest.raises(ValueError):
        reference_speed(120, 33)


def test_obs_local_config_diagnostic_and_error_classification(tmp_path):
    path = tmp_path / "config.json"
    save_json(path, {"server_enabled": False, "server_port": 4466, "auth_required": True, "server_password": "secret"})
    assert "password" not in local_obs_settings(path)
    assert local_obs_settings(path, include_password=True)["password"] == "secret"
    def refused(**kwargs):
        raise ConnectionRefusedError()
    with pytest.raises(CaptureError, match="勾选启用"):
        ObsCapture(refused).sources({})
    def auth_error(**kwargs):
        raise ValueError("authentication enabled but no password provided")
    with pytest.raises(CaptureError, match="密码验证失败"):
        ObsCapture(auth_error).sources({})

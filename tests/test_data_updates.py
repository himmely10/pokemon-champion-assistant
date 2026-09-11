"""Source contracts and real filesystem failure/recovery cases for catalog updates."""
import copy
import json
from pathlib import Path

import pytest
import requests

from champion_assistant.data.catalog import build_catalog
from champion_assistant.data.sources import HttpCache, OPGG_URL, discover_file_images, parse_opgg, parse_wiki
from champion_assistant.data.storage import (confined, digest, json_bytes, read_json, resolve_dataset,
                                            save_json, update_lock, validate_bundle)
from champion_assistant.data.sync import rollback, run_update
from champion_assistant.recognition import OpponentRecognizer, PROJECT_ROOT

RESEARCH = PROJECT_ROOT / "docs/research/2026-09-10-opgg"
ALIASES = read_json(PROJECT_ROOT / "config/source_aliases.json")


def html_for(rows):
    frame = "0:" + json.dumps(["$", "catalog", None, {"pokemon": rows}], ensure_ascii=False) + "\n"
    return ("<script>self.__next_f.push(" + json.dumps([1, frame], ensure_ascii=False) + ")</script>").encode()


def test_move_only_update_and_missing_list_preserve_old_bundle(fixture_data):
    root, folder, rows, image = fixture_data
    move = {"key": "tackle", "name": "撞击", "category": "physical", "type": "normal",
            "power": 40, "accuracy": 100, "effect": "攻击目标。", "isAvailable": True}
    def write_moves():
        frame = "0:" + json.dumps(["$", "catalog", None, {"pokemon": rows, "moveList": [move]}], ensure_ascii=False) + "\n"
        (folder / "pokedex.html").write_bytes(("<script>self.__next_f.push(" + json.dumps([1, frame], ensure_ascii=False) + ")</script>").encode())
    write_moves()
    run_update(root, "sync", folder, minimum=1, client=OfflineImages(image))
    old = resolve_dataset(root)
    move["effect"] = "新的效果说明。"
    write_moves()
    report = run_update(root, "sync", folder, minimum=1, client=OfflineImages(image))
    assert report["moves_changed"] and report["status"] == "published"
    assert resolve_dataset(root) != old
    assert read_json(resolve_dataset(root) / "moves.json")["tackle"]["description"] == "新的效果说明。"
    pointer = (root / "current.json").read_bytes()
    (folder / "pokedex.html").write_bytes(html_for(rows))
    with pytest.raises(ValueError, match="招式清单丢失"):
        run_update(root, "sync", folder, minimum=1, client=OfflineImages(image))
    assert (root / "current.json").read_bytes() == pointer


def wiki_for(dexes):
    rows = []
    for dex in dexes:
        cells = [f"<td>#{dex:04d}</td>"]
        for suffix in ("", "_s"):
            url = f"https://media.52poke.com/wiki/a/ab/Champions_{dex:04d}{suffix}_Sprite.png"
            cells.append(f'<td><img src="{url}"></td>')
        cells.append("<td>名称</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return ("<table>" + "".join(rows) + "</table>").encode()


class OfflineImages:
    def __init__(self, image, failure=False):
        self.image = image
        self.failure = failure
        self.events = []

    def get(self, url, **kwargs):
        self.events.append({"url": url})
        if self.failure:
            raise requests.Timeout("simulated interrupted download")
        return self.image


@pytest.fixture
def fixture_data(tmp_path):
    # Reuse a real sprite to test the production PNG validation, not mocked image decoding.
    active = resolve_dataset(PROJECT_ROOT / "pokemon")
    original = next(r for r in read_json(active / "index.json")["pokemon"] if r["source_slug"] == "venusaur")
    record = copy.deepcopy(original)
    for key in list(record):
        if key in ("opgg_key", "source_presence", "record_id"):
            record.pop(key)
    record["directory"] = record["name"]
    record["images"] = copy.deepcopy(original["images"])
    root = tmp_path / "pokemon"
    for asset in record["images"].values():
        target = root / record["directory"] / asset["file"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((active / original["directory"] / asset["file"]).read_bytes())
    index = {"schema_version": 1, "species_count": 1, "form_count": 1, "pokemon": [record]}
    save_json(root / "index.json", index)
    source = read_json(RESEARCH / "pokemon-observed.json")
    source = [r for r in source if r["key"] in ("venusaur", "blastoise")]
    folder = tmp_path / "source"
    folder.mkdir()
    (folder / "pokedex.html").write_bytes(html_for(source))
    (folder / "wiki-roster.html").write_bytes(wiki_for([3, 9]))
    image = (root / record["directory"] / record["images"]["normal"]["file"]).read_bytes()
    return root, folder, source, image


def test_real_source_full_catalog_and_cosmetic_mapping():
    source = parse_opgg((RESEARCH / "pokedex.html").read_bytes())
    assert len(source) == 352  # Captured fixture, not a runtime roster-count constant.
    wiki = parse_wiki((RESEARCH / "wiki-roster.html").read_bytes())
    legacy = read_json(PROJECT_ROOT / "pokemon/_sources/roster.json")
    assert len(wiki) <= len(legacy)  # Shared icons collapse, not individual visual records.
    active = resolve_dataset(PROJECT_ROOT / "pokemon")
    previous = read_json(active / "index.json")
    records, report = build_catalog(previous, source, wiki, ALIASES)
    assert report["unmapped"] == []
    by_name = {r["name"]: r for r in records}
    assert by_name["超级花叶蒂"]["opgg_key"] == "mega-floette"
    assert by_name["超级超能妙喵"]["opgg_key"] == "mega-meowstic"
    assert by_name["一家鼠（三只家庭）"]["opgg_key"] == "maushold-family-of-three"
    assert by_name["飘浮泡泡（雨水的样子）"]["source_presence"] != "present"
    tea = [r for r in records if r["source_slug"] == "sinistcha"]
    assert len(tea) == 2 and all(r["opgg_key"] == "sinistcha" for r in tea)


@pytest.mark.parametrize("kind", ["error_page", "truncated", "duplicate", "bad_stat", "missing_parent"])
def test_parser_rejects_incomplete_or_corrupt_sources(fixture_data, kind):
    _, _, rows, _ = fixture_data
    rows = copy.deepcopy(rows)
    content = html_for(rows)
    minimum = 1
    if kind == "error_page":
        content = b"<html>Service temporarily unavailable</html>"
    elif kind == "truncated":
        minimum = 200
    elif kind == "duplicate":
        content = html_for(rows + rows[:1])
    elif kind == "bad_stat":
        rows[0]["stats"]["speed"] = True
        content = html_for(rows)
    else:
        rows[0]["base_key"] = "absent"
        content = html_for(rows)
    with pytest.raises(ValueError):
        parse_opgg(content, minimum)


def test_sync_rollback_and_existing_reader_stays_pinned(fixture_data):
    root, folder, _, image = fixture_data
    old_reader = OpponentRecognizer(root)
    original_bytes = (root / "index.json").read_bytes()
    check = run_update(root, "check", folder, minimum=1, client=OfflineImages(image))
    assert [r["name"] for r in check["new_species"]] == ["水箭龟"]
    assert (root / "index.json").read_bytes() == original_bytes
    assert not (root / "current.json").exists()
    report = run_update(root, "sync", folder, minimum=1, client=OfflineImages(image))
    assert report["status"] == "published"
    first = resolve_dataset(root)
    assert validate_bundle(first)["recognition_ready"] == 2
    assert old_reader.data_dir == root and old_reader.dataset_id == "legacy"
    new_reader = OpponentRecognizer(root)
    assert new_reader.data_dir == first
    assert any(m["name"] == "水箭龟" for t in new_reader.templates for m in t.members)
    assert not any(m["name"] == "水箭龟" for t in old_reader.templates for m in t.members)
    again = run_update(root, "sync", folder, minimum=1, client=OfflineImages(image))
    assert again["status"] == "up_to_date" and resolve_dataset(root) == first
    assert again["downloads"]["image_fetches"] == 0
    restored = rollback(root)
    assert restored["validation"]["forms"] == 1
    assert new_reader.data_dir == first  # Rollback cannot mutate a live reader either.
    export = read_json(root / "index.json")
    assert (root / export["pokemon"][0]["directory"]).is_dir()


def test_missing_icons_are_data_only(fixture_data):
    root, folder, _, image = fixture_data
    (folder / "wiki-roster.html").write_bytes(wiki_for([3]))
    report = run_update(root, "sync", folder, minimum=1, client=OfflineImages(image))
    assert report["pending_assets"] == ["水箭龟"]
    catalog = read_json(resolve_dataset(root) / "index.json")
    blastoise = next(r for r in catalog["pokemon"] if r["name"] == "水箭龟")
    assert blastoise["types"] == ["water"] and blastoise["images"] == {}
    reader = OpponentRecognizer(root)
    assert not any(m["name"] == "水箭龟" for t in reader.templates for m in t.members)


def test_download_failure_preserves_active_bundle(fixture_data):
    root, folder, _, image = fixture_data
    run_update(root, "sync", folder, minimum=1, client=OfflineImages(image))
    pointer = (root / "current.json").read_bytes()
    with pytest.raises(requests.Timeout):
        run_update(root, "sync", folder, refresh_images=True, minimum=1, client=OfflineImages(image, failure=True))
    assert (root / "current.json").read_bytes() == pointer
    validate_bundle(resolve_dataset(root))


def test_mass_removal_is_blocked(fixture_data):
    root, folder, rows, image = fixture_data
    run_update(root, "sync", folder, minimum=1, client=OfflineImages(image))
    pointer = (root / "current.json").read_bytes()
    (folder / "pokedex.html").write_bytes(html_for(rows[:1]))
    report = run_update(root, "check", folder, minimum=1, client=OfflineImages(image))
    assert report["large_removal"]
    with pytest.raises(ValueError, match="减少"):
        run_update(root, "sync", folder, minimum=1, client=OfflineImages(image))
    assert (root / "current.json").read_bytes() == pointer


@pytest.mark.parametrize("path", ["../escape", "C:/outside", "/absolute", "folder/../../escape", "file:stream", "a\\b", "CON.png"])
def test_paths_cannot_escape(tmp_path, path):
    with pytest.raises(ValueError):
        confined(tmp_path, path)


def test_manifest_rejects_traversal_even_with_correct_hash(fixture_data):
    root, folder, _, image = fixture_data
    run_update(root, "sync", folder, minimum=1, client=OfflineImages(image))
    bundle = resolve_dataset(root)
    manifest = read_json(bundle / "manifest.json")
    manifest["files"]["../outside"] = digest(b"hello")
    save_json(bundle / "manifest.json", manifest)
    with pytest.raises(ValueError, match="路径"):
        validate_bundle(bundle)


def test_process_lock_prevents_duplicate_updates(tmp_path):
    with update_lock(tmp_path):
        with pytest.raises(ValueError, match="已有更新"):
            with update_lock(tmp_path):
                pass


class Response:
    def __init__(self, status, body=b"", headers=None):
        self.status_code, self.content, self.headers = status, body, headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


class Session:
    def __init__(self, responses):
        self.responses, self.calls, self.headers = list(responses), [], {}

    def get(self, url, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def test_cached_html_is_revalidated_and_changes_are_seen(tmp_path):
    session = Session([Response(200, b"old", {"ETag": "v1"}), Response(304), Response(200, b"new", {"ETag": "v2"})])
    cache = HttpCache(tmp_path, session, lambda _: None)
    assert cache.get(OPGG_URL) == b"old"
    assert cache.get(OPGG_URL) == b"old"
    assert session.calls[1]["headers"] == {"If-None-Match": "v1"}
    assert cache.get(OPGG_URL) == b"new"
    assert len(session.calls) == 3


def test_rate_limit_retry_is_bounded(tmp_path):
    session = Session([Response(429, headers={"Retry-After": "2"})] * 3)
    delays = []
    with pytest.raises(requests.HTTPError):
        HttpCache(tmp_path, session, delays.append).get(OPGG_URL)
    assert len(session.calls) == 3 and delays == [2, 2]


def test_long_server_cooldown_stops_without_early_retry(tmp_path):
    session = Session([Response(429, headers={"Retry-After": "120"})])
    with pytest.raises(ValueError, match="稍后"):
        HttpCache(tmp_path, session, lambda _: pytest.fail("must not retry early")).get(OPGG_URL)
    assert len(session.calls) == 1


def test_file_library_finds_uploads_before_roster_article(tmp_path):
    normal = "Champions_0373_Sprite.png"
    shiny = "Champions_0373_s_Sprite.png"
    pages = {}
    for number, filename in enumerate((normal, shiny)):
        pages[str(number)] = {"title": "File:" + filename.replace("_", " "), "imageinfo": [{
            "url": "https://media.52poke.com/wiki/a/ab/" + filename, "width": 128, "height": 128}]}
    session = Session([Response(200, json_bytes({"batchcomplete": "", "query": {"pages": pages}}))])
    record = {"_expected_sprite": normal, "recognition_ready": False}
    snapshots = discover_file_images([record], HttpCache(tmp_path, session))
    assert len(snapshots) == 1
    assert record["_desired_images"]["normal"]["source_filename"] == normal
    assert record["_desired_images"]["shiny"]["source_filename"] == shiny


def test_file_library_missing_is_not_a_broken_response(tmp_path):
    names = ["Champions_0373_Sprite.png", "Champions_0373_s_Sprite.png"]
    pages = {str(i): {"title": "File:" + n.replace("_", " "), "missing": ""} for i, n in enumerate(names)}
    session = Session([Response(200, json_bytes({"query": {"pages": pages}}))])
    record = {"_expected_sprite": names[0], "recognition_ready": False}
    discover_file_images([record], HttpCache(tmp_path, session))
    assert "_desired_images" not in record


def test_file_library_partial_batch_is_rejected(tmp_path):
    session = Session([Response(200, json_bytes({"query": {"pages": {}}}))])
    with pytest.raises(ValueError, match="遗漏"):
        discover_file_images([{"_expected_sprite": "Champions_0373_Sprite.png", "recognition_ready": False}], HttpCache(tmp_path, session))


def test_wiki_cannot_pair_another_species_shiny_sprite():
    content = wiki_for([3]).replace(b"Champions_0003_s_Sprite", b"Champions_0009_s_Sprite")
    with pytest.raises(ValueError, match="不对应"):
        parse_wiki(content)


def test_atomic_publication_failure_preserves_pointer(fixture_data, monkeypatch):
    root, folder, rows, image = fixture_data
    run_update(root, "sync", folder, minimum=1, client=OfflineImages(image))
    pointer = (root / "current.json").read_bytes()
    rows[0]["stats"]["speed"] += 1
    (folder / "pokedex.html").write_bytes(html_for(rows))
    from champion_assistant.data import storage
    original = storage.save_json

    def fail_pointer(path, value):
        if Path(path).name == "current.json":
            raise OSError("simulated write failure")
        original(path, value)

    monkeypatch.setattr(storage, "save_json", fail_pointer)
    with pytest.raises(OSError):
        run_update(root, "sync", folder, minimum=1, client=OfflineImages(image))
    assert (root / "current.json").read_bytes() == pointer
    validate_bundle(resolve_dataset(root))


def test_rollback_recovers_corrupt_current_index(fixture_data):
    root, folder, _, image = fixture_data
    run_update(root, "sync", folder, minimum=1, client=OfflineImages(image))
    current = resolve_dataset(root)
    (current / "index.json").write_text("broken", encoding="utf-8")
    with pytest.raises(ValueError, match="索引校验"):
        resolve_dataset(root)
    assert rollback(root)["validation"]["forms"] == 1


def test_recognizer_rejects_changed_sprite_bytes(fixture_data):
    root, _, _, _ = fixture_data
    record = read_json(root / "index.json")["pokemon"][0]
    (root / record["directory"] / record["images"]["normal"]["file"]).write_bytes(b"broken")
    with pytest.raises(ValueError, match="图标校验"):
        OpponentRecognizer(root)

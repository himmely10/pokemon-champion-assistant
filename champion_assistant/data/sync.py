"""Check and publish source updates without changing an active reader's snapshot."""
from __future__ import annotations

import uuid
from pathlib import Path

from .catalog import build_catalog, compare
from .moves import parse_moves
from .sources import HttpCache, OPGG_URL, WIKI_URL, discover_file_images, parse_opgg, parse_wiki, verify_sprite
from .storage import (atomic_bytes, confined, digest, discard_stage, export_compatibility_index, json_bytes,
                      make_bundle, now, publish, read_json, resolve_dataset, save_json,
                      validate_bundle, validate_index)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG = PROJECT_ROOT / "config"
CATALOG_REVISION = 2


def inputs(root, client, source_dir=None, minimum=200, aliases=None):
    current = resolve_dataset(root)
    previous = read_json(current / "index.json")
    if (current / "manifest.json").exists():
        validate_bundle(current)
    else:
        validate_index(previous, current)
    previous_source = read_json(current / "source_catalog.json") if (current / "source_catalog.json").exists() else []
    if source_dir:
        source_dir = Path(source_dir)
        opgg = (source_dir / "pokedex.html").read_bytes()
        wiki = (source_dir / "wiki-roster.html").read_bytes()
    else:
        opgg = client.get(OPGG_URL)
        wiki = client.get(WIKI_URL)
    source_records = parse_opgg(opgg, minimum)
    wiki_entries = parse_wiki(wiki)
    policy = aliases or read_json(CONFIG / "source_aliases.json")
    records, details = build_catalog(previous, source_records, wiki_entries, policy)
    file_info = [] if source_dir else discover_file_images(records, client)
    report = compare(previous, records, previous_source, source_records, details)
    report.update({"checked_at": now(), "source_mode": "offline_snapshot" if source_dir else "live_revalidated",
                   "source_urls": [OPGG_URL, WIKI_URL], "active_bundle": current.name if current != root else "legacy",
                   "requested_battle_format": "double", "statistics_included": False})
    report["file_library_batches"] = len(file_info)
    return current, previous, previous_source, records, source_records, policy, report, opgg, wiki, file_info


def materialize_images(records, previous_root, work, client, refresh=False):
    reused, downloaded = 0, 0
    for record in records:
        desired = record.get("_desired_images", {})
        assets = {}
        for variant in sorted(set(record["images"]) | set(desired)):
            old = record["images"].get(variant)
            intent = desired.get(variant) or old
            content = None
            if old and not refresh and old["source_url"] == intent["source_url"]:
                old_path = confined(previous_root, f"{record['directory']}/{old['file']}")
                if old_path.exists():
                    content = old_path.read_bytes()
                    if digest(content) != old["sha256"]:
                        raise ValueError(f"旧图标损坏：{record['name']}/{variant}")
                    reused += 1
            if content is None:
                content = client.get(intent["source_url"], immutable=not refresh, png=True)
                downloaded += 1
                if downloaded % 20 == 0:
                    print(f"已取得 {downloaded} 张增量图标……", flush=True)
            verify_sprite(content)
            suffix = "_闪光" if variant == "shiny" else ""
            filename = f"{record['name']}{suffix}.png"
            atomic_bytes(confined(work, f"{record['directory']}/{filename}"), content)
            assets[variant] = {"file": filename, "source_url": intent["source_url"],
                               "source_filename": intent["source_filename"], "sha256": digest(content),
                               "width": 128, "height": 128, "bytes": len(content)}
        record["images"] = assets
        record["recognition_ready"] = set(assets) == {"normal", "shiny"}
    return {"local_images_reused": reused, "image_fetches": downloaded}


def write_report(root, report):
    token = report["checked_at"].replace(":", "").replace("+", "_")
    path = confined(root, f"_reports/{token}-{report.get('operation', 'update')}.json")
    save_json(path, report)
    save_json(confined(root, "_reports/latest.json"), report)
    return path


def run_update(root, operation, source_dir=None, refresh_images=False, minimum=200, client=None):
    root = Path(root).resolve()
    client = client or HttpCache(confined(root, "_update_cache"))
    current, previous, previous_source, records, source_records, aliases, report, opgg, wiki, file_info = inputs(
        root, client, source_dir, minimum)
    report["operation"] = operation
    moves = parse_moves(opgg)
    previous_moves = read_json(current / "moves.json") if (current / "moves.json").exists() else {}
    if previous_moves and not moves:
        raise ValueError("来源招式清单丢失，已保留旧资料包；请检查来源解析结构。")
    report["move_count"] = len(moves)
    report["moves_changed"] = digest(json_bytes(previous_moves)) != digest(json_bytes(moves))
    if operation == "sync" and report["large_removal"]:
        report["status"] = "blocked_large_removal"
        write_report(root, report)
        raise ValueError("来源条目减少超过 10%，已保留旧包；请核验完整性及退签名单后调整适配器。")
    identity_policy = read_json(CONFIG / "recognition_identity_groups.json")
    policy_changed = ((current / "recognition_identity_groups.json").exists()
                      and read_json(current / "recognition_identity_groups.json") != identity_policy)
    aliases_changed = ((current / "source_aliases.json").exists()
                       and read_json(current / "source_aliases.json") != aliases)
    report["schema_migration_required"] = previous.get("catalog_revision") != CATALOG_REVISION
    source_changed = digest(json_bytes(sorted(previous_source, key=lambda r: r["key"]))) != report["source_version"]
    report["image_source_changes"] = [r["name"] for r in records if any(
        r["images"].get(v, {}).get("source_url") != a["source_url"]
        for v, a in r.get("_desired_images", {}).items())]
    if operation == "sync":
        work = confined(root, f"_staging/assets-{uuid.uuid4().hex}")
        work.mkdir(parents=True)
        report["downloads"] = materialize_images(records, current, work, client, refresh_images)
        details = {k: report[k] for k in ("unmapped", "conflicts")}
        report.update(compare(previous, records, previous_source, source_records, details))
    changed = bool(report["added"] or report["changed"] or report["removed_candidate"] or source_changed
                   or policy_changed or aliases_changed or report["schema_migration_required"] or report["image_source_changes"]
                   or report["moves_changed"])
    report["has_changes"] = changed
    report["http"] = client.events
    if operation == "check":
        report["status"] = "changes_available" if changed else "up_to_date"
        write_report(root, report)
        return report
    if not changed:
        report["status"] = "up_to_date"
        export_compatibility_index(root)  # Repair the non-authoritative export after an interrupted run.
        write_report(root, report)
        discard_stage(root, work)
        return report
    for record in records:
        record.pop("_desired_images", None)
        record.pop("_expected_sprite", None)
    index = {"schema_version": 2, "catalog_revision": CATALOG_REVISION, "generated_at": now(), "battle_format": "double", "reference_season": None,
             "locale": "zh-Hans", "roster_source": OPGG_URL, "sprite_source": WIKI_URL,
             "source_version": report["source_version"], "source_regulations": report["source_regulations"],
             "base_stats_note": "物种／形态固有数值，不随单／双打改变；本包不包含模式使用率。",
             "availability_note": "来源收录与规则合法性分开；保留历史外观条目，不自动推断当前过签范围。",
             "species_count": len({r["dex_number"] for r in records}), "form_count": len(records),
             "image_count": sum(len(r["images"]) for r in records), "pokemon": records}
    validate_index(index, work)
    extra = {"source_catalog.json": json_bytes(source_records), "source_aliases.json": json_bytes(aliases), "moves.json": json_bytes(moves),
             "_sources/opgg.html": opgg, "_sources/wiki-roster.html": wiki,
             "_sources/wiki-file-info.json": json_bytes(file_info)}
    target = make_bundle(root, index, work, identity_policy, extra)
    discard_stage(root, work)
    # First migration snapshots the old flat catalog before changing the root index export.
    if not (root / "current.json").exists():
        baseline = make_bundle(root, previous, current, identity_policy)
        publish(root, baseline)
        report["baseline_bundle"] = baseline.name
    publish(root, target)
    report.update({"status": "published", "published_bundle": target.name, "validation": validate_bundle(target)})
    try:
        export_compatibility_index(root)
    except OSError as exc:
        report["compatibility_export_warning"] = str(exc)  # Published pointer is still valid.
    write_report(root, report)
    return report


def rollback(root, target_id=None):
    root = Path(root).resolve()
    pointer = read_json(root / "current.json")
    if target_id is None:
        if not pointer.get("history"):
            raise ValueError("没有可回滚的历史版本")
        target_id = pointer["history"][-1]
    target = confined(root, f"_versions/{target_id}")
    publish(root, target)
    export_compatibility_index(root)
    report = {"operation": "rollback", "checked_at": now(), "status": "rolled_back", "published_bundle": target.name,
              "validation": validate_bundle(target)}
    write_report(root, report)
    return report

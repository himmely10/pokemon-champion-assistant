"""Conservative cross-site identity mapping and explainable catalog differences."""
from __future__ import annotations

import copy
import re
from collections import defaultdict

from .sources import OPGG_URL, STAT_MAP
from .storage import TYPE_NAMES, confined, digest, json_bytes


def legacy_slug(raw, aliases):
    key = raw["key"]
    if key in aliases["opgg_to_legacy_slug"]:
        return aliases["opgg_to_legacy_slug"][key]
    if key.startswith("mega-"):
        base = raw.get("base_key")
        if not base or key not in [f"mega-{base}" + tail for tail in ("", "-x", "-y", "-z")]:
            return None
        return base + "-mega" + key[len("mega-" + base):]
    return key.replace("-alolan", "-alola").replace("-galarian", "-galar").replace("-paldean", "-paldea")


def simplified_name(name):
    return re.sub(r"\s*\(", "（", name).replace(")", "）").translate(str.maketrans("ＸＹＺ", "XYZ"))


def species_identity(raw, by_key, legacy, aliases):
    """Use established mapping, declared parent or an unambiguous base record."""
    slug = legacy_slug(raw, aliases)
    if legacy.get(slug):
        values = {(r["dex_number"], r["species_name"]) for r in legacy[slug]}
        if len(values) == 1:
            return next(iter(values))
    parent = raw.get("base_key") or aliases["species_roots"].get(raw["key"])
    if parent:
        if parent not in by_key or parent == raw["key"]:
            return None
        return species_identity(by_key[parent], by_key, legacy, aliases)
    if raw["id"] < 10000:
        return raw["id"], simplified_name(raw["name"]).split("（")[0]
    for suffix in ("-alolan", "-galarian", "-hisui", "-female"):
        if raw["key"].endswith(suffix) and raw["key"][:-len(suffix)] in by_key:
            base = by_key[raw["key"][:-len(suffix)]]
            if base["id"] < 10000:
                return species_identity(base, by_key, legacy, aliases)
    return None


def source_fields(raw):
    return {"opgg_key": raw["key"], "opgg_id": raw["id"],
            "aliases": [raw["name"]], "types": list(raw["types"]),
            "type_names": [TYPE_NAMES[t] for t in raw["types"]],
            "base_stats": {STAT_MAP[k]: v for k, v in raw["stats"].items()},
            "base_stat_total": sum(raw["stats"].values()),
            "source_regulation": raw["regulation"], "source_is_new": raw.get("isNew", False),
            "availability": "source_listed_unverified_rules", "source_presence": "present",
            "stats_source": {"provider": "opgg", "url": OPGG_URL + "/" + raw["key"],
                             "raw_path": "_sources/opgg.html", "field": "pokemon.stats"},
            "types_source": {"provider": "opgg", "url": OPGG_URL + "/" + raw["key"],
                             "field": "pokemon.types"},
            "source_base_key": raw.get("base_key"), "mega_item": raw.get("item")}


def sprite_filename(raw, dex, slug):
    """Only established filename conventions; unknown form codes remain pending."""
    if "-mega" in slug:
        code = {"mega": "M", "mega-x": "MX", "mega-y": "MY", "mega-z": "MZ"}.get("mega" + slug.split("-mega", 1)[1])
        if code:
            return f"Champions_{dex:04d}{code}_Sprite.png"
    for suffix, code in [("-alola", "A"), ("-galar", "G"), ("-hisui", "H")]:
        if slug.endswith(suffix):
            return f"Champions_{dex:04d}{code}_Sprite.png"
    if raw["key"].endswith("-female"):
        return f"Champions_{dex:04d}F_Sprite.png"
    # The ordinary base record only; never infer arbitrary special-form codes.
    if raw["id"] == dex and not raw["key"].endswith("-female"):
        return f"Champions_{dex:04d}_Sprite.png"
    return None


def build_catalog(previous, source_records, wiki_entries, aliases):
    records = copy.deepcopy(previous["pokemon"])
    legacy, by_opgg = defaultdict(list), defaultdict(list)
    for record in records:
        legacy[record["source_slug"]].append(record)
        if record.get("opgg_key"):
            by_opgg[record["opgg_key"]].append(record)
        record["source_presence"] = "not_listed_or_unmapped"
        record["availability"] = "unverified"
        record["record_id"] = record.get("record_id", f"legacy:{record['dex_number']}:{record['directory']}")
    by_key = {r["key"]: r for r in source_records}
    wiki_images = {e["images"]["normal"]["source_filename"]: e for e in wiki_entries}
    unmapped, conflicts = [], []
    claimed = set()
    for raw in source_records:
        key, slug = raw["key"], legacy_slug(raw, aliases)
        candidates = by_opgg.get(key, []) or list(legacy.get(slug, []))
        if key in aliases["legacy_names"]:
            allowed = aliases["legacy_names"][key]
            candidates = [r for r in candidates if r["name"] in allowed]
        if len(candidates) > 1 and key not in aliases["legacy_names"] and slug not in aliases["shared_profile_slugs"]:
            unmapped.append({"key": key, "name": raw["name"], "reason": "ambiguous_legacy_form"})
            continue
        identity = species_identity(raw, by_key, legacy, aliases)
        if not slug or not identity:
            unmapped.append({"key": key, "name": raw["name"], "reason": "unknown_species_or_form_mapping"})
            continue
        dex, species = identity
        if not candidates:
            name = simplified_name(raw["name"])
            if key.startswith("mega-"):
                name = "超级" + species + {"-x": "X", "-y": "Y", "-z": "Z"}.get(key[-2:], "")
            for region, label in [("-alola", "阿罗拉"), ("-galar", "伽勒尔"), ("-hisui", "洗翠")]:
                if slug.endswith(region):
                    name = species + f"（{label}）"
            if any(r["name"] == name for r in records):
                unmapped.append({"key": key, "name": name, "reason": "name_collision"})
                continue
            confined(".", name)  # Reject path-bearing source names before constructing files.
            record = {"schema_version": 2, "record_id": f"opgg:{key}", "dex_number": dex,
                      "name": name, "species_name": species, "form_name": None if name == species else name,
                      "directory": name, "source_slug": slug, "images": {},
                      "name_source": "opgg_zh_cn", "stats_mapping": "exact_form"}
            records.append(record)
            candidates = [record]
        for record in candidates:
            if record["record_id"] in claimed:
                raise ValueError(f"两个来源条目映射到同一形态：{record['name']}")
            claimed.add(record["record_id"])
            new_stats = {STAT_MAP[k]: v for k, v in raw["stats"].items()}
            if record.get("base_stats") and record["base_stats"] != new_stats:
                conflicts.append({"name": record["name"], "field": "base_stats", "old": record["base_stats"],
                                  "new": new_stats, "resolution": "opgg_preferred_previous_bundle_retained"})
            aliases_old = record.get("aliases", [])
            if record.get("mapping_note"):
                record["legacy_mapping_note"] = record.pop("mapping_note")
            record.update(source_fields(raw))
            record["stats_mapping"] = "shared_source_profile" if len(candidates) > 1 else "exact_form"
            record["aliases"] = sorted(set(aliases_old + record["aliases"]))
            normal = record["images"].get("normal", {})
            filename = normal.get("source_filename") or sprite_filename(raw, dex, slug)
            record["_expected_sprite"] = filename
            row = wiki_images.get(filename)
            if row and row["dex_number"] == dex:
                # Download intent is transient; actual assets are validated separately.
                record["_desired_images"] = row["images"]
    for record in records:
        # Existing images still get source-URL updates even if the data site omits this visual form.
        normal = record["images"].get("normal", {})
        row = wiki_images.get(normal.get("source_filename"))
        if row and row["dex_number"] == record["dex_number"]:
            record.setdefault("_desired_images", row["images"])
        record["recognition_ready"] = set(record["images"]) == {"normal", "shiny"}
        record["data_ready"] = bool(record.get("base_stats"))
        record["types_ready"] = bool(record.get("types"))
    # Store references rather than silently turning a base form into its Mega.
    mega_by_base = defaultdict(list)
    for record in records:
        if record.get("source_base_key") and record.get("opgg_key", "").startswith("mega-"):
            mega_by_base[record["source_base_key"]].append(record["record_id"])
    for record in records:
        record["mega_form_ids"] = sorted(mega_by_base.get(record.get("opgg_key"), []))
    return records, {"unmapped": unmapped, "conflicts": conflicts}


def meaningful(record):
    """Exclude request times, source badges and transient download intentions from diffs."""
    fields = ("name", "species_name", "source_slug", "base_stats", "types", "aliases", "opgg_key",
              "source_presence", "source_regulation", "mega_form_ids", "recognition_ready", "types_ready")
    value = {k: record.get(k) for k in fields}
    value["images"] = {k: {f: a.get(f) for f in ("source_url", "sha256")} for k, a in record["images"].items()}
    return value


def compare(previous, records, previous_source, source_records, details):
    old = {r["directory"]: r for r in previous["pokemon"]}
    added = [r for r in records if r["directory"] not in old]
    changed = []
    for record in records:
        before = old.get(record["directory"])
        if before and meaningful(before) != meaningful(record):
            a, b = meaningful(before), meaningful(record)
            changed.append({"name": record["name"], "fields": sorted(k for k in a if a[k] != b[k])})
    previous_keys = {r["key"] for r in previous_source}
    current_keys = {r["key"] for r in source_records}
    removed = sorted(previous_keys - current_keys)
    old_dex = {r["dex_number"] for r in previous["pokemon"]}
    species = {r["dex_number"]: r["species_name"] for r in added if r["dex_number"] not in old_dex}
    return {**details, "source_count": len(source_records), "source_is_new_count": sum(bool(r.get("isNew")) for r in source_records),
            "source_version": digest(json_bytes(sorted(source_records, key=lambda r: r["key"]))),
            "source_regulations": sorted({r["regulation"] for r in source_records}),
            "added": [{"name": r["name"], "dex_number": r["dex_number"], "opgg_key": r.get("opgg_key")} for r in added],
            "new_species": [{"dex_number": k, "name": v} for k, v in sorted(species.items())],
            "changed": changed, "removed_candidate": removed,
            "missing_source": [r["name"] for r in records if r.get("source_presence") != "present"],
            "pending_assets": [r["name"] for r in records if not r["recognition_ready"]],
            "download_available": [r["name"] for r in records if not r["recognition_ready"] and r.get("_desired_images")],
            "large_removal": bool(previous_keys and len(removed) / len(previous_keys) > .1),
            "note": "来源规则标签不等于当前赛季合法性；未列出的历史条目保留，不自动退签或删除。"}

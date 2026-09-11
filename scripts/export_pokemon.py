"""Build the simplified-Chinese per-form dataset from the downloaded sources.

No network requests. Fails on unmapped forms, missing sources, or image conflicts.
The two 52Poke supplements were explicitly authorized by the user.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import json5
from bs4 import BeautifulSoup
from PIL import Image

from collect_pokemon import ROOT, SOURCES, DB_URL, WIKI_URL, detail_props, save_json

STAT_KEYS = {"hp": "hp", "atk": "attack", "def": "defense", "spAtk": "special_attack",
             "spDef": "special_defense", "speed": "speed"}
SPECIAL_FORMS = {
    (128, "PA"): "tauros-paldea-aqua", (128, "PB"): "tauros-paldea-blaze",
    (128, "PC"): "tauros-paldea-combat",
    (479, "F"): "rotom-frost", (479, "Fa"): "rotom-fan", (479, "H"): "rotom-heat",
    (479, "M"): "rotom-mow", (479, "W"): "rotom-wash",
    (670, "E"): "floette", (678, "F"): "meowstic-female", (681, "B"): "aegislash-blade",
    (711, "J"): "gourgeist-super", (711, "L"): "gourgeist-large", (711, "S"): "gourgeist-small",
    (745, "Mn"): "lycanroc-midnight", (745, "D"): "lycanroc-dusk",
    (902, "F"): "basculegion-female", (964, "H"): "palafin-hero",
}
# These forms use a species-level source profile, rather than a separate site record.
# Explicit allowlist: never infer equal stats for arbitrary unseen forms.
SHARED_PROFILE_DEX = {351, 666, 668, 671, 676, 855, 869, 877, 925, 1013}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def extract_names():
    bundle = SOURCES / "534-ec63c932371f2141.js"
    text = bundle.read_text(encoding="utf-8")
    pivot = text.index('garchomp:"烈咬陆鲨"')
    names = json5.loads(text[text.rfind("{", 0, pivot):text.index("}", pivot) + 1])
    assert names["venusaur"] == "妙蛙花" and len(names) > 200
    save_json(SOURCES / "names-zh-Hans.json", names)
    return names


def build_catalog():
    catalog, primary = {}, defaultdict(list)
    for path in sorted((SOURCES / "details").glob("*.html")):
        props = detail_props(path.read_bytes())
        dex = props["initialDetail"]["dexNo"]
        slug = props["slug"]
        primary[dex].append(slug)
        records = [(props["profile"], "profile.baseStats")]
        for group in ("megaForms", "alternateForms"):
            records.extend((record, f"{group}[{i}].baseStats") for i, record in enumerate(props[group]))
        for record, field in records:
            value = {"dex_number": dex, "stats": record["baseStats"],
                     "provider": "pokechamdb", "page_slug": slug, "field": field,
                     "url": f"https://pokechamdb.com/zh-Hans/pokemon/{slug}?format=double&season=M-5",
                     "raw_path": path.relative_to(ROOT).as_posix()}
            key = record["slug"]
            if key in catalog:
                assert catalog[key]["stats"] == value["stats"], key
            catalog[key] = value
    roots = {}
    for dex, slugs in primary.items():
        candidates = [s for s in slugs if all(other == s or other.startswith(s + "-") for other in slugs)]
        assert len(candidates) == 1, (dex, slugs)
        roots[dex] = candidates[0]
    return catalog, roots


def wiki_supplements(catalog, roots):
    for dex, slug, chinese in [(681, "aegislash-blade", "坚盾剑怪"), (923, "pawmot", "巴布土拨")]:
        path = SOURCES / f"wiki-{dex}-main.html"
        soup = BeautifulSoup(path.read_bytes(), "html.parser")
        if dex == 681:
            label = soup.select_one(".toggle-p-2base").get_text(strip=True)
            assert label == "刀剑形态（第八世代起）", label
            table = soup.select_one("div.toggle-2base table")
            field = "种族值 / 刀剑形态（第八世代起）"
        else:
            table = soup.find(id="种族值").find_next("table")
            field = "种族值"
        labels = {"ＨＰ": "hp", "攻击": "atk", "防御": "def", "特攻": "spAtk", "特防": "spDef", "速度": "speed"}
        stats = {}
        for tr in table.select("tr"):
            th = tr.find("th")
            if th is None:
                continue
            match = re.fullmatch(r"(ＨＰ|攻击|防御|特攻|特防|速度)\s*：\s*(\d+)", th.get_text(" ", strip=True))
            if match:
                stats[labels[match[1]]] = int(match[2])
        assert set(stats) == set(STAT_KEYS), stats
        total = int(re.search(r"总和：\s*(\d+)", table.get_text(" ", strip=True))[1])
        assert total == sum(stats.values())
        catalog[slug] = {"dex_number": dex, "stats": stats, "provider": "52poke",
                         "page_slug": slug, "field": field,
                         "url": f"https://wiki.52poke.com/zh-hans/{chinese}#种族值",
                         "raw_path": path.relative_to(ROOT).as_posix()}
        if dex == 923:
            roots[dex] = slug


def select_profile(entry, roots):
    dex = entry["dex_number"]
    base = roots[dex]
    code = re.fullmatch(r"Champions_\d{4}(.*?)_Sprite.png", entry["images"]["normal"]["source_filename"])[1]
    form = (entry["form_name"] or "").strip("（）()")
    if form.startswith("超级"):
        suffix = {"M": "mega", "MX": "mega-x", "MY": "mega-y", "MZ": "mega-z"}[code]
        return base + "-" + suffix, "exact_form", form
    if (dex, code) in SPECIAL_FORMS:
        return SPECIAL_FORMS[dex, code], "exact_form", form
    if any(region in form for region in ["阿罗拉", "伽勒尔", "洗翠"]):
        return base + "-" + {"A": "alola", "G": "galar", "H": "hisui"}[code], "exact_form", form
    if dex in SHARED_PROFILE_DEX:
        return base, "shared_species_profile", form
    assert code == "", f"Unmapped form: {entry['name']} / {code}"
    return base, "exact_form", form


def display_name(entry, slug, base, names, form):
    species = names.get(base)
    if base == "pawmot":
        species = "巴布土拨"
    assert species, base
    if form.startswith("超级"):
        postfix = {"mega-x": "X", "mega-y": "Y", "mega-z": "Z"}.get(slug.split("-", 1)[1], "")
        return species, "超级" + species + postfix
    if slug == "floette":
        return species, names["floette-eternal"]
    variant = names.get(slug, species)
    if variant != species:
        return species, variant
    return species, species + (f"（{form}）" if form else "")


def export():
    if (ROOT / "current.json").exists():
        raise SystemExit("目录已启用版本管理；请使用 scripts/update_pokemon_data.py sync，不能用旧导出器覆盖。")
    names = extract_names()
    catalog, roots = build_catalog()
    wiki_supplements(catalog, roots)
    save_json(SOURCES / "stats-catalog.json", catalog)
    roster = read_json(SOURCES / "roster.json")
    previous = read_json(ROOT / "index.json") if (ROOT / "index.json").exists() else {}
    previous_dirs = {r["wiki_name"]: r["directory"] for r in previous.get("pokemon", [])}
    records, seen, moved_from = [], set(), set()
    for entry in roster:
        slug, mapping, form = select_profile(entry, roots)
        source = catalog[slug]
        assert source["dex_number"] == entry["dex_number"]
        species, name = display_name(entry, slug, roots[entry["dex_number"]], names, form)
        assert name not in seen and not re.search(r'[<>:"/\\|?*]', name), name
        seen.add(name)
        raw_stats = source["stats"]
        assert set(raw_stats) == set(STAT_KEYS)
        assert all(isinstance(v, int) and 0 < v <= 255 for v in raw_stats.values())
        stats = {STAT_KEYS[k]: raw_stats[k] for k in STAT_KEYS}
        record = {"schema_version": 1, "dex_number": entry["dex_number"], "name": name,
                  "species_name": species, "form_name": form or None, "wiki_name": entry["name"],
                  "directory": name, "source_slug": slug, "base_stats": stats,
                  "base_stat_total": sum(stats.values()), "images": {},
                  "stats_source": {k: source[k] for k in ["provider", "url", "raw_path", "field"]},
                  "name_source": "52poke_zh_hans" if slug == "pawmot" else "pokechamdb_zh_hans",
                  "form_label_source": "52poke_zh_hans", "stats_mapping": mapping}
        if mapping == "shared_species_profile":
            record["mapping_note"] = "此形态与同种其他外观/花纹形态共用种族值；数据站仅提供种级配置，未逐外观独立列值。"
        if source["provider"] == "52poke":
            record["mapping_note"] = "PokéChamp DB 未提供该条目；经用户允许，使用百科种族值补齐。"
        for variant, asset in entry["images"].items():
            suffix = "_闪光" if variant == "shiny" else ""
            target = ROOT / name / f"{name}{suffix}.png"
            old = ROOT / asset["path"]
            if not old.exists() and entry["name"] in previous_dirs:
                old_name = previous_dirs[entry["name"]]
                old = ROOT / old_name / f"{old_name}{suffix}.png"
            content = old.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            assert digest == asset["sha256"], old
            with Image.open(old) as image:
                width, height = image.size
                assert image.format == "PNG"
                image.verify()
            if old != target:
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    assert target.read_bytes() == content, f"Conflicting existing image: {target}"
                    old.unlink()
                else:
                    # All source and destination paths must stay within the data root.
                    assert old.resolve().is_relative_to(ROOT.resolve()) and target.resolve().is_relative_to(ROOT.resolve())
                    old.rename(target)
                moved_from.add(old.parent)
            record["images"][variant] = {"file": target.name, "source_url": asset["source_url"],
                                         "source_filename": asset["source_filename"], "sha256": digest,
                                         "width": width, "height": height, "bytes": len(content)}
        save_json(ROOT / name / f"{name}.json", record)
        records.append(record)
    for directory in moved_from:
        if directory.exists() and not any(directory.iterdir()):
            directory.rmdir()
    index = {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
             "battle_format": "double", "reference_season": "M-5", "locale": "zh-Hans",
             "roster_source": WIKI_URL, "preferred_data_source": DB_URL,
             "base_stats_note": "种族值为物种/形态固有数值，不随单打、双打或闪光变化，不是实战速度。",
             "species_count": len({r["dex_number"] for r in records}), "form_count": len(records),
             "image_count": 2 * len(records), "pokemon": records}
    save_json(ROOT / "index.json", index)
    save_json(SOURCES / "final-image-paths.json", {r["wiki_name"]: r["directory"] for r in records})
    report = {"validated_at": index["generated_at"], "species_count": index["species_count"],
              "form_count": len(records), "png_count": sum(len(list((ROOT/r['directory']).glob('*.png'))) for r in records),
              "metadata_count": len(records), "stats_sources": dict(Counter(r["stats_source"]["provider"] for r in records)),
              "stats_mapping": dict(Counter(r["stats_mapping"] for r in records)),
              "image_sizes": dict(Counter(f"{a['width']}x{a['height']}" for r in records for a in r['images'].values())),
              "unique_image_urls": len({a["source_url"] for r in records for a in r["images"].values()}),
              "missing_images": [], "missing_stats": [], "duplicate_names": []}
    assert report["png_count"] == len(records) * 2
    save_json(ROOT / "validation.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    export()

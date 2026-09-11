"""Collect the requested public Champions sprites and source pages; resumable.

Run from any directory: python -X utf8 scripts/collect_pokemon.py
Dependencies: requests, beautifulsoup4, Pillow (already available locally).
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urljoin

import requests
from bs4 import BeautifulSoup
from PIL import Image

ROOT = Path(__file__).resolve().parents[1] / "pokemon"
SOURCES = ROOT / "_sources"
WIKI_URL = "https://wiki.52poke.com/zh-hant/宝可梦列表（Champions）"
WIKI_HANS_URL = "https://wiki.52poke.com/zh-hans/宝可梦列表（Champions）"
DB_URL = "https://pokechamdb.com/zh-Hans?format=double&season=M-5&view=pokemon"
LOCAL = threading.local()


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def fetch(url, path, png=False):
    if path.exists():
        content = path.read_bytes()
        if not png:
            return content
        try:
            with Image.open(io.BytesIO(content)) as im:
                im.verify()
            return content
        except Exception:
            pass
    if not hasattr(LOCAL, "session"):
        LOCAL.session = requests.Session()
        LOCAL.session.headers.update({"User-Agent": "PokemonChampionAssistant-DataCollector/0.1 (local research; limited concurrency)"})
    for attempt in range(4):
        try:
            response = LOCAL.session.get(url, timeout=(20, 60))
            response.raise_for_status()
            content = response.content
            if png:
                with Image.open(io.BytesIO(content)) as im:
                    assert im.format == "PNG", f"Unexpected image type: {im.format}"
                    im.verify()
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_suffix(path.suffix + ".tmp")
            temp.write_bytes(content)
            temp.replace(path)
            time.sleep(0.15)
            return content
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 ** (attempt + 1))


def parse_roster():
    soup = BeautifulSoup(fetch(WIKI_HANS_URL, SOURCES / "wiki-hans.html"), "html.parser")
    table = next(t for t in soup.select("table") if "Champions_0003_Sprite.png" in str(t))
    entries = []
    for tr in table.select("tr"):
        cells = tr.find_all("td", recursive=False)
        if not cells or not re.fullmatch(r"#\d{4}", cells[0].get_text(strip=True)):
            continue
        name = cells[3].find("a").get_text(strip=True)
        small = cells[3].find("small")
        form = small.get_text("", strip=True) if small else None
        name = name.translate(str.maketrans("ＸＹＺ", "XYZ"))
        form = form.translate(str.maketrans("ＸＹＺ", "XYZ")) if form else None
        display = (form if form.startswith("超级") else f"{name}（{form}）") if form else name
        assert not re.search(r'[<>:"/\\|?*]', display), display
        images = {}
        for column, variant, suffix in [(1, "normal", ""), (2, "shiny", "_闪光")]:
            img = cells[column].find("img")
            srcset = img.get("data-loginonly-srcset") or img.get("srcset")
            url = srcset.split(",")[-1].strip().split()[0] if srcset else img["src"]
            url = urljoin(WIKI_URL, url)
            filename = unquote(url.rsplit("/", 1)[-1])
            assert filename.startswith("Champions_") and filename.endswith(".png"), url
            images[variant] = {"source_url": url, "source_filename": filename,
                               "path": f"{display}/{display}{suffix}.png"}
        entries.append({"dex_number": int(cells[0].get_text(strip=True)[1:]),
                        "species_name": name, "form_name": form, "name": display,
                        "directory": display, "wiki_page": urljoin(WIKI_URL, cells[3].find("a")["href"]),
                        "images": images})
    assert entries and len({e["directory"] for e in entries}) == len(entries), "Duplicate/empty roster"
    # Reuse final Chinese paths on subsequent runs after export/renaming.
    path_map_file = SOURCES / "final-image-paths.json"
    if path_map_file.exists():
        path_map = json.loads(path_map_file.read_text(encoding="utf-8"))
        for entry in entries:
            if entry["name"] in path_map:
                final = path_map[entry["name"]]
                for variant, asset in entry["images"].items():
                    suffix = "_闪光" if variant == "shiny" else ""
                    asset["path"] = f"{final}/{final}{suffix}.png"
    return entries


def download_images(entries):
    jobs = {}
    for entry in entries:
        for asset in entry["images"].values():
            jobs.setdefault(asset["source_url"], []).append(asset)
    failures = []

    def work(url, assets):
        content = fetch(url, ROOT / assets[0]["path"], png=True)
        with Image.open(io.BytesIO(content)) as im:
            width, height = im.size
        digest = hashlib.sha256(content).hexdigest()
        for asset in assets:
            target = ROOT / asset["path"]
            if not target.exists() or target.read_bytes() != content:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            asset.update({"sha256": digest, "width": width, "height": height, "bytes": len(content)})

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(work, url, assets): url for url, assets in jobs.items()}
        for count, future in enumerate(as_completed(futures), 1):
            try:
                future.result()
            except Exception as exc:
                failures.append({"url": futures[future], "error": str(exc)})
            if count % 40 == 0 or count == len(jobs):
                print(f"Images: {count}/{len(jobs)} unique URLs; errors={len(failures)}", flush=True)
    return failures


def download_details():
    soup = BeautifulSoup(fetch(DB_URL, SOURCES / "pokechamdb.html"), "html.parser")
    paths = sorted({a["href"].split("?")[0] for a in soup.select("a[href]") if "/zh-Hans/pokemon/" in a["href"]})
    assert paths, "No source detail links"
    failures = []

    def work(path):
        slug = path.rsplit("/", 1)[-1]
        url = urljoin(DB_URL, path) + "?format=double&season=M-5"
        content = fetch(url, SOURCES / "details" / f"{slug}.html")
        props = detail_props(content)
        assert props.get("profile", {}).get("baseStats"), f"No base stats: {slug}"

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(work, path): path for path in paths}
        for count, future in enumerate(as_completed(futures), 1):
            try:
                future.result()
            except Exception as exc:
                failures.append({"path": futures[future], "error": str(exc)})
            if count % 30 == 0 or count == len(paths):
                print(f"Detail pages: {count}/{len(paths)}; errors={len(failures)}", flush=True)
    return failures


def detail_props(content):
    soup = BeautifulSoup(content, "html.parser")
    payload = ""
    for script in soup.select("script"):
        text = script.string or ""
        if text.startswith("self.__next_f.push("):
            args = json.loads(text[len("self.__next_f.push("):].rstrip(";\n ")[:-1])
            if args[0] == 1 and isinstance(args[1], str):
                payload += args[1]
    for line in payload.splitlines():
        if ":" not in line:
            continue
        raw = line.split(":", 1)[1]
        if not raw.startswith("["):
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if len(obj) == 4 and isinstance(obj[3], dict) and "profile" in obj[3]:
            return obj[3]
    raise ValueError("No detail props in source page")


def main():
    if (ROOT / "current.json").exists():
        raise SystemExit("目录已启用版本管理；请使用 scripts/update_pokemon_data.py sync。此旧脚本仅保留为历史采集工具。")
    SOURCES.mkdir(parents=True, exist_ok=True)
    entries = parse_roster()
    save_json(SOURCES / "roster.json", entries)
    print(f"Roster: {len(entries)} forms / {len({e['dex_number'] for e in entries})} species", flush=True)
    with ThreadPoolExecutor(max_workers=2) as executor:
        images = executor.submit(download_images, entries)
        details = executor.submit(download_details)
        errors = {"images": images.result(), "details": details.result()}
    save_json(SOURCES / "roster.json", entries)
    save_json(SOURCES / "collection-report.json", {"collected_at": datetime.now(timezone.utc).isoformat(),
              "roster_count": len(entries), "errors": errors})
    if any(errors.values()):
        raise SystemExit("Some downloads failed; inspect collection-report.json and rerun to resume")


if __name__ == "__main__":
    main()

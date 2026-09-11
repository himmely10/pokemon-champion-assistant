"""Read public HTML as data. No JavaScript execution or private API assumptions."""
from __future__ import annotations

import io
import json
import re
import time
from pathlib import Path
from urllib.parse import unquote, urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from PIL import Image

from .storage import TYPE_NAMES, atomic_bytes, confined, digest, now, read_json, save_json

OPGG_URL = "https://op.gg/zh-cn/pokemon-champions/pokedex"
WIKI_URL = "https://wiki.52poke.com/zh-hans/宝可梦列表（Champions）"
STAT_MAP = {"hp": "hp", "attack": "attack", "defense": "defense", "spAttack": "special_attack",
            "spDefense": "special_defense", "speed": "speed"}


class HttpCache:
    def __init__(self, root, session=None, sleep=time.sleep):
        self.root = Path(root)
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": "PokemonChampionAssistant/0.2 (personal offline catalog; bounded requests)"})
        self.sleep = sleep
        self.events = []

    def get(self, url, *, immutable=False, png=False):
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in {"op.gg", "s-stats-platform-cdn.op.gg", "wiki.52poke.com", "media.52poke.com"}:
            raise ValueError(f"不支持的资料来源：{url}")
        key = digest(url.encode("utf-8"))
        meta_path = confined(self.root, f"requests/{key}.json")
        meta = read_json(meta_path) if meta_path.exists() else {}
        cached = None
        if meta.get("sha256"):
            path = confined(self.root, f"blobs/{meta['sha256']}")
            if path.exists() and digest(path.read_bytes()) == meta["sha256"]:
                cached = path.read_bytes()
        if immutable and cached is not None:
            self.events.append({"url": url, "status": "reused", "sha256": meta["sha256"]})
            return cached
        headers = {}
        if cached is not None:
            if meta.get("etag"):
                headers["If-None-Match"] = meta["etag"]
            if meta.get("last_modified"):
                headers["If-Modified-Since"] = meta["last_modified"]
        for attempt in range(3):
            try:
                # Redirects are checked explicitly; remote pages cannot redirect us to arbitrary hosts.
                response = self.session.get(url, headers=headers, timeout=(10, 25), allow_redirects=False)
                if response.status_code == 429 or 500 <= response.status_code < 600:
                    if attempt == 2:
                        response.raise_for_status()
                    retry = response.headers.get("Retry-After", "")
                    # Never retry earlier than a long server cooldown: stop this batch instead.
                    if retry and (not retry.isdigit() or int(retry) > 30):
                        raise ValueError(f"来源要求稍后重试（{retry}）：{url}")
                    self.sleep(max(2 ** attempt, int(retry or "0")))
                    continue
                if response.status_code == 304:
                    if cached is None:
                        raise ValueError("来源返回 304，但本地没有可用响应缓存")
                    content = cached
                else:
                    if 300 <= response.status_code < 400:
                        raise ValueError(f"来源地址已跳转，请核验适配器：{url}")
                    response.raise_for_status()
                    content = response.content
                limit = 2_000_000 if png else 30_000_000
                if not content or len(content) > limit:
                    raise ValueError(f"来源内容为空或超出大小限制：{url}")
                if png:
                    verify_sprite(content)
                checksum = digest(content)
                atomic_bytes(confined(self.root, f"blobs/{checksum}"), content)
                save_json(meta_path, {"url": url, "sha256": checksum, "checked_at": now(),
                          "etag": response.headers.get("ETag", meta.get("etag")),
                          "last_modified": response.headers.get("Last-Modified", meta.get("last_modified"))})
                self.events.append({"url": url, "status": response.status_code, "sha256": checksum})
                return content
            except (requests.Timeout, requests.ConnectionError):
                if attempt == 2:
                    raise
                self.sleep(2 ** attempt)
        raise ValueError(f"来源请求失败：{url}")


def verify_sprite(content):
    with Image.open(io.BytesIO(content)) as image:
        if image.format != "PNG" or image.size != (128, 128) or "A" not in image.getbands():
            raise ValueError("图标需要 128x128 带透明通道的 Champions PNG")
        image.verify()


def next_objects(content):
    soup = BeautifulSoup(content, "html.parser")
    payload = []
    for script in soup.select("script"):
        text = (script.string or "").strip()
        prefix = "self.__next_f.push("
        if text.startswith(prefix):
            try:
                args, _ = json.JSONDecoder().raw_decode(text[len(prefix):])
            except json.JSONDecodeError as exc:
                raise ValueError("OP.GG 内嵌数据格式已变化") from exc
            if isinstance(args, list) and len(args) > 1 and args[0] == 1 and isinstance(args[1], str):
                payload.append(args[1])
    for line in "".join(payload).splitlines():
        if ":" not in line:
            continue
        try:
            yield json.loads(line.split(":", 1)[1])
        except json.JSONDecodeError:
            continue  # RSC also carries module references and non-JSON text frames.


def dictionaries(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from dictionaries(child)
    elif isinstance(value, list):
        for child in value:
            yield from dictionaries(child)


def parse_opgg(content, minimum=200):
    candidates = []
    for obj in next_objects(content):
        for props in dictionaries(obj):
            rows = props.get("pokemon")
            if isinstance(rows, list) and rows and isinstance(rows[0], dict) and "stats" in rows[0]:
                candidates.append(rows)
    if len(candidates) != 1 or len(candidates[0]) < minimum:
        raise ValueError("未取得 OP.GG 完整图鉴数据（页面变化、截断或返回了分页／错误页面）")
    records, seen = [], set()
    for raw in candidates[0]:
        key = raw.get("key")
        if not isinstance(key, str) or not re.fullmatch(r"[a-z0-9.-]+", key) or key in seen:
            raise ValueError(f"重复或非法 OP.GG 身份：{key}")
        if type(raw.get("id")) is not int or raw["id"] <= 0:
            raise ValueError(f"非法来源 ID：{key}")
        if not isinstance(raw.get("name"), str) or not re.search(r"[\u3400-\u9fff]", raw["name"]):
            raise ValueError(f"未取得简体中文名称：{key}")
        stats = raw.get("stats", {})
        if set(stats) != set(STAT_MAP) or any(type(v) is not int or not 0 < v <= 255 for v in stats.values()):
            raise ValueError(f"种族值缺失／非法：{key}")
        types = raw.get("types")
        if not isinstance(types, list) or not 1 <= len(types) <= 2 or any(t not in TYPE_NAMES for t in types):
            raise ValueError(f"属性缺失／非法：{key}")
        if raw.get("base_key") is not None and not isinstance(raw["base_key"], str):
            raise ValueError(f"非法基础形态关联：{key}")
        if not isinstance(raw.get("regulation"), str) or not raw["regulation"]:
            raise ValueError(f"缺少来源规则标签：{key}")
        seen.add(key)
        records.append(raw)
    if any(r.get("base_key") and r["base_key"] not in seen for r in records):
        raise ValueError("图鉴包含缺失的基础形态，拒绝不完整清单")
    return records


def parse_wiki(content):
    soup = BeautifulSoup(content, "html.parser")
    tables = [t for t in soup.select("table") if "Champions_0003_Sprite.png" in str(t)]
    if len(tables) != 1:
        raise ValueError("百科 Champions 图标表结构已变化")
    entries, seen = [], set()
    for tr in tables[0].select("tr"):
        cells = tr.find_all("td", recursive=False)
        if not cells or not re.fullmatch(r"#\d{4}", cells[0].get_text(strip=True)):
            continue
        if len(cells) < 4:
            raise ValueError("百科图标行不完整")
        assets = {}
        for column, variant in [(1, "normal"), (2, "shiny")]:
            img = cells[column].find("img")
            if not img:
                raise ValueError("百科图标行缺少图片")
            srcset = img.get("data-loginonly-srcset") or img.get("srcset")
            src = srcset.split(",")[-1].strip().split()[0] if srcset else img.get("src", "")
            url = urljoin(WIKI_URL, src)
            filename = unquote(urlparse(url).path.rsplit("/", 1)[-1])
            if not re.fullmatch(r"Champions_\d{4}[A-Za-z0-9_]*_Sprite\.png", filename):
                raise ValueError(f"非 Champions 图标：{filename}")
            if urlparse(url).hostname != "media.52poke.com":
                raise ValueError("百科图片来源域名已变化")
            assets[variant] = {"source_url": url, "source_filename": filename}
        key = assets["normal"]["source_filename"]
        dex = int(cells[0].get_text(strip=True)[1:])
        if (not key.startswith(f"Champions_{dex:04d}") or key.endswith("_s_Sprite.png")
                or assets["shiny"]["source_filename"] != key.replace("_Sprite.png", "_s_Sprite.png")):
            raise ValueError("百科普通／闪光图标与物种形态不对应")
        if key in seen:
            # Several cosmetic records legitimately share an identical image.
            existing = next(e for e in entries if e["images"]["normal"]["source_filename"] == key)
            if existing["images"] != assets:
                raise ValueError("同名图标对应不同来源")
            continue
        seen.add(key)
        entries.append({"dex_number": dex, "images": assets})
    if not entries:
        raise ValueError("百科图标清单为空")
    return entries


def discover_file_images(records, client):
    """The roster article can lag uploads. Query exact, established filenames in the public file library."""
    targets = {}
    for record in records:
        normal = record.get("_expected_sprite")
        if normal and not record["recognition_ready"] and not record.get("_desired_images"):
            targets[normal] = [normal, normal.replace("_Sprite.png", "_s_Sprite.png")]
    filenames = sorted({name for pair in targets.values() for name in pair})
    found, snapshots = {}, []
    for offset in range(0, len(filenames), 40):
        batch = filenames[offset:offset + 40]
        url = "https://wiki.52poke.com/api.php?" + urlencode({"action": "query", "format": "json",
              "titles": "|".join("File:" + n for n in batch), "prop": "imageinfo", "iiprop": "url|size"})
        payload = json.loads(client.get(url))
        pages = payload.get("query", {}).get("pages")
        if not isinstance(pages, dict) or "error" in payload or "continue" in payload:
            raise ValueError("百科文件库返回错误或不完整批次")
        observed = set()
        for page in pages.values():
            name = page.get("title", "").removeprefix("File:").replace(" ", "_")
            if name not in batch or name in observed:
                raise ValueError("百科文件库返回了异常文件身份")
            observed.add(name)
            if "missing" in page:
                continue
            infos = page.get("imageinfo")
            if not infos:
                continue
            info = infos[0]
            parsed = urlparse(info["url"])
            if (parsed.scheme != "https" or parsed.hostname != "media.52poke.com"
                    or unquote(parsed.path.rsplit("/", 1)[-1]) != name):
                raise ValueError("百科文件元数据与目标图标身份不一致")
            if info.get("width") == 128 and info.get("height") == 128:
                found[name] = {"source_filename": name, "source_url": info["url"]}
        if observed != set(batch):
            raise ValueError("百科文件库遗漏了请求文件的存在状态")
        snapshots.append({"url": url, "response": payload})
    for record in records:
        pair = targets.get(record.get("_expected_sprite"))
        if pair and all(name in found for name in pair):
            record["_desired_images"] = {variant: found[name] for variant, name in zip(("normal", "shiny"), pair)}
    return snapshots

"""Explicit-season doubles usage, fetched through OP.GG's public page actions."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import gzip
import json
import math
from pathlib import Path
import re
import time

from bs4 import BeautifulSoup
import requests

from .sources import HttpCache, next_objects, dictionaries
from .storage import atomic_bytes, confined, digest, json_bytes, now, read_json, save_json, update_lock

TIER_URL = "https://op.gg/zh-cn/pokemon-champions/tier"
ACTION_NAMES = {"getPokemonTierRankingFormatAction", "getPokemonTierRankedBattleDetail"}


def action_result(content):
    """Only accept the JSON value referenced by the public action response envelope."""
    frames = {}
    for line in content.decode("utf-8").splitlines():
        key, separator, value = line.partition(":")
        if separator and re.fullmatch(r"[0-9a-f]+", key):
            try:
                frames[key] = json.loads(value)
            except json.JSONDecodeError:
                continue
    ref = frames.get("0", {}).get("a")
    if not isinstance(ref, str) or not ref.startswith("$@") or ref[2:] not in frames:
        raise ValueError("OP.GG 统计响应结构改变，保留旧采用率。")
    return frames[ref[2:]]


def parse_detail(payload, key, season, fallback=None):
    detail_data = payload.get("detailData")
    if not isinstance(detail_data, dict) or "doubleDetail" not in detail_data:
        raise ValueError("缺少明确的双打统计字段")
    detail = detail_data["doubleDetail"]
    entry = {"pokemon_key": key, "format": "double", "season": season,
             "source_updated_at": detail_data.get("updatedAt"), "fetched_at": now(),
             "source_url": TIER_URL, "moves": {}, "statistics_key": key, "status": "no_data"}
    if detail is None:
        return entry
    if not isinstance(detail, dict) or not isinstance(detail.get("moves"), list):
        raise ValueError("双打招式统计结构不完整")
    identity = detail.get("pokemon", {}).get("key")
    if identity != key and (not fallback or identity != fallback):
        raise ValueError("统计返回的宝可梦身份不匹配")
    entry["statistics_key"] = identity
    lookup = payload.get("lookupData", {}).get("moves", [])
    move_ids = {m["id"]: m["key"] for m in lookup}
    seen = set()
    for row in detail["moves"]:
        move_id, rate = row.get("id"), row.get("usagePercent")
        if (move_id in seen or move_id not in move_ids or type(rate) not in (int, float)
                or not math.isfinite(rate) or not 0 <= rate <= 100):
            raise ValueError("招式采用率或招式映射无效")
        seen.add(move_id)
        entry["moves"][move_ids[move_id]] = rate
    entry["status"] = "available" if entry["moves"] else "no_data"
    training = detail.get('training', [])
    if not isinstance(training, list):raise ValueError('培养点统计结构异常')
    entry['training'] = []
    seen_spreads = set()
    for row in training:
        encoded, rate = row.get('spread'), row.get('usagePercent')
        if not isinstance(encoded,str) or not re.fullmatch(r'[0-9a-fA-F]{2}(?:-[0-9a-fA-F]{2}){5}',encoded):
            raise ValueError('培养点编码无效')
        points = [int(part,16) for part in encoded.split('-')]
        if max(points)>32 or sum(points)>66 or tuple(points) in seen_spreads:
            raise ValueError('培养点分配超限或重复')
        if type(rate) not in (int,float) or not math.isfinite(rate) or not 0<=rate<=100:
            raise ValueError('培养点采用率无效')
        seen_spreads.add(tuple(points))
        entry['training'].append({'points':dict(zip(('hp','attack','defense','special_attack','special_defense','speed'),points)), 'usage_percent':rate})
    nature_lookup = {n['id']:n for n in payload.get('lookupData',{}).get('natures',[])}
    entry['natures'] = []
    for row in detail.get('natures',[]):
        nature,rate = nature_lookup.get(row.get('id')),row.get('usagePercent')
        if nature is None or type(rate) not in (int,float) or not math.isfinite(rate) or not 0<=rate<=100:
            raise ValueError('性格采用率或身份无效')
        entry['natures'].append({**nature,'usage_percent':rate})
    return entry


class UsageClient:
    def __init__(self, cache_root):
        self.cache_root = Path(cache_root)
        self.http = HttpCache(self.cache_root / "discovery")
        self.actions = {}

    def discover(self):
        page = self.http.get(TIER_URL)
        props = [d for ob in next_objects(page) for d in dictionaries(ob)
                 if isinstance(d.get("seasonOptionIds"), list) and isinstance(d.get("seasons"), list)]
        if len(props) != 1 or not props[0]["seasons"]:
            raise ValueError("无法确定 OP.GG 当前赛季")
        season = props[0]["seasons"][0]["id"]
        if not re.fullmatch(r"m-[0-9]+", season):
            raise ValueError("未知的 OP.GG 赛季标识")
        soup = BeautifulSoup(page, "html.parser")
        urls = list(dict.fromkeys(s["src"] for s in soup.find_all("script", src=True)
                                 if s["src"].startswith("https://s-stats-platform-cdn.op.gg/app-router/_next/static/chunks/")))
        if not urls or len(urls) > 100:
            raise ValueError("公开页面脚本结构异常")
        pattern = re.compile(r'createServerReference\)\("([a-f0-9]{40,64})",.{0,300}?"(getPokemonTierRankingFormatAction|getPokemonTierRankedBattleDetail)"\)', re.S)
        for url in urls:
            script = self.http.get(url, immutable=True).decode("utf-8")
            for action, name in pattern.findall(script):
                self.actions[name] = action
            if set(self.actions) == ACTION_NAMES:
                return season
        raise ValueError("未找到公开双打统计入口；请更新适配器，旧资料保持可用。")

    def call(self, name, args):
        for attempt in range(3):
            response = requests.post(TIER_URL, headers={"Next-Action": self.actions[name],
                "Accept": "text/x-component", "Content-Type": "text/plain;charset=UTF-8",
                "Origin": "https://op.gg", "User-Agent": "PokemonChampionAssistant/0.2"},
                data=json.dumps([args]), timeout=(10, 25), allow_redirects=False)
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < 2:
                    retry = response.headers.get("Retry-After", "")
                    if retry and (not retry.isdigit() or int(retry) > 30):
                        raise ValueError("OP.GG 要求稍后重试")
                    time.sleep(max(2 ** attempt, int(retry or "0")))
                    continue
            response.raise_for_status()
            if response.is_redirect or len(response.content) > 5_000_000:
                raise ValueError("统计请求响应异常")
            result = action_result(response.content)
            # Retain only the latest compressed public response for each explicit query.
            cache_key = digest(json_bytes({"name": name, "args": args}))
            atomic_bytes(self.cache_root / "responses" / f"{cache_key}.gz", gzip.compress(response.content))
            return result
        raise ValueError("统计请求重试失败")

    def ranking(self, season):
        result = self.call("getPokemonTierRankingFormatAction", {"lang": "zh-cn", "format": "double", "seasonIds": [season]})
        matches = [f for s in result if s.get("id") == season for f in s.get("formats", []) if f.get("id") == "double"]
        if len(matches) != 1 or not matches[0].get("rankings"):
            raise ValueError("来源未返回指定赛季的双打榜单")
        return matches[0]

    def detail(self, season, row):
        key = row["key"]
        fallback = row.get("pokemon", {}).get("base_key")
        if fallback == "$undefined":
            fallback = None
        args = {"lang": "zh-cn", "format": "double", "season": season, "pokemonKey": key}
        if fallback:
            args["fallbackPokemonKey"] = fallback
        return parse_detail(self.call("getPokemonTierRankedBattleDetail", args), key, season, fallback)


def load_usage_snapshot(path):
    """Read a fixed snapshot path without consulting a mutable current pointer."""
    path = Path(path)
    if path.suffix == '.sqlite':
        from .sqlite_catalog import read_usage_database
        return read_usage_database(path)
    return read_json(path)


def load_usage(root):
    root = Path(root)
    if not (root / "current.json").exists():
        return None
    pointer = read_json(root / "current.json")
    data = confined(root, pointer["file"]).read_bytes()
    if digest(data) != pointer["sha256"]:
        raise ValueError("采用率快照校验失败")
    result = json.loads(data)
    if result.get("format") != "double" or result.get("schema_version") != 1:
        raise ValueError("采用率快照模式不匹配")
    if pointer.get('database_file'):
        path = confined(root, pointer['database_file'])
        if digest(path.read_bytes()) != pointer.get('database_sha256'):
            raise ValueError('采用率数据库校验失败')
        sql_result = load_usage_snapshot(path)
        if sql_result != result:
            raise ValueError('采用率数据库与来源证据不一致')
        result = sql_result
    elif pointer.get('reference_schema'):
        raise ValueError('采用率快照缺少数据库')
    return result


def write_usage_snapshot(root, snapshot):
    """Publish immutable JSON evidence and authoritative SQL before the pointer."""
    from .sqlite_catalog import build_usage_database, read_usage_database
    root = Path(root)
    data = json_bytes(snapshot)
    checksum = digest(data)
    relative = f'snapshots/usage-{checksum[:24]}.json'
    sql_relative = f'snapshots/usage-{checksum[:24]}/usage.sqlite'
    path = root / sql_relative
    if path.exists():
        if read_usage_database(path) != snapshot:
            raise ValueError('已有采用率数据库内容不符')
    else:
        build_usage_database(path, snapshot)
    # Never modify an existing evidence file, even on a repeated identical update.
    if (root/relative).exists():
        if (root/relative).read_bytes() != data: raise ValueError('已有采用率证据校验失败')
    else:
        atomic_bytes(root / relative, data)
    save_json(root / 'current.json', {'file': relative, 'sha256': checksum,
                                    'database_file': sql_relative, 'database_sha256': digest(path.read_bytes()),
                                    'reference_schema': 1})
    return relative


def update_usage(root, *, due_hours=None, client=None, progress=lambda message: None):
    root = Path(root)
    with update_lock(root):
        old = load_usage(root)
        if due_hours and old and old.get('features_version') == 2 and not old.get("errors"):
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(old["fetched_at"])).total_seconds()
            if 0 <= age < due_hours * 3600:
                return {"status": "not_due", "season": old["season"], "entries": len(old["pokemon"])}
        client = client or UsageClient(root / "cache")
        season = client.discover()
        ranking = client.ranking(season)
        rows = ranking["rankings"]
        keys = [r["key"] for r in rows]
        if len(set(keys)) != len(keys) or any(not re.fullmatch(r"[a-z0-9][a-z0-9.-]*", k) or ".." in k for k in keys):
            raise ValueError("双打名单身份无效或重复")
        entries, errors = {}, {}
        previous = old["pokemon"] if old and old["season"] == season else {}
        progress(f"同步 {season.upper()} 双打采用率：{len(rows)} 个统计身份")
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(client.detail, season, row): row["key"] for row in rows}
            for count, future in enumerate(as_completed(futures), 1):
                key = futures[future]
                try:
                    entries[key] = future.result()
                except Exception as exc:
                    errors[key] = str(exc)
                    if key in previous:
                        entries[key] = previous[key]
                if count % 25 == 0 or count == len(rows):
                    progress(f"已读取 {count}/{len(rows)}，失败 {len(errors)}")
        if len(errors) > len(rows) * .2:
            save_json(root / "last_failure.json", {"checked_at": now(), "errors": errors})
            raise ValueError("超过 20% 的统计请求失败，未替换旧采用率快照")
        snapshot = {"schema_version": 1, "features_version": 2, "format": "double", "season": season, "fetched_at": now(),
                    "ranking_updated_at": ranking.get("createdAt"), "source_url": TIER_URL,
                    "pokemon": entries, "errors": errors}
        relative = write_usage_snapshot(root, snapshot)
        return {"status": "partial" if errors else "updated", "season": season,
                "entries": len(entries), "errors": len(errors), "snapshot": relative}


def move_order(move):
    rate, power = move.get("usage_percent"), move.get("power")
    return (rate is None, -(rate if rate is not None else 0),
            -(power if isinstance(power, (int, float)) else -1), move["name"])


def reparse_usage_cache(root):
    """Enrich the current snapshot from exact-query cached public responses, without redating it."""
    root=Path(root)
    with update_lock(root):
        snapshot=load_usage(root)
        if not snapshot:raise ValueError('没有可补充的采用率快照，请先联网更新')
        count=0
        for key,entry in snapshot['pokemon'].items():
            for fallback in dict.fromkeys([None,entry.get('statistics_key'),key]):
                args={'lang':'zh-cn','format':'double','season':entry['season'],'pokemonKey':key}
                if fallback:args['fallbackPokemonKey']=fallback
                cache_key=digest(json_bytes({'name':'getPokemonTierRankedBattleDetail','args':args}))
                path=root/'cache/responses'/f'{cache_key}.gz'
                if not path.exists():continue
                parsed=parse_detail(action_result(gzip.decompress(path.read_bytes())),key,entry['season'],fallback)
                if parsed['source_updated_at']!=entry['source_updated_at'] or parsed['moves']!=entry['moves']:continue
                entry.update(training=parsed.get('training',[]),natures=parsed.get('natures',[]))
                count+=1;break
        relative=write_usage_snapshot(root,snapshot)
        return {'status':'cache_reparsed','entries':count,'snapshot':relative}

"""Versioned move facts; display formatting never invents a numerical value."""
from __future__ import annotations

import html

from .sources import OPGG_URL, dictionaries, next_objects
from .storage import TYPE_NAMES

CATEGORIES = {"physical": "物理", "special": "特殊", "status": "变化"}
TARGETS = {
    "selected-pokemon": "选择的单个目标", "all-other-pokemon": "周围所有宝可梦（包含同伴）",
    "all-opponents": "对方全体", "user": "自己", "user-or-ally": "自己或同伴",
    "ally": "同伴", "all-allies": "我方全体", "user-and-allies": "自己与同伴",
    "users-field": "我方场地", "opponents-field": "对方场地", "entire-field": "整个场地",
    "all-pokemon": "场上所有宝可梦", "random-opponent": "随机对手",
    "selected-pokemon-me-first": "选定目标（依招式机制）", "specific-move": "指定招式",
    "fainting-pokemon": "濒死的宝可梦",
}


def parse_moves(content):
    candidates = []
    for obj in next_objects(content):
        for props in dictionaries(obj):
            if isinstance(props.get("pokemon"), list) and "moveList" in props:
                candidates.append(props["moveList"])
    if not candidates:
        return {}  # Legacy/static-only source bundles remain readable.
    if len(candidates) != 1 or not isinstance(candidates[0], list) or not candidates[0]:
        raise ValueError("OP.GG 招式清单结构异常")
    result = {}
    for raw in candidates[0]:
        if not isinstance(raw, dict):
            raise ValueError("招式条目不是有效对象")
        key = raw.get("key")
        if not isinstance(key, str) or key in result or raw.get("type") not in TYPE_NAMES or raw.get("category") not in CATEGORIES:
            raise ValueError(f"招式身份／属性／分类无效：{key}")
        if not isinstance(raw.get("name"), str) or not isinstance(raw.get("effect", ""), str):
            raise ValueError(f"招式名称／说明无效：{key}")
        if type(raw.get("isAvailable")) is not bool:
            raise ValueError(f"招式可用性标记无效：{key}")
        for field in ("power", "accuracy", "pp", "priority"):
            value = raw.get(field)
            if value is not None and (type(value) is not int or not -10 <= value <= 1000):
                raise ValueError(f"招式数值无效：{key}/{field}")
        description = raw.get("description") or raw.get("effect") or "来源暂未提供详细说明。"
        if not isinstance(description, str):
            raise ValueError(f"招式说明无效：{key}")
        result[key] = {**raw, "description": " ".join(description.split()),
                       "power_known": "power" in raw, "accuracy_known": "accuracy" in raw,
                       "source_url": OPGG_URL.rsplit("/", 1)[0] + "/moves/" + key}
    return result


def power_label(move):
    if move["category"] == "status":
        return "—"
    if not move.get("power_known", "power" in move):
        return "未知"
    return str(move["power"]) if move.get("power") is not None else "特殊"


def accuracy_label(move):
    if not move.get("accuracy_known", "accuracy" in move):
        return "未知"
    return f"{move['accuracy']}%" if move.get("accuracy") is not None else "—"


def move_tooltip(move):
    # Qt tooltips understand HTML: all site text is escaped, never executed/rendered raw.
    title = html.escape(move["name"])
    desc = html.escape(move["description"])
    return (f"<b>{title}</b> · {TYPE_NAMES[move['type']]} · {CATEGORIES[move['category']]}<br>"
            f"威力 {power_label(move)} · 命中 {accuracy_label(move)}<br><br>{desc}<br><br>点击查看完整说明")

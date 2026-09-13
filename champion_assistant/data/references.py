"""A read-only reference view pinned to the same bundle as the recognizer."""
from __future__ import annotations

from pathlib import Path
from copy import deepcopy

from .moves import parse_moves
from .storage import confined, digest, read_json, resolve_dataset, validate_bundle
from .usage import load_usage, move_order
from datetime import datetime, timezone


class ReferenceCatalog:
    def __init__(self, data_dir, usage_dir=None, *, usage_snapshot=None):
        self.root = resolve_dataset(Path(data_dir))
        data_root = self.root.parents[1] if self.root.parent.name == "_versions" else self.root
        self.usage_dir = Path(usage_dir) if usage_dir else data_root / "_usage"
        self._fixed_usage = deepcopy(usage_snapshot)
        self.usage, self.usage_error = None, ""
        self.reload_usage()
        self.bundle_id = self.root.name if (self.root / "manifest.json").exists() else "legacy"
        self._verified_files = set()
        sql_facts = None
        if (self.root / 'catalog.sqlite').exists():
            from .sqlite_catalog import read_catalog_database
            if self.bundle_id != 'legacy':
                validate_bundle(self.root)
                self._verified_files = set(read_json(self.root / 'manifest.json')['files'])
                if 'catalog.sqlite' not in self._verified_files:
                    raise ValueError('SQLite 不在资料清单内')
            sql_facts = read_catalog_database(self.root / 'catalog.sqlite')
        elif self.bundle_id != 'legacy' and read_json(self.root/'manifest.json').get('reference_schema'):
            raise ValueError('资料包缺少 catalog.sqlite')
        self.index = sql_facts['index'] if sql_facts else read_json(self.root / "index.json")
        self.records = self.index["pokemon"]
        self.by_id = {r.get("record_id", r["directory"]): r for r in self.records}
        self.by_name = {}
        for r in self.records:
            self.by_name.setdefault(r['name'], []).append(r)
        self.ambiguous_names = {name for name, values in self.by_name.items() if len(values) > 1}
        self.by_name = {name: values[0] for name, values in self.by_name.items() if len(values) == 1}
        self.source = {}
        if sql_facts:
            self.source = {r['key']: r for r in sql_facts['source']}
        elif (self.root / "source_catalog.json").exists():
            self.source = {r["key"]: r for r in read_json(self.verified_file("source_catalog.json"))}
        if sql_facts:
            self.moves = sql_facts['moves']
        elif (self.root / "moves.json").exists():
            self.moves = read_json(self.verified_file("moves.json"))
        elif (self.root / "_sources/opgg.html").exists():
            self.moves = parse_moves(self.verified_file("_sources/opgg.html").read_bytes())
        else:
            self.moves = {}
        policy_path = self.root / "recognition_identity_groups.json"
        self.cosmetic_names = {}
        if sql_facts or policy_path.exists():
            policy = sql_facts['policy'] if sql_facts else read_json(self.verified_file('recognition_identity_groups.json'))
            for group in policy['groups']:
                for slug in group["source_slugs"]:
                    self.cosmetic_names[slug] = group["name"]

    def reload_usage(self):
        try:
            self.usage = deepcopy(self._fixed_usage) if self._fixed_usage is not None else load_usage(self.usage_dir)
            self.usage_error = ""
        except (OSError, ValueError, KeyError) as exc:
            self.usage_error = "采用率快照读取失败，保留已加载的数据。"
        return self.usage_error

    def verified_file(self, relative):
        path = confined(self.root, relative)
        if self.bundle_id != "legacy" and relative not in self._verified_files:
            manifest = read_json(self.root / "manifest.json")
            if relative not in manifest["files"] or digest(path.read_bytes()) != manifest["files"][relative]:
                raise ValueError(f"资料文件校验失败：{relative}")
            self._verified_files.add(relative)
        return path

    def display_name(self, record):
        return self.cosmetic_names.get(record["source_slug"], record["name"])

    def record_for_name(self, name):
        if name in self.ambiguous_names:
            return None
        if name in self.by_name:
            return self.by_name[name]
        return next((r for r in self.records if self.display_name(r) == name), None)

    def search_records(self):
        seen = set()
        values = []
        for record in self.records:
            label = self.display_name(record)
            if label not in seen:
                seen.add(label)
                values.append((label, record))
        return sorted(values, key=lambda pair: (pair[1]["dex_number"], pair[0]))

    def sprite(self, record):
        asset = record["images"].get("normal")
        if asset:
            return self.verified_file(f"{record['directory']}/{asset['file']}")
        return None

    def form_family(self, record):
        # Mega branches share a declared source parent, not just a national-dex number.
        base_key = record.get("source_base_key") if record.get("opgg_key", "").startswith("mega-") else record.get("opgg_key")
        if not base_key:
            return [record]
        base = next((r for r in self.records if r.get("opgg_key") == base_key), record)
        family = [base]
        for identifier in base.get("mega_form_ids", []):
            if identifier in self.by_id:
                family.append(self.by_id[identifier])
        return family

    def learnset(self, record):
        raw = self.source.get(record.get("opgg_key"))
        if raw is None:
            return [], [], "当前来源没有这个形态的独立招式池。"
        banned = set(raw.get("bannedMoves", []))
        usage = self.usage["pokemon"].get(record.get("opgg_key")) if self.usage else None
        rates = usage["moves"] if usage else {}
        damage, status, missing = [], [], []
        for key in dict.fromkeys(raw.get("moves", [])):
            if key in banned:
                continue
            move = self.moves.get(key)
            if not move:
                missing.append(key)
            elif move.get("isAvailable") is True:
                (status if move["category"] == "status" else damage).append({**move, "usage_percent": rates.get(key)})
        if usage:
            notice = f"OP.GG · {usage['season'].upper()} 双打 · 来源更新 {usage['source_updated_at'] or '未标明'}。"
            if usage["statistics_key"] != usage["pokemon_key"]:
                notice += f" 采用来源的合并统计（{usage['statistics_key']}），非本形态独立统计。"
            if record.get("opgg_key") in self.usage.get("errors", {}):
                notice += " 本项更新失败，显示旧缓存。"
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(usage["fetched_at"])).total_seconds()
            if age > 48 * 3600:
                notice += " 缓存超过 48 小时，请更新。"
        else:
            notice = "该形态暂无双打采用率；未借用其他形态或单打数据。"
        notice += " 分组内采用率降序；— 表示未公布，其余按固定威力降序。"
        if self.usage_error:
            notice += " " + self.usage_error
        if missing:
            notice += f" {len(missing)} 项招式资料缺失。"
        return sorted(damage, key=move_order), sorted(status, key=move_order), notice

"""Local-only HTTP API and static web host for Champion Lab.

The browser is a presentation layer. All catalog, team, recognition and damage
work continues to run through the existing Python domain services.
"""
from __future__ import annotations

from copy import deepcopy
import base64
import binascii
from http import HTTPStatus
from http.client import HTTPConnection, HTTPException
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import argparse
import json
import mimetypes
from pathlib import Path
import re
import socket
import sys
import tempfile
from threading import Lock, Timer
from time import monotonic
from urllib.parse import parse_qs, unquote, urlsplit
from uuid import uuid4
import webbrowser

from PIL import Image

from .capture.obs import ObsCapture, local_obs_settings
from .credentials import CredentialStoreError, ObsPasswordStore
from .damage import DamageService, battle_defaults
from .ability_conditions import (ABILITY_HP_REQUIREMENTS, ABILITY_SCENE_REQUIREMENTS,
                                 ABILITY_TRIGGER_LABELS)
from .battle_effects import SUPPORT_EFFECTS
from .data.snapshot import SnapshotManager
from .data.storage import TYPE_NAMES, read_json, save_json
from .paths import app_paths
from .recognition import ALGORITHM_VERSION, OpponentRecognizer
from .speed import SPEED_TIERS, reference_speed, speed_lines
from .team_import import ScreenshotImporter
from .teams import STATS, TeamRules, TeamStore
from .type_matchups import type_matchups
from .version import __version__

DEFAULT_PORT = 32145
MAX_JSON_BYTES = 2_000_000
MAX_IMAGE_BYTES = 25_000_000
TEAM_IMPORT_TTL = 30 * 60
TEAM_IMPORT_MAX_HANDLES = 64
CATEGORY_NAMES = {"physical": "物理", "special": "特殊", "status": "变化"}
STATUS_OPTIONS = (
    ("", "无异常"), ("brn", "灼伤"), ("par", "麻痹"), ("psn", "中毒"),
    ("tox", "剧毒"), ("slp", "睡眠"), ("frz", "冰冻"),
)


class ApiError(ValueError):
    """A safe client-facing API error."""

    def __init__(self, message: str, status: int = HTTPStatus.BAD_REQUEST):
        super().__init__(message)
        self.status = int(status)


class LocalWebServer(ThreadingHTTPServer):
    """Own the loopback port exclusively so repeated launches cannot split traffic."""

    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class WebServices:
    """Thread-safe adapters around the existing application services."""

    def __init__(self, *, data_dir: Path | None = None, layout_path: Path | None = None,
                 teams_path: Path | None = None, settings_path: Path | None = None,
                 obs: ObsCapture | None = None):
        self.paths = app_paths().ensure()
        self.snapshots = SnapshotManager(data_dir or self.paths.data, layout_path)
        self.snapshot = self.snapshots.initial()
        self.catalog = self.snapshot.catalog
        self.rules = TeamRules(self.catalog)
        self.store = TeamStore(teams_path or self.paths.teams, self.rules)
        self.damage = DamageService(self.catalog)
        self.settings_path = Path(settings_path or self.paths.settings)
        self.obs = obs or ObsCapture()
        self.obs_password_store = ObsPasswordStore(
            self.settings_path.with_name("obs-password.dpapi")
        )
        self.obs_password = self.obs_password_store.load()
        self._recognizer = None
        self._recognizer_token = None
        self._recognition_lock = Lock()
        self._team_import_lock = Lock()
        self._team_import_evidence = {}

    def _settings(self) -> dict:
        try:
            value = read_json(self.settings_path) if self.settings_path.exists() else {}
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def public_settings(self) -> dict:
        saved = self._settings()
        return {
            "host": saved.get("host", "127.0.0.1"),
            "port": saved.get("port", 4455),
            "source": saved.get("source", ""),
            "selected_team_id": saved.get("selected_team_id"),
            "theme": saved.get("theme", "light"),
            "reduced_motion": bool(saved.get("reduced_motion", False)),
            "obs_local": local_obs_settings(),
            "password_in_memory": bool(self.obs_password),
            "password_saved": bool(self.obs_password and self.obs_password_store.path.is_file()),
            "user_directory": str(self.paths.user),
        }

    def update_settings(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ApiError("设置格式无效。")
        saved = self._settings()
        for key in ("host", "source", "selected_team_id", "theme", "reduced_motion"):
            if key in payload:
                saved[key] = payload[key]
        if "port" in payload:
            port = payload["port"]
            if type(port) is not int or not 1 <= port <= 65535:
                raise ApiError("OBS 端口须为 1–65535。")
            saved["port"] = port
        if saved.get("theme", "light") not in ("light", "dark"):
            raise ApiError("主题设置无效。")
        host = saved.get("host", "127.0.0.1")
        source = saved.get("source", "")
        if not isinstance(host, str) or len(host) > 255:
            raise ApiError("OBS 主机地址无效。")
        if not isinstance(source, str) or len(source) > 512:
            raise ApiError("OBS 来源名称无效。")
        clear_password = payload.get("clear_obs_password", False)
        if type(clear_password) is not bool:
            raise ApiError("清除 OBS 密码的设置无效。")
        password = payload.get("password")
        if password not in (None, ""):
            if not isinstance(password, str) or len(password) > 1024:
                raise ApiError("OBS 密码格式无效。")
            try:
                self.obs_password_store.save(password)
            except CredentialStoreError as exc:
                raise ApiError("OBS 密码无法使用当前 Windows 用户凭据安全保存。") from exc
            self.obs_password = password
        elif password is not None and not isinstance(password, str):
            raise ApiError("OBS 密码格式无效。")
        if clear_password:
            self.obs_password_store.clear()
            self.obs_password = ""
        saved.pop("password", None)
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        save_json(self.settings_path, saved)
        return self.public_settings()

    def bootstrap(self) -> dict:
        return {
            "app": {
                "name": "Champion Lab", "version": __version__,
                "dataset_id": self.catalog.bundle_id,
                "pokemon_forms": len(self.catalog.records),
                "recognition_algorithm": ALGORITHM_VERSION, "api": "local",
            },
            "settings": self.public_settings(),
            "teams": self.teams(),
            "featured": self.search_pokemon("", limit=12),
        }

    def _record(self, identity: str):
        if not isinstance(identity, str) or len(identity) > 300:
            raise ApiError("宝可梦身份无效。")
        record = self.rules.record(identity)
        if record is None:
            raise ApiError("当前资料中没有这个宝可梦形态。", HTTPStatus.NOT_FOUND)
        return record

    def _pokemon_summary_fields(self, record) -> dict:
        identity = self.rules.identity(record)
        return {
            "id": identity, "name": self.catalog.display_name(record),
            "dex": f"{record['dex_number']:04d}",
            "types": [TYPE_NAMES.get(value, value) for value in record.get("types", [])],
            "type_keys": list(record.get("types", [])),
            "speed": record.get("base_stats", {}).get("speed"),
            "image": f"/api/pokemon/sprite?id={identity}",
            "form": record.get("form_name"),
        }

    def pokemon_summary(self, record) -> dict:
        result = self._pokemon_summary_fields(record)
        base = self.catalog.form_family(record)[0]
        result["family_base"] = self._pokemon_summary_fields(base)
        result["is_battle_form"] = result["id"] != result["family_base"]["id"]
        return result

    def search_pokemon(self, query: str, *, limit: int = 30, offset: int = 0) -> list[dict]:
        if not isinstance(query, str) or len(query) > 100:
            raise ApiError("搜索内容过长。")
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ApiError("搜索数量无效。")
        if type(offset) is not int or offset < 0:
            raise ApiError("搜索起点无效。")
        needle = query.strip().casefold()
        results = []
        matched = 0
        for label, record in self.catalog.search_records():
            type_text = " ".join(TYPE_NAMES.get(value, value) for value in record.get("types", []))
            aliases = " ".join(record.get("aliases", []))
            haystack = f"{label} {record.get('source_slug', '')} {type_text} {aliases}".casefold()
            if needle and needle not in haystack:
                continue
            if matched < offset:
                matched += 1
                continue
            results.append(self.pokemon_summary(record))
            if len(results) >= limit:
                break
        return results

    def pokemon_detail(self, identity: str) -> dict:
        record = self._record(identity)
        damage_moves, status_moves, notice = self.catalog.learnset(record)
        matchups = type_matchups(record.get("types", [])) or {
            "weakness": [], "resistance": [], "immune": [],
        }

        def matchup_rows(values):
            return [{"type": TYPE_NAMES.get(key, key), "multiplier": value} for key, value in values]

        def move_row(move):
            return {
                "id": move["key"], "name": move["name"],
                "type": TYPE_NAMES.get(move.get("type"), move.get("type")),
                "category": CATEGORY_NAMES.get(move.get("category"), move.get("category")),
                "power": move.get("power"), "accuracy": move.get("accuracy"),
                "usage": move.get("usage_percent"), "description": move.get("description", ""),
            }

        usage, inherited = self.catalog.usage_for(record)
        return {
            **self.pokemon_summary(record),
            "base_stats": record.get("base_stats", {}),
            "base_stat_total": record.get("base_stat_total"),
            "matchups": {key: matchup_rows(value) for key, value in matchups.items()},
            "moves": [move_row(move) for move in damage_moves + status_moves],
            "notice": notice,
            "usage": {
                "season": usage.get("season") if usage else None,
                "source_updated_at": usage.get("source_updated_at") if usage else None,
                "inherited_from": self.catalog.display_name(inherited) if inherited else None,
            },
            "forms": [self.pokemon_summary(item) for item in self.catalog.form_family(record)],
            "abilities": [self._ability_view(key) for key in self.rules.ability_keys(identity)],
        }

    def _ability_view(self, key: str) -> dict:
        entry = self.rules.options["abilities"].get(key, {})
        requirement = ABILITY_SCENE_REQUIREMENTS.get(key)
        return {
            "id": key,
            "name": entry.get("name", key),
            "description": entry.get("description", ""),
            "trigger_label": ABILITY_TRIGGER_LABELS.get(key),
            "scene_requirement": (
                {"kind": requirement[0], "value": requirement[1]} if requirement else None
            ),
            "hp_requirement": ABILITY_HP_REQUIREMENTS.get(key),
        }

    def damage_options(self, identity: str) -> dict:
        record = self._record(identity)
        blocked = {"trace", "receiver", "power-of-alchemy", "protean", "libero", "color-change", "imposter"}
        return {
            "pokemon": self.pokemon_summary(record),
            "forms": [
                {
                    **self.pokemon_summary(form),
                    "abilities": [self._ability_view(key) for key in self.rules.ability_keys(self.rules.identity(form))],
                }
                for form in self.catalog.form_family(record)
            ],
            "abilities": [self._ability_view(key) for key in self.rules.ability_keys(identity)],
            "copiable_abilities": [
                self._ability_view(key) for key in self.rules.options["abilities"] if key not in blocked
            ],
            "support_effects": [
                {"id": key, "engine_id": engine, "label": label, "group": group, "description": description}
                for key, engine, label, group, description in SUPPORT_EFFECTS
            ],
            "statuses": [{"id": key, "name": name} for key, name in STATUS_OPTIONS],
        }

    def sprite_path(self, identity: str) -> Path:
        sprite = self.catalog.sprite(self._record(identity))
        if sprite is None:
            raise ApiError("这个形态没有可用图标。", HTTPStatus.NOT_FOUND)
        return sprite

    def _member_view(self, member: dict) -> dict:
        result = deepcopy(member)
        record = self.rules.record(member.get("identity"))
        result["pokemon"] = self.pokemon_summary(record) if record else None
        result["nature_name"] = self.rules.options["natures"].get(member.get("nature"), {}).get("name")
        result["ability_name"] = self.rules.options["abilities"].get(member.get("ability"), {}).get("name")
        result["item_name"] = self.rules.options["items"].get(member.get("item"), {}).get("name")
        result["move_names"] = [self.catalog.moves.get(key, {}).get("name") if key else None
                                for key in member.get("moves", [])]
        return result

    def team_view(self, team: dict) -> dict:
        result = deepcopy(team)
        result["members"] = [self._member_view(member) for member in team.get("members", [])]
        return result

    def teams(self) -> list[dict]:
        return [self.team_view(team) for team in self.store.list()]

    def save_team(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ApiError("队伍格式无效。")
        # TeamStore preserves unknown keys verbatim; constrain this API boundary
        # so a crafted client cannot embed screenshots or credentials elsewhere.
        cleaned = {key: deepcopy(payload[key]) for key in
                   ('id', 'revision', 'name', 'registration', 'members', 'import_source')
                   if key in payload}
        if cleaned.get('import_source') is None:
            cleaned.pop('import_source', None)
        else:
            cleaned['import_source'] = self._clean_import_source(cleaned['import_source'])
        for member in cleaned.get("members", []):
            if isinstance(member, dict):
                for key in tuple(member):
                    if key not in ('identity', 'points', 'nature', 'ability', 'item', 'moves'):
                        member.pop(key, None)
        try:
            return self.team_view(self.store.save(cleaned))
        except (ValueError, TypeError, KeyError) as exc:
            raise ApiError(str(exc)) from exc

    @staticmethod
    def _clean_import_source(source):
        """Do not persist client-controlled paths, image bytes, or OBS credentials."""
        if not isinstance(source, dict):
            raise ApiError('截图来源信息无效。')
        code = source.get('team_code')
        if not isinstance(code, str) or not re.fullmatch(r'[A-Z0-9]{10}', code):
            raise ApiError('截图来源的队伍码无效。')
        clean = {'method': 'local_ocr', 'team_code': code, 'review_required': True}
        for mode in ('ability', 'status'):
            page = source.get(mode)
            if not isinstance(page, dict) or page.get('mode') != mode:
                raise ApiError('截图来源页信息无效。')
            image = page.get('source')
            if not isinstance(image, dict) or not isinstance(image.get('sha256'), str) or not re.fullmatch(r'[a-f0-9]{64}', image['sha256']):
                raise ApiError('截图来源校验值无效。')
            size = image.get('size')
            if (not isinstance(size, list) or len(size) != 2 or
                    any(type(n) is not int or n <= 0 or n > 30_000 for n in size) or
                    size[0] * size[1] > 30_000_000):
                raise ApiError('截图来源尺寸无效。')
            members = page.get('members')
            if not isinstance(members, list) or len(members) != 6:
                raise ApiError('截图来源槽位无效。')
            corrections = []
            for index, item in enumerate(members, 1):
                if not isinstance(item, dict) or item.get('slot') != index:
                    raise ApiError('截图来源槽位无效。')
                corrections.append({'slot': index, 'identity_corrected': item.get('identity_corrected') is True})
            clean[mode] = {
                'mode': mode,
                'source': {'sha256': image['sha256'], 'size': size},
                'code_corrected': page.get('code_corrected') is True,
                'members': corrections,
            }
        return clean

    def delete_team(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ApiError("队伍版本信息无效。")
        try:
            self.store.delete({"id": payload.get("id"), "revision": payload.get("revision")})
        except (ValueError, TypeError, KeyError) as exc:
            raise ApiError(str(exc)) from exc
        return {"deleted": True}

    def team_options(self, identity: str) -> dict:
        record = self._record(identity)
        damage_moves, status_moves, _ = self.catalog.learnset(record)

        def options(values):
            return [{"id": key, "name": value.get("name", key)} for key, value in values.items()]

        abilities = {
            key: self.rules.options["abilities"][key] for key in self.rules.ability_keys(identity)
            if key in self.rules.options["abilities"]
        }
        return {
            "pokemon": self.pokemon_summary(record),
            "natures": options(self.rules.options["natures"]),
            "abilities": options(abilities),
            "items": [{"id": "none", "name": "无道具"}] + options(self.rules.options["items"]),
            "moves": [{"id": move["key"], "name": move["name"]} for move in damage_moves + status_moves],
            "point_rules": deepcopy(self.rules.options["point_rules"]),
        }

    def _recognizer_for_snapshot(self):
        snapshot = self.snapshots.candidate()
        token = (snapshot.token, str(snapshot.layout_path))
        if self._recognizer is None or self._recognizer_token != token:
            self._recognizer = OpponentRecognizer(snapshot.data_dir, snapshot.layout_path)
            self._recognizer_token = token
        return snapshot, self._recognizer

    def recognize_bytes(self, content: bytes) -> dict:
        if not content or len(content) > MAX_IMAGE_BYTES:
            raise ApiError("截图为空或超过 25 MB。", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        try:
            with Image.open(BytesIO(content)) as source:
                if source.width * source.height > 40_000_000:
                    raise ApiError("截图像素过大。")
                source.load()
                image = source.convert("RGB")
        except ApiError:
            raise
        except OSError as exc:
            raise ApiError("无法读取截图，请使用 PNG、JPG、WebP 或 BMP。") from exc
        return self.recognize_image(image)

    def recognize_image(self, image: Image.Image) -> dict:
        with self._recognition_lock:
            snapshot, recognizer = self._recognizer_for_snapshot()
            report, _, _ = recognizer.recognize(image)
            report["snapshot_token"] = snapshot.token
        for slot in report["opponent"]:
            record = self.catalog.record_for_name(slot.get("name")) if slot.get("name") else None
            slot["pokemon"] = self.pokemon_summary(record) if record else None
            for candidate in slot.get("candidates", []):
                candidate.pop("template_path", None)
                candidate_record = self.catalog.record_for_name(candidate.get("name"))
                if candidate_record is None and len(candidate.get("form_candidates", [])) == 1:
                    candidate_record = self.catalog.record_for_name(candidate["form_candidates"][0])
                candidate["pokemon"] = self.pokemon_summary(candidate_record) if candidate_record else None
        return report

    def _obs_settings(self, payload: dict | None = None) -> dict:
        values = {**self.public_settings(), **(payload or {})}
        password = values.pop("password", None)
        if password not in (None, ""):
            if not isinstance(password, str) or len(password) > 1024:
                raise ApiError("OBS 密码格式无效。")
            self.obs_password = password
        elif password is not None and not isinstance(password, str):
            raise ApiError("OBS 密码格式无效。")
        values["password"] = self.obs_password
        return values

    def obs_sources(self, payload: dict) -> dict:
        try:
            return self.obs.sources(self._obs_settings(payload))
        except ValueError as exc:
            raise ApiError(str(exc)) from exc

    def obs_capture(self, payload: dict) -> dict:
        try:
            return self.recognize_image(self.obs.screenshot(self._obs_settings(payload)))
        except ValueError as exc:
            raise ApiError(str(exc)) from exc

    @staticmethod
    def _team_import_image(content: bytes, *, expected_format: str | None = None) -> None:
        if not content or len(content) > MAX_IMAGE_BYTES:
            raise ApiError('截图为空或超过 25 MB。', HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        try:
            with Image.open(BytesIO(content)) as image:
                if image.format not in ('PNG', 'JPEG', 'WEBP', 'BMP'):
                    raise ApiError('请使用 PNG、JPG、WebP 或 BMP 截图。')
                if expected_format and image.format != expected_format:
                    raise ApiError('OBS 未返回有效的 PNG 截图。')
                if image.width * image.height > 30_000_000:
                    raise ApiError('截图像素过大，请限制在 3000 万像素以内。')
                image.verify()
        except ApiError:
            raise
        except (OSError, ValueError) as exc:
            raise ApiError('无法读取截图，请使用 PNG、JPG、WebP 或 BMP。') from exc

    def team_import_recognize(self, content: bytes, mode: str) -> dict:
        if mode not in ('ability', 'status'):
            raise ApiError('截图类型必须为能力或状态。')
        self._team_import_image(content)
        token = self.snapshots.candidate().token
        if token != self.snapshot.token:
            raise ApiError('资料已更新，请重启工作台后重新识别截图。', HTTPStatus.CONFLICT)
        with tempfile.TemporaryDirectory(prefix='champion-team-import-') as directory:
            path = Path(directory) / (uuid4().hex + '.png')
            path.write_bytes(content)
            try:
                page = ScreenshotImporter(self.rules).read_page(path, mode)
            except ValueError as exc:
                raise ApiError(str(exc)) from exc
        page['source'].pop('filename', None)
        handle = uuid4().hex
        now = monotonic()
        with self._team_import_lock:
            self._team_import_evidence = {
                key: entry for key, entry in self._team_import_evidence.items()
                if now - entry[0] < TEAM_IMPORT_TTL
            }
            while len(self._team_import_evidence) >= TEAM_IMPORT_MAX_HANDLES:
                oldest = min(self._team_import_evidence, key=lambda key: self._team_import_evidence[key][0])
                self._team_import_evidence.pop(oldest)
            self._team_import_evidence[handle] = (now, token, deepcopy(page))
        return {'handle': handle, 'page': page}

    def team_import_obs_capture(self, payload: dict) -> dict:
        try:
            data_url = self.obs.screenshot_data_url(self._obs_settings(payload))
            prefix = 'data:image/png;base64,'
            if not isinstance(data_url, str) or not data_url.startswith(prefix) or len(data_url) > 33_333_400:
                raise ApiError('OBS 截图为空或超过 25 MB。', HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            try:
                content = base64.b64decode(data_url[len(prefix):], validate=True)
            except (ValueError, binascii.Error) as exc:
                raise ApiError('OBS 截图格式无效。') from exc
            self._team_import_image(content, expected_format='PNG')
            return {'data_url': data_url}
        except ValueError as exc:
            if isinstance(exc, ApiError):
                raise
            raise ApiError(str(exc)) from exc

    def team_import_combine(self, payload: dict) -> dict:
        if not isinstance(payload, dict) or set(payload) != {
                'ability_handle', 'status_handle', 'ability_review', 'status_review'}:
            raise ApiError('请提交两页截图及其复核信息。')
        handles = (payload['ability_handle'], payload['status_handle'])
        if any(not isinstance(handle, str) or len(handle) != 32 for handle in handles) or handles[0] == handles[1]:
            raise ApiError('截图复核已过期，请重新识别。')
        now = monotonic()
        with self._team_import_lock:
            entries = [self._team_import_evidence.get(handle) for handle in handles]
        if any(entry is None or now - entry[0] >= TEAM_IMPORT_TTL for entry in entries):
            raise ApiError('截图复核已过期，请重新识别。', HTTPStatus.CONFLICT)
        current = self.snapshots.candidate().token
        if entries[0][1] != entries[1][1] or entries[0][1] != current:
            raise ApiError('资料已更新，请重新识别两页截图。', HTTPStatus.CONFLICT)
        ability, status = deepcopy(entries[0][2]), deepcopy(entries[1][2])
        if ability.get('mode') != 'ability' or status.get('mode') != 'status':
            raise ApiError('需要一张能力页和一张状态页。')
        importer = ScreenshotImporter(self.rules)
        try:
            ability = importer.review_page(ability, payload['ability_review'])
            status = importer.review_page(status, payload['status_review'])
            result = importer.combine(ability, status)
        except (ValueError, TypeError, KeyError) as exc:
            raise ApiError(str(exc)) from exc
        result['draft']['id'] = ''
        result['draft']['revision'] = 0
        result['draft']['import_source'] = self._clean_import_source(result['draft']['import_source'])
        result['draft'] = self.team_view(result['draft'])
        return result

    @staticmethod
    def _verdict(minimum: float, maximum: float) -> str:
        if minimum >= 100:
            return "确定击杀"
        if maximum >= 100:
            return "乱数击杀"
        if minimum >= 50:
            return "稳定二击"
        if maximum >= 50:
            return "乱数二击"
        if minimum >= 33.34:
            return "稳定三击"
        if maximum >= 33.34:
            return "乱数三击"
        return "需要多次攻击"

    @staticmethod
    def _ko_chance(rolls, current_hp) -> float | None:
        """Return the conditional-on-hit KO chance represented by damage rolls."""
        if not isinstance(rolls, list) or not rolls:
            return None
        if not isinstance(current_hp, (int, float)) or isinstance(current_hp, bool):
            return None
        if any(not isinstance(value, (int, float)) or isinstance(value, bool) for value in rolls):
            return None
        knockouts = sum(value >= current_hp for value in rolls)
        return round(knockouts * 100 / len(rolls), 1)

    @staticmethod
    def _clean_member(member: dict | None):
        if not isinstance(member, dict):
            return None
        result = deepcopy(member)
        for key in ("pokemon", "nature_name", "ability_name", "item_name", "move_names"):
            result.pop(key, None)
        return result

    @staticmethod
    def _battle_state(value: dict | None) -> dict:
        value = value if isinstance(value, dict) else {}
        result = battle_defaults()
        result["hp"] = value.get("hp", 100)
        result["status"] = value.get("status", "")
        result["allies_fainted"] = value.get("allies_fainted", 0)
        boosts = value.get("boosts") if isinstance(value.get("boosts"), dict) else {}
        result["boosts"] = {key: boosts.get(key, 0) for key in result["boosts"]}
        for key in (
            "ability_on", "reflect", "light_screen", "protected", "helping_hand",
            "friend_guard", "tailwind", "aurora_veil", "charge_boost_included",
        ):
            result[key] = bool(value.get(key, False))
        if "copied_ability" in value:
            result["copied_ability"] = value["copied_ability"]
        return result

    def _combat_member(self, member: dict, form_identity: str | None,
                       ability: str | None = None) -> dict:
        member = self._clean_member(member)
        if member is None:
            raise ApiError("缺少我方预存配置。")
        identity = form_identity or member.get("identity")
        if identity != member.get("identity"):
            record = self._record(identity)
            stone = record.get("mega_item")
            if stone:
                member["item"] = stone
            member = self.damage.battle_form(member, identity)
        legal = self.rules.ability_keys(identity)
        if ability is not None:
            if ability != "__none__" and ability not in legal:
                raise ApiError("所选特性不属于当前战斗形态。")
            member["ability"] = ability
        return member

    @staticmethod
    def _effect_rows(result: dict) -> list[dict]:
        labels = {engine: label for _, engine, label, *_ in SUPPORT_EFFECTS}
        return [{**effect, "label": labels.get(effect.get("key"), effect.get("key"))}
                for effect in result.get("support_effects", [])]

    def _format_direction(self, attacker_record, defender_record, attacker: dict,
                          scenario: dict, comparison: dict, rows: list[dict],
                          results: list[dict], environment: dict) -> dict:
        moves = []
        for row, result in zip(rows, results):
            move = row.get("move") or {}
            item = {
                "id": move.get("key"), "name": move.get("name", "未填写"),
                "type": TYPE_NAMES.get(move.get("type"), move.get("type", "一般")),
                "category": CATEGORY_NAMES.get(move.get("category"), move.get("category")),
                "power": move.get("power"), "accuracy": move.get("accuracy"),
                "usage": move.get("usage_percent"), "description": move.get("description", ""),
                "status": result.get("status"), "reason": result.get("reason"),
                "hit_chance": row.get("hit_chance"), "priority": row.get("priority"),
                "support_effects": self._effect_rows(result),
            }
            if result.get("status") == "ok":
                low, high = result["percent_min"], result["percent_max"]
                verdict = self._verdict(low, high)
                item.update({
                    "damage": [round(low, 1), round(high, 1)],
                    "verdict": verdict,
                    "attacker_stats": result.get("attacker_stats"),
                    "defender_stats": result.get("defender_stats"),
                    "rolls": result.get("rolls"), "note": result.get("note"),
                    "minimum": result.get("minimum"), "maximum": result.get("maximum"),
                    "max_hp": result.get("max_hp"), "current_hp": result.get("current_hp"),
                    "ko_chance": self._ko_chance(
                        result.get("rolls"), result.get("current_hp")
                    ) if verdict == "乱数击杀" else None,
                    "details": result.get("details"), "multi_hit": result.get("multi_hit"),
                })
            moves.append(item)
        return {
            "attacker": self.pokemon_summary(attacker_record),
            "defender": self.pokemon_summary(defender_record),
            "preset": attacker["name"], "target_preset": scenario["name"],
            "spread_usage": comparison.get("spread_usage"),
            "scenario_points": deepcopy(comparison["member"]["points"]),
            "scenario_nature": self.rules.options["natures"].get(
                comparison["member"]["nature"], {}
            ).get("name", comparison["member"]["nature"]),
            "speed": self.damage.speed(attacker["member"], attacker["battle"], environment),
            "moves": moves,
        }

    def _configured_directions(self, own_member: dict, own_battle: dict, rival_record,
                               rival_ability: str, rival_battle: dict, environment: dict,
                               direction: str) -> list[dict]:
        scenarios = [item for item in self.damage.comparison_presets(rival_record)
                     if item["direction"] == direction]
        if not scenarios:
            raise ApiError("没有可用的对位情景。")
        scenarios = deepcopy(scenarios)
        for scenario in scenarios:
            scenario["member"]["ability"] = rival_ability
            scenario["battle"] = deepcopy(rival_battle)
        rows, jobs = self.damage.jobs(
            own_member, own_battle, scenarios, environment,
            common=direction == "对手 → 我方",
        )
        results = self.damage.execute(jobs)
        own_record = self.rules.record(own_member["identity"])
        formatted = []
        for index, comparison in enumerate(scenarios):
            selected = [(row, result) for row, result in zip(rows, results)
                        if row["scenario_index"] == index]
            selected_rows = [row for row, _ in selected]
            selected_results = [result for _, result in selected]
            if direction == "我方 → 对手":
                attacker = {"name": "预存队伍配置", "member": own_member,
                            "battle": own_battle}
                formatted.append(self._format_direction(
                    own_record, rival_record, attacker, comparison, comparison,
                    selected_rows, selected_results, environment,
                ))
                continue
            attacker = {"name": comparison["name"], "member": comparison["member"],
                        "battle": rival_battle}
            defender = {"name": "预存队伍配置", "member": own_member,
                        "battle": own_battle}
            formatted.append(self._format_direction(
                rival_record, own_record, attacker, defender, comparison,
                selected_rows, selected_results, environment,
            ))
        return formatted

    def _speed_comparison(self, own_member: dict, own_battle: dict, rival_record,
                          rival_ability: str, rival_battle: dict, environment: dict) -> dict:
        own = self.damage.speed(own_member, own_battle, environment)
        def relation(speed):
            if own.get("status") != "ok":
                return "待确认"
            if own["speed"] > speed:
                return "我方更快"
            if own["speed"] == speed:
                return "同速"
            return "对手更快"
        try:
            values = speed_lines(
                rival_record["base_stats"]["speed"],
                stage=rival_battle["boosts"]["speed"],
                tailwind=rival_battle["tailwind"],
                ability=rival_ability,
                ability_on=rival_battle["ability_on"],
                status=rival_battle["status"],
                weather=environment["weather"], terrain=environment["terrain"],
            )
            tiers = [
                {"name": tier[0], "speed": speed, "description": tier[4],
                 "kind": "reference", "relation": relation(speed)}
                for tier, speed in zip(SPEED_TIERS, values)
            ]
            common = [item for item in self.damage.comparison_presets(rival_record)
                      if item["direction"] == "我方 → 对手"
                      and item.get("spread_usage") is not None]
            for scenario in common:
                member = scenario["member"]
                nature = self.rules.options["natures"].get(member["nature"], {})
                nature_tenths = (11 if nature.get("increased") == "speed" else
                                 9 if nature.get("decreased") == "speed" else 10)
                speed = reference_speed(
                    rival_record["base_stats"]["speed"], member["points"]["speed"],
                    nature_tenths, False,
                    stage=rival_battle["boosts"]["speed"],
                    tailwind=rival_battle["tailwind"], ability=rival_ability,
                    ability_on=rival_battle["ability_on"], status=rival_battle["status"],
                    weather=environment["weather"], terrain=environment["terrain"],
                )
                points = " / ".join(
                    f"{STATS[key]} {value}" for key, value in member["points"].items()
                    if value
                ) or "无培养点"
                rate = scenario["spread_usage"]
                tiers.append({
                    "name": scenario["name"], "speed": speed, "kind": "common",
                    "usage": rate, "relation": relation(speed),
                    "description": (
                        f"常用培养分配（采用率 {rate:g}%）；"
                        f"{nature.get('name', member['nature'])}；{points}；未假设讲究围巾"
                    ),
                })
            tiers.sort(key=lambda item: -item["speed"])
        except (ValueError, KeyError, TypeError) as exc:
            tiers = []
            return {"own": own, "tiers": tiers, "reason": str(exc)}
        return {"own": own, "tiers": tiers}

    def quick_damage(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ApiError("计算参数无效。")
        own = self._record(payload.get("own_id"))
        rival_base = self._record(payload.get("rival_id"))
        own_member = self._clean_member(payload.get("own_member"))
        if own_member and own_member.get("identity") != self.rules.identity(own):
            raise ApiError("我方预存配置与当前选择不一致。")
        if own_member is None:
            own_member = self.damage.presets(own)[0]["member"]
        own_form_id = payload.get("own_form_id") or self.rules.identity(own)
        own_member = self._combat_member(own_member, own_form_id, payload.get("own_ability"))
        own = self._record(own_member["identity"])

        rival_form_id = payload.get("rival_form_id") or self.rules.identity(rival_base)
        family_ids = {self.rules.identity(record) for record in self.catalog.form_family(rival_base)}
        if rival_form_id not in family_ids:
            raise ApiError("对手战斗形态不属于当前选择的形态家族。")
        rival = self._record(rival_form_id)
        legal_rival_abilities = self.rules.ability_keys(rival_form_id)
        default_rival_ability = legal_rival_abilities[0] if len(legal_rival_abilities) == 1 else "__none__"
        rival_ability = payload.get("rival_ability", default_rival_ability)
        if rival_ability != "__none__" and rival_ability not in legal_rival_abilities:
            raise ApiError("所选对手特性不属于当前战斗形态。")

        own_battle = self._battle_state(payload.get("own_battle"))
        rival_battle = self._battle_state(payload.get("rival_battle"))
        if own_member.get("ability") == "trace":
            own_battle["copied_ability"] = payload.get("copied_ability", "__none__")
        source = payload.get("environment") or {}
        environment = {
            "weather": source.get("weather", ""), "terrain": source.get("terrain", ""),
            "targets": source.get("targets", 2), "critical": bool(source.get("critical", False)),
        }
        try:
            own_scenarios = self._configured_directions(
                own_member, own_battle, rival, rival_ability, rival_battle,
                environment, "我方 → 对手",
            )
            rival_scenarios = self._configured_directions(
                own_member, own_battle, rival, rival_ability, rival_battle,
                environment, "对手 → 我方",
            )
            return {
                "environment": environment,
                "own": own_scenarios[0],
                "rival": rival_scenarios[0],
                "own_scenarios": own_scenarios,
                "rival_scenarios": rival_scenarios,
                "speed_comparison": self._speed_comparison(
                    own_member, own_battle, rival, rival_ability, rival_battle, environment,
                ),
                "dataset_id": self.catalog.bundle_id,
            }
        except (ValueError, KeyError, TypeError) as exc:
            raise ApiError(str(exc)) from exc


class ChampionRequestHandler(BaseHTTPRequestHandler):
    server_version = "ChampionLab/1"

    @property
    def services(self) -> WebServices:
        return self.server.services  # type: ignore[attr-defined]

    @property
    def static_root(self) -> Path:
        return self.server.static_root  # type: ignore[attr-defined]

    def log_message(self, format, *args):
        if sys.stdout is not None:
            print(f"[web] {self.address_string()} - {format % args}")

    def _json(self, payload, status=HTTPStatus.OK):
        content = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)

    def _error(self, exc):
        status = exc.status if isinstance(exc, ApiError) else HTTPStatus.INTERNAL_SERVER_ERROR
        message = str(exc) if isinstance(exc, (ApiError, ValueError)) else "本地服务发生异常。"
        self._json({"error": message}, status)

    def _length(self, maximum: int) -> int:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ApiError("请求长度无效。") from exc
        if length <= 0 or length > maximum:
            raise ApiError("请求内容为空或过大。", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        return length

    def _json_body(self) -> dict:
        try:
            value = json.loads(self.rfile.read(self._length(MAX_JSON_BYTES)))
        except json.JSONDecodeError as exc:
            raise ApiError("JSON 请求格式无效。") from exc
        if not isinstance(value, dict):
            raise ApiError("请求须为 JSON 对象。")
        return value

    def _check_origin(self):
        origin = self.headers.get("Origin")
        if origin and (urlsplit(origin).hostname or "").lower() not in {"127.0.0.1", "localhost", "::1"}:
            raise ApiError("本地 API 拒绝了非本机网页请求。", HTTPStatus.FORBIDDEN)

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Allow", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self):
        try:
            route = urlsplit(self.path)
            query = parse_qs(route.query)
            if route.path == "/api/health":
                return self._json({"status": "ok", "version": __version__})
            if route.path == "/api/bootstrap":
                return self._json(self.services.bootstrap())
            if route.path == "/api/settings":
                return self._json(self.services.public_settings())
            if route.path == "/api/teams":
                return self._json(self.services.teams())
            if route.path == "/api/pokemon":
                try:
                    limit = int(query.get("limit", ["30"])[0])
                    offset = int(query.get("offset", ["0"])[0])
                except ValueError as exc:
                    raise ApiError("搜索数量或起点无效。") from exc
                return self._json(self.services.search_pokemon(query.get("q", [""])[0], limit=limit, offset=offset))
            if route.path == "/api/pokemon/detail":
                return self._json(self.services.pokemon_detail(query.get("id", [""])[0]))
            if route.path == "/api/pokemon/options":
                return self._json(self.services.team_options(query.get("id", [""])[0]))
            if route.path == "/api/damage/options":
                return self._json(self.services.damage_options(query.get("id", [""])[0]))
            if route.path == "/api/pokemon/sprite":
                return self._file(self.services.sprite_path(query.get("id", [""])[0]), cache=True)
            if route.path.startswith("/api/"):
                raise ApiError("接口不存在。", HTTPStatus.NOT_FOUND)
            return self._static(route.path)
        except Exception as exc:
            return self._error(exc)

    def do_POST(self):
        try:
            self._check_origin()
            parsed = urlsplit(self.path)
            route = parsed.path
            if route == "/api/recognize":
                content = self.rfile.read(self._length(MAX_IMAGE_BYTES))
                return self._json(self.services.recognize_bytes(content))
            if route == "/api/team-import/recognize":
                query = parse_qs(parsed.query)
                mode = query.get('mode', [''])[0]
                content = self.rfile.read(self._length(MAX_IMAGE_BYTES))
                return self._json(self.services.team_import_recognize(content, mode))
            payload = self._json_body()
            if route == "/api/settings":
                result = self.services.update_settings(payload)
            elif route == "/api/teams":
                result = self.services.save_team(payload)
            elif route == "/api/teams/delete":
                result = self.services.delete_team(payload)
            elif route == "/api/obs/sources":
                result = self.services.obs_sources(payload)
            elif route == "/api/obs/capture":
                result = self.services.obs_capture(payload)
            elif route == "/api/team-import/obs-capture":
                result = self.services.team_import_obs_capture(payload)
            elif route == "/api/team-import/combine":
                result = self.services.team_import_combine(payload)
            elif route == "/api/damage/quick":
                result = self.services.quick_damage(payload)
            else:
                raise ApiError("接口不存在。", HTTPStatus.NOT_FOUND)
            return self._json(result)
        except Exception as exc:
            return self._error(exc)

    def _file(self, path: Path, *, cache=False):
        content = path.read_bytes()
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "public, max-age=86400" if cache else "no-cache")
        self.end_headers()
        self.wfile.write(content)

    def _static(self, route: str):
        root = self.static_root.resolve()
        relative = unquote(route).lstrip("/") or "index.html"
        requested = (root / relative).resolve()
        if not requested.is_relative_to(root):
            raise ApiError("静态资源路径无效。", HTTPStatus.FORBIDDEN)
        if requested.is_file():
            return self._file(requested)
        index = root / "index.html"
        if index.is_file() and "." not in Path(relative).name:
            return self._file(index)
        raise ApiError("网页资源不存在，请先运行网页构建。", HTTPStatus.NOT_FOUND)


def create_server(*, host="127.0.0.1", port=DEFAULT_PORT, static_root=None,
                  services: WebServices | None = None, services_factory=None):
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("为保护本机队伍与 OBS 配置，网页服务只能监听本机回环地址。")
    root = Path(static_root or app_paths().resource("web/dist"))
    server = LocalWebServer((host, port), ChampionRequestHandler)
    try:
        server.services = services or (services_factory() if services_factory else WebServices())
    except Exception:
        server.server_close()
        raise
    server.static_root = root
    return server


def is_champion_lab_running(port=DEFAULT_PORT):
    """Distinguish an existing Champion Lab instance from an unrelated local service."""
    connection = HTTPConnection('127.0.0.1', int(port), timeout=0.6)
    try:
        connection.request('GET', '/api/health', headers={'Accept': 'application/json'})
        response = connection.getresponse()
        response.read()
        return response.status == HTTPStatus.OK and response.getheader(
            'Server', '').startswith('ChampionLab/')
    except (OSError, ValueError, HTTPException):
        return False
    finally:
        connection.close()


def reuse_running_instance(url, *, no_browser=False):
    print(f"Champion Lab 网页版已经运行：{url}")
    if not no_browser:
        webbrowser.open(url)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="启动 Champion Lab 本地网页版。")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--static-root", type=Path)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--layout", type=Path)
    args = parser.parse_args(argv)
    url = f"http://127.0.0.1:{args.port}"
    if is_champion_lab_running(args.port):
        return reuse_running_instance(url, no_browser=args.no_browser)
    services = WebServices(data_dir=args.data_dir, layout_path=args.layout)
    try:
        server = create_server(port=args.port, static_root=args.static_root, services=services)
    except OSError as exc:
        if is_champion_lab_running(args.port):
            return reuse_running_instance(url, no_browser=args.no_browser)
        raise SystemExit(f"无法启动网页版：本机端口 {args.port} 已被其他程序占用。") from exc
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"Champion Lab 网页版已启动：{url}")
    print("关闭此窗口或按 Ctrl+C 即可停止本地服务。")
    if not args.no_browser:
        Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

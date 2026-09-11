"""Atomic files, confined paths, immutable bundles and a process-wide update lock."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath

from PIL import Image

STAT_KEYS = {"hp", "attack", "defense", "special_attack", "special_defense", "speed"}


def now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def digest(content):
    return hashlib.sha256(content).hexdigest()


def atomic_bytes(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temp.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def save_json(path, value):
    atomic_bytes(path, json_bytes(value))


def confined(root, relative):
    """Reject absolute, traversal, NTFS stream and symlink/junction escapes."""
    root = Path(root).resolve()
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError(f"非法资料路径：{relative!r}")
    parts = relative.split("/")
    if (PureWindowsPath(relative).drive or relative.startswith("/")
            or any(p in ("", ".", "..") or re.search(r'[<>:"|?*\x00-\x1f]', p)
                   or p.endswith((".", " ")) or re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", p)
                   for p in parts)):
        raise ValueError(f"非法资料路径：{relative!r}")
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"资料路径越界：{relative}")
    return path


@contextmanager
def update_lock(root):
    """OS-owned lock: a killed updater does not leave an unrecoverable stale lock."""
    path = confined(root, "_update.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError("已有更新任务运行，请等待完成后重试。") from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def resolve_dataset(root):
    """Resolve once per recognizer/session; existing instances keep their old bundle."""
    root = Path(root).resolve()
    pointer = root / "current.json"
    if not pointer.exists():
        return root
    value = read_json(pointer)
    bundle_id = value["bundle_id"]
    if not re.fullmatch(r"[a-z0-9-]{1,80}", bundle_id):
        raise ValueError("资料包 ID 非法")
    bundle = confined(root, f"_versions/{bundle_id}")
    manifest = confined(bundle, "manifest.json").read_bytes()
    if digest(manifest) != value["manifest_sha256"]:
        raise ValueError("当前资料包清单校验失败，请运行 validate 或 rollback。")
    meta = json.loads(manifest)
    if meta["bundle_id"] != bundle_id or digest((bundle / "index.json").read_bytes()) != meta["files"]["index.json"]:
        raise ValueError("当前资料索引校验失败，请运行 validate 或 rollback。")
    return bundle


def validate_index(index, folder):
    records = index.get("pokemon")
    if not isinstance(records, list) or not records:
        raise ValueError("资料索引为空")
    names, identities = set(), set()
    images = ready = 0
    for record in records:
        name, directory = record["name"], record["directory"]
        if name in names or directory.casefold() in identities:
            raise ValueError(f"重复名称／目录：{name}")
        names.add(name)
        identities.add(directory.casefold())
        confined(folder, directory)
        stats = record["base_stats"]
        if set(stats) != STAT_KEYS or any(type(v) is not int or not 0 < v <= 255 for v in stats.values()):
            raise ValueError(f"非法种族值：{name}")
        if record["base_stat_total"] != sum(stats.values()):
            raise ValueError(f"种族值总和不符：{name}")
        if record.get("types") is not None and (not 1 <= len(record["types"]) <= 2
                or any(t not in TYPE_NAMES for t in record["types"])):
            raise ValueError(f"非法属性：{name}")
        for variant, asset in record["images"].items():
            if variant not in {"normal", "shiny"}:
                raise ValueError(f"非法图标版本：{variant}")
            content = confined(folder, f"{directory}/{asset['file']}").read_bytes()
            if digest(content) != asset["sha256"]:
                raise ValueError(f"图标校验失败：{name}/{variant}")
            import io
            with Image.open(io.BytesIO(content)) as image:
                if image.format != "PNG" or image.size != (128, 128) or "A" not in image.getbands():
                    raise ValueError(f"图标规格不符：{name}/{variant}，需要 128x128 透明 PNG")
                if [image.width, image.height] != [asset["width"], asset["height"]]:
                    raise ValueError(f"图标尺寸元数据不符：{name}")
                image.verify()
            images += 1
        complete = set(record["images"]) == {"normal", "shiny"}
        if record.get("recognition_ready", complete) != complete:
            raise ValueError(f"识别就绪状态不符：{name}")
        ready += complete
    if index["form_count"] != len(records) or index["species_count"] != len({r["dex_number"] for r in records}):
        raise ValueError("索引条目计数不符")
    return {"forms": len(records), "species": index["species_count"], "images": images,
            "recognition_ready": ready, "pending_assets": len(records) - ready}


TYPE_NAMES = dict(zip(
    "normal fire water electric grass ice fighting poison ground flying psychic bug rock ghost dragon dark steel fairy".split(),
    "一般 火 水 电 草 冰 格斗 毒 地面 飞行 超能力 虫 岩石 幽灵 龙 恶 钢 妖精".split()))


def validate_bundle(folder):
    folder = Path(folder).resolve()
    manifest = read_json(folder / "manifest.json")
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("files"), dict):
        raise ValueError("不支持的资料包清单")
    for relative, checksum in manifest["files"].items():
        if digest(confined(folder, relative).read_bytes()) != checksum:
            raise ValueError(f"资料包文件校验失败：{relative}")
    if "index.json" not in manifest["files"] or "recognition_identity_groups.json" not in manifest["files"]:
        raise ValueError("资料包缺少索引或外观合并配置")
    index = read_json(folder / "index.json")
    for record in index["pokemon"]:
        required = [f"{record['directory']}/{record['name']}.json"]
        required += [f"{record['directory']}/{a['file']}" for a in record["images"].values()]
        if any(p not in manifest["files"] for p in required):
            raise ValueError("索引引用了清单外的文件")
        if read_json(confined(folder, required[0])) != record:
            raise ValueError(f"单体资料与索引不一致：{record['name']}")
    return {**validate_index(index, folder), "bundle_id": manifest["bundle_id"]}


def make_bundle(root, index, assets_root, identity_policy, extra_files=None):
    """Write every file before publishing anything. Unpublished stages are harmless."""
    stage = confined(root, f"_staging/{uuid.uuid4().hex}")
    stage.mkdir(parents=True)
    for record in index["pokemon"]:
        for asset in record["images"].values():
            relative = f"{record['directory']}/{asset['file']}"
            dest = confined(stage, relative)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(confined(assets_root, relative), dest)
        save_json(confined(stage, f"{record['directory']}/{record['name']}.json"), record)
    save_json(stage / "index.json", index)
    save_json(stage / "recognition_identity_groups.json", identity_policy)
    for relative, content in (extra_files or {}).items():
        atomic_bytes(confined(stage, relative), content)
    files = {p.relative_to(stage).as_posix(): digest(p.read_bytes()) for p in sorted(stage.rglob("*")) if p.is_file()}
    bundle_id = "data-" + digest(json_bytes(files))[:24]
    save_json(stage / "manifest.json", {"schema_version": 1, "bundle_id": bundle_id, "created_at": now(), "files": files})
    validate_bundle(stage)
    target = confined(root, f"_versions/{bundle_id}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        validate_bundle(target)
        discard_stage(root, stage)
    else:
        if not stage.resolve().is_relative_to(Path(root).resolve()) or not target.resolve().is_relative_to(Path(root).resolve()):
            raise ValueError("资料包目标越界")
        stage.rename(target)
    return target


def discard_stage(root, stage):
    """Remove only a verified updater-owned UUID directory, never a data/version directory."""
    stage = Path(stage)
    staging_root = confined(root, "_staging")
    if (stage.is_symlink() or (hasattr(stage, "is_junction") and stage.is_junction())
            or stage.resolve().parent != staging_root
            or not re.fullmatch(r"(?:assets-)?[0-9a-f]{32}", stage.name)):
        raise ValueError("拒绝清理非本次更新暂存目录")
    # Both resolved absolute paths have been checked inside the intended data root.
    if stage.exists():
        shutil.rmtree(stage.resolve())


def publish(root, bundle):
    root, bundle = Path(root).resolve(), Path(bundle).resolve()
    if bundle.parent != confined(root, "_versions"):
        raise ValueError("只能发布本地已验证的版本目录")
    validate_bundle(bundle)
    previous = read_json(root / "current.json") if (root / "current.json").exists() else {}
    bundle_id = bundle.name
    if previous.get("bundle_id") == bundle_id:
        return
    history = list(previous.get("history", []))
    if previous.get("bundle_id"):
        history.append(previous["bundle_id"])
    save_json(root / "current.json", {"schema_version": 1, "bundle_id": bundle_id,
              "manifest_sha256": digest((bundle / "manifest.json").read_bytes()), "published_at": now(), "history": history})


def export_compatibility_index(root):
    """Derived convenience export. current.json remains the only authoritative pointer."""
    root = Path(root).resolve()
    bundle = resolve_dataset(root)
    if bundle == root:
        return
    index = read_json(bundle / "index.json")
    index["active_bundle_id"] = bundle.name
    index["compatibility_note"] = "派生索引；权威入口为 current.json。单体 JSON 与 PNG 位于对应版本目录。"
    for record in index["pokemon"]:
        record["directory"] = f"_versions/{bundle.name}/{record['directory']}"
    save_json(root / "index.json", index)

"""Version updates: check / sync / validate / rollback. Run from any directory."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from champion_assistant.data.storage import (now, read_json, resolve_dataset, update_lock,
                                             validate_bundle, validate_index)
from champion_assistant.data.sync import rollback, run_update, write_report


def main(argv=None):
    parser = argparse.ArgumentParser(description="自动检查和同步 Champions 物种、属性、种族值、招式及图标；默认面向双打，不导入单打统计。")
    parser.add_argument("operation", choices=["check", "sync", "validate", "rollback"])
    parser.add_argument("--data-dir", type=Path, default=ROOT / "pokemon", help="现有资料根目录")
    parser.add_argument("--source-dir", type=Path, help="使用含 pokedex.html 和 wiki-roster.html 的离线快照，报告明确标记离线")
    parser.add_argument("--refresh-images", action="store_true", help="sync 时重新验证图片 URL，否则复用已校验图片")
    parser.add_argument("--to", dest="target", help="rollback 目标包 ID；省略则回到上次发布版本")
    parser.add_argument("--bundle", type=Path, help="validate 指定版本目录；省略则校验当前有效目录")
    args = parser.parse_args(argv)
    if args.target and args.operation != "rollback" or args.bundle and args.operation != "validate":
        parser.error("--to 仅用于 rollback，--bundle 仅用于 validate")
    if (args.source_dir or args.refresh_images) and args.operation not in {"check", "sync"}:
        parser.error("来源／图标选项仅用于 check 或 sync")
    if args.refresh_images and args.operation != "sync":
        parser.error("--refresh-images 仅用于 sync")
    try:
        with update_lock(args.data_dir):
            print({"check": "正在重新检查公开资料来源……", "sync": "正在同步；有效资料在完成校验前保持原状……",
                   "validate": "正在校验本地资料……", "rollback": "正在校验并恢复历史资料包……"}[args.operation], flush=True)
            if args.operation in {"check", "sync"}:
                result = run_update(args.data_dir, args.operation, args.source_dir, args.refresh_images)
            elif args.operation == "rollback":
                result = rollback(args.data_dir, args.target)
            else:
                folder = args.bundle or resolve_dataset(args.data_dir)
                result = validate_bundle(folder) if (folder / "manifest.json").exists() else validate_index(read_json(folder / "index.json"), folder)
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 0
        print(f"状态：{result['status']}")
        if "source_count" in result:
            print(f"来源 {result['source_count']} 条；新增 {len(result['new_species'])} 个物种、{len(result['added'])} 个形态；变更 {len(result['changed'])} 条。")
            for value in result["new_species"]:
                print(f"  + {value['name']}")
            print(f"图标待就绪 {len(result['pending_assets'])}；映射待处理 {len(result['unmapped'])}；退签候选 {len(result['removed_candidate'])}。")
            print(f"招式资料 {result.get('move_count', 0)} 条；招式变更：{'是' if result.get('moves_changed') else '否'}。")
            print("当前仅同步静态资料，不含模式使用率；规则标签不等于已核验的当前合法性。")
        if result.get("published_bundle"):
            print("有效版本：" + result["published_bundle"])
        print("完整报告：" + str((args.data_dir / "_reports/latest.json").resolve()))
        return 2 if args.operation == "check" and result.get("has_changes") else 0
    except (KeyboardInterrupt, Exception) as exc:
        # OS lock is released by its context manager even after cancellation.
        message = "用户取消；已发布数据未被未完成批次覆盖。" if isinstance(exc, KeyboardInterrupt) else str(exc)
        print("更新未完成：" + message, file=sys.stderr)
        try:
            write_report(args.data_dir, {"operation": args.operation, "checked_at": now(), "status": "failed", "error": message})
        except OSError:
            pass
        return 130 if isinstance(exc, KeyboardInterrupt) else 1


if __name__ == "__main__":
    raise SystemExit(main())

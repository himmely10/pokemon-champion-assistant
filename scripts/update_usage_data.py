"""Refresh doubles moves, training spreads and nature usage for the daily updater."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from champion_assistant.data.usage import update_usage, reparse_usage_cache


def main():
    parser = argparse.ArgumentParser(description="更新 OP.GG 当前赛季双打招式、培养点和性格统计")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "pokemon/_usage")
    parser.add_argument("--if-due", action="store_true", help="上次完整同步未满 24 小时则跳过")
    parser.add_argument("--json", action="store_true", help="输出单行结果供桌面程序读取")
    parser.add_argument('--reparse-cache',action='store_true',help='从同赛季同查询的本地原始响应补充培养点／性格统计，保留原时间')
    args = parser.parse_args()
    try:
        progress = (lambda m: None) if args.json else (lambda m: print(m, flush=True))
        result = reparse_usage_cache(args.data_dir) if args.reparse_cache else update_usage(args.data_dir, due_hours=24 if args.if_due else None, progress=progress)
        print(json.dumps(result, ensure_ascii=False, indent=None if args.json else 2))
        return 2 if result["status"] == "partial" else 0
    except Exception as exc:
        print(f"采用率更新失败，旧快照保留：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

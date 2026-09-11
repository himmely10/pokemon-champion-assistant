"""Usage: python recognize_opponent.py 例子.png --output-dir artifacts/opponent"""
import argparse
import sys
from pathlib import Path

from PIL import Image

from champion_assistant.recognition import DEFAULT_LAYOUT, PROJECT_ROOT, OpponentRecognizer
from champion_assistant.report import save_report


def main(argv=None):
    parser = argparse.ArgumentParser(description="识别 Champions 选队画面右侧六只宝可梦，输出简体中文名。")
    parser.add_argument("image", type=Path, help="完整游戏截图，默认布局为 16:9")
    parser.add_argument("--layout", type=Path, default=DEFAULT_LAYOUT, help="裁剪位置与匹配阈值 JSON")
    parser.add_argument("--data-dir", type=Path, default=PROJECT_ROOT / "pokemon")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "artifacts/opponent")
    args = parser.parse_args(argv)
    try:
        print("加载图标库并匹配右侧六个槽位……", flush=True)
        recognizer = OpponentRecognizer(args.data_dir, args.layout)
        with Image.open(args.image) as image:
            result, normalized, crops = recognizer.recognize(image)
        result["input_file"] = str(args.image.resolve())
        save_report(result, normalized, crops, args.output_dir, recognizer.data_dir)
        for item in result["opponent"]:
            print(f"{item['slot']}. {item['name'] or '待确认'}  [相似度 {item['similarity']:.3f}]")
            if item["form_status"] == "indistinguishable":
                print("   同图标形态无法区分：" + "、".join(item["form_candidates"]))
        print(f"已识别 {result['recognized_count']}/6；匹配耗时 {result['elapsed_seconds']:.2f} 秒。")
        print(f"预览：{(args.output_dir / 'report.html').resolve()}")
        return 0 if result["recognized_count"] == 6 else 2
    except (OSError, ValueError, KeyError) as exc:
        print(f"识别失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

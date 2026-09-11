"""Write machine-readable results and a self-contained visual review page."""
import base64
import html
import io
import json
from pathlib import Path

from PIL import Image, ImageDraw


def data_url(image, format="PNG"):
    buffer = io.BytesIO()
    image.save(buffer, format=format)
    mime = "image/jpeg" if format == "JPEG" else "image/png"
    return f"data:{mime};base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def save_report(result, normalized, crops, output_dir: Path, data_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    annotated = normalized.copy()
    draw = ImageDraw.Draw(annotated)
    rows = []
    names = []
    for item, crop in zip(result["opponent"], crops):
        number = item["slot"]
        crop.save(output_dir / f"slot_{number}.png")
        color = "#22c55e" if item["status"] == "recognized" else "#f59e0b"
        box = item["crop_box_reference"]
        draw.rectangle(box, outline=color, width=3)
        draw.text((box[0] + 4, box[1] + 3), str(number), fill="white", stroke_width=2, stroke_fill="black")
        display = item["name"] or "待确认"
        names.append(f"{number}. {display}")
        template_html = ""
        if item["candidates"]:
            with Image.open(data_dir / item["candidates"][0]["template_path"]) as template:
                template_html = f'<img alt="最佳候选模板" src="{data_url(template)}">'
        candidate_text = "；".join(f"{c['name']} {c['similarity']:.3f}" for c in item["candidates"])
        note = ""
        if item["form_status"] == "indistinguishable":
            note = "图标相同，无法区分：" + "、".join(item["form_candidates"])
        elif item["status"] != "recognized":
            note = "分数不足或候选接近，请核对截图/裁剪位置。"
        rows.append(f'''<article>
          <div class="number">{number:02}</div><div class="images">
          <figure><img alt="截图槽位 {number}" src="{data_url(crop)}"><figcaption>截图</figcaption></figure>
          <figure>{template_html}<figcaption>最佳候选模板</figcaption></figure></div>
          <div class="info"><h2>{html.escape(display)}</h2><p class="note">{html.escape(note)}</p>
          <p>相似度 <b>{item['similarity']:.3f}</b> · 候选差距 {item['margin']:.3f}</p>
          <details><summary>查看前三个候选</summary><p>{html.escape(candidate_text)}</p></details></div></article>''')
    annotated.save(output_dir / "annotated.jpg", quality=90)
    preview = annotated.copy()
    preview.thumbnail((1280, 720))
    doc = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1"><title>对手宝可梦识别结果</title>
    <style>body{{margin:0;background:#101725;color:#edf2fa;font-family:system-ui,"Microsoft YaHei",sans-serif}}
    main{{max-width:1040px;margin:auto;padding:32px 20px}}h1{{margin:0 0 12px;font-size:28px}}
    header p,.note,figcaption,details{{color:#9eafc8}}.summary{{color:#7ee5b6}}.preview{{width:100%;border-radius:12px;margin:20px 0}}
    article{{display:flex;align-items:center;gap:20px;background:#1a2436;margin:12px 0;padding:20px;border-radius:12px}}
    .number{{font-size:24px;color:#6e89b2}}.images{{display:flex;gap:10px}}figure{{margin:0;text-align:center}}
    figure img{{width:130px;height:100px;object-fit:contain;background:#33415a;border-radius:6px}}figcaption{{font-size:12px}}
    h2{{font-size:22px;margin:0 0 6px}}p{{margin:8px 0}}.note{{font-size:13px}}summary{{cursor:pointer}}
    @media(max-width:700px){{article{{flex-wrap:wrap;gap:12px}}.info{{width:100%}}}}</style>
    <main><header><h1>对手队伍识别</h1><p>按画面右侧从上到下排列</p>
    <p class="summary">已识别 {result['recognized_count']} / 6 · 匹配耗时 {result['elapsed_seconds']:.2f} 秒</p>
    <p>相似度是模板匹配分数，不代表正确率。低分结果显示待确认。</p></header>
    <img class="preview" alt="截图及六个裁剪区域" src="{data_url(preview, 'JPEG')}">
    {''.join(rows)}<footer><p>当前为固定选队布局原型；本页仅保存在本机。</p></footer></main></html>'''
    (output_dir / "report.html").write_text(doc, encoding="utf-8")
    (output_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "names.txt").write_text("\n".join(names) + "\n", encoding="utf-8")

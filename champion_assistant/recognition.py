"""Match opponent icons against the entire local sprite collection.

The layout fixes positions, not Pokémon identities. Normal/shiny templates and
explicitly grouped cosmetic forms compete as one recognition identity.
"""
from __future__ import annotations

import json
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from .data.storage import confined, digest, read_json, resolve_dataset

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LAYOUT = PROJECT_ROOT / "config/opponent_team_preview.json"
IDENTITY_GROUPS = PROJECT_ROOT / "config/recognition_identity_groups.json"


@dataclass
class Template:
    members: list[dict]
    scaled: list[np.ndarray]


class OpponentRecognizer:
    def __init__(self, data_dir: Path | None = None, layout_path: Path | None = None):
        self.data_dir = resolve_dataset(Path(data_dir or PROJECT_ROOT / "pokemon"))
        self.dataset_id = self.data_dir.name if (self.data_dir / "manifest.json").exists() else "legacy"
        self.layout = json.loads(Path(layout_path or DEFAULT_LAYOUT).read_text(encoding="utf-8"))
        self._validate_layout()
        cv2.setNumThreads(1)
        index = json.loads((self.data_dir / "index.json").read_text(encoding="utf-8"))
        policy_path = self.data_dir / "recognition_identity_groups.json"
        if self.dataset_id != "legacy":
            manifest = read_json(self.data_dir / "manifest.json")
            if digest(policy_path.read_bytes()) != manifest["files"]["recognition_identity_groups.json"]:
                raise ValueError("外观合并规则校验失败，请运行资料 validate。")
        policy = json.loads((policy_path if policy_path.exists() else IDENTITY_GROUPS).read_text(encoding="utf-8"))
        display_groups = {}
        for group in policy["groups"]:
            for slug in group["source_slugs"]:
                if slug in display_groups:
                    raise ValueError(f"外观形态合并规则重复：{slug}")
                display_groups[slug] = group["name"]
        groups = defaultdict(list)
        for record in index["pokemon"]:
            if not record.get("recognition_ready", True):
                continue
            for variant, asset in record["images"].items():
                groups[asset["sha256"]].append({
                    "name": display_groups.get(record["source_slug"], record["name"]),
                    "cosmetic_merged": record["source_slug"] in display_groups,
                    "species_name": record["species_name"],
                    "dex_number": record["dex_number"], "variant": variant,
                    "path": f"{record['directory']}/{asset['file']}",
                })
        self.templates = []
        for checksum, members in groups.items():
            template_path = confined(self.data_dir, members[0]["path"])
            if digest(template_path.read_bytes()) != checksum:
                raise ValueError(f"图标校验失败：{members[0]['name']}")
            with Image.open(template_path) as image:
                rgba = np.array(image.convert("RGBA"))
            scaled = [cv2.resize(rgba, (size, size), interpolation=cv2.INTER_AREA)
                      for size in self.layout["template_sizes"]]
            self.templates.append(Template(members, scaled))
        if not self.templates:
            raise ValueError("图标库为空，请先采集 pokemon 数据。")

    def _validate_layout(self):
        width, height = self.layout["reference_size"]
        if width <= 0 or height <= 0 or len(self.layout["slots"]) != 6:
            raise ValueError("布局必须包含有效的参考尺寸和六个槽位。")
        for x1, y1, x2, y2 in self.layout["slots"]:
            if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
                raise ValueError("槽位坐标超出参考画面范围。")
        sizes = self.layout["template_sizes"]
        if not sizes or any(not isinstance(s, int) or s < 8 for s in sizes):
            raise ValueError("模板尺寸必须为不小于 8 的整数。")
        if not 0 <= self.layout["min_score"] <= 1 or not 0 <= self.layout["min_margin"] <= 1:
            raise ValueError("识别阈值必须在 0 到 1 之间。")
        padding = self.layout.get("slot_padding_y", 0)
        if type(padding) is not int or not 0 <= padding <= 16:
            raise ValueError("槽位垂直扩展必须为 0 到 16 的整数参考像素。")

    def crop_boxes(self) -> list[list[int]]:
        """Expand search space within the gap midpoint, never into another slot.

        Missing padding retains the original layout behavior. Geometry is computed
        per call so diagnostics and recognition share exactly the same boxes.
        """
        _, height = self.layout["reference_size"]
        padding = self.layout.get("slot_padding_y", 0)
        boxes = []
        for x1, y1, x2, y2 in self.layout["slots"]:
            top, bottom = max(0, y1 - padding), min(height, y2 + padding)
            for ox1, oy1, ox2, oy2 in self.layout["slots"]:
                if min(x2, ox2) <= max(x1, ox1):
                    continue
                if oy2 <= y1:
                    top = max(top, (oy2 + y1 + 1) // 2)
                elif oy1 >= y2:
                    bottom = min(bottom, (y2 + oy1) // 2)
            boxes.append([x1, top, x2, bottom])
        return boxes

    def prepare_image(self, image: Image.Image) -> tuple[Image.Image, list[Image.Image]]:
        width, height = self.layout["reference_size"]
        aspect_error = abs((image.width / image.height) / (width / height) - 1)
        if aspect_error > 0.02:
            raise ValueError("截图比例与布局不符；默认需要完整 16:9 游戏画面，请裁掉窗口边框或使用自定义布局。")
        normalized = image.convert("RGB").resize((width, height), Image.Resampling.LANCZOS)
        return normalized, [normalized.crop(box) for box in self.crop_boxes()]

    def match_slot(self, crop: Image.Image, slot: int = 1) -> dict:
        roi = np.array(crop.convert("RGB"))
        base = {"slot": slot, "status": "unknown", "name": None, "species_name": None,
                "similarity": 0.0, "margin": 0.0, "form_status": "unknown", "form_candidates": [], "candidates": []}
        if float(np.std(roi.astype(np.float32), axis=(0, 1)).max()) < 3.0:
            return {**base, "reason": "empty_or_uniform_region"}
        background = np.median(roi.reshape(-1, 3), axis=0)
        identities = {}
        for template in self.templates:
            best_score, best_geometry = -1.0, None
            for rgba in template.scaled:
                size = rgba.shape[0]
                if size > min(roi.shape[:2]):
                    continue
                alpha = rgba[:, :, 3:] / 255.0
                composite = np.uint8(rgba[:, :, :3] * alpha + background * (1 - alpha))
                response = cv2.matchTemplate(roi, composite, cv2.TM_CCOEFF_NORMED)
                response = np.nan_to_num(response, nan=-1.0, posinf=-1.0, neginf=-1.0)
                _, score, _, location = cv2.minMaxLoc(response)
                if score > best_score:
                    best_score = score
                    best_geometry = {"x": location[0], "y": location[1], "size": size}
            if best_geometry is None:
                continue
            names = tuple(sorted({m["name"] for m in template.members}))
            if names in identities and identities[names]["similarity"] >= best_score:
                continue
            species = sorted({m["species_name"] for m in template.members})
            display = names[0] if len(names) == 1 else (species[0] if len(species) == 1 else " / ".join(species))
            member = template.members[0]
            identities[names] = {
                "name": display, "species_name": species[0] if len(species) == 1 else None,
                "dex_number": member["dex_number"], "similarity": best_score,
                "form_candidates": [] if all(m["cosmetic_merged"] for m in template.members) else list(names),
                "cosmetic_merged": all(m["cosmetic_merged"] for m in template.members),
                "template_path": member["path"],
                "best_template_variant": member["variant"], "match_box": best_geometry,
            }
        candidates = sorted(identities.values(), key=lambda c: c["similarity"], reverse=True)
        if not candidates:
            return {**base, "reason": "no_template_fits_region"}
        first = candidates[0]
        margin = first["similarity"] - (candidates[1]["similarity"] if len(candidates) > 1 else 0)
        accepted = first["similarity"] >= self.layout["min_score"] and margin >= self.layout["min_margin"]
        base.update({"similarity": round(first["similarity"], 6), "margin": round(margin, 6),
                     "candidates": [{**c, "similarity": round(c["similarity"], 6)} for c in candidates[:3]]})
        if accepted:
            base.update({"status": "recognized", "name": first["name"], "species_name": first["species_name"],
                         "dex_number": first["dex_number"], "form_candidates": first["form_candidates"],
                         "form_status": ("not_applicable" if first["cosmetic_merged"] else
                                         "indistinguishable" if len(first["form_candidates"]) > 1 else "matched"),
                         "reason": None})
        else:
            base["reason"] = "low_similarity" if first["similarity"] < self.layout["min_score"] else "ambiguous_match"
        return base

    def recognize(self, image: Image.Image) -> tuple[dict, Image.Image, list[Image.Image]]:
        start = time.perf_counter()
        normalized, crops = self.prepare_image(image)
        with ThreadPoolExecutor(max_workers=3) as executor:
            results = list(executor.map(lambda args: self.match_slot(*args), zip(crops, range(1, 7))))
        width, height = self.layout["reference_size"]
        def input_box(box):
            return [round(box[0] * image.width / width), round(box[1] * image.height / height),
                    round(box[2] * image.width / width), round(box[3] * image.height / height)]

        for result, box in zip(results, self.crop_boxes()):
            result["crop_box_reference"] = box
            result["crop_box_input"] = input_box(box)
            for candidate in result["candidates"]:
                match = candidate["match_box"]
                x, y = box[0] + match["x"], box[1] + match["y"]
                reference = [x, y, x + match["size"], y + match["size"]]
                candidate["match_box_reference"] = reference
                candidate["match_box_input"] = input_box(reference)
        report = {"schema_version": 1, "dataset_id": self.dataset_id, "layout": self.layout["name"], "input_size": list(image.size),
                  "reference_size": [width, height], "unique_templates": len(self.templates),
                  "thresholds": {k: self.layout[k] for k in ("min_score", "min_margin")},
                  "score_note": "模板相关性分数，不是识别正确率或概率。普通/闪光仅作为匹配模板，不输出闪光判定。",
                  "elapsed_seconds": round(time.perf_counter() - start, 3),
                  "recognized_count": sum(r["status"] == "recognized" for r in results), "opponent": results}
        return report, normalized, crops

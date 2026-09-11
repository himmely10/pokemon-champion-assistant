"""Real screenshot regression and failure cases; not a general accuracy benchmark."""
import io
import json

import numpy as np
import pytest
from PIL import Image

from champion_assistant.recognition import PROJECT_ROOT, OpponentRecognizer
from champion_assistant.report import save_report


EXPECTED = ["苍炎刃鬼", "风妖精", "巨金怪", "来悲粗茶", "烈咬陆鲨", "姆克鹰"]


@pytest.fixture(scope="module")
def recognizer():
    return OpponentRecognizer()


@pytest.fixture(scope="module")
def screenshot():
    with Image.open(PROJECT_ROOT / "例子.png") as image:
        return image.convert("RGB")


def assert_team(result, names):
    assert result["recognized_count"] == 6
    assert [r["name"] for r in result["opponent"]] == names


def test_real_screenshot_and_output_files(recognizer, screenshot, tmp_path):
    result, normalized, crops = recognizer.recognize(screenshot)
    assert_team(result, EXPECTED)
    tea = result["opponent"][3]
    assert tea["form_status"] == "not_applicable"
    assert tea["form_candidates"] == []
    save_report(result, normalized, crops, tmp_path, recognizer.data_dir)
    assert_team(json.loads((tmp_path / "result.json").read_text(encoding="utf-8")), EXPECTED)
    assert len(list(tmp_path.glob("slot_*.png"))) == 6
    assert "苍炎刃鬼" in (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "凡作" not in (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "杰作" not in (tmp_path / "names.txt").read_text(encoding="utf-8")


def test_lower_resolution_jpeg(recognizer, screenshot):
    buffer = io.BytesIO()
    screenshot.resize((1280, 720), Image.Resampling.LANCZOS).save(buffer, format="JPEG", quality=75)
    buffer.seek(0)
    with Image.open(buffer) as image:
        result, _, _ = recognizer.recognize(image)
    assert_team(result, EXPECTED)


def test_reordered_slots_are_recognized_from_pixels(recognizer, screenshot):
    normalized, crops = recognizer.prepare_image(screenshot)
    order = [4, 0, 5, 2, 1, 3]
    for box, source in zip(recognizer.layout["slots"], order):
        normalized.paste(crops[source], box[:2])
    result, _, _ = recognizer.recognize(normalized)
    assert_team(result, [EXPECTED[i] for i in order])


@pytest.mark.parametrize("color", ["black", "white", "#900030"])
def test_blank_slot_is_unknown(recognizer, color):
    result = recognizer.match_slot(Image.new("RGB", (130, 95), color))
    assert result["status"] == "unknown"
    assert result["name"] is None


def test_noise_is_not_forced_into_a_species(recognizer):
    noise = np.random.default_rng(123).integers(0, 256, (95, 130, 3), dtype=np.uint8)
    result = recognizer.match_slot(Image.fromarray(noise))
    assert result["status"] == "unknown"
    assert result["name"] is None


def test_wrong_aspect_ratio_is_rejected(recognizer):
    with pytest.raises(ValueError, match="比例"):
        recognizer.recognize(Image.new("RGB", (800, 600)))


@pytest.mark.parametrize("name,variant,expected", [
    ("超级喷火龙X", "normal", "超级喷火龙X"),
    ("九尾（阿罗拉）", "shiny", "九尾（阿罗拉）"),
    ("彩粉蝶（花园花纹）", "normal", "彩粉蝶"),
    ("彩粉蝶（冰雪花纹）", "shiny", "彩粉蝶"),
])
def test_other_library_species_and_shifted_icons(recognizer, name, variant, expected):
    # Synthetic placement checks library coverage/translation; it is not held-out game evidence.
    index = json.loads((recognizer.data_dir / "index.json").read_text(encoding="utf-8"))
    record = next(r for r in index["pokemon"] if r["name"] == name)
    path = recognizer.data_dir / record["directory"] / record["images"][variant]["file"]
    with Image.open(path) as sprite:
        sprite = sprite.convert("RGBA").resize((80, 80), Image.Resampling.LANCZOS)
    crop = Image.new("RGB", (130, 95), "#900030")
    crop.paste(sprite, (11, 7), sprite)
    result = recognizer.match_slot(crop)
    assert result["status"] == "recognized"
    assert result["name"] == expected
    if expected == "彩粉蝶":
        assert result["form_status"] == "not_applicable"
        assert result["form_candidates"] == []
        assert sum(c["name"] == "彩粉蝶" for c in result["candidates"]) == 1


def test_cosmetic_competitors_do_not_reduce_acceptance_margin(recognizer):
    # Nearly identical patterns are alternate templates for one identity, not runner-up species.
    from champion_assistant.recognition import Template
    rgba = np.random.default_rng(9).integers(0, 256, (32, 32, 4), dtype=np.uint8)
    rgba[:, :, 3] = 255
    alternate = rgba.copy()
    alternate[10, 10, 0] ^= 1
    member = {"name": "彩粉蝶", "species_name": "彩粉蝶", "dex_number": 666,
              "variant": "normal", "cosmetic_merged": True, "path": "unused.png"}
    engine = object.__new__(OpponentRecognizer)
    engine.layout = recognizer.layout
    engine.templates = [Template([member], [rgba]), Template([member], [alternate])]
    crop = Image.new("RGB", (130, 95), "#900030")
    crop.paste(Image.fromarray(rgba).convert("RGB"), (20, 10))
    result = engine.match_slot(crop)
    assert result["status"] == "recognized"
    assert result["name"] == "彩粉蝶"
    assert len(result["candidates"]) == 1

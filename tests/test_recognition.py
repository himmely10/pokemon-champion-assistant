"""Real screenshot regression and failure cases; not a general accuracy benchmark."""
import io
import json

import numpy as np
import pytest
from PIL import Image

from champion_assistant.recognition import PROJECT_ROOT, OpponentRecognizer
from champion_assistant.report import save_report


EXPECTED = ["苍炎刃鬼", "风妖精", "巨金怪", "来悲粗茶", "烈咬陆鲨", "姆克鹰"]
MANIFEST = json.loads((PROJECT_ROOT / "tests/fixtures/recognition/manifest.json").read_text(encoding="utf-8"))


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


@pytest.mark.parametrize("sample", MANIFEST["screenshots"], ids=lambda sample: sample["path"])
def test_real_screenshot_manifest(recognizer, sample):
    with Image.open(PROJECT_ROOT / sample["path"]) as image:
        result, _, crops = recognizer.recognize(image)
        input_size = image.size
    assert result["thresholds"] == {"min_score": 0.78, "min_margin": 0.10}
    assert_team(result, sample["names"])
    for row, crop, box in zip(result["opponent"], crops, recognizer.crop_boxes()):
        assert row["crop_box_reference"] == box
        assert crop.size == (box[2] - box[0], box[3] - box[1])
        assert row["crop_box_input"] == [round(value * input_size[i % 2] / (1600, 900)[i % 2])
                                         for i, value in enumerate(box)]
        candidate = row["candidates"][0]
        match = candidate["match_box"]
        x, y = box[0] + match["x"], box[1] + match["y"]
        assert candidate["match_box_reference"] == [x, y, x + match["size"], y + match["size"]]
        assert candidate["match_box_input"] == [
            round(value * input_size[i % 2] / (1600, 900)[i % 2])
            for i, value in enumerate(candidate["match_box_reference"])]


@pytest.mark.parametrize("offset", [(-4, -4), (-2, 2), (2, -2), (4, 4)])
@pytest.mark.parametrize("sample", MANIFEST["screenshots"], ids=lambda sample: sample["path"])
def test_synthetic_small_translation(recognizer, sample, offset):
    with Image.open(PROJECT_ROOT / sample["path"]) as image:
        normalized, _ = recognizer.prepare_image(image)
    shifted = Image.new("RGB", normalized.size, "black")
    shifted.paste(normalized, offset)
    result, _, _ = recognizer.recognize(shifted)
    # Difficult perturbations may abstain; accepted names must never change identity.
    for row, expected in zip(result["opponent"], sample["names"]):
        assert row["name"] in (None, expected)
    expected_count = 5 if sample["path"] == "例子2.png" and offset == (-4, -4) else 6
    assert result["recognized_count"] == expected_count


@pytest.mark.parametrize("size", [(1280, 720), (1920, 1080), (1604, 904)])
def test_example2_scale_and_small_border(recognizer, size):
    sample = MANIFEST["screenshots"][1]
    with Image.open(PROJECT_ROOT / sample["path"]) as image:
        normalized, _ = recognizer.prepare_image(image)
    if size == (1604, 904):
        frame = Image.new("RGB", size, "black")
        frame.paste(normalized, (2, 2))
    else:
        frame = normalized.resize(size, Image.Resampling.LANCZOS)
    result, _, _ = recognizer.recognize(frame)
    assert_team(result, sample["names"])


def test_slot_expansion_bounds_and_legacy_layout(recognizer):
    engine = object.__new__(OpponentRecognizer)
    engine.layout = {**recognizer.layout, "slot_padding_y": 16}
    boxes = engine.crop_boxes()
    assert boxes[0][1] == 114
    assert boxes[-1][3] == 766
    for box, following in zip(boxes, boxes[1:]):
        assert box[3] <= following[1]
    engine.layout = {**engine.layout, "slots": [[10, y, 110, y + 95] for y in (0, 105, 210, 315, 420, 805)]}
    assert engine.crop_boxes()[0][1] == 0
    assert engine.crop_boxes()[-1][3] == 900
    engine.layout.pop("slot_padding_y")
    engine._validate_layout()
    assert engine.crop_boxes() == engine.layout["slots"]


@pytest.mark.parametrize("padding", [-1, 17, 1.5, True, "4", None])
def test_invalid_expansion_is_rejected(recognizer, padding):
    engine = object.__new__(OpponentRecognizer)
    engine.layout = {**recognizer.layout, "slot_padding_y": padding}
    with pytest.raises(ValueError, match="垂直扩展"):
        engine._validate_layout()


def test_severe_occlusion_and_incomplete_icon_abstain(recognizer, screenshot):
    _, crops = recognizer.prepare_image(screenshot)
    for crop in (crops[0], crops[-1]):
        covered = Image.new("RGB", crop.size, "black")
        covered.paste(crop.crop((0, 0, crop.width, 8)), (0, 0))
        result = recognizer.match_slot(covered)
        assert result["status"] == "unknown"
        assert result["name"] is None


def test_blank_slot_does_not_borrow_neighbor_icon(recognizer, screenshot):
    normalized, _ = recognizer.prepare_image(screenshot)
    box = recognizer.crop_boxes()[2]
    normalized.paste("black", box)
    result, _, _ = recognizer.recognize(normalized)
    assert result["opponent"][2]["name"] is None
    assert result["opponent"][3]["name"] == EXPECTED[3]


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
    for box, source in zip(recognizer.crop_boxes(), order):
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

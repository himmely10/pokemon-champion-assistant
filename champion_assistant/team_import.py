"""Offline OCR of the six-card replica Ability/Status screens into a review-only draft."""
from __future__ import annotations

from difflib import SequenceMatcher
from hashlib import sha256
from pathlib import Path
import re
import unicodedata
from threading import Lock

import cv2
import numpy as np
from PIL import Image, ImageOps

from .teams import STATS, blank_member
from .paths import app_paths


def normalize(text):
    return re.sub(r'[\s·・（）()：:—\-]', '', unicodedata.normalize('NFKC', text)).lower()


def cards(image):
    rgb = np.asarray(image.convert('RGB'))
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, np.array([105, 40, 70]), np.array([150, 255, 255]))
    kernel = max(3, round(image.width / 210))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((kernel, kernel), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = [cv2.boundingRect(c) for c in contours]
    if sum(.30 < w / image.width < .45 and .20 < h / w < .31 for x, y, w, h in boxes) != 6:
        # Sprites can bridge adjacent cards. Remove narrow vertical connections
        # only when ordinary contour detection cannot recover the six cards.
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,
                               np.ones((1, max(3, round(image.width * .039))), np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        boxes = [cv2.boundingRect(c) for c in contours]
    boxes = [(x, y + h - round(w * .257), w, round(w * .257)) for x, y, w, h in boxes
             if .30 < w / image.width < .45 and .20 < h / w < .31]
    if len(boxes) != 6:
        raise ValueError('没有找到完整的六张紫色队伍卡片，请使用包含整个队伍的能力／状态页截图。')
    # Row-major order: 1,2 / 3,4 / 5,6. Reject overlapping/misaligned layouts.
    boxes.sort(key=lambda b: b[1] + b[3] / 2)
    rows = [sorted(boxes[i:i + 2]) for i in (0, 2, 4)]
    for left, right in rows:
        if abs(left[1] - right[1]) > left[3] * .1 or right[0] < left[0] + left[2]:
            raise ValueError('队伍卡片布局不完整或被遮挡。')
    return [b for row in rows for b in row]


def region(image, box, rect):
    x, y, w, h = box
    a, b, c, d = rect
    return image.crop((round(x + w*a), round(y + h*b), round(x + w*c), round(y + h*d)))


def trim_name_whitespace(image):
    """Locate light title lettering on the purple card, retaining a small margin."""
    hsv = cv2.cvtColor(np.asarray(image.convert('RGB')), cv2.COLOR_RGB2HSV)
    mask = ((hsv[:, :, 1] < 80) & (hsv[:, :, 2] > 180)).astype('uint8') * 255
    pixels = cv2.findNonZero(mask)
    if pixels is None:
        return None
    x, y, w, h = cv2.boundingRect(pixels)
    if w < 8 or h < 8:
        return None
    return image.crop((max(0, x-4), max(0, y-4), min(image.width, x+w+4), min(image.height, y+h+4)))


class LocalOCR:
    def __init__(self):
        try:
            from rapidocr import RapidOCR
        except ImportError as exc:
            raise ValueError('请先安装 requirements-ocr.txt 中的本地 OCR 依赖。') from exc
        params = {'Global.log_level': 'error', 'EngineConfig.onnxruntime.intra_op_num_threads': 2}
        paths = app_paths()
        if paths.installed:
            for task, filename in [('Det', 'PP-OCRv6_det_small.onnx'), ('Rec', 'PP-OCRv6_rec_small.onnx'),
                                   ('Cls', 'ch_ppocr_mobile_v2.0_cls_mobile.onnx')]:
                model = paths.resource('models/' + filename)
                if not model.is_file():
                    raise ValueError('缺少内置 OCR 模型，请重新安装完整版本。')
                params[task + '.model_path'] = str(model)
        self.engine = RapidOCR(params=params)
        # RapidOCR keeps mutable inference/output state. Sharing its models is safe
        # only when each call and extraction of its result are serialized.
        self._lock = Lock()

    def read(self, image, *, detect=False):
        # PIL RGB must be passed as PIL, not an ndarray that the OCR loader treats as BGR.
        with self._lock:
            result = self.engine(image, use_det=detect, use_cls=False)
            if result.txts is None:
                return '', 0.0
            return ' '.join(result.txts), min(float(v) for v in result.scores)


_ocr_lock = Lock()
_ocr_cached = None


def shared_local_ocr():
    """One lazy model instance per resource bundle, never cache team/rules/results.

    Keeping only the latest bundle bounds retained model memory. Failed model
    initialization leaves the previous entry intact and a later import can retry.
    """
    global _ocr_cached
    paths = app_paths()
    key = (str(paths.resources.resolve()), paths.installed)
    with _ocr_lock:
        if _ocr_cached is None or _ocr_cached[0] != key:
            instance = LocalOCR()
            _ocr_cached = (key, instance)
        return _ocr_cached[1]


def color_mark(image, kind):
    hsv = cv2.cvtColor(np.asarray(image.convert('RGB')), cv2.COLOR_RGB2HSV)
    h, s, v = cv2.split(hsv)
    if kind == 'gender':
        red = ((h < 12) | (h > 165)) & (s > 100) & (v > 140)
        blue = (h > 90) & (h < 120) & (s > 100) & (v > 140)
    else:
        red = ((h < 15) | (h > 165)) & (s > 45) & (v > 160)
        blue = (h > 78) & (h < 104) & (s > 45) & (v > 160)
    a, b = np.count_nonzero(red), np.count_nonzero(blue)
    minimum = max(5, hsv.shape[0] * hsv.shape[1] * .015)
    if a > minimum and a > 3*b:
        return 'female' if kind == 'gender' else 'up'
    if b > minimum and b > 3*a:
        return 'male' if kind == 'gender' else 'down'
    return None


class ScreenshotImporter:
    def __init__(self, rules, ocr=None):
        self.rules = rules
        self.ocr = ocr if ocr is not None else shared_local_ocr()

    def field(self, image, box, rect, *, retry=False):
        crop = region(image, box, rect)
        text, score = self.ocr.read(crop)
        result = {'text': text, 'score': round(score, 4)}
        if retry:
            crop = ImageOps.autocontrast(ImageOps.grayscale(crop)).convert('RGB')
            text, score = self.ocr.read(crop, detect=True)
            result['alternate'] = {'text': text, 'score': round(score, 4)}
        return result

    def resolve(self, evidence, choices):
        matches = [key for name, key in choices if normalize(name) == normalize(evidence['text'])]
        matches = list(dict.fromkeys(matches))
        if len(matches) == 1 and evidence['score'] >= .90:
            evidence['value'] = matches[0]
            return matches[0]
        alternate = evidence.get('alternate')
        if alternate:
            alt_matches = list(dict.fromkeys(key for name, key in choices
                if normalize(name) == normalize(alternate['text'])))
            if len(alt_matches) == 1 and alternate['score'] >= .85:
                evidence['value'] = alt_matches[0]
                evidence['used_alternate'] = True
                return alt_matches[0]
        tight_reads = evidence.get('tight_reads', [])
        if (len(tight_reads) == 2 and all(r['score'] >= .85 for r in tight_reads)
                and normalize(tight_reads[0]['text']) == normalize(tight_reads[1]['text'])):
            tight_matches = list(dict.fromkeys(key for name, key in choices
                if normalize(name) == normalize(tight_reads[0]['text'])))
            if len(tight_matches) == 1:
                evidence.update(value=tight_matches[0], used_alternate=True, recovery='tight_consensus')
                evidence.pop('suggestions', None)
                return tight_matches[0]
        # Fuzzy results are suggestions only, never silently saved as recognized facts.
        evidence['suggestions'] = [name for name, key in sorted(choices,
            key=lambda p: SequenceMatcher(None, normalize(evidence['text']), normalize(p[0])).ratio(), reverse=True)[:3]]
        evidence['value'] = None
        return None

    def identity(self, evidence, gender):
        choices = []
        for r in self.rules.catalog.records:
            key = r.get('opgg_key') or ''
            # The screen omits sex in these two species' names. Their battle forms differ.
            if r['dex_number'] in (876, 902):
                if not gender or not key.endswith('-' + gender):
                    continue
                choices.append((r['species_name'], self.rules.identity(r)))
            else:
                choices.append((self.rules.catalog.display_name(r), self.rules.identity(r)))
        return self.resolve(evidence, choices)

    def read_page(self, path, mode, progress=lambda text: None):
        if mode not in ('ability', 'status'):
            raise ValueError('截图类型必须为能力或状态。')
        path = Path(path)
        with Image.open(path) as opened:
            if opened.width * opened.height > 30_000_000:
                raise ValueError('截图过大，请限制在 3000 万像素以内。')
            image = ImageOps.exif_transpose(opened).convert('RGB')
        boxes = cards(image)
        code = self.field(image, (0, 0, image.width, image.height), (.33, .10, .55, .153))
        code_match = re.search(r'(?:ID|1D)\s*[：:]?\s*([A-Z0-9]{10})(?![A-Z0-9])', code['text'].upper())
        if not code_match:
            # Confirmation screens place the ID farther left than video layouts.
            code = self.field(image, (0, 0, image.width, image.height), (.23, .085, .55, .16))
            code_match = re.search(r'(?:ID|1D)\s*[：:]?\s*([A-Z0-9]{10})(?![A-Z0-9])', code['text'].upper())
        team_code = code_match.group(1) if code_match and code['score'] >= .90 else None
        # Verify page content, not just purple-card geometry.
        probe = self.field(image, boxes[0], (.10, .28, .28, .48))
        is_status = 'HP' in probe['text'].upper()
        if is_status != (mode == 'status'):
            raise ValueError('所选页面类型与图片内容不符，请分别选择“能力”和“状态”截图。')
        members = []
        for slot, box in enumerate(boxes):
            progress(f"识别{'能力' if mode == 'ability' else '状态'}页 · 成员 {slot + 1}/6")
            name = self.field(image, box, (.10, .025, .41, .25), retry=True)
            gender = color_mark(region(image, box, (.418, .035, .469, .245)), 'gender')
            identity = self.identity(name, gender)
            if identity is None:
                # Small video frames can turn 狃 into 狂 with high confidence when
                # blank space dominates the crop. Require two exact dictionary readings,
                # never a species-specific typo substitution or a fuzzy auto-match.
                tight = trim_name_whitespace(region(image, box, (.10, .025, .41, .25)))
                if tight is not None:
                    name['tight_reads'] = []
                    for variant in (tight, ImageOps.invert(ImageOps.grayscale(tight)).convert('RGB')):
                        text, score = self.ocr.read(variant)
                        name['tight_reads'].append({'text': text, 'score': round(score, 4)})
                    identity = self.identity(name, gender)
            member = blank_member(identity)
            evidence = {'name': name, 'gender': gender}
            if mode == 'ability':
                ability = self.field(image, box, (.115, .28, .59, .50), retry=True)
                item = self.field(image, box, (.115, .52, .59, .76), retry=True)
                member['ability'] = self.resolve(ability, [(self.rules.options['abilities'].get(k, {}).get('name', k), k)
                                                         for k in self.rules.ability_keys(identity)])
                member['item'] = self.resolve(item, [(v['name'], k) for k, v in self.rules.options['items'].items()])
                evidence.update(ability=ability, item=item, moves=[])
                for i in range(4):
                    move = self.field(image, box, (.659, .02 + i*.24, .94, .245 + i*.24))
                    member['moves'][i] = self.resolve(move, [(self.rules.catalog.moves[k]['name'], k) for k in self.rules.move_keys(identity)])
                    evidence['moves'].append(move)
            else:
                evidence.update(points={}, panel_stats={}, marks={})
                for index, key in enumerate(STATS):
                    col, row = divmod(index, 3)
                    yc = .375 + .24*row
                    for field, x1, x2, cap in [('panel_stats', .28, .362, 999), ('points', .418, .478, 32)]:
                        e = self.field(image, box, (x1 + .468*col, yc-.10, x2 + .468*col, yc+.10))
                        number = int(e['text']) if re.fullmatch(r'\d{1,3}', e['text']) and e['score'] >= .90 else None
                        if number is not None and not (0 <= number <= cap):
                            number = None
                        e['value'] = number
                        evidence[field][key] = e
                        if field == 'points':
                            member['points'][key] = number
                    mark = color_mark(region(image, box, (.185 + .468*col, yc-.10, .226 + .468*col, yc+.10)), 'nature')
                    evidence['marks'][key] = mark
                up = [k for k, v in evidence['marks'].items() if v == 'up']
                down = [k for k, v in evidence['marks'].items() if v == 'down']
                stat_keys = {'special_attack': 'spAttack', 'special_defense': 'spDefense'}
                if len(up) == len(down) == 1:
                    member['nature'] = next((k for k, n in self.rules.options['natures'].items()
                        if n['increased'] == stat_keys.get(up[0], up[0]) and n['decreased'] == stat_keys.get(down[0], down[0])), None)
                if sum(v or 0 for v in member['points'].values()) > 66:
                    member['points'] = dict.fromkeys(STATS)
                    evidence['warning'] = '培养点总和超过 66，已清空待核对。'
            members.append({'slot': slot + 1, 'member': member, 'evidence': evidence, 'box': list(box)})
        return {'mode': mode, 'team_code': team_code, 'code_evidence': code, 'members': members,
                'source': {'filename': path.name, 'sha256': sha256(path.read_bytes()).hexdigest(), 'size': list(image.size)}}

    def combine(self, ability, status):
        if ability['mode'] != 'ability' or status['mode'] != 'status':
            raise ValueError('需要一张能力页和一张状态页。')
        if not ability['team_code'] or ability['team_code'] != status['team_code']:
            raise ValueError('两张截图的队伍码未能确认一致，拒绝合并。请换用清晰截图。')
        members, warnings = [], []
        if any(c in ability['team_code'] for c in '0O1I'):
            warnings.append('队伍码包含易混淆的 0/O 或 1/I，需对照原图核对；未进行线上验证。')
        for a, s in zip(ability['members'], status['members']):
            am, sm = a['member'], s['member']
            # Even the same code cannot justify mixing different slot/identity evidence.
            if am['identity'] is None or am['identity'] != sm['identity']:
                raise ValueError(f"第 {a['slot']} 槽身份未能在两页一致确认，拒绝合并。")
            member = {**am, 'points': sm['points'], 'nature': sm['nature']}
            missing = [k for k in ('ability', 'item', 'nature') if member[k] is None]
            if missing or None in member['moves'] or None in member['points'].values():
                warnings.append(f"第 {a['slot']} 槽有未知字段，请核对原图。")
            if a['evidence']['name'].get('used_alternate') or s['evidence']['name'].get('used_alternate'):
                warnings.append(f"第 {a['slot']} 槽身份采用局部增强重识别，请特别核对。")
            members.append(member)
        draft = {'name': '截图导入 ' + ability['team_code'], 'registration': 'full', 'members': members,
                 'import_source': {'method': 'local_ocr', 'team_code': ability['team_code'],
                                   'ability': ability, 'status': status, 'review_required': True}}
        self.rules.validate(draft)
        return {'draft': draft, 'warnings': warnings,
                'notice': 'OCR 草稿：请核对性别形态、性格、数字与招式后保存。面板数值只保留为来源证据。'}

    def run(self, ability_path, status_path, progress=lambda text: None):
        return self.combine(self.read_page(ability_path, 'ability', progress), self.read_page(status_path, 'status', progress))

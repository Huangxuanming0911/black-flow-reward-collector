from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

import cv2
import numpy as np

from .models import FrameObservation, OCRToken, ScreenKind


_KNOWN_NON_STAGE_TEXT = {
    "作战",
    "紧急作战",
    "成功通过",
    "目标生命值",
    "护盾值",
    "指挥等级",
    "本次作战",
    "完美的战术",
}

_AREA_FLOORS = {
    "玻利瓦尔肤层": "1",
    "甜美的伤口": "2",
    "血色空脉": "3",
    "受害者腐殖": "4",
    "卡德霍之颅": "5",
    "源流交汇处": "6",
}

_ROMAN_FLOORS = {
    "I": "1",
    "II": "2",
    "III": "3",
    "IV": "4",
    "V": "5",
    "VI": "6",
}


def _token_from_raw(
    raw: Any,
    width: int,
    height: int,
) -> OCRToken | None:
    if not isinstance(raw, (list, tuple)) or len(raw) < 3:
        return None
    box, text, confidence = raw[0], str(raw[1]).strip(), raw[2]
    if not text or not isinstance(box, (list, tuple)) or len(box) < 4:
        return None
    points = tuple(
        (float(point[0]) / width, float(point[1]) / height)
        for point in box
    )
    return OCRToken(
        text=text,
        confidence=float(confidence),
        box=points,
        center_x=sum(point[0] for point in points) / len(points),
        center_y=sum(point[1] for point in points) / len(points),
    )


def parse_rapidocr_output(
    output: Any,
    image_shape: tuple[int, ...],
) -> tuple[OCRToken, ...]:
    height, width = image_shape[:2]
    raw_items = output[0] if isinstance(output, tuple) else output
    if raw_items is None:
        return ()
    parsed = (
        _token_from_raw(item, width, height)
        for item in raw_items
    )
    return tuple(token for token in parsed if token is not None)


def classify_tokens(tokens: Iterable[OCRToken]) -> ScreenKind:
    texts = [token.text.replace(" ", "") for token in tokens]
    joined = "\n".join(texts)
    if (
        "成功通过" in joined
        and ("本次作战" in joined or "指挥等级" in joined)
    ):
        return ScreenKind.SETTLEMENT
    take_count = sum("收下" in text for text in texts)
    if take_count >= 2 or (
        "直接离开" in joined and take_count >= 1
    ):
        return ScreenKind.REWARDS
    return ScreenKind.OTHER


def _stage_name(tokens: tuple[OCRToken, ...]) -> str:
    candidates: list[OCRToken] = []
    for token in tokens:
        text = token.text.strip()
        compact = text.replace(" ", "")
        if compact in _KNOWN_NON_STAGE_TEXT:
            continue
        if not (0.04 <= token.center_x <= 0.38):
            continue
        if not (0.48 <= token.center_y <= 0.72):
            continue
        if not (2 <= len(compact) <= 12):
            continue
        if re.fullmatch(r"[\d/+\-×xX]+", compact):
            continue
        if compact.startswith(("…", ".", "也还")):
            continue
        candidates.append(token)
    if not candidates:
        return ""
    candidates.sort(
        key=lambda item: (
            "作战" in item.text,
            item.confidence,
            len(item.text),
        ),
        reverse=True,
    )
    return candidates[0].text.strip()


def _battle_command_xp(
    tokens: tuple[OCRToken, ...],
) -> int | None:
    values: list[tuple[float, int]] = []
    for token in tokens:
        compact = token.text.replace(" ", "")
        match = re.fullmatch(r"\D*(\d{1,3})\D*", compact)
        if not match:
            continue
        if 0.58 <= token.center_x <= 0.80 and 0.30 <= token.center_y <= 0.48:
            values.append((token.confidence, int(match.group(1))))
    if not values:
        return None
    values.sort(reverse=True)
    return values[0][1]


def _reward_names(tokens: tuple[OCRToken, ...]) -> tuple[str, ...]:
    ignored = {
        "收下",
        "直接离开",
        "目标生命值",
        "指挥等级",
        "收藏品",
        "零件箱",
        "干员",
        "编队",
        "总估价",
    }
    names: list[str] = []
    for token in tokens:
        text = token.text.strip()
        compact = text.replace(" ", "")
        # Card titles occupy one stable horizontal band. Restricting to it
        # keeps effect descriptions out of the offered-reward list.
        if not (0.44 <= token.center_y <= 0.53):
            continue
        if not (0.04 <= token.center_x <= 0.75):
            continue
        if compact in ignored or "收下" in compact:
            continue
        if len(compact) < 2 or len(compact) > 12:
            continue
        if re.fullmatch(r"[\d/+\-×xX]+", compact):
            continue
        if any(
            marker in compact
            for marker in (
                "装载后",
                "每次进入",
                "队伍中",
                "获得",
                "移动至",
            )
        ):
            continue
        if text not in names:
            names.append(text)
    return tuple(names)


def _reward_ingots(tokens: tuple[OCRToken, ...]) -> int | None:
    ingot_tokens = [
        token for token in tokens if "源石锭" in token.text
    ]
    if not ingot_tokens:
        return None
    anchor = ingot_tokens[0]
    numbers: list[tuple[float, int]] = []
    for token in tokens:
        compact = token.text.replace(" ", "")
        match = re.fullmatch(r"[×xX]?(\d{1,3})", compact)
        if not match:
            continue
        if abs(token.center_x - anchor.center_x) > 0.10:
            continue
        if not (anchor.center_y < token.center_y < anchor.center_y + 0.22):
            continue
        distance = abs(token.center_y - anchor.center_y)
        numbers.append((distance, int(match.group(1))))
    return min(numbers)[1] if numbers else None


def _page_context(
    tokens: tuple[OCRToken, ...],
    kind: ScreenKind,
) -> tuple[str, str, str, tuple[str, ...]]:
    source_floor = ""
    location_context = ""
    combat_context = ""
    evidence: list[str] = []

    top_tokens = tuple(
        token
        for token in tokens
        if token.center_y <= 0.18 and 0.28 <= token.center_x <= 0.72
    )
    top_text = " ".join(token.text for token in top_tokens)
    compact_top = top_text.replace(" ", "")
    for area_name, floor in _AREA_FLOORS.items():
        if area_name in compact_top:
            source_floor = floor
            location_context = "main_map"
            evidence.append(f"area_title:{area_name}")
            break
    if not source_floor:
        roman_match = re.search(
            r"[\(（]\s*(VI|IV|III|II|V|I)\s*[\)）]",
            top_text,
            flags=re.IGNORECASE,
        )
        if roman_match:
            roman = roman_match.group(1).upper()
            source_floor = _ROMAN_FLOORS[roman]
            location_context = "main_map"
            evidence.append(f"roman_floor:{roman}")

    if (
        "未萌生的摇篮" in compact_top
        or re.search(r"[\(（]\s*\?{2}\s*[\)）]", top_text)
    ):
        location_context = "portal_internal"
        evidence.append("portal_internal_title")

    if kind == ScreenKind.SETTLEMENT:
        context_tokens = tuple(
            token
            for token in tokens
            if token.center_x <= 0.38 and 0.42 <= token.center_y <= 0.72
        )
    else:
        # Pre-battle headers generally live near the top. This avoids treating
        # unrelated node labels scattered across a map as the selected battle.
        context_tokens = tuple(
            token
            for token in tokens
            if token.center_y <= 0.28
        )
    context_text = "".join(
        token.text.replace(" ", "") for token in context_tokens
    )
    rules = (
        ("resident_base", ("“居民”据点", "\"居民\"据点", "居民据点")),
        (
            "resident_occupied",
            ("流窜“居民”", "流窜居民", "居民占领"),
        ),
        ("encounter", ("狭路相逢",)),
        ("emergency_combat", ("紧急作战",)),
        ("boss", ("险路恶敌",)),
        ("pursuit", ("追猎",)),
        ("combat", ("作战",)),
    )
    for context_id, markers in rules:
        marker = next(
            (item for item in markers if item in context_text),
            None,
        )
        if marker is not None:
            combat_context = context_id
            evidence.append(f"combat_text:{marker}")
            break
    return (
        source_floor,
        location_context,
        combat_context,
        tuple(evidence),
    )


def analyze_tokens(tokens: tuple[OCRToken, ...]) -> FrameObservation:
    kind = classify_tokens(tokens)
    if kind == ScreenKind.SETTLEMENT:
        confidence = 0.98
    elif kind == ScreenKind.REWARDS:
        confidence = 0.96
    else:
        confidence = 0.35
    reward_names = _reward_names(tokens) if kind == ScreenKind.REWARDS else ()
    source_floor, location_context, combat_context, evidence = (
        _page_context(tokens, kind)
    )
    return FrameObservation(
        kind=kind,
        confidence=confidence,
        tokens=tokens,
        stage_name=_stage_name(tokens) if kind == ScreenKind.SETTLEMENT else "",
        battle_command_xp=(
            _battle_command_xp(tokens)
            if kind == ScreenKind.SETTLEMENT
            else None
        ),
        reward_ingots=(
            _reward_ingots(tokens)
            if kind == ScreenKind.REWARDS
            else None
        ),
        reward_tickets=(
            sum(name.endswith("招募券") for name in reward_names)
            if kind == ScreenKind.REWARDS
            else None
        ),
        visible_reward_names=reward_names,
        source_floor=source_floor,
        location_context=location_context,
        combat_context=combat_context,
        context_evidence=evidence,
    )


class FrameAnalyzer:
    def __init__(self, ocr_engine: Any | None = None) -> None:
        self._ocr_engine = ocr_engine

    def _engine(self) -> Any:
        if self._ocr_engine is None:
            from rapidocr_onnxruntime import RapidOCR

            self._ocr_engine = RapidOCR()
        return self._ocr_engine

    def analyze(self, image: np.ndarray) -> FrameObservation:
        if image.ndim != 3:
            raise ValueError("expected BGR image")
        height, width = image.shape[:2]
        max_width = 1920
        if width > max_width:
            scale = max_width / width
            image = cv2.resize(
                image,
                (max_width, round(height * scale)),
                interpolation=cv2.INTER_AREA,
            )
        output = self._engine()(image)
        tokens = parse_rapidocr_output(output, image.shape)
        return analyze_tokens(tokens)


def frame_signature(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return cv2.resize(gray, (64, 36), interpolation=cv2.INTER_AREA)


def signature_difference(left: np.ndarray, right: np.ndarray) -> float:
    return float(cv2.absdiff(left, right).mean())

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from .knowledge import KNOWN_STAGE_CONTEXTS
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


@dataclass(frozen=True, slots=True)
class _RewardCard:
    action: OCRToken
    tokens: tuple[OCRToken, ...]
    title: str


def _reward_cards(
    tokens: tuple[OCRToken, ...],
) -> tuple[_RewardCard, ...]:
    """Find every currently visible reward card from its action button.

    Card count and x positions are deliberately not fixed. As rewards are
    claimed, later cards can slide into the row; every analyzed frame yields
    a fresh set of button-anchored columns for the session merger.
    """
    actions = sorted(
        (
            token
            for token in tokens
            if 0.62 <= token.center_y <= 0.80
            and (
                "收下" in token.text.replace(" ", "")
                or token.text.replace(" ", "") == "选择"
            )
        ),
        key=lambda token: token.center_x,
    )
    cards: list[_RewardCard] = []
    for index, action in enumerate(actions):
        left = (
            0.0
            if index == 0
            else (actions[index - 1].center_x + action.center_x) / 2
        )
        right = (
            1.0
            if index == len(actions) - 1
            else (action.center_x + actions[index + 1].center_x) / 2
        )
        column_tokens = tuple(
            token
            for token in tokens
            if left <= token.center_x < right
            and abs(token.center_x - action.center_x) <= 0.14
            and 0.30 <= token.center_y <= 0.70
        )
        title_candidates = [
            token
            for token in column_tokens
            if 0.43 <= token.center_y <= 0.53
            and 2 <= len(token.text.replace(" ", "")) <= 16
        ]
        title = ""
        if title_candidates:
            title = min(
                title_candidates,
                key=lambda token: (
                    abs(token.center_x - action.center_x),
                    abs(token.center_y - 0.49),
                    -token.confidence,
                ),
            ).text.strip()
        cards.append(_RewardCard(action, column_tokens, title))
    return tuple(cards)


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
    labels = [
        token
        for token in tokens
        if token.text.replace(" ", "") == "作战"
        and token.center_x <= 0.20
        and 0.50 <= token.center_y <= 0.75
    ]
    if labels:
        anchor = max(labels, key=lambda token: token.center_y)
        anchored = [
            token
            for token in tokens
            if abs(token.center_x - anchor.center_x) <= 0.16
            and 0.015 <= token.center_y - anchor.center_y <= 0.10
            and 2 <= len(token.text.replace(" ", "")) <= 12
            and "成功通过" not in token.text
        ]
        if anchored:
            return min(
                anchored,
                key=lambda token: token.center_y - anchor.center_y,
            ).text.strip()

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
    level_labels = [
        token for token in tokens if "指挥等级" in token.text
    ]
    anchors = [
        token
        for token in tokens
        if "本次作战" in token.text
        and 0.30 <= token.center_y <= 0.62
        and any(
            label.center_x < token.center_x
            and abs(label.center_y - token.center_y) <= 0.04
            for label in level_labels
        )
    ]
    if anchors:
        # The lower "本次作战" label belongs to command XP; the upper one
        # belongs to leak count. Anchor-relative reading avoids shield values.
        anchor = max(anchors, key=lambda token: token.center_y)
        anchored_values: list[tuple[float, int]] = []
        for token in tokens:
            compact = token.text.replace(" ", "")
            match = re.fullmatch(r"(\d{1,3})", compact)
            if not match:
                continue
            if abs(token.center_x - anchor.center_x) > 0.12:
                continue
            vertical_distance = token.center_y - anchor.center_y
            if not (0.02 <= vertical_distance <= 0.14):
                continue
            anchored_values.append(
                (vertical_distance, int(match.group(1)))
            )
        if anchored_values:
            return min(anchored_values)[1]
    return None


def _reward_ticket_names(
    tokens: tuple[OCRToken, ...],
) -> tuple[str, ...]:
    ticket_names: list[str] = []
    for card in _reward_cards(tokens):
        for token in card.tokens:
            compact = token.text.replace(" ", "").replace("卷", "券")
            if "招募券" not in compact:
                continue
            known_match = re.search(
                r"(先锋|近卫|重装|狙击|术师|医疗|辅助|特种|高级资深)"
                r"招募券",
                compact,
            )
            if known_match:
                ticket_names.append(known_match.group(0))
                break
            named_match = re.search(
                r"([\u4e00-\u9fff]{1,10}招募券)",
                compact,
            )
            ticket_names.append(
                named_match.group(1) if named_match else compact
            )
            break
    return tuple(ticket_names)


def _reward_ticket_count(tokens: tuple[OCRToken, ...]) -> int:
    return len(_reward_ticket_names(tokens))


def _reward_collectible_count(tokens: tuple[OCRToken, ...]) -> int:
    if any(token.text.replace(" ", "") == "或是" for token in tokens):
        return 0
    count = 0
    for card in _reward_cards(tokens):
        if "收下" not in card.action.text:
            continue
        column_text = "".join(
            token.text.replace(" ", "")
            for token in card.tokens
            if 0.38 <= token.center_y <= 0.62
        )
        if "源石锭" in column_text:
            continue
        if "招募券" in column_text or "招募卷" in column_text:
            continue
        count += 1
    return count


def _parts_box_used(tokens: tuple[OCRToken, ...]) -> int | None:
    candidates: list[tuple[float, int]] = []
    for token in tokens:
        if not (0.55 <= token.center_x <= 0.75):
            continue
        if token.center_y < 0.90:
            continue
        match = re.fullmatch(
            r"(\d{1,2})\s*/\s*(\d{1,2})",
            token.text,
        )
        if match:
            candidates.append((token.confidence, int(match.group(1))))
    return max(candidates)[1] if candidates else None


def _part_grant_effects(
    tokens: tuple[OCRToken, ...],
) -> tuple[tuple[str, int], ...]:
    effects: list[tuple[str, int]] = []
    for card in _reward_cards(tokens):
        if not card.title:
            continue
        description = "".join(
            token.text.replace(" ", "")
            for token in sorted(
                card.tokens,
                key=lambda item: item.center_y,
            )
            if 0.52 <= token.center_y <= 0.62
        )
        match = re.search(
            r"立刻获得(\d{1,2})个.*(?:加工品|零件)",
            description,
        )
        if match:
            effects.append((card.title, int(match.group(1))))
    return tuple(dict.fromkeys(effects))


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
    for card in _reward_cards(tokens):
        text = card.title
        if not text:
            continue
        compact = text.replace(" ", "")
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


def _reward_ingot_components(
    tokens: tuple[OCRToken, ...],
) -> tuple[int | None, int | None, int | None]:
    ingot_tokens = [
        token for token in tokens if "源石锭" in token.text
    ]
    if not ingot_tokens:
        return None, None, None
    normal = 0
    unowned = 0
    found = False
    wealth_tokens = [
        token for token in tokens if "无主的财富" in token.text
    ]
    for anchor in ingot_tokens:
        numbers: list[tuple[float, int]] = []
        for token in tokens:
            compact = token.text.replace(" ", "")
            match = re.fullmatch(r"[×xX]?(\d{1,3})", compact)
            if not match:
                continue
            if abs(token.center_x - anchor.center_x) > 0.10:
                continue
            if not (
                anchor.center_y
                < token.center_y
                < anchor.center_y + 0.22
            ):
                continue
            numbers.append(
                (
                    abs(token.center_y - anchor.center_y),
                    int(match.group(1)),
                )
            )
        if not numbers:
            continue
        quantity = min(numbers)[1]
        found = True
        is_unowned = any(
            abs(token.center_x - anchor.center_x) <= 0.11
            and 0.03
            <= anchor.center_y - token.center_y
            <= 0.18
            for token in wealth_tokens
        )
        if is_unowned:
            unowned += quantity
        else:
            normal += quantity
    if not found:
        return None, None, None
    return (
        normal + unowned,
        normal if normal else None,
        unowned if unowned else None,
    )


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

    # The top-right action-point label is visible on the interactive map but
    # not on settlement or reward-card overlays. It is therefore stronger
    # return-to-map evidence than the area title and persistent bottom HUD.
    if kind == ScreenKind.OTHER and any(
        "行动力" in token.text.replace(" ", "")
        and token.center_x >= 0.78
        and 0.05 <= token.center_y <= 0.30
        for token in tokens
    ):
        location_context = "main_map"
        evidence.append("main_map_hud:action_points")

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
    full_text = "".join(
        token.text.replace(" ", "") for token in tokens
    )
    if (
        "流窜“居民”已经从林间消失" in full_text
        or "流窜居民已经从林间消失" in full_text
    ):
        combat_context = "resident_occupied"
        evidence.append("settlement_notice:resident_disappeared")
        return (
            source_floor,
            location_context,
            combat_context,
            tuple(evidence),
        )
    rules: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("resident_base", ("“居民”据点", "\"居民\"据点", "居民据点")),
        (
            "resident_occupied",
            ("流窜“居民”", "流窜居民", "居民占领"),
        ),
        ("encounter", ("狭路相逢",)),
        ("emergency_combat", ("紧急作战",)),
        ("boss", ("险路恶敌",)),
        ("combat", ("作战",)),
    )
    if kind == ScreenKind.SETTLEMENT:
        rules = (
            ("pursuit", ("追猎",)),
            *rules,
        )
    elif "追猎" in context_text:
        # 追猎 is normally a forced state caused by depleted action points,
        # not the selected map node. Keep it as evidence without assigning
        # the battle type from a general map/pre-battle frame.
        evidence.append("forced_state:pursuit")
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
    if kind == ScreenKind.REWARDS:
        reward_ingots, normal_ingots, unowned_ingots = (
            _reward_ingot_components(tokens)
        )
    else:
        reward_ingots = normal_ingots = unowned_ingots = None
    source_floor, location_context, combat_context, evidence = (
        _page_context(tokens, kind)
    )
    stage_name = _stage_name(tokens) if kind == ScreenKind.SETTLEMENT else ""
    known_stage_context = KNOWN_STAGE_CONTEXTS.get(stage_name)
    if known_stage_context:
        combat_context = known_stage_context
        evidence = (
            *evidence,
            f"stage_context:{stage_name}",
        )
    return FrameObservation(
        kind=kind,
        confidence=confidence,
        tokens=tokens,
        stage_name=stage_name,
        battle_command_xp=(
            _battle_command_xp(tokens)
            if kind == ScreenKind.SETTLEMENT
            else None
        ),
        reward_ingots=reward_ingots,
        normal_reward_ingots=normal_ingots,
        unowned_wealth_ingots=unowned_ingots,
        reward_tickets=(
            _reward_ticket_count(tokens)
            if kind == ScreenKind.REWARDS
            else None
        ),
        reward_ticket_names=(
            _reward_ticket_names(tokens)
            if kind == ScreenKind.REWARDS
            else ()
        ),
        reward_collectibles=(
            _reward_collectible_count(tokens)
            if kind == ScreenKind.REWARDS
            else None
        ),
        parts_box_used=(
            _parts_box_used(tokens)
            if kind == ScreenKind.REWARDS
            else None
        ),
        part_grant_effects=(
            _part_grant_effects(tokens)
            if kind == ScreenKind.REWARDS
            else ()
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

            # Avoid occupying every logical CPU while the game is running.
            self._ocr_engine = RapidOCR(
                intra_op_num_threads=4,
                inter_op_num_threads=1,
            )
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

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class ScreenKind(StrEnum):
    SETTLEMENT = "battle_settlement"
    REWARDS = "post_battle_rewards"
    OTHER = "other"


LOCATION_CONTEXTS: tuple[tuple[str, str], ...] = (
    ("main_map", "常规区域"),
    ("portal_internal", "误入奇境内部"),
)

COMBAT_CONTEXTS: tuple[tuple[str, str], ...] = (
    ("encounter", "狭路相逢"),
    ("combat", "普通作战"),
    ("emergency_combat", "紧急作战"),
    ("boss", "险路恶敌/Boss"),
    ("pursuit", "追猎"),
    ("resident_occupied", "流窜“居民”普通占领战"),
    ("resident_base", "“居民”据点"),
)

BONUS_SOURCES: tuple[tuple[str, str], ...] = (
    ("none", "无额外来源"),
    ("chest", "局内宝箱"),
    ("treasure_enemy", "宝物怪"),
    ("both", "宝箱与宝物怪"),
    ("unknown", "不确定"),
)


@dataclass(frozen=True, slots=True)
class OCRToken:
    text: str
    confidence: float
    box: tuple[tuple[float, float], ...]
    center_x: float
    center_y: float


@dataclass(frozen=True, slots=True)
class FrameObservation:
    kind: ScreenKind
    confidence: float
    tokens: tuple[OCRToken, ...] = ()
    stage_name: str = ""
    battle_command_xp: int | None = None
    reward_ingots: int | None = None
    normal_reward_ingots: int | None = None
    unowned_wealth_ingots: int | None = None
    reward_tickets: int | None = None
    reward_ticket_names: tuple[str, ...] = ()
    reward_collectibles: int | None = None
    parts_box_used: int | None = None
    part_grant_effects: tuple[tuple[str, int], ...] = ()
    visible_reward_names: tuple[str, ...] = ()
    source_floor: str = ""
    location_context: str = ""
    combat_context: str = ""
    context_evidence: tuple[str, ...] = ()

    @property
    def raw_text(self) -> str:
        return "\n".join(token.text for token in self.tokens)


@dataclass(slots=True)
class PendingBattle:
    sample_id: str
    started_at: str
    settlement_screenshots: list[str] = field(default_factory=list)
    reward_screenshots: list[str] = field(default_factory=list)
    stage_name: str = ""
    battle_command_xp: int | None = None
    reward_ingots: int | None = None
    normal_reward_ingots: int | None = None
    unowned_wealth_ingots: int | None = None
    reward_tickets: int | None = None
    reward_ticket_names: list[str] = field(default_factory=list)
    reward_ticket_name_counts: dict[str, int] = field(
        default_factory=dict
    )
    reward_collectibles: int | None = None
    parts_box_start: int | None = None
    parts_box_end: int | None = None
    parts_box_last: int | None = None
    bonus_parts: int = 0
    part_grant_candidates: dict[str, int] = field(default_factory=dict)
    applied_part_effects: list[str] = field(default_factory=list)
    visible_reward_names: list[str] = field(default_factory=list)
    ocr_text: list[str] = field(default_factory=list)
    saw_rewards: bool = False
    source_floor: str = ""
    location_context: str = ""
    combat_context: str = ""
    context_evidence: list[str] = field(default_factory=list)

    @property
    def parts_total(self) -> int | None:
        if self.parts_box_start is None or self.parts_box_end is None:
            return None
        return max(0, self.parts_box_end - self.parts_box_start)

    @property
    def reward_parts(self) -> int | None:
        if self.parts_total is None:
            return None
        return max(0, self.parts_total - self.bonus_parts)

    @property
    def parts_bonus_details(self) -> str:
        return "；".join(self.applied_part_effects)


@dataclass(frozen=True, slots=True)
class RewardRecord:
    sample_id: str
    captured_at: str
    source_floor: str
    location_context: str
    combat_context: str
    stage_name: str
    command_xp: int | None
    originium_ingots: int
    normal_reward_ingots: int
    unowned_wealth_ingots: int
    hope: int
    recruitment_tickets: int
    collectibles: int
    parts: int
    bonus_source: str
    bonus_details: str
    command_xp_multiplier: float
    ingot_multiplier: float
    displayed_reward_names: tuple[str, ...]
    settlement_screenshots: tuple[str, ...]
    reward_screenshots: tuple[str, ...]
    ocr_text: str
    reviewer_notes: str
    bonus_parts: int = 0
    parts_total: int = 0
    parts_bonus_details: str = ""
    detected_combat_context: str = ""
    context_evidence: tuple[str, ...] = ()
    review_status: str = "confirmed"
    schema_version: str = "0.3.0"

    @property
    def eligible_for_base_statistics(self) -> bool:
        return (
            self.review_status == "confirmed"
            and self.bonus_source == "none"
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["eligible_for_base_statistics"] = (
            self.eligible_for_base_statistics
        )
        return payload

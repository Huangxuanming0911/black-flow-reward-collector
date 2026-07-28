from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import time
import uuid

from .models import FrameObservation, PendingBattle, ScreenKind


def new_sample_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    return f"{timestamp}-{uuid.uuid4().hex[:8]}"


class BattleSessionTracker:
    def __init__(self, finalize_delay_seconds: float = 2.5) -> None:
        self.finalize_delay_seconds = finalize_delay_seconds
        self.pending: PendingBattle | None = None
        self._last_target_at: float | None = None
        self._source_floor = ""
        self._location_context = ""
        self._combat_context = ""
        self._context_evidence: list[str] = []

    def offer(
        self,
        observation: FrameObservation,
        screenshot_path: Path | None = None,
        now: float | None = None,
    ) -> PendingBattle | None:
        now = time.monotonic() if now is None else now
        self._remember_context(observation)
        if observation.kind in (
            ScreenKind.SETTLEMENT,
            ScreenKind.REWARDS,
        ):
            self._last_target_at = now
            if self.pending is None:
                self.pending = PendingBattle(
                    sample_id=new_sample_id(),
                    started_at=datetime.now(UTC).isoformat(),
                    source_floor=self._source_floor,
                    location_context=self._location_context,
                    combat_context=self._combat_context,
                    context_evidence=list(self._context_evidence),
                )
            self._merge(observation, screenshot_path)
            return None

        if self.pending is None or self._last_target_at is None:
            return None
        if now - self._last_target_at < self.finalize_delay_seconds:
            return None
        completed = self.pending
        self.pending = None
        self._last_target_at = None
        return completed

    def _remember_context(
        self,
        observation: FrameObservation,
    ) -> None:
        if observation.source_floor:
            self._source_floor = observation.source_floor
        if observation.location_context:
            self._location_context = observation.location_context
        if observation.combat_context:
            self._combat_context = observation.combat_context
        for item in observation.context_evidence:
            if item not in self._context_evidence:
                self._context_evidence.append(item)

    def force_finalize(self) -> PendingBattle | None:
        completed = self.pending
        self.pending = None
        self._last_target_at = None
        return completed

    def _merge(
        self,
        observation: FrameObservation,
        screenshot_path: Path | None,
    ) -> None:
        assert self.pending is not None
        pending = self.pending
        if observation.source_floor:
            pending.source_floor = observation.source_floor
        if observation.location_context:
            pending.location_context = observation.location_context
        if observation.combat_context:
            pending.combat_context = observation.combat_context
        for item in observation.context_evidence:
            if item not in pending.context_evidence:
                pending.context_evidence.append(item)
        # The first settlement frame has the cleanest stage title. Later
        # overlays add dialogue/stat text that can look like another title.
        if observation.stage_name and not pending.stage_name:
            pending.stage_name = observation.stage_name
        if observation.battle_command_xp is not None:
            pending.battle_command_xp = observation.battle_command_xp
        if observation.reward_ingots is not None:
            pending.reward_ingots = observation.reward_ingots
        if observation.normal_reward_ingots is not None:
            pending.normal_reward_ingots = max(
                pending.normal_reward_ingots or 0,
                observation.normal_reward_ingots,
            )
        if observation.unowned_wealth_ingots is not None:
            pending.unowned_wealth_ingots = max(
                pending.unowned_wealth_ingots or 0,
                observation.unowned_wealth_ingots,
            )
        if (
            pending.normal_reward_ingots is not None
            or pending.unowned_wealth_ingots is not None
        ):
            pending.reward_ingots = (
                (pending.normal_reward_ingots or 0)
                + (pending.unowned_wealth_ingots or 0)
            )
        if observation.reward_tickets is not None:
            pending.reward_tickets = max(
                pending.reward_tickets or 0,
                observation.reward_tickets,
            )
        if observation.reward_collectibles is not None:
            pending.reward_collectibles = max(
                pending.reward_collectibles or 0,
                observation.reward_collectibles,
            )
        if observation.parts_box_used is not None:
            if pending.parts_box_start is None:
                pending.parts_box_start = observation.parts_box_used
            else:
                pending.parts_box_start = min(
                    pending.parts_box_start,
                    observation.parts_box_used,
                )
            if pending.parts_box_end is None:
                pending.parts_box_end = observation.parts_box_used
            else:
                pending.parts_box_end = max(
                    pending.parts_box_end,
                    observation.parts_box_used,
                )
        for name in observation.visible_reward_names:
            if name not in pending.visible_reward_names:
                pending.visible_reward_names.append(name)
        if observation.raw_text and observation.raw_text not in pending.ocr_text:
            pending.ocr_text.append(observation.raw_text)
        if observation.kind == ScreenKind.REWARDS:
            pending.saw_rewards = True
        if screenshot_path is None:
            return
        target = (
            pending.settlement_screenshots
            if observation.kind == ScreenKind.SETTLEMENT
            else pending.reward_screenshots
        )
        value = str(screenshot_path)
        if value not in target:
            target.append(value)

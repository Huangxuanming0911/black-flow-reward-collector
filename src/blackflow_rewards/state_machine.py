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

    def offer(
        self,
        observation: FrameObservation,
        screenshot_path: Path | None = None,
        now: float | None = None,
    ) -> PendingBattle | None:
        now = time.monotonic() if now is None else now
        if observation.kind in (
            ScreenKind.SETTLEMENT,
            ScreenKind.REWARDS,
        ):
            self._last_target_at = now
            if self.pending is None:
                self.pending = PendingBattle(
                    sample_id=new_sample_id(),
                    started_at=datetime.now(UTC).isoformat(),
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
        if observation.stage_name:
            pending.stage_name = observation.stage_name
        if observation.battle_command_xp is not None:
            pending.battle_command_xp = observation.battle_command_xp
        if observation.reward_ingots is not None:
            pending.reward_ingots = observation.reward_ingots
        if observation.reward_tickets is not None:
            pending.reward_tickets = observation.reward_tickets
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


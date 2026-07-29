from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
import time
import uuid

from .knowledge import KNOWN_COLLECTIBLE_PART_GRANTS
from .models import FrameObservation, PendingBattle, ScreenKind


def _prefer_combat_context(existing: str, incoming: str) -> str:
    if not incoming:
        return existing
    # An explicit pre-battle “居民”据点 header is stronger than the generic
    # post-battle resident-disappearance notice.
    if existing == "resident_base" and incoming == "resident_occupied":
        return existing
    if existing and existing != "combat" and incoming == "combat":
        return existing
    return incoming


def new_sample_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    return f"{timestamp}-{uuid.uuid4().hex[:8]}"


class BattleSessionTracker:
    def __init__(
        self,
        finalize_delay_seconds: float = 2.5,
        settlement_grace_seconds: float = 30.0,
        map_return_delay_seconds: float = 1.0,
    ) -> None:
        self.finalize_delay_seconds = finalize_delay_seconds
        self.settlement_grace_seconds = settlement_grace_seconds
        self.map_return_delay_seconds = map_return_delay_seconds
        self.pending: PendingBattle | None = None
        self._last_target_at: float | None = None
        self._map_returned_at: float | None = None
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
            self._map_returned_at = None
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
        returned_to_map = (
            self.pending.saw_rewards
            and any(
                item.startswith("main_map_hud:")
                for item in observation.context_evidence
            )
        )
        if returned_to_map:
            if self._map_returned_at is None:
                self._map_returned_at = now
                return None
            if (
                now - self._map_returned_at
                < self.map_return_delay_seconds
            ):
                return None
            return self._complete()
        required_delay = (
            self.finalize_delay_seconds
            if self.pending.saw_rewards
            else self.settlement_grace_seconds
        )
        if now - self._last_target_at < required_delay:
            return None
        return self._complete()

    def _complete(self) -> PendingBattle:
        assert self.pending is not None
        completed = self.pending
        self.pending = None
        self._last_target_at = None
        self._map_returned_at = None
        self._combat_context = ""
        self._context_evidence = []
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
            self._combat_context = _prefer_combat_context(
                self._combat_context,
                observation.combat_context,
            )
        for item in observation.context_evidence:
            if item not in self._context_evidence:
                self._context_evidence.append(item)

    def force_finalize(self) -> PendingBattle | None:
        completed = self.pending
        self.pending = None
        self._last_target_at = None
        self._map_returned_at = None
        self._combat_context = ""
        self._context_evidence = []
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
            pending.combat_context = _prefer_combat_context(
                pending.combat_context,
                observation.combat_context,
            )
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
        observed_ticket_counts = Counter(
            observation.reward_ticket_names
        )
        for name, count in observed_ticket_counts.items():
            if name not in pending.reward_ticket_names:
                pending.reward_ticket_names.append(name)
            pending.reward_ticket_name_counts[name] = max(
                pending.reward_ticket_name_counts.get(name, 0),
                count,
            )
        if pending.reward_ticket_name_counts:
            specific_counts = {
                name: count
                for name, count in pending.reward_ticket_name_counts.items()
                if name != "招募券"
            }
            generic_count = pending.reward_ticket_name_counts.get(
                "招募券",
                0,
            )
            specific_total = sum(specific_counts.values())
            pending.reward_tickets = max(specific_total, generic_count)
            pending.reward_ticket_names = list(specific_counts)
            if not specific_counts and generic_count:
                pending.reward_ticket_names.append("招募券")
        elif observation.reward_tickets is not None:
            pending.reward_tickets = max(
                pending.reward_tickets or 0,
                observation.reward_tickets,
            )
        if observation.reward_target_life is not None:
            pending.reward_target_life = max(
                pending.reward_target_life or 0,
                observation.reward_target_life,
            )
        if observation.reward_collectibles is not None:
            pending.reward_collectibles = max(
                pending.reward_collectibles or 0,
                observation.reward_collectibles,
            )
        for name in observation.visible_reward_names:
            if name not in pending.visible_reward_names:
                pending.visible_reward_names.append(name)
            if name in KNOWN_COLLECTIBLE_PART_GRANTS:
                pending.part_grant_candidates.setdefault(
                    name,
                    KNOWN_COLLECTIBLE_PART_GRANTS[name],
                )
        for name, amount in observation.part_grant_effects:
            pending.part_grant_candidates[name] = amount
        if observation.parts_box_used is not None:
            current_used = observation.parts_box_used
            previous_used = pending.parts_box_last
            if previous_used is not None and current_used > previous_used:
                delta = current_used - previous_used
                for name, amount in pending.part_grant_candidates.items():
                    if (
                        name in pending.visible_reward_names
                        and not any(
                            item.startswith(f"{name} +")
                            for item in pending.applied_part_effects
                        )
                        and delta == amount
                    ):
                        pending.bonus_parts += amount
                        pending.applied_part_effects.append(
                            f"{name} +{amount}"
                        )
                        break
            pending.parts_box_last = current_used
            if pending.parts_box_start is None:
                pending.parts_box_start = current_used
            else:
                pending.parts_box_start = min(
                    pending.parts_box_start,
                    current_used,
                )
            if pending.parts_box_end is None:
                pending.parts_box_end = current_used
            else:
                pending.parts_box_end = max(
                    pending.parts_box_end,
                    current_used,
                )
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

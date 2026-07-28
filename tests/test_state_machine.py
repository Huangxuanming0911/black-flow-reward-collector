from __future__ import annotations

from pathlib import Path
import unittest

from blackflow_rewards.models import FrameObservation, ScreenKind
from blackflow_rewards.state_machine import BattleSessionTracker


class BattleSessionTrackerTests(unittest.TestCase):
    def test_settlement_rewards_then_other_emits_one_review(self) -> None:
        tracker = BattleSessionTracker(finalize_delay_seconds=2.0)
        settlement = FrameObservation(
            ScreenKind.SETTLEMENT,
            0.98,
            stage_name="趁火打劫",
            battle_command_xp=30,
            combat_context="combat",
        )
        rewards = FrameObservation(
            ScreenKind.REWARDS,
            0.96,
            reward_ingots=3,
            normal_reward_ingots=3,
            reward_tickets=1,
            visible_reward_names=("源石锭", "术师招募券"),
        )
        other = FrameObservation(ScreenKind.OTHER, 0.3)
        self.assertIsNone(
            tracker.offer(
                settlement,
                Path("settlement.jpg"),
                now=0.0,
            )
        )
        self.assertIsNone(
            tracker.offer(
                FrameObservation(
                    ScreenKind.SETTLEMENT,
                    0.98,
                    stage_name="对话误判",
                ),
                now=0.5,
            )
        )
        self.assertIsNone(
            tracker.offer(rewards, Path("rewards.jpg"), now=1.0)
        )
        self.assertIsNone(tracker.offer(other, now=2.9))
        completed = tracker.offer(other, now=3.1)
        self.assertIsNotNone(completed)
        assert completed is not None
        self.assertEqual(completed.stage_name, "趁火打劫")
        self.assertEqual(completed.battle_command_xp, 30)
        self.assertEqual(completed.reward_ingots, 3)
        self.assertEqual(completed.normal_reward_ingots, 3)
        self.assertEqual(completed.reward_tickets, 1)
        self.assertTrue(completed.saw_rewards)
        self.assertEqual(completed.combat_context, "combat")
        self.assertIsNone(tracker.offer(other, now=6.0))

    def test_context_seen_before_settlement_is_inherited(self) -> None:
        tracker = BattleSessionTracker(
            finalize_delay_seconds=0.0,
            settlement_grace_seconds=0.0,
        )
        context = FrameObservation(
            ScreenKind.OTHER,
            0.8,
            source_floor="3",
            location_context="portal_internal",
            combat_context="emergency_combat",
            context_evidence=("roman_floor:III",),
        )
        tracker.offer(context, now=0.0)
        tracker.offer(
            FrameObservation(ScreenKind.SETTLEMENT, 0.9),
            now=1.0,
        )
        completed = tracker.offer(
            FrameObservation(ScreenKind.OTHER, 0.2),
            now=2.0,
        )
        self.assertIsNotNone(completed)
        assert completed is not None
        self.assertEqual(completed.source_floor, "3")
        self.assertEqual(
            completed.location_context,
            "portal_internal",
        )
        self.assertEqual(
            completed.combat_context,
            "emergency_combat",
        )

    def test_ingot_components_survive_separate_reward_frames(self) -> None:
        tracker = BattleSessionTracker(finalize_delay_seconds=0.0)
        tracker.offer(
            FrameObservation(
                ScreenKind.REWARDS,
                0.96,
                reward_ingots=2,
                normal_reward_ingots=2,
                reward_tickets=1,
                reward_collectibles=1,
                parts_box_used=5,
            ),
            now=0.0,
        )
        tracker.offer(
            FrameObservation(
                ScreenKind.REWARDS,
                0.96,
                reward_ingots=2,
                unowned_wealth_ingots=2,
                reward_tickets=0,
                reward_collectibles=0,
                parts_box_used=7,
            ),
            now=1.0,
        )
        completed = tracker.offer(
            FrameObservation(ScreenKind.OTHER, 0.2),
            now=2.0,
        )
        self.assertIsNotNone(completed)
        assert completed is not None
        self.assertEqual(completed.normal_reward_ingots, 2)
        self.assertEqual(completed.unowned_wealth_ingots, 2)
        self.assertEqual(completed.reward_ingots, 4)
        self.assertEqual(completed.reward_tickets, 1)
        self.assertEqual(completed.reward_collectibles, 1)
        self.assertEqual(completed.reward_parts, 2)

    def test_settlement_waits_through_upgrade_pages_for_rewards(self) -> None:
        tracker = BattleSessionTracker(
            finalize_delay_seconds=1.0,
            settlement_grace_seconds=30.0,
        )
        tracker.offer(
            FrameObservation(
                ScreenKind.SETTLEMENT,
                0.98,
                stage_name="本性难移",
                battle_command_xp=21,
                combat_context="combat",
            ),
            Path("settlement.jpg"),
            now=0.0,
        )
        self.assertIsNone(
            tracker.offer(
                FrameObservation(ScreenKind.OTHER, 0.3),
                now=8.0,
            )
        )
        tracker.offer(
            FrameObservation(
                ScreenKind.REWARDS,
                0.96,
                reward_tickets=1,
                visible_reward_names=("先锋招募券",),
            ),
            Path("rewards.jpg"),
            now=9.0,
        )
        completed = tracker.offer(
            FrameObservation(ScreenKind.OTHER, 0.3),
            now=10.1,
        )
        self.assertIsNotNone(completed)
        assert completed is not None
        self.assertEqual(completed.stage_name, "本性难移")
        self.assertEqual(completed.battle_command_xp, 21)
        self.assertEqual(completed.combat_context, "combat")
        self.assertEqual(completed.reward_tickets, 1)
        self.assertEqual(
            completed.settlement_screenshots,
            ["settlement.jpg"],
        )
        self.assertEqual(
            completed.reward_screenshots,
            ["rewards.jpg"],
        )


if __name__ == "__main__":
    unittest.main()

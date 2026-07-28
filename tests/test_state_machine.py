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
        )
        rewards = FrameObservation(
            ScreenKind.REWARDS,
            0.96,
            reward_ingots=3,
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
            tracker.offer(rewards, Path("rewards.jpg"), now=1.0)
        )
        self.assertIsNone(tracker.offer(other, now=2.9))
        completed = tracker.offer(other, now=3.1)
        self.assertIsNotNone(completed)
        assert completed is not None
        self.assertEqual(completed.stage_name, "趁火打劫")
        self.assertEqual(completed.battle_command_xp, 30)
        self.assertEqual(completed.reward_ingots, 3)
        self.assertEqual(completed.reward_tickets, 1)
        self.assertTrue(completed.saw_rewards)
        self.assertIsNone(tracker.offer(other, now=6.0))


if __name__ == "__main__":
    unittest.main()


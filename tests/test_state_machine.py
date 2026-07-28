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

    def test_distinct_tickets_are_unioned_across_reward_frames(self) -> None:
        tracker = BattleSessionTracker(finalize_delay_seconds=0.0)
        tracker.offer(
            FrameObservation(
                ScreenKind.REWARDS,
                0.96,
                reward_tickets=1,
                reward_ticket_names=("重装招募券",),
            ),
            now=0.0,
        )
        tracker.offer(
            FrameObservation(
                ScreenKind.REWARDS,
                0.96,
                reward_tickets=1,
                reward_ticket_names=("远程协议招募券",),
            ),
            now=1.0,
        )
        completed = tracker.offer(
            FrameObservation(ScreenKind.OTHER, 0.2),
            now=2.0,
        )
        self.assertIsNotNone(completed)
        assert completed is not None
        self.assertEqual(completed.reward_tickets, 2)
        self.assertEqual(
            completed.reward_ticket_names,
            ["重装招募券", "远程协议招募券"],
        )

    def test_collectible_part_grant_is_separate_from_node_parts(self) -> None:
        tracker = BattleSessionTracker(finalize_delay_seconds=0.0)
        tracker.offer(
            FrameObservation(
                ScreenKind.REWARDS,
                0.96,
                reward_collectibles=1,
                parts_box_used=7,
                visible_reward_names=("囊中骨", "“抉择”"),
            ),
            now=0.0,
        )
        tracker.offer(
            FrameObservation(
                ScreenKind.REWARDS,
                0.96,
                reward_collectibles=1,
                parts_box_used=10,
                visible_reward_names=("囊中骨", "“抉择”"),
            ),
            now=1.0,
        )
        tracker.offer(
            FrameObservation(
                ScreenKind.REWARDS,
                0.96,
                reward_collectibles=0,
                parts_box_used=10,
                visible_reward_names=("“抉择”",),
            ),
            now=2.0,
        )
        tracker.offer(
            FrameObservation(
                ScreenKind.REWARDS,
                0.96,
                reward_collectibles=0,
                parts_box_used=11,
                visible_reward_names=("“抉择”",),
            ),
            now=3.0,
        )
        completed = tracker.offer(
            FrameObservation(ScreenKind.OTHER, 0.2),
            now=4.0,
        )
        self.assertIsNotNone(completed)
        assert completed is not None
        self.assertEqual(completed.parts_total, 4)
        self.assertEqual(completed.bonus_parts, 3)
        self.assertEqual(completed.reward_parts, 1)
        self.assertEqual(completed.parts_bonus_details, "囊中骨 +3")

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

    def test_return_to_map_finishes_one_second_after_rewards(self) -> None:
        tracker = BattleSessionTracker(
            finalize_delay_seconds=5.0,
            map_return_delay_seconds=1.0,
        )
        tracker.offer(
            FrameObservation(ScreenKind.SETTLEMENT, 0.98),
            now=0.0,
        )
        tracker.offer(
            FrameObservation(
                ScreenKind.REWARDS,
                0.96,
                reward_tickets=1,
            ),
            now=1.0,
        )
        returned_map = FrameObservation(
            ScreenKind.OTHER,
            0.8,
            location_context="main_map",
            context_evidence=("main_map_hud:action_points",),
        )
        self.assertIsNone(tracker.offer(returned_map, now=2.0))
        self.assertIsNone(tracker.offer(returned_map, now=2.9))
        completed = tracker.offer(returned_map, now=3.1)
        self.assertIsNotNone(completed)
        assert completed is not None
        self.assertEqual(completed.reward_tickets, 1)

    def test_map_before_rewards_keeps_settlement_grace(self) -> None:
        tracker = BattleSessionTracker(
            settlement_grace_seconds=30.0,
            map_return_delay_seconds=1.0,
        )
        tracker.offer(
            FrameObservation(ScreenKind.SETTLEMENT, 0.98),
            now=0.0,
        )
        returned_map = FrameObservation(
            ScreenKind.OTHER,
            0.8,
            location_context="main_map",
            context_evidence=("main_map_hud:action_points",),
        )
        self.assertIsNone(tracker.offer(returned_map, now=2.0))
        self.assertIsNone(tracker.offer(returned_map, now=3.1))

    def test_specific_type_survives_generic_settlement_label(self) -> None:
        tracker = BattleSessionTracker(finalize_delay_seconds=0.0)
        tracker.offer(
            FrameObservation(
                ScreenKind.OTHER,
                0.9,
                combat_context="emergency_combat",
                context_evidence=("combat_text:紧急作战",),
            ),
            now=0.0,
        )
        tracker.offer(
            FrameObservation(
                ScreenKind.SETTLEMENT,
                0.98,
                combat_context="combat",
                context_evidence=("combat_text:作战",),
            ),
            now=1.0,
        )
        tracker.offer(
            FrameObservation(ScreenKind.REWARDS, 0.96),
            now=2.0,
        )
        completed = tracker.offer(
            FrameObservation(ScreenKind.OTHER, 0.3),
            now=3.0,
        )
        self.assertIsNotNone(completed)
        assert completed is not None
        self.assertEqual(
            completed.combat_context,
            "emergency_combat",
        )

    def test_specific_type_does_not_leak_into_next_battle(self) -> None:
        tracker = BattleSessionTracker(finalize_delay_seconds=0.0)
        tracker.offer(
            FrameObservation(
                ScreenKind.OTHER,
                0.9,
                combat_context="emergency_combat",
            ),
            now=0.0,
        )
        tracker.offer(
            FrameObservation(
                ScreenKind.SETTLEMENT,
                0.98,
                combat_context="combat",
            ),
            now=1.0,
        )
        tracker.offer(
            FrameObservation(ScreenKind.REWARDS, 0.96),
            now=2.0,
        )
        first = tracker.offer(
            FrameObservation(ScreenKind.OTHER, 0.3),
            now=3.0,
        )
        self.assertIsNotNone(first)
        assert first is not None
        self.assertEqual(first.combat_context, "emergency_combat")

        tracker.offer(
            FrameObservation(
                ScreenKind.SETTLEMENT,
                0.98,
                combat_context="combat",
            ),
            now=4.0,
        )
        tracker.offer(
            FrameObservation(ScreenKind.REWARDS, 0.96),
            now=5.0,
        )
        second = tracker.offer(
            FrameObservation(ScreenKind.OTHER, 0.3),
            now=6.0,
        )
        self.assertIsNotNone(second)
        assert second is not None
        self.assertEqual(second.combat_context, "combat")


if __name__ == "__main__":
    unittest.main()

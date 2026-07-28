from __future__ import annotations

import unittest

from blackflow_rewards.models import OCRToken, ScreenKind
from blackflow_rewards.vision import analyze_tokens, classify_tokens


def token(text: str, x: float, y: float) -> OCRToken:
    return OCRToken(
        text=text,
        confidence=0.99,
        box=((x, y), (x, y), (x, y), (x, y)),
        center_x=x,
        center_y=y,
    )


class VisionRuleTests(unittest.TestCase):
    def test_settlement_text_and_fields(self) -> None:
        tokens = (
            token("成功通过", 0.16, 0.70),
            token("本次作战", 0.66, 0.32),
            token("指挥等级", 0.56, 0.35),
            token("作战", 0.10, 0.52),
            token("趁火打劫", 0.16, 0.58),
            token("30", 0.65, 0.39),
        )
        result = analyze_tokens(tokens)
        self.assertEqual(result.kind, ScreenKind.SETTLEMENT)
        self.assertEqual(result.stage_name, "趁火打劫")
        self.assertEqual(result.battle_command_xp, 30)
        self.assertEqual(result.combat_context, "combat")

    def test_command_xp_uses_lower_battle_anchor_not_shield(self) -> None:
        tokens = (
            token("成功通过", 0.12, 0.79),
            token("本次作战", 0.75, 0.24),
            token("护盾值", 0.65, 0.24),
            token("2", 0.65, 0.30),
            token("本次作战", 0.66, 0.39),
            token("14", 0.67, 0.45),
            token("指挥等级", 0.54, 0.39),
        )
        result = analyze_tokens(tokens)
        self.assertEqual(result.kind, ScreenKind.SETTLEMENT)
        self.assertEqual(result.battle_command_xp, 14)

    def test_reward_text_and_ingot_quantity(self) -> None:
        tokens = (
            token("源石锭", 0.15, 0.47),
            token("×3", 0.15, 0.56),
            token("术师招募券", 0.58, 0.47),
            token("招募一个术师干员", 0.58, 0.56),
            token("收下", 0.15, 0.72),
            token("收下", 0.35, 0.72),
            token("收下", 0.55, 0.72),
            token("直接离开", 0.83, 0.56),
        )
        result = analyze_tokens(tokens)
        self.assertEqual(result.kind, ScreenKind.REWARDS)
        self.assertEqual(result.reward_ingots, 3)
        self.assertEqual(result.normal_reward_ingots, 3)
        self.assertIsNone(result.unowned_wealth_ingots)
        self.assertEqual(result.reward_tickets, 1)
        self.assertEqual(
            result.visible_reward_names,
            ("源石锭", "术师招募券"),
        )

    def test_normal_and_unowned_wealth_ingots_are_separate(self) -> None:
        tokens = (
            token("源石锭", 0.12, 0.47),
            token("×2", 0.12, 0.57),
            token("无主的财富", 0.34, 0.39),
            token("源石锭", 0.34, 0.47),
            token("×2", 0.34, 0.57),
            token("收下", 0.12, 0.72),
            token("收下", 0.34, 0.72),
        )
        result = analyze_tokens(tokens)
        self.assertEqual(result.kind, ScreenKind.REWARDS)
        self.assertEqual(result.normal_reward_ingots, 2)
        self.assertEqual(result.unowned_wealth_ingots, 2)
        self.assertEqual(result.reward_ingots, 4)

    def test_top_area_title_extracts_floor_and_location(self) -> None:
        tokens = (
            token("血色空脉", 0.50, 0.04),
            token("(III) Yerca", 0.50, 0.08),
        )
        result = analyze_tokens(tokens)
        self.assertEqual(result.source_floor, "3")
        self.assertEqual(result.location_context, "main_map")

    def test_hidden_area_is_a_location_not_a_battle_type(self) -> None:
        tokens = (
            token("未萌生的摇篮", 0.52, 0.03),
            token("(??) Feto", 0.52, 0.07),
            token("紧急作战", 0.20, 0.20),
        )
        result = analyze_tokens(tokens)
        self.assertEqual(result.location_context, "portal_internal")
        self.assertEqual(result.combat_context, "emergency_combat")
        self.assertEqual(result.source_floor, "")

    def test_unrelated_text_is_other(self) -> None:
        self.assertEqual(
            classify_tokens((token("行动力", 0.9, 0.1),)),
            ScreenKind.OTHER,
        )


if __name__ == "__main__":
    unittest.main()

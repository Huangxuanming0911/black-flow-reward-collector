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
            token("趁火打劫", 0.16, 0.58),
            token("30", 0.65, 0.39),
        )
        result = analyze_tokens(tokens)
        self.assertEqual(result.kind, ScreenKind.SETTLEMENT)
        self.assertEqual(result.stage_name, "趁火打劫")
        self.assertEqual(result.battle_command_xp, 30)

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
        self.assertEqual(result.reward_tickets, 1)
        self.assertEqual(
            result.visible_reward_names,
            ("源石锭", "术师招募券"),
        )

    def test_unrelated_text_is_other(self) -> None:
        self.assertEqual(
            classify_tokens((token("行动力", 0.9, 0.1),)),
            ScreenKind.OTHER,
        )


if __name__ == "__main__":
    unittest.main()

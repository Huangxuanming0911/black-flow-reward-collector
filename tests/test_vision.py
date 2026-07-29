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
            token("本次作战", 0.66, 0.35),
            token("指挥等级", 0.56, 0.35),
            token("作战", 0.10, 0.52),
            token("趁火打劫", 0.16, 0.58),
            token("30", 0.65, 0.42),
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

    def test_command_xp_supports_lower_16_by_9_layout(self) -> None:
        tokens = (
            token("成功通过", 0.12, 0.79),
            token("本次作战", 0.75, 0.36),
            token("护盾值", 0.65, 0.36),
            token("2", 0.65, 0.42),
            token("指挥等级", 0.54, 0.515),
            token("本次作战", 0.66, 0.515),
            token("21/55", 0.55, 0.58),
            token("15", 0.666, 0.576),
        )
        result = analyze_tokens(tokens)
        self.assertEqual(result.kind, ScreenKind.SETTLEMENT)
        self.assertEqual(result.battle_command_xp, 15)

    def test_animating_settlement_does_not_use_shield_as_xp(self) -> None:
        tokens = (
            token("成功通过", 0.12, 0.79),
            token("本次作战", 0.75, 0.24),
            token("护盾值", 0.65, 0.24),
            token("2", 0.65, 0.30),
        )
        result = analyze_tokens(tokens)
        self.assertEqual(result.kind, ScreenKind.SETTLEMENT)
        self.assertIsNone(result.battle_command_xp)

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

    def test_recruit_ticket_ocr_variant_is_counted(self) -> None:
        tokens = (
            token("重装招募卷INFO/", 0.24, 0.53),
            token("直接离开", 0.55, 0.57),
            token("收下", 0.20, 0.72),
        )
        result = analyze_tokens(tokens)
        self.assertEqual(result.kind, ScreenKind.REWARDS)
        self.assertEqual(result.reward_tickets, 1)
        self.assertEqual(result.reward_ticket_names, ("重装招募券",))
        self.assertEqual(
            result.visible_reward_names,
            ("重装招募券",),
        )

    def test_target_life_reward_is_read_inside_reward_card(self) -> None:
        tokens = (
            token("目标生命", 0.47, 0.49),
            token("+1", 0.47, 0.58),
            token("收下", 0.47, 0.73),
            token("直接离开", 0.85, 0.57),
        )
        result = analyze_tokens(tokens)
        self.assertEqual(result.kind, ScreenKind.REWARDS)
        self.assertEqual(result.reward_target_life, 1)

    def test_distinct_protocol_tickets_are_counted_separately(self) -> None:
        tokens = (
            token("破坏协议招募券", 0.24, 0.49),
            token("远程协议招募券", 0.48, 0.49),
            token("收下", 0.24, 0.72),
            token("收下", 0.48, 0.72),
            token("直接离开", 0.82, 0.57),
        )
        result = analyze_tokens(tokens)
        self.assertEqual(result.kind, ScreenKind.REWARDS)
        self.assertEqual(result.reward_tickets, 2)

    def test_fifth_reward_card_ticket_is_not_clipped(self) -> None:
        tokens = (
            token("重装招募券", 0.84, 0.52),
            token("收下", 0.84, 0.72),
            token("直接离开", 0.96, 0.57),
        )
        result = analyze_tokens(tokens)
        self.assertEqual(result.kind, ScreenKind.REWARDS)
        self.assertEqual(result.reward_tickets, 1)
        self.assertEqual(result.reward_ticket_names, ("重装招募券",))
        self.assertIn("重装招募券", result.visible_reward_names)

    def test_reward_cards_are_discovered_from_all_visible_buttons(self) -> None:
        positions = (0.06, 0.20, 0.34, 0.48, 0.62, 0.76, 0.90)
        titles = (
            "奖励一",
            "奖励二",
            "奖励三",
            "奖励四",
            "奖励五",
            "奖励六",
            "医疗招募券",
        )
        tokens = tuple(
            item
            for x, title in zip(positions, titles, strict=True)
            for item in (
                token(title, x, 0.49),
                token("收下", x, 0.73),
            )
        )
        result = analyze_tokens(tokens)
        self.assertEqual(result.kind, ScreenKind.REWARDS)
        self.assertEqual(result.visible_reward_names, titles)
        self.assertEqual(result.reward_tickets, 1)
        self.assertEqual(result.reward_ticket_names, ("医疗招募券",))

    def test_identical_ticket_cards_are_counted_separately(self) -> None:
        tokens = (
            token("重装招募券", 0.30, 0.49),
            token("收下", 0.30, 0.73),
            token("重装招募券", 0.70, 0.49),
            token("收下", 0.70, 0.73),
        )
        result = analyze_tokens(tokens)
        self.assertEqual(result.reward_tickets, 2)
        self.assertEqual(
            result.reward_ticket_names,
            ("重装招募券", "重装招募券"),
        )

    def test_direct_collectible_and_parts_box_are_read(self) -> None:
        tokens = (
            token("残破合影", 0.30, 0.49),
            token("收下", 0.30, 0.73),
            token("辅助招募券", 0.48, 0.49),
            token("收下", 0.48, 0.73),
            token("“抉择”", 0.67, 0.49),
            token("选择", 0.67, 0.73),
            token("直接离开", 0.85, 0.57),
            token("5/14", 0.65, 0.97),
        )
        result = analyze_tokens(tokens)
        self.assertEqual(result.kind, ScreenKind.REWARDS)
        self.assertEqual(result.reward_tickets, 1)
        self.assertEqual(result.reward_collectibles, 1)
        self.assertEqual(result.parts_box_used, 5)

    def test_immediate_part_grant_is_read_from_card_text(self) -> None:
        tokens = (
            token("囊中骨", 0.48, 0.494),
            token("立刻获得3个随机的普通加工", 0.48, 0.552),
            token("品", 0.48, 0.579),
            token("收下", 0.48, 0.728),
            token("7/14", 0.65, 0.967),
            token("直接离开", 0.85, 0.57),
        )
        result = analyze_tokens(tokens)
        self.assertEqual(
            result.part_grant_effects,
            (("囊中骨", 3),),
        )

    def test_part_choice_screen_is_not_counted_as_collectibles(self) -> None:
        tokens = (
            token("霜晶树", 0.39, 0.46),
            token("或是", 0.50, 0.46),
            token("报废轮子", 0.61, 0.46),
            token("收下", 0.39, 0.69),
            token("收下", 0.61, 0.69),
            token("直接离开", 0.80, 0.57),
        )
        result = analyze_tokens(tokens)
        self.assertEqual(result.kind, ScreenKind.REWARDS)
        self.assertEqual(result.reward_collectibles, 0)

    def test_processing_part_cards_are_not_collectibles(self) -> None:
        tokens = (
            token("加工品", 0.35, 0.18),
            token("标准引擎", 0.39, 0.46),
            token("收下", 0.39, 0.69),
            token("加工品", 0.57, 0.18),
            token("一次性喷气背包", 0.61, 0.46),
            token("收下", 0.61, 0.69),
            token("直接离开", 0.82, 0.57),
        )
        result = analyze_tokens(tokens)
        self.assertEqual(result.kind, ScreenKind.REWARDS)
        self.assertEqual(result.reward_collectibles, 0)

    def test_resident_base_notice_and_stage_set_node_type(self) -> None:
        tokens = (
            token("成功通过", 0.12, 0.79),
            token("本次作战", 0.75, 0.36),
            token("作战", 0.08, 0.64),
            token("枯枝", 0.10, 0.69),
            token(
                "流窜“居民”已经从林间消失",
                0.80,
                0.18,
            ),
        )
        result = analyze_tokens(tokens)
        self.assertEqual(result.kind, ScreenKind.SETTLEMENT)
        self.assertEqual(result.combat_context, "resident_base")

    def test_pursuit_status_on_map_is_not_a_node_type(self) -> None:
        result = analyze_tokens(
            (
                token("追猎", 0.50, 0.12),
                token("行动力", 0.92, 0.145),
            )
        )
        self.assertEqual(result.kind, ScreenKind.OTHER)
        self.assertEqual(result.combat_context, "")
        self.assertIn("forced_state:pursuit", result.context_evidence)

    def test_known_encounter_stage_overrides_generic_combat(self) -> None:
        result = analyze_tokens(
            (
                token("成功通过", 0.12, 0.79),
                token("指挥等级", 0.54, 0.515),
                token("本次作战", 0.66, 0.515),
                token("作战", 0.08, 0.64),
                token("共斗", 0.08, 0.69),
            )
        )
        self.assertEqual(result.kind, ScreenKind.SETTLEMENT)
        self.assertEqual(result.stage_name, "共斗")
        self.assertEqual(result.combat_context, "encounter")
        self.assertIn(
            "stage_context:共斗",
            result.context_evidence,
        )

    def test_resident_occupied_stage_overrides_emergency_header(self) -> None:
        tokens = (
            token("成功通过", 0.16, 0.70),
            token("本次作战", 0.66, 0.35),
            token("紧急作战", 0.10, 0.50),
            token("进退趋同", 0.16, 0.58),
            token("21", 0.65, 0.42),
        )
        result = analyze_tokens(tokens)
        self.assertEqual(result.stage_name, "进退趋同")
        self.assertEqual(result.combat_context, "resident_occupied")
        self.assertIn(
            "stage_context:进退趋同",
            result.context_evidence,
        )

    def test_resident_base_stage_overrides_generic_combat(self) -> None:
        tokens = (
            token("成功通过", 0.16, 0.70),
            token("本次作战", 0.66, 0.35),
            token("作战", 0.10, 0.50),
            token("败叶", 0.16, 0.58),
            token("36", 0.65, 0.42),
        )
        result = analyze_tokens(tokens)
        self.assertEqual(result.stage_name, "败叶")
        self.assertEqual(
            result.combat_context,
            "resident_base",
        )
        self.assertIn(
            "stage_context:败叶",
            result.context_evidence,
        )

    def test_top_area_title_extracts_floor_and_location(self) -> None:
        tokens = (
            token("血色空脉", 0.50, 0.04),
            token("(III) Yerca", 0.50, 0.08),
        )
        result = analyze_tokens(tokens)
        self.assertEqual(result.source_floor, "3")
        self.assertEqual(result.location_context, "main_map")

    def test_action_point_hud_marks_interactive_main_map(self) -> None:
        result = analyze_tokens(
            (
                token("行动力", 0.92, 0.145),
                token("4", 0.91, 0.196),
                token("零件箱", 0.65, 0.925),
            )
        )
        self.assertEqual(result.kind, ScreenKind.OTHER)
        self.assertEqual(result.location_context, "main_map")
        self.assertIn(
            "main_map_hud:action_points",
            result.context_evidence,
        )

    def test_node_labels_and_bottom_hud_mark_main_map(self) -> None:
        result = analyze_tokens(
            (
                token("未知的诡秘", 0.40, 0.42),
                token("零件箱", 0.65, 0.925),
                token("收藏品", 0.16, 0.925),
                token("干员", 0.76, 0.925),
            )
        )
        self.assertEqual(result.kind, ScreenKind.OTHER)
        self.assertEqual(result.location_context, "main_map")
        self.assertIn(
            "main_map_hud:node_map",
            result.context_evidence,
        )

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

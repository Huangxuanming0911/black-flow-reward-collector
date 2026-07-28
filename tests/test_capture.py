from __future__ import annotations

from types import SimpleNamespace
import unittest

from blackflow_rewards.capture import select_game_window


def window(name: str, hwnd: int) -> SimpleNamespace:
    return SimpleNamespace(window_name=name, hwnd=hwnd)


class WindowSelectionTests(unittest.TestCase):
    def test_exact_game_title_wins_over_browser_page(self) -> None:
        game = window("明日方舟", 1)
        browser = window(
            "Huangxuanming0911/black-flow-reward-collector: "
            "只读的明日方舟黑流树海战后奖励采集与统计工具 "
            "- Google Chrome",
            2,
        )
        selected = select_game_window([browser, game], "明日方舟")
        self.assertIs(selected, game)

    def test_browser_candidate_is_excluded_without_exact_title(self) -> None:
        game = window("明日方舟 PC客户端", 1)
        browser = window("明日方舟攻略 - Microsoft Edge", 2)
        selected = select_game_window([browser, game], "明日方舟")
        self.assertIs(selected, game)

    def test_ambiguous_game_candidates_still_fail_safely(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "无法唯一确定"):
            select_game_window(
                [
                    window("明日方舟 PC客户端", 1),
                    window("明日方舟 云游戏", 2),
                ],
                "明日方舟",
            )


if __name__ == "__main__":
    unittest.main()

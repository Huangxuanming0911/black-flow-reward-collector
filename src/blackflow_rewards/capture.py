from __future__ import annotations

from pathlib import Path
from typing import Any


_NON_GAME_WINDOW_MARKERS = (
    "google chrome",
    "microsoft edge",
    "mozilla firefox",
    "brave",
    "opera",
    "战后奖励采集器",
    "black-flow-reward-collector",
)


def select_game_window(
    windows: list[Any],
    window_title: str,
) -> Any:
    """Prefer the exact game title over pages mentioning the game."""
    target = window_title.strip().casefold()
    matches = [
        item
        for item in windows
        if target in item.window_name.strip().casefold()
    ]
    exact = [
        item
        for item in matches
        if item.window_name.strip().casefold() == target
    ]
    if len(exact) == 1:
        return exact[0]

    filtered = [
        item
        for item in matches
        if not any(
            marker in item.window_name.casefold()
            for marker in _NON_GAME_WINDOW_MARKERS
        )
    ]
    if len(filtered) == 1:
        return filtered[0]

    names = [item.window_name for item in matches]
    raise RuntimeError(
        f"无法唯一确定游戏窗口 {window_title!r}，候选窗口：{names!r}"
    )


class MaaWindowCapture:
    """Read-only MaaFramework capture source for one PC client window."""

    def __init__(
        self,
        window_title: str = "明日方舟",
        target_long_side: int = 1920,
    ) -> None:
        import maa
        from maa.controller import Win32Controller
        from maa.define import (
            MaaWin32InputMethodEnum,
            MaaWin32ScreencapMethodEnum,
        )
        from maa.library import Library
        from maa.toolkit import Toolkit

        package_root = Path(maa.__file__).resolve().parent
        Library.open(package_root / "bin")
        game_window = select_game_window(
            Toolkit.find_desktop_windows(),
            window_title,
        )
        self.window_name = game_window.window_name
        self.controller: Any = Win32Controller(
            game_window.hwnd,
            # FramePool avoids the repeated PrintWindow fallback that can
            # briefly stall a hardware-accelerated game window.
            screencap_method=MaaWin32ScreencapMethodEnum.FramePool,
            # This collector never sends input, so do not install input hooks.
            mouse_method=MaaWin32InputMethodEnum.PostMessage,
            keyboard_method=MaaWin32InputMethodEnum.PostMessage,
        )
        self.controller.set_screenshot_target_long_side(target_long_side)
        connection = self.controller.post_connection().wait()
        if not connection.succeeded:
            raise RuntimeError("MaaFramework 无法连接明日方舟窗口")

    def capture(self):
        job = self.controller.post_screencap().wait()
        if not job.succeeded:
            raise RuntimeError("MaaFramework 截图失败")
        return job.get()

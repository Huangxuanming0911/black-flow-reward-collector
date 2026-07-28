from __future__ import annotations

from pathlib import Path
from typing import Any


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
        windows = [
            item
            for item in Toolkit.find_desktop_windows()
            if window_title.casefold() in item.window_name.casefold()
        ]
        if len(windows) != 1:
            names = [item.window_name for item in windows]
            raise RuntimeError(
                f"需要唯一的窗口匹配 {window_title!r}，当前找到：{names!r}"
            )
        self.window_name = windows[0].window_name
        self.controller: Any = Win32Controller(
            windows[0].hwnd,
            screencap_method=MaaWin32ScreencapMethodEnum.Background,
            mouse_method=MaaWin32InputMethodEnum.Seize,
            keyboard_method=MaaWin32InputMethodEnum.Seize,
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


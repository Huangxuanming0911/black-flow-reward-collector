from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
import tkinter as tk

from blackflow_rewards.images import read_image
from blackflow_rewards.models import PendingBattle
from blackflow_rewards.state_machine import BattleSessionTracker
from blackflow_rewards.store import RewardStore
from blackflow_rewards.ui import (
    COMBAT_NAMES,
    LOCATION_NAMES,
    ReviewDialog,
)
from blackflow_rewards.vision import FrameAnalyzer


def load_session(directory: Path) -> PendingBattle:
    paths = sorted(
        directory.glob("*.jpg"),
        key=lambda path: path.stat().st_mtime,
    )
    if not paths:
        raise RuntimeError(f"目录中没有证据截图：{directory}")
    analyzer = FrameAnalyzer()
    tracker = BattleSessionTracker()
    for index, path in enumerate(paths):
        observation = analyzer.analyze(read_image(path))
        tracker.offer(
            observation,
            screenshot_path=path.resolve(),
            now=float(index),
        )
    pending = tracker.force_finalize()
    if pending is None:
        raise RuntimeError("截图中没有识别到结算页或奖励页")
    pending.sample_id = f"{directory.name}-recovered"
    pending.started_at = datetime.fromtimestamp(
        min(path.stat().st_mtime for path in paths),
        tz=UTC,
    ).isoformat()
    return pending


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Review a saved settlement/reward screenshot session."
    )
    parser.add_argument("directory", type=Path)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
    )
    args = parser.parse_args()
    pending = load_session(args.directory.resolve())

    root = tk.Tk()
    root.withdraw()
    dialog = ReviewDialog(
        root,
        pending,
        defaults={
            "source_floor": pending.source_floor or "未知",
            "location_context": LOCATION_NAMES.get(
                pending.location_context,
                LOCATION_NAMES["main_map"],
            ),
            "combat_context": COMBAT_NAMES.get(
                pending.combat_context,
                COMBAT_NAMES["combat"],
            ),
        },
        topmost=True,
    )
    root.wait_window(dialog.window)
    if dialog.record is not None:
        RewardStore(
            args.project_root.resolve() / "data" / "records"
        ).append(dialog.record)
    root.destroy()


if __name__ == "__main__":
    main()

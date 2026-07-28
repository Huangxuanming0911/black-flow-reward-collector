from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import queue
import threading
import time

from .capture import MaaWindowCapture
from .images import write_jpeg
from .models import FrameObservation, PendingBattle, ScreenKind
from .state_machine import BattleSessionTracker
from .vision import (
    FrameAnalyzer,
    frame_signature,
    signature_difference,
)


class LiveCollector:
    def __init__(
        self,
        output_root: Path,
        events: queue.Queue[tuple[str, object]],
        window_title: str = "明日方舟",
        interval_seconds: float = 0.75,
    ) -> None:
        self.output_root = output_root
        self.events = events
        self.window_title = window_title
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="blackflow-reward-live",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        try:
            capture = MaaWindowCapture(self.window_title)
            analyzer = FrameAnalyzer()
            tracker = BattleSessionTracker()
            self.events.put(
                ("status", f"已只读连接：{capture.window_name}")
            )
            previous_signature = None
            previous_observation = FrameObservation(
                ScreenKind.OTHER,
                0.0,
            )
            last_saved_signature = None
            pending_dir: Path | None = None
            while not self._stop.is_set():
                frame = capture.capture()
                signature = frame_signature(frame)
                changed = (
                    previous_signature is None
                    or signature_difference(
                        signature,
                        previous_signature,
                    )
                    >= 1.4
                )
                if changed:
                    previous_observation = analyzer.analyze(frame)
                    previous_signature = signature
                    self.events.put(
                        (
                            "status",
                            "画面："
                            f"{previous_observation.kind.value} "
                            f"({previous_observation.confidence:.0%})",
                        )
                    )
                screenshot_path = None
                if previous_observation.kind in (
                    ScreenKind.SETTLEMENT,
                    ScreenKind.REWARDS,
                ):
                    if tracker.pending is None:
                        pending_dir = (
                            self.output_root
                            / "screenshots"
                            / datetime.now(UTC).strftime(
                                "%Y%m%dT%H%M%S"
                            )
                        )
                    should_save = (
                        last_saved_signature is None
                        or signature_difference(
                            signature,
                            last_saved_signature,
                        )
                        >= 1.4
                    )
                    if should_save and pending_dir is not None:
                        pending_dir.mkdir(parents=True, exist_ok=True)
                        prefix = (
                            "settlement"
                            if previous_observation.kind
                            == ScreenKind.SETTLEMENT
                            else "rewards"
                        )
                        screenshot_path = (
                            pending_dir
                            / f"{prefix}-{int(time.time() * 1000)}.jpg"
                        )
                        write_jpeg(screenshot_path, frame)
                        last_saved_signature = signature.copy()
                completed = tracker.offer(
                    previous_observation,
                    screenshot_path=screenshot_path,
                )
                if completed is not None:
                    self.events.put(("review", completed))
                    pending_dir = None
                    last_saved_signature = None
                time.sleep(max(0.25, self.interval_seconds))
            completed = tracker.force_finalize()
            if completed is not None:
                self.events.put(("review", completed))
            self.events.put(("status", "采集已停止"))
        except Exception as exc:
            self.events.put(("error", str(exc)))

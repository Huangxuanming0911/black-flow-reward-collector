from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import queue
import threading
import time

import cv2
import numpy as np

from .capture import MaaWindowCapture
from .images import write_jpeg
from .models import FrameObservation, ScreenKind
from .state_machine import BattleSessionTracker
from .vision import (
    FrameAnalyzer,
    frame_signature,
    signature_difference,
)


@dataclass(frozen=True, slots=True)
class CapturedFrame:
    jpeg: bytes
    signature: np.ndarray
    captured_at: float
    epoch_ms: int

    def decode(self) -> np.ndarray:
        encoded = np.frombuffer(self.jpeg, dtype=np.uint8)
        frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if frame is None:
            raise RuntimeError("无法解码采集帧")
        return frame


class FrameBuffer:
    """A bounded, thread-safe buffer that keeps recent pre-roll frames."""

    def __init__(
        self,
        normal_limit: int = 8,
        burst_limit: int = 32,
    ) -> None:
        self.normal_limit = normal_limit
        self.burst_limit = burst_limit
        self._items: deque[CapturedFrame] = deque()
        self._condition = threading.Condition()
        self._error: Exception | None = None

    def put(self, item: CapturedFrame, burst: bool) -> None:
        limit = self.burst_limit if burst else self.normal_limit
        with self._condition:
            self._items.append(item)
            while len(self._items) > limit:
                if burst and len(self._items) > 2:
                    self._drop_least_distinct_interior()
                else:
                    self._items.popleft()
            self._condition.notify()

    def _drop_least_distinct_interior(self) -> None:
        """Compact animation frames without deleting visual transitions.

        In burst mode OCR is much slower than capture. Dropping the oldest
        frame loses short-lived reward cards; instead, remove the interior
        frame whose two adjacent visual changes are smallest. The first
        pending frame, newest frame, and both sides of large transitions are
        consequently retained.
        """
        items = list(self._items)
        remove_at = min(
            range(1, len(items) - 1),
            key=lambda index: max(
                signature_difference(
                    items[index - 1].signature,
                    items[index].signature,
                ),
                signature_difference(
                    items[index].signature,
                    items[index + 1].signature,
                ),
            ),
        )
        del items[remove_at]
        self._items = deque(items)

    def get(self, timeout: float) -> CapturedFrame | None:
        deadline = time.monotonic() + timeout
        with self._condition:
            while not self._items and self._error is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._condition.wait(remaining)
            if self._error is not None:
                raise self._error
            return self._items.popleft() if self._items else None

    def set_error(self, error: Exception) -> None:
        with self._condition:
            self._error = error
            self._condition.notify_all()

    def wake(self) -> None:
        with self._condition:
            self._condition.notify_all()

    def __len__(self) -> int:
        with self._condition:
            return len(self._items)


class LiveCollector:
    def __init__(
        self,
        output_root: Path,
        events: queue.Queue[tuple[str, object]],
        window_title: str = "明日方舟",
        interval_seconds: float = 0.55,
        burst_interval_seconds: float = 0.18,
    ) -> None:
        self.output_root = output_root
        self.events = events
        self.window_title = window_title
        self.interval_seconds = interval_seconds
        self.burst_interval_seconds = burst_interval_seconds
        self._stop = threading.Event()
        self._burst = threading.Event()
        self._thread: threading.Thread | None = None
        self._capture_thread: threading.Thread | None = None
        self._frames = FrameBuffer()
        self._last_phase = ""

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._burst.clear()
        self._frames = FrameBuffer()
        self._last_phase = ""
        self._thread = threading.Thread(
            target=self._run,
            name="blackflow-reward-analyze",
            daemon=True,
        )
        self._thread.start()

    def _emit_phase(self, phase: str) -> None:
        if phase == self._last_phase:
            return
        self._last_phase = phase
        self.events.put(("phase", phase))

    def stop(self) -> None:
        self._stop.set()
        self._frames.wake()

    def _capture_loop(self) -> None:
        try:
            capture = MaaWindowCapture(self.window_title)
            self.events.put(
                ("status", f"已只读连接：{capture.window_name}")
            )
            self._emit_phase("monitoring")
            previous_signature: np.ndarray | None = None
            while not self._stop.is_set():
                started = time.monotonic()
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
                    success, encoded = cv2.imencode(
                        ".jpg",
                        frame,
                        (cv2.IMWRITE_JPEG_QUALITY, 94),
                    )
                    if not success:
                        raise RuntimeError("无法压缩采集帧")
                    self._frames.put(
                        CapturedFrame(
                            jpeg=encoded.tobytes(),
                            signature=signature,
                            captured_at=time.monotonic(),
                            epoch_ms=int(time.time() * 1000),
                        ),
                        burst=self._burst.is_set(),
                    )
                    previous_signature = signature
                interval = (
                    self.burst_interval_seconds
                    if self._burst.is_set()
                    else self.interval_seconds
                )
                elapsed = time.monotonic() - started
                self._stop.wait(max(0.02, interval - elapsed))
        except Exception as exc:
            self._frames.set_error(exc)

    def _run(self) -> None:
        # Reward cards are shown one by one and their transition animations
        # can briefly look like an unrelated screen. Keep the same battle
        # alive long enough for later ingot/collectible/ticket cards to arrive.
        tracker = BattleSessionTracker(finalize_delay_seconds=5.0)
        last_observation = FrameObservation(ScreenKind.OTHER, 0.0)
        last_saved_signature: np.ndarray | None = None
        pending_dir: Path | None = None
        try:
            self._capture_thread = threading.Thread(
                target=self._capture_loop,
                name="blackflow-reward-capture",
                daemon=True,
            )
            self._capture_thread.start()
            analyzer = FrameAnalyzer()
            while not self._stop.is_set():
                captured = self._frames.get(timeout=0.25)
                if captured is None:
                    if (
                        last_observation.kind == ScreenKind.OTHER
                        and tracker.pending is not None
                    ):
                        completed = tracker.offer(
                            last_observation,
                            now=time.monotonic(),
                        )
                        if completed is not None:
                            self._emit_phase("review")
                            self.events.put(("review", completed))
                            self._burst.clear()
                            pending_dir = None
                            last_saved_signature = None
                    continue

                frame = captured.decode()
                observation = analyzer.analyze(frame)
                last_observation = observation
                self.events.put(
                    (
                        "status",
                        "画面："
                        f"{observation.kind.value} "
                        f"({observation.confidence:.0%}) "
                        f"缓冲 {len(self._frames)}",
                    )
                )
                if observation.kind in (
                    ScreenKind.SETTLEMENT,
                    ScreenKind.REWARDS,
                ):
                    self._burst.set()
                if (
                    observation.kind == ScreenKind.SETTLEMENT
                    and tracker.pending is None
                ):
                    self._emit_phase("settlement")
                elif (
                    observation.kind == ScreenKind.REWARDS
                    and (
                        tracker.pending is None
                        or not tracker.pending.saw_rewards
                    )
                ):
                    self._emit_phase("rewards")
                elif (
                    observation.kind == ScreenKind.OTHER
                    and tracker.pending is not None
                    and tracker.pending.saw_rewards
                    and "main_map_hud:action_points"
                    in observation.context_evidence
                ):
                    self._emit_phase("finalizing")

                screenshot_path = None
                if observation.kind in (
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
                            captured.signature,
                            last_saved_signature,
                        )
                        >= 1.4
                    )
                    if should_save and pending_dir is not None:
                        pending_dir.mkdir(parents=True, exist_ok=True)
                        prefix = (
                            "settlement"
                            if observation.kind == ScreenKind.SETTLEMENT
                            else "rewards"
                        )
                        screenshot_path = (
                            pending_dir
                            / f"{prefix}-{captured.epoch_ms}.jpg"
                        )
                        write_jpeg(screenshot_path, frame)
                        last_saved_signature = captured.signature.copy()

                completed = tracker.offer(
                    observation,
                    screenshot_path=screenshot_path,
                    now=captured.captured_at,
                )
                if completed is not None:
                    self._emit_phase("review")
                    self.events.put(("review", completed))
                    self._burst.clear()
                    pending_dir = None
                    last_saved_signature = None

            completed = tracker.force_finalize()
            if completed is not None:
                self._emit_phase("review")
                self.events.put(("review", completed))
            self._emit_phase("stopped")
            self.events.put(("status", "采集已停止"))
        except Exception as exc:
            self.events.put(("error", str(exc)))
        finally:
            self._burst.clear()

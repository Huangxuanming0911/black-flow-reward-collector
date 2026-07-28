from __future__ import annotations

import unittest

import numpy as np

from blackflow_rewards.runtime import CapturedFrame, FrameBuffer


def frame(index: int) -> CapturedFrame:
    return CapturedFrame(
        jpeg=b"frame",
        signature=np.full((2, 2), index, dtype=np.uint8),
        captured_at=float(index),
        epoch_ms=index,
    )


class FrameBufferTests(unittest.TestCase):
    def test_normal_mode_keeps_recent_preroll(self) -> None:
        buffer = FrameBuffer(normal_limit=3, burst_limit=5)
        for index in range(5):
            buffer.put(frame(index), burst=False)
        self.assertEqual(len(buffer), 3)
        self.assertEqual(buffer.get(0.0).epoch_ms, 2)
        self.assertEqual(buffer.get(0.0).epoch_ms, 3)
        self.assertEqual(buffer.get(0.0).epoch_ms, 4)

    def test_burst_mode_has_larger_capacity(self) -> None:
        buffer = FrameBuffer(normal_limit=2, burst_limit=4)
        for index in range(5):
            buffer.put(frame(index), burst=True)
        self.assertEqual(len(buffer), 4)
        self.assertEqual(buffer.get(0.0).epoch_ms, 1)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np

from blackflow_rewards.images import read_image, write_jpeg


class UnicodeImagePathTests(unittest.TestCase):
    def test_round_trip_with_chinese_filename(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "结算页-趁火打劫.jpg"
            image = np.zeros((32, 48, 3), dtype=np.uint8)
            image[:, :, 1] = 200
            write_jpeg(path, image)
            restored = read_image(path)
            self.assertEqual(restored.shape, image.shape)


if __name__ == "__main__":
    unittest.main()

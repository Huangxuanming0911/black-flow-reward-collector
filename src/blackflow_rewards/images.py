from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def read_image(path: Path) -> np.ndarray:
    buffer = np.fromfile(path, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"无法读取图片：{path}")
    return image


def write_jpeg(
    path: Path,
    image: np.ndarray,
    quality: int = 94,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    succeeded, encoded = cv2.imencode(
        ".jpg",
        image,
        [cv2.IMWRITE_JPEG_QUALITY, quality],
    )
    if not succeeded:
        raise RuntimeError(f"无法编码图片：{path}")
    encoded.tofile(path)


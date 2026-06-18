"""
OpenCV preprocessing for legal document OCR — denoise, sharpen, threshold, deskew.
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)


def preprocess_for_ocr(image: Any) -> Any:
    """
    Apply grayscale → denoise → contrast → adaptive threshold → optional deskew.
    Accepts numpy RGB/BGR array or PIL Image; returns numpy array for OCR engines.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        return image

    arr = image
    if hasattr(image, "mode"):
        import numpy as np
        from PIL import Image

        if isinstance(image, Image.Image):
            arr = np.array(image.convert("RGB"))

    if arr is None:
        return image

    try:
        if len(arr.shape) == 3 and arr.shape[2] >= 3:
            gray = cv2.cvtColor(arr[:, :, :3], cv2.COLOR_RGB2GRAY)
        else:
            gray = arr if len(arr.shape) == 2 else cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)

        gray = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
        gray = cv2.convertScaleAbs(gray, alpha=1.35, beta=8)
        sharp_kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
        gray = cv2.filter2D(gray, -1, sharp_kernel)

        binary = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            11,
        )

        angle = _estimate_skew_angle(binary)
        if abs(angle) >= 0.4:
            binary = _rotate_image(binary, angle)

        return binary
    except Exception as exc:
        logger.debug("OCR preprocess fallback: %s", exc)
        return arr


def _estimate_skew_angle(gray: Any) -> float:
    try:
        import cv2
        import numpy as np

        coords = np.column_stack(np.where(gray < 128))
        if len(coords) < 100:
            return 0.0
        rect = cv2.minAreaRect(coords)
        angle = rect[-1]
        if angle < -45:
            angle = 90 + angle
        return float(angle)
    except Exception:
        return 0.0


def _rotate_image(image: Any, angle: float) -> Any:
    try:
        import cv2
        import numpy as np

        (h, w) = image.shape[:2]
        center = (w // 2, h // 2)
        mat = cv2.getRotationMatrix2D(center, angle, 1.0)
        return cv2.warpAffine(
            image,
            mat,
            (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )
    except Exception:
        return image


def ocr_confidence_score(text: str) -> float:
    """Heuristic OCR quality 0..1 based on alphanumeric ratio and word shape."""
    t = (text or "").strip()
    if not t:
        return 0.0
    alnum = sum(1 for c in t if c.isalnum())
    ratio = alnum / max(len(t), 1)
    words = t.split()
    if not words:
        return ratio
    good = sum(1 for w in words if len(w) >= 2 and sum(c.isalpha() for c in w) / max(len(w), 1) > 0.5)
    word_ratio = good / len(words)
    return min(1.0, 0.55 * ratio + 0.45 * word_ratio)

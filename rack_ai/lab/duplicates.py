"""Confirm hash candidates using pixels, including the reviewed rack regions.

A 64-bit scene hash alone cannot establish duplication in fixed CCTV views.
These conservative thresholds detect nearly identical frames, not semantically
similar racks. Exact hashes and source/session isolation remain separate checks.
"""
import cv2
import numpy as np


def thumbnail(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return cv2.GaussianBlur(cv2.resize(gray, (256, 256), interpolation=cv2.INTER_AREA), (3, 3), 0)


def confirmed_duplicate(first: np.ndarray, second: np.ndarray,
                        first_boxes: list, second_boxes: list) -> bool:
    difference = cv2.absdiff(first, second).astype(np.float32)
    if float(difference.mean()) > 3.0:
        return False
    mask = np.zeros(first.shape, dtype=bool)
    height, width = first.shape
    for a, b, c, d in first_boxes + second_boxes:
        x1, y1 = max(0, int(a*width)), max(0, int(b*height))
        x2, y2 = min(width, int(np.ceil(c*width))), min(height, int(np.ceil(d*height)))
        mask[y1:y2, x1:x2] = True
    values = difference[mask] if mask.any() else difference.ravel()
    return float(values.mean()) <= 5.0 and float(np.mean(values > 12.0)) <= .02

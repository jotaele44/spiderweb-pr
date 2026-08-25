"""Fail-closed per-screenshot georeferencing from OCR-matched anchor points."""

from __future__ import annotations

from dataclasses import dataclass
import re

import cv2
import numpy as np


@dataclass(frozen=True)
class GeoAnchor:
    pixel_x: float
    pixel_y: float
    longitude: float
    latitude: float


@dataclass(frozen=True)
class HomographyFit:
    matrix: np.ndarray
    rms_error_px: float
    anchor_count: int

    def project(self, pixel_x: float, pixel_y: float) -> tuple[float, float]:
        point = cv2.perspectiveTransform(
            np.array([[[pixel_x, pixel_y]]], dtype=np.float64), self.matrix
        )[0][0]
        return float(point[0]), float(point[1])


def fit_homography(
    anchors: list[GeoAnchor], *, max_rms_error_px: float = 5.0
) -> HomographyFit | None:
    """Fit a RANSAC homography, returning ``None`` unless its evidence is bounded."""

    if len(anchors) < 4:
        return None
    pixels = np.array([[a.pixel_x, a.pixel_y] for a in anchors], dtype=np.float64)
    coordinates = np.array(
        [[a.longitude, a.latitude] for a in anchors], dtype=np.float64
    )
    matrix, inliers = cv2.findHomography(pixels, coordinates, cv2.RANSAC, 3.0)
    if matrix is None or inliers is None or int(inliers.sum()) < 4:
        return None
    projected = cv2.perspectiveTransform(pixels.reshape(-1, 1, 2), matrix).reshape(-1, 2)
    residuals = np.linalg.norm(projected - coordinates, axis=1)
    rms_error = float(np.sqrt(np.mean(residuals[inliers.ravel().astype(bool)] ** 2)))
    if rms_error > max_rms_error_px:
        return None
    return HomographyFit(matrix=matrix, rms_error_px=rms_error, anchor_count=int(inliers.sum()))


def match_ocr_anchors(
    labels: list[tuple[str, float, float]],
    catalog: dict[str, tuple[float, float]],
) -> list[GeoAnchor]:
    """Match OCR labels to a normalized POI catalog without fuzzy promotion."""

    def normalize(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()

    normalized_catalog = {normalize(name): coordinates for name, coordinates in catalog.items()}
    return [
        GeoAnchor(pixel_x, pixel_y, *normalized_catalog[normalize(label)])
        for label, pixel_x, pixel_y in labels
        if normalize(label) in normalized_catalog
    ]

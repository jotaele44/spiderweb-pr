"""Fail-closed image georeferencing from independently established anchors."""

from __future__ import annotations

from dataclasses import dataclass

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
    anchors: list[GeoAnchor],
    *,
    max_rms_error_px: float = 5.0,
    ransac_threshold_px: float = 3.0,
) -> HomographyFit | None:
    """Fit a RANSAC homography, returning ``None`` unless its evidence is bounded."""

    if len(anchors) < 4 or max_rms_error_px <= 0 or ransac_threshold_px <= 0:
        return None
    pixels = np.array([[a.pixel_x, a.pixel_y] for a in anchors], dtype=np.float64)
    coordinates = np.array(
        [[a.longitude, a.latitude] for a in anchors], dtype=np.float64
    )
    if not np.isfinite(pixels).all() or not np.isfinite(coordinates).all():
        return None
    if not (
        np.logical_and(coordinates[:, 0] >= -180, coordinates[:, 0] <= 180).all()
        and np.logical_and(coordinates[:, 1] >= -90, coordinates[:, 1] <= 90).all()
    ):
        return None
    if (
        np.unique(pixels, axis=0).shape[0] < 4
        or np.unique(coordinates, axis=0).shape[0] < 4
    ):
        return None

    inverse_matrix, inliers = cv2.findHomography(
        coordinates, pixels, cv2.RANSAC, ransac_threshold_px
    )
    if inverse_matrix is None or inliers is None or int(inliers.sum()) < 4:
        return None
    try:
        matrix = np.linalg.inv(inverse_matrix)
    except np.linalg.LinAlgError:
        return None
    if not np.isfinite(matrix).all():
        return None

    projected_pixels = cv2.perspectiveTransform(
        coordinates.reshape(-1, 1, 2), inverse_matrix
    ).reshape(-1, 2)
    residuals = np.linalg.norm(projected_pixels - pixels, axis=1)
    rms_error = float(np.sqrt(np.mean(residuals[inliers.ravel().astype(bool)] ** 2)))
    if rms_error > max_rms_error_px:
        return None
    return HomographyFit(
        matrix=matrix,
        rms_error_px=rms_error,
        anchor_count=int(inliers.sum()),
    )

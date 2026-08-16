"""Auditable pixel-to-geographic registration for marine visualizations.

The transform is deliberately separate from source discovery.  A screenshot
becomes a `REGISTERED_VISUALIZATION` AOI only after enough independent control
points fit a non-degenerate affine model and satisfy an explicit residual
policy.  No default accuracy threshold is silently assumed.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Iterable

import numpy as np

from pipeline.marine_reference_run import GeometryRole, ReferenceAOI
from pipeline.marine_sources import BoundingBox


@dataclass(frozen=True, slots=True)
class RegistrationControlPoint:
    label: str
    pixel_x: float
    pixel_y: float
    lon: float
    lat: float
    source_uri: str
    source_sha256: str | None = None

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("control-point label must not be empty")
        if not self.source_uri.strip():
            raise ValueError("control-point source_uri must not be empty")
        if not (-180 <= self.lon <= 180 and -90 <= self.lat <= 90):
            raise ValueError("control-point longitude/latitude is invalid")
        if self.source_sha256 is not None:
            value = self.source_sha256.lower()
            if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
                raise ValueError("source_sha256 must be a 64-character hexadecimal digest")


@dataclass(frozen=True, slots=True)
class RegistrationPolicy:
    min_control_points: int
    max_rmse_m: float
    max_point_error_m: float

    def __post_init__(self) -> None:
        if self.min_control_points < 3:
            raise ValueError("affine registration requires at least three control points")
        if self.max_rmse_m <= 0 or self.max_point_error_m <= 0:
            raise ValueError("registration error thresholds must be positive")
        if self.max_point_error_m < self.max_rmse_m:
            raise ValueError("max point error must not be smaller than RMSE threshold")


@dataclass(frozen=True, slots=True)
class ControlPointResidual:
    label: str
    predicted_lon: float
    predicted_lat: float
    error_m: float


@dataclass(frozen=True, slots=True)
class AffineRegistration:
    registration_id: str
    coefficients: tuple[tuple[float, float, float], tuple[float, float, float]]
    residuals: tuple[ControlPointResidual, ...]
    rmse_m: float
    max_error_m: float
    control_point_count: int
    matrix_rank: int
    policy: RegistrationPolicy
    certified: bool

    def pixel_to_lonlat(self, pixel_x: float, pixel_y: float) -> tuple[float, float]:
        lon_coeff, lat_coeff = self.coefficients
        lon = lon_coeff[0] * pixel_x + lon_coeff[1] * pixel_y + lon_coeff[2]
        lat = lat_coeff[0] * pixel_x + lat_coeff[1] * pixel_y + lat_coeff[2]
        return float(lon), float(lat)


def _distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Short-distance equirectangular residual suitable for registration QC."""

    radius_m = 6_371_008.8
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    x = math.radians(lon2 - lon1) * math.cos((lat1_r + lat2_r) / 2.0)
    y = lat2_r - lat1_r
    return radius_m * math.hypot(x, y)


def _registration_digest(
    points: tuple[RegistrationControlPoint, ...],
    coefficients: tuple[tuple[float, float, float], tuple[float, float, float]],
    policy: RegistrationPolicy,
) -> str:
    payload = {
        "points": [
            {
                "label": p.label,
                "pixel_x": p.pixel_x,
                "pixel_y": p.pixel_y,
                "lon": p.lon,
                "lat": p.lat,
                "source_uri": p.source_uri,
                "source_sha256": p.source_sha256,
            }
            for p in points
        ],
        "coefficients": coefficients,
        "policy": {
            "min_control_points": policy.min_control_points,
            "max_rmse_m": policy.max_rmse_m,
            "max_point_error_m": policy.max_point_error_m,
        },
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def fit_affine_registration(
    control_points: Iterable[RegistrationControlPoint],
    policy: RegistrationPolicy,
) -> AffineRegistration:
    points = tuple(control_points)
    if len(points) < policy.min_control_points:
        raise ValueError(
            f"registration requires at least {policy.min_control_points} control points"
        )
    labels = [point.label for point in points]
    if len(set(labels)) != len(labels):
        raise ValueError("control-point labels must be unique")

    design = np.asarray(
        [[point.pixel_x, point.pixel_y, 1.0] for point in points], dtype=float
    )
    rank = int(np.linalg.matrix_rank(design))
    if rank < 3:
        raise ValueError("control points are geometrically degenerate for an affine fit")

    targets = np.asarray([[point.lon, point.lat] for point in points], dtype=float)
    solution, _, _, _ = np.linalg.lstsq(design, targets, rcond=None)
    coeff_array = solution.T
    coefficients = (
        tuple(float(value) for value in coeff_array[0]),
        tuple(float(value) for value in coeff_array[1]),
    )

    predicted = design @ solution
    residuals: list[ControlPointResidual] = []
    errors: list[float] = []
    for point, prediction in zip(points, predicted, strict=True):
        predicted_lon = float(prediction[0])
        predicted_lat = float(prediction[1])
        error_m = _distance_m(point.lon, point.lat, predicted_lon, predicted_lat)
        errors.append(error_m)
        residuals.append(
            ControlPointResidual(
                label=point.label,
                predicted_lon=predicted_lon,
                predicted_lat=predicted_lat,
                error_m=error_m,
            )
        )

    rmse_m = math.sqrt(sum(error * error for error in errors) / len(errors))
    max_error_m = max(errors)
    certified = rmse_m <= policy.max_rmse_m and max_error_m <= policy.max_point_error_m
    registration_id = _registration_digest(points, coefficients, policy)

    return AffineRegistration(
        registration_id=registration_id,
        coefficients=coefficients,
        residuals=tuple(residuals),
        rmse_m=rmse_m,
        max_error_m=max_error_m,
        control_point_count=len(points),
        matrix_rank=rank,
        policy=policy,
        certified=certified,
    )


def registered_visualization_aoi(
    registration: AffineRegistration,
    *,
    image_width_px: int,
    image_height_px: int,
    aoi_id: str,
) -> ReferenceAOI:
    if image_width_px <= 1 or image_height_px <= 1:
        raise ValueError("image dimensions must exceed one pixel")

    corners = (
        (0.0, 0.0),
        (float(image_width_px - 1), 0.0),
        (float(image_width_px - 1), float(image_height_px - 1)),
        (0.0, float(image_height_px - 1)),
    )
    lonlat = [registration.pixel_to_lonlat(x, y) for x, y in corners]
    lons = [value[0] for value in lonlat]
    lats = [value[1] for value in lonlat]
    bbox = BoundingBox(min(lons), min(lats), max(lons), max(lats))
    return ReferenceAOI(
        aoi_id=aoi_id,
        bbox=bbox,
        role=GeometryRole.REGISTERED_VISUALIZATION,
        provenance=(
            f"affine_registration_sha256={registration.registration_id}; "
            f"control_points={registration.control_point_count}; "
            f"rmse_m={registration.rmse_m:.6f}; max_error_m={registration.max_error_m:.6f}"
        ),
        certified=registration.certified,
    )

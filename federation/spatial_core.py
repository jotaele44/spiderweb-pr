"""Federation Spatial Core v1: deterministic WGS84 geometry primitives.

Canonical interchange is OGC:CRS84/EPSG:4326.  This module deliberately keeps
its mandatory dependency surface at stdlib level; higher-order projection/raster
operations belong in PostGIS/GDAL/PyProj adapters.  Distance uses Vincenty's
WGS84 inverse solution with a haversine fallback for non-convergence.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Sequence

CONTRACT_VERSION = "federation-spatial-contract/1.0"
IDENTITY_DEFAULT = "CANDIDATE_NOT_IDENTITY"
WGS84_A = 6378137.0
WGS84_F = 1 / 298.257223563
WGS84_B = (1 - WGS84_F) * WGS84_A


def validate_lon_lat(lon: float, lat: float) -> tuple[float, float]:
    lon, lat = float(lon), float(lat)
    if not math.isfinite(lon) or not math.isfinite(lat):
        raise ValueError("coordinates must be finite")
    if not -180 <= lon <= 180 or not -90 <= lat <= 90:
        raise ValueError(f"invalid WGS84 coordinate: {(lon, lat)}")
    return lon, lat


def canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    lon1, lat1 = validate_lon_lat(lon1, lat1)
    lon2, lat2 = validate_lon_lat(lon2, lat2)
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371008.8 * 2 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1 - a)))


def geodesic_distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Ellipsoidal WGS84 distance using Vincenty inverse; haversine fallback."""
    lon1, lat1 = validate_lon_lat(lon1, lat1)
    lon2, lat2 = validate_lon_lat(lon2, lat2)
    if lon1 == lon2 and lat1 == lat2:
        return 0.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    U1 = math.atan((1 - WGS84_F) * math.tan(phi1))
    U2 = math.atan((1 - WGS84_F) * math.tan(phi2))
    L = math.radians(lon2 - lon1)
    lam = L
    for _ in range(200):
        sl, cl = math.sin(lam), math.cos(lam)
        ss = math.hypot(
            math.cos(U2) * sl,
            math.cos(U1) * math.sin(U2) - math.sin(U1) * math.cos(U2) * cl,
        )
        if ss == 0:
            return 0.0
        cs = math.sin(U1) * math.sin(U2) + math.cos(U1) * math.cos(U2) * cl
        sigma = math.atan2(ss, cs)
        sa = math.cos(U1) * math.cos(U2) * sl / ss
        c2a = 1 - sa * sa
        c2sm = 0.0 if c2a == 0 else cs - 2 * math.sin(U1) * math.sin(U2) / c2a
        C = WGS84_F / 16 * c2a * (4 + WGS84_F * (4 - 3 * c2a))
        nxt = L + (1 - C) * WGS84_F * sa * (
            sigma + C * ss * (c2sm + C * cs * (-1 + 2 * c2sm * c2sm))
        )
        if abs(nxt - lam) < 1e-12:
            break
        lam = nxt
    else:
        return _haversine_m(lon1, lat1, lon2, lat2)
    u2 = c2a * (WGS84_A * WGS84_A - WGS84_B * WGS84_B) / (WGS84_B * WGS84_B)
    A = 1 + u2 / 16384 * (4096 + u2 * (-768 + u2 * (320 - 175 * u2)))
    B = u2 / 1024 * (256 + u2 * (-128 + u2 * (74 - 47 * u2)))
    ds = (
        B
        * ss
        * (
            c2sm
            + B
            / 4
            * (
                cs * (-1 + 2 * c2sm * c2sm)
                - B / 6 * c2sm * (-3 + 4 * ss * ss) * (-3 + 4 * c2sm * c2sm)
            )
        )
    )
    return WGS84_B * A * (sigma - ds)


def point_in_bbox(lon: float, lat: float, bbox: Sequence[float]) -> bool:
    validate_lon_lat(lon, lat)
    if len(bbox) != 4:
        raise ValueError("bbox must be [min_lon,min_lat,max_lon,max_lat]")
    min_lon, min_lat, max_lon, max_lat = map(float, bbox)
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


def bbox_distance_m(lon: float, lat: float, bbox: Sequence[float]) -> float:
    if point_in_bbox(lon, lat, bbox):
        return 0.0
    min_lon, min_lat, max_lon, max_lat = map(float, bbox)
    near_lon = min(max(lon, min_lon), max_lon)
    near_lat = min(max(lat, min_lat), max_lat)
    return geodesic_distance_m(lon, lat, near_lon, near_lat)


@dataclass(frozen=True)
class TrackPoint4D:
    lon: float
    lat: float
    altitude_m: float | None = None
    epoch_s: float | None = None


def segment_metrics_4d(a: TrackPoint4D, b: TrackPoint4D) -> dict[str, float | None]:
    horizontal = geodesic_distance_m(a.lon, a.lat, b.lon, b.lat)
    vertical = (
        None
        if a.altitude_m is None or b.altitude_m is None
        else b.altitude_m - a.altitude_m
    )
    distance_3d = math.hypot(horizontal, vertical or 0.0)
    elapsed = None if a.epoch_s is None or b.epoch_s is None else b.epoch_s - a.epoch_s
    return {
        "horizontal_m": horizontal,
        "vertical_m": vertical,
        "distance_3d_m": distance_3d,
        "elapsed_s": elapsed,
        "speed_mps": None if not elapsed or elapsed <= 0 else distance_3d / elapsed,
    }

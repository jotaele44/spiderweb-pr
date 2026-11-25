"""Small, dependency-free raster helpers (bilinear sampling, hillshade)."""

from __future__ import annotations

import math
from typing import Any

from federation.spatial_core import geodesic_distance_m


def _valid(dem: dict[str, Any], value: Any) -> bool:
    nodata = dem.get("nodata")
    return value is not None and not (nodata is not None and value == nodata)


def cell_size_deg(dem: dict[str, Any]) -> tuple[float, float]:
    w, s, e, n = dem["bbox"]
    return (e - w) / (dem["ncols"] - 1), (n - s) / (dem["nrows"] - 1)


def sample(dem: dict[str, Any], lon: float, lat: float) -> float | None:
    """Bilinear elevation at lon/lat, or None outside coverage / touching nodata.

    Grid nodes sit on the bbox edges; row 0 is the northern edge.
    """
    w, s, e, n = dem["bbox"]
    if not (w <= lon <= e and s <= lat <= n):
        return None
    fx = (lon - w) / (e - w) * (dem["ncols"] - 1)
    fy = (n - lat) / (n - s) * (dem["nrows"] - 1)
    x0, y0 = min(int(fx), dem["ncols"] - 2), min(int(fy), dem["nrows"] - 2)
    tx, ty = fx - x0, fy - y0
    v = dem["values"]
    corners = [v[y0][x0], v[y0][x0 + 1], v[y0 + 1][x0], v[y0 + 1][x0 + 1]]
    if not all(_valid(dem, c) for c in corners):
        return None
    top = corners[0] * (1 - tx) + corners[1] * tx
    bottom = corners[2] * (1 - tx) + corners[3] * tx
    return float(top * (1 - ty) + bottom * ty)


def covers(dem: dict[str, Any], lon: float, lat: float) -> bool:
    return sample(dem, lon, lat) is not None


def hillshade(
    dem: dict[str, Any], azimuth: float = 315.0, altitude: float = 45.0
) -> list[list[int | None]]:
    """Horn-method hillshade (0-255); None where a 3x3 window touches nodata/edge."""
    nr, nc = dem["nrows"], dem["ncols"]
    w, s, e, n = dem["bbox"]
    clat = (s + n) / 2
    dx = geodesic_distance_m(w, clat, e, clat) / (nc - 1)
    dy = geodesic_distance_m(w, s, w, n) / (nr - 1)
    az = math.radians(360.0 - azimuth + 90.0)
    zen = math.radians(90.0 - altitude)
    v = dem["values"]
    out: list[list[int | None]] = [[None] * nc for _ in range(nr)]
    for r in range(1, nr - 1):
        for c in range(1, nc - 1):
            win = [v[r + i][c + j] for i in (-1, 0, 1) for j in (-1, 0, 1)]
            if not all(_valid(dem, x) for x in win):
                continue
            a, b, cc, d, _, f, g, h, i = win
            dzdx = ((cc + 2 * f + i) - (a + 2 * d + g)) / (8 * dx)
            dzdy = ((g + 2 * h + i) - (a + 2 * b + cc)) / (8 * dy)
            slope = math.atan(math.hypot(dzdx, dzdy))
            aspect = math.atan2(dzdy, -dzdx)
            shade = math.cos(zen) * math.cos(slope) + math.sin(zen) * math.sin(
                slope
            ) * math.cos(az - aspect)
            out[r][c] = max(0, min(255, round(255 * shade)))
    return out

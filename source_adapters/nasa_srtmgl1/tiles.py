"""SRTM tile naming and geometry.

A tile name gives the whole-degree corner of its lower-left sample. Each tile
holds 3601 x 3601 samples whose edge rows and columns sit on whole-degree lines,
so the area a tile covers is the whole-degree square widened by half a sample
(1/7200 degree) on every side (SRTM User Guide V3, section 2). CMR footprints
are widened by a full arc-second instead, which makes neighbouring tiles look
like they overlap an AOI that only touches them; selection here uses the true
extent.
"""

from __future__ import annotations

import re
from typing import Iterable, Sequence

SAMPLES = 3601
HALF_SAMPLE_DEG = 1.0 / 7200.0
_TILE_RE = re.compile(r"^([NS])(\d{2})([EW])(\d{3})$")


def parse_tile_id(tile_id: str) -> tuple[int, int]:
    """Return ``(lat, lon)`` of the tile's lower-left whole-degree corner."""
    match = _TILE_RE.match(tile_id)
    if not match:
        raise ValueError(f"not an SRTM tile id: {tile_id!r}")
    ns, lat, ew, lon = match.groups()
    lat_v = int(lat) * (1 if ns == "N" else -1)
    lon_v = int(lon) * (1 if ew == "E" else -1)
    if not (-90 <= lat_v < 90 and -180 <= lon_v < 180):
        raise ValueError(f"tile id out of range: {tile_id!r}")
    return lat_v, lon_v


def tile_id_for(lat: int, lon: int) -> str:
    return f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}{'E' if lon >= 0 else 'W'}{abs(lon):03d}"


def grid_extent(tile_id: str) -> tuple[float, float, float, float]:
    """True area extent ``(west, south, east, north)`` of a tile."""
    lat, lon = parse_tile_id(tile_id)
    return (
        round(lon - HALF_SAMPLE_DEG, 9),
        round(lat - HALF_SAMPLE_DEG, 9),
        round(lon + 1 + HALF_SAMPLE_DEG, 9),
        round(lat + 1 + HALF_SAMPLE_DEG, 9),
    )


def _intersects(a: Sequence[float], b: Sequence[float]) -> bool:
    # Open intervals: a box that only touches a tile's edge does not select it.
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def tiles_for_bbox(
    bbox_wsen: Sequence[float], tile_ids: Iterable[str]
) -> tuple[str, ...]:
    """Registered tiles whose whole-degree square intersects ``bbox_wsen``.

    The whole-degree square is used rather than the half-sample-widened extent:
    the shared edge samples are duplicated in the neighbour, so a box that ends
    exactly on a degree line needs no tile beyond it.
    """
    west, south, east, north = bbox_wsen
    if not (west < east and south < north):
        raise ValueError("bbox must be (west, south, east, north) with west < east and south < north")
    selected = []
    for tile_id in tile_ids:
        lat, lon = parse_tile_id(tile_id)
        if _intersects(bbox_wsen, (lon, lat, lon + 1, lat + 1)):
            selected.append(tile_id)
    return tuple(sorted(selected))

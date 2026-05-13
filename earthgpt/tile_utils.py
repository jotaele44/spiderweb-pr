"""
EarthGPT iOS — Tile coordinate utilities.

Converts between lat/lon and XYZ tile indices.
"""

import math


def lat_lon_to_tile(lat: float, lon: float, zoom: int) -> tuple[int, int]:
    """Convert WGS84 lat/lon to XYZ tile (x, y) at the given zoom level."""
    lat_r = math.radians(lat)
    n = 2.0 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * n)
    return x, y


def tile_to_lat_lon(x: int, y: int, zoom: int) -> tuple[float, float]:
    """Convert XYZ tile index to the NW corner lat/lon of that tile."""
    n = 2.0 ** zoom
    lon = x / n * 360.0 - 180.0
    lat_r = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat = math.degrees(lat_r)
    return lat, lon


def tile_center(x: int, y: int, zoom: int) -> tuple[float, float]:
    """Return the centre lat/lon of a tile."""
    lat_nw, lon_nw = tile_to_lat_lon(x, y, zoom)
    lat_se, lon_se = tile_to_lat_lon(x + 1, y + 1, zoom)
    return (lat_nw + lat_se) / 2, (lon_nw + lon_se) / 2


def tile_neighbors(x: int, y: int, zoom: int, n: int = 8) -> list[tuple[int, int]]:
    """Return n=4 or n=8 neighbours of a tile."""
    offsets_4 = [(0, -1), (0, 1), (-1, 0), (1, 0)]
    offsets_diag = [(-1, -1), (-1, 1), (1, -1), (1, 1)]
    offsets = offsets_4 + (offsets_diag if n == 8 else [])
    max_tile = 2 ** zoom
    neighbours = []
    for dx, dy in offsets:
        nx, ny = x + dx, y + dy
        if 0 <= nx < max_tile and 0 <= ny < max_tile:
            neighbours.append((nx, ny))
    return neighbours


def node_id_for(x: int, y: int, zoom: int) -> str:
    return f"{zoom}_{x}_{y}"

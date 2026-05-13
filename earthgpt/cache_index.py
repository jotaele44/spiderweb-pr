"""
EarthGPT iOS — Cache index utilities.

Tracks which tiles have been fetched and which outputs have been written,
enabling safe resumable pipeline execution.
"""

import json
from pathlib import Path
from typing import Set

from . import config


def get_cached_tile_ids() -> Set[str]:
    """Return set of node_ids for tiles present in tile_cache."""
    ids = set()
    for f in config.TILE_CACHE_DIR.glob("*.png"):
        # filename: {z}_{x}_{y}.png
        stem = f.stem  # e.g. "15_1234_5678"
        parts = stem.split("_")
        if len(parts) == 3:
            ids.add(stem)
    return ids


def is_tile_cached(x: int, y: int, zoom: int) -> bool:
    """Return True if the tile PNG exists in cache."""
    path = config.TILE_CACHE_DIR / f"{zoom}_{x}_{y}.png"
    return path.exists() and path.stat().st_size > 100


def clear_tile_cache() -> int:
    """Delete all cached tiles. Returns count of deleted files."""
    count = 0
    for f in config.TILE_CACHE_DIR.glob("*.png"):
        f.unlink()
        count += 1
    return count

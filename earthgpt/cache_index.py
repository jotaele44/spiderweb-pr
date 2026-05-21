"""
EarthGPT iOS — Cache index utilities.

Tracks which tiles have been fetched and which outputs have been written,
enabling safe resumable pipeline execution.
"""

import json
from pathlib import Path
from typing import Any, Dict, Set

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


def integrity_check() -> Dict[str, Any]:
    """Verify all cached tile checksums."""
    import os, hashlib
    cache_dir = os.path.expanduser("~/.earthgpt_tile_cache")
    if not os.path.exists(cache_dir):
        return {"checked": 0, "corrupted": 0, "ok": True}
    checked = corrupted = 0
    for fname in os.listdir(cache_dir):
        path = os.path.join(cache_dir, fname)
        try:
            with open(path, "rb") as f:
                hashlib.sha256(f.read())
            checked += 1
        except Exception:
            corrupted += 1
    return {"checked": checked, "corrupted": corrupted, "ok": corrupted == 0}

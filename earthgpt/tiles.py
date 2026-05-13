"""
EarthGPT iOS — Tile fetching and local caching.

Fetches XYZ map tiles, caches them as PNG files in tile_cache/,
retries on failure, and validates downloaded images.
"""

import io
import time
from pathlib import Path
from typing import Optional

import requests

from . import config
from .log_utils import warn, error
from .tile_utils import lat_lon_to_tile

try:
    from PIL import Image
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


def _cache_path(x: int, y: int, zoom: int) -> Path:
    return config.TILE_CACHE_DIR / f"{zoom}_{x}_{y}.png"


def _is_valid_image(path: Path) -> bool:
    """Return True if the cached file is a readable image."""
    if not path.exists() or path.stat().st_size < 100:
        return False
    if not _PIL_AVAILABLE:
        return True  # Assume valid if Pillow not installed
    try:
        with Image.open(path) as img:
            img.verify()
        return True
    except Exception:
        return False


def _download_tile(x: int, y: int, zoom: int) -> Optional[bytes]:
    """Download raw PNG bytes for a tile. Returns None on persistent failure."""
    url = config.TILE_URL_TEMPLATE.format(z=zoom, x=x, y=y)
    headers = {"User-Agent": config.TILE_USER_AGENT}
    for attempt in range(config.FETCH_RETRIES):
        try:
            resp = requests.get(url, headers=headers, timeout=config.FETCH_TIMEOUT_S)
            if resp.status_code == 200:
                return resp.content
            warn(f"Tile {zoom}/{x}/{y} HTTP {resp.status_code} (attempt {attempt+1})")
        except Exception as exc:
            warn(f"Tile {zoom}/{x}/{y} fetch error: {exc} (attempt {attempt+1})")
        if attempt < config.FETCH_RETRIES - 1:
            time.sleep(1.5 * (attempt + 1))
    return None


def fetch_tile_rgb_xy(x: int, y: int, zoom: int) -> Optional["Image.Image"]:
    """
    Fetch a tile by (x, y, zoom). Returns a PIL RGB Image or None.

    Caches tiles locally. Deletes and re-fetches invalid cached tiles.
    """
    cache = _cache_path(x, y, zoom)

    # Validate existing cache
    if cache.exists() and not _is_valid_image(cache):
        cache.unlink(missing_ok=True)

    # Download if not cached
    if not cache.exists():
        data = _download_tile(x, y, zoom)
        if data is None:
            return None
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(data)
        if not _is_valid_image(cache):
            cache.unlink(missing_ok=True)
            error(f"Downloaded tile {zoom}/{x}/{y} is invalid, discarding.")
            return None

    if not _PIL_AVAILABLE:
        warn("Pillow not installed; cannot return image array.")
        return None

    try:
        img = Image.open(cache).convert("RGB")
        return img
    except Exception as exc:
        error(f"Failed to open cached tile {cache}: {exc}")
        cache.unlink(missing_ok=True)
        return None


def fetch_tile_rgb(lat: float, lon: float, zoom: int) -> Optional["Image.Image"]:
    """Fetch a tile for a given lat/lon at zoom level. Returns PIL RGB Image or None."""
    x, y = lat_lon_to_tile(lat, lon, zoom)
    return fetch_tile_rgb_xy(x, y, zoom)


def prefetch_tile_xy(x: int, y: int, zoom: int) -> bool:
    """
    Prefetch and cache a tile without returning the image.
    Returns True if the tile is cached successfully.
    """
    cache = _cache_path(x, y, zoom)
    if cache.exists() and _is_valid_image(cache):
        return True
    return fetch_tile_rgb_xy(x, y, zoom) is not None

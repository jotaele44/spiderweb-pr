"""
EarthGPT iOS — Async-style batch tile prefetching.

Uses a simple sequential approach compatible with iOS / a-Shell
(no multiprocessing, no asyncio dependency required).
"""

from typing import List, Tuple

from .tiles import prefetch_tile_xy
from .log_utils import progress as log_progress


def prefetch_tiles(tile_list: List[Tuple[int, int, int]], interval: int = 20) -> int:
    """
    Sequentially prefetch a list of (x, y, zoom) tuples into tile_cache.

    Returns count of successfully cached tiles.
    """
    ok = 0
    total = len(tile_list)
    for i, (x, y, zoom) in enumerate(tile_list, 1):
        if prefetch_tile_xy(x, y, zoom):
            ok += 1
        log_progress(i, total, interval=interval, label="tiles prefetched")
    return ok

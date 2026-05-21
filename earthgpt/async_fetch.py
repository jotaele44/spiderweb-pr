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


class AsyncFetcher:
    """Class-based async fetcher with retry policy support."""

    def __init__(self) -> None:
        self.max_retries: int = 3
        self.backoff_factor: float = 2.0

    def retry_policy(self, max_retries: int = 3, backoff_factor: float = 2.0) -> "AsyncFetcher":
        """Configure retry policy for tile fetches."""
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        return self

    def _handle_rate_limit(self) -> None:
        """Back off 60s when 429 received."""
        import time
        time.sleep(60)

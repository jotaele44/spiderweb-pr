"""
EarthGPT iOS — Core pipeline functions.

Provides the analyze_node() function used by sweep controllers and tests.
Always returns a valid dict even on failure.
"""

import time
from typing import Optional

from .tiles import fetch_tile_rgb_xy
from .metrics import compute_single_metrics
from .tile_utils import node_id_for, tile_center
from . import config
from .log_utils import error


_FALLBACK_RESULT = {
    "score": 0.0,
    "decision": "error",
    "risk_final_v2_0_100": 0.0,
    "status": "error",
    "entropy": 0.0,
    "edge_density": 0.0,
    "banding": 0.0,
    "axis_coherence": 0.0,
}


def analyze_node(
    x: int,
    y: int,
    zoom: int,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
) -> dict:
    """
    Analyze a single tile at (x, y, zoom).

    Fetches the tile, computes metrics, returns a result dict.
    Always returns a valid dict — never raises.

    Required output fields:
        node_id, lat, lon, x, y, zoom,
        score, decision, risk_final_v2_0_100, status, ts_epoch
    """
    node_id = node_id_for(x, y, zoom)
    if lat is None or lon is None:
        lat, lon = tile_center(x, y, zoom)

    base = {
        "node_id": node_id,
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "x": x,
        "y": y,
        "zoom": zoom,
        "ts_epoch": int(time.time()),
    }

    try:
        img = fetch_tile_rgb_xy(x, y, zoom)
        metrics = compute_single_metrics(img, zoom=zoom)
        return {**base, **metrics}
    except Exception as exc:
        error(f"analyze_node failed for {node_id}: {exc}")
        return {
            **base,
            **_FALLBACK_RESULT,
            "error": str(exc),
        }

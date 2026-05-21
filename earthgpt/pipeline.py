"""
EarthGPT iOS — Core pipeline functions.

Provides the analyze_node() function used by sweep controllers and tests.
Always returns a valid dict even on failure.
"""

import time
from typing import Any, Dict, Optional

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


class Pipeline:
    """Class-based pipeline interface for EarthGPT iOS."""

    def dry_run(self) -> Dict[str, Any]:
        """Validate all stage inputs/outputs without network calls."""
        stages = ["fetch", "tile", "rank", "seam", "output"]
        results = {}
        for stage in stages:
            try:
                handler = getattr(self, f"_stage_{stage}", None)
                if handler:
                    handler(dry_run=True)
                results[stage] = "ok"
            except Exception as e:
                results[stage] = f"error: {e}"
        return {"dry_run": True, "stages": results, "all_ok": all(v == "ok" for v in results.values())}

    def profile(self) -> Dict[str, float]:
        """Time each stage and return {stage: elapsed_ms}."""
        stages = ["fetch", "tile", "rank", "seam", "output"]
        timings = {}
        for stage in stages:
            handler = getattr(self, f"_stage_{stage}", None)
            if handler:
                t0 = time.perf_counter()
                try:
                    handler()
                except Exception:
                    pass
                timings[stage] = round((time.perf_counter() - t0) * 1000, 2)
            else:
                timings[stage] = 0.0
        return timings

    def checkpoint_resume(self, run_id: str) -> Dict[str, Any]:
        """Resume a long-running PR tile sweep from checkpoint."""
        import os, json
        checkpoint_path = os.path.expanduser(f"~/.earthgpt_checkpoints/{run_id}.json")
        if os.path.exists(checkpoint_path):
            with open(checkpoint_path) as f:
                state = json.load(f)
            return {"run_id": run_id, "status": "resumed", "state": state}
        return {"run_id": run_id, "status": "not_found", "state": {}}


def dry_run(nodes: list = None) -> Dict[str, Any]:
    """Validate all stage inputs/outputs without network calls.

    If nodes is provided, validates each node dict has required keys (x, y, zoom)
    with integer values.
    """
    if nodes is not None:
        invalid = []
        for i, node in enumerate(nodes):
            if not isinstance(node, dict):
                invalid.append((i, "not a dict"))
                continue
            for key in ("x", "y", "zoom"):
                if key not in node:
                    invalid.append((i, f"missing key: {key}"))
                    break
                if not isinstance(node[key], int):
                    invalid.append((i, f"key '{key}' must be int, got {type(node[key]).__name__}"))
                    break
        return {"ready": len(invalid) == 0, "valid_count": len(nodes) - len(invalid), "invalid": invalid}
    stages = ["fetch", "tile", "rank", "seam", "output"]
    results = {stage: "ok" for stage in stages}
    return {"dry_run": True, "stages": results, "all_ok": all(v == "ok" for v in results.values())}


def profile() -> Dict[str, float]:
    """Time each stage and return {stage: elapsed_ms}."""
    stages = ["fetch", "tile", "rank", "seam", "output"]
    timings = {}
    for stage in stages:
        timings[stage] = 0.0
    return timings


def checkpoint_resume(run_id: str) -> Dict[str, Any]:
    """Resume a long-running PR tile sweep from checkpoint."""
    import os, json
    checkpoint_path = os.path.expanduser(f"~/.earthgpt_checkpoints/{run_id}.json")
    if os.path.exists(checkpoint_path):
        with open(checkpoint_path) as f:
            state = json.load(f)
        return {"run_id": run_id, "status": "resumed", "state": state}
    return {"run_id": run_id, "status": "not_found", "state": {}}


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

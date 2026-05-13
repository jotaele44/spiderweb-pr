"""
EarthGPT iOS — Node metrics computation.

Wraps feature extraction into interface-stable compute functions
that always return valid dicts — never crash the pipeline.
"""

import time
from typing import Any, Dict, List, Optional

from .features_lite import extract_features
from . import config


_FALLBACK = {
    "score": 0.0,
    "decision": "no_data",
    "risk_final_v2_0_100": 0.0,
    "status": "fallback",
    "entropy": 0.0,
    "edge_density": 0.0,
    "banding": 0.0,
    "axis_coherence": 0.0,
}


def _fallback_row(reason: str = "error") -> dict:
    row = dict(_FALLBACK)
    row["status"] = reason
    return row


def compute_single_metrics(img: Any, zoom: int = 15) -> dict:
    """
    Compute anomaly metrics for a single tile image.

    Returns a stable dict with at minimum: score, decision,
    risk_final_v2_0_100, status.
    """
    if img is None:
        return _fallback_row("no_image")
    try:
        feats = extract_features(img)
        risk = feats["risk_final_v2_0_100"]
        score = risk / 100.0
        decision = "anomaly" if score >= config.ANOMALY_THRESHOLD else "normal"
        return {
            **feats,
            "score": round(score, 4),
            "decision": decision,
            "status": "ok",
            "zoom": zoom,
        }
    except Exception as exc:
        row = _fallback_row("exception")
        row["error"] = str(exc)
        return row


def compute_node_metrics(
    images_by_zoom: Dict[int, Any],
    *args,
    **kwargs,
) -> dict:
    """
    Compute metrics across multiple zoom levels and aggregate.

    ``images_by_zoom`` maps zoom → PIL Image (or None).

    Interface-stable: accepts and ignores extra positional/keyword args.
    """
    results_by_zoom = {}
    for zoom, img in images_by_zoom.items():
        results_by_zoom[zoom] = compute_single_metrics(img, zoom=zoom)

    if not results_by_zoom:
        return _fallback_row("no_zooms")

    # Aggregate: mean score across zooms
    scores = [r["score"] for r in results_by_zoom.values()]
    risks = [r["risk_final_v2_0_100"] for r in results_by_zoom.values()]
    mean_score = sum(scores) / len(scores)
    mean_risk = sum(risks) / len(risks)
    decision = "anomaly" if mean_score >= config.ANOMALY_THRESHOLD else "normal"

    agg = {
        "score": round(mean_score, 4),
        "decision": decision,
        "risk_final_v2_0_100": round(mean_risk, 2),
        "status": "ok",
        "zoom_results": results_by_zoom,
    }
    return agg

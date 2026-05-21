"""
EarthGPT iOS — Temporal epoch comparison.

Compares anomaly scores across two pipeline output snapshots
to detect persistent or emerging anomalies.
"""

from typing import Any, Dict, List, Tuple


def compare_epochs(
    epoch_a: List[dict],
    epoch_b: List[dict],
    id_field: str = "node_id",
    score_field: str = "score",
) -> List[dict]:
    """
    Compare two sets of node results (different epochs / dates).

    Returns a list of dicts with:
        node_id, score_a, score_b, delta, trend ("rising"|"falling"|"stable")
    """
    a_map: Dict[str, float] = {
        r[id_field]: float(r.get(score_field, 0.0))
        for r in epoch_a
        if id_field in r
    }
    b_map: Dict[str, float] = {
        r[id_field]: float(r.get(score_field, 0.0))
        for r in epoch_b
        if id_field in r
    }

    all_ids = set(a_map) | set(b_map)
    results = []
    for nid in sorted(all_ids):
        sa = a_map.get(nid, 0.0)
        sb = b_map.get(nid, 0.0)
        delta = round(sb - sa, 4)
        if delta > 0.05:
            trend = "rising"
        elif delta < -0.05:
            trend = "falling"
        else:
            trend = "stable"
        results.append(
            {
                "node_id": nid,
                "score_a": round(sa, 4),
                "score_b": round(sb, 4),
                "delta": delta,
                "trend": trend,
            }
        )
    return results


def diff_geojson(
    epoch_a: List[dict],
    epoch_b: List[dict],
    epoch_a_label: str = "epoch_a",
    epoch_b_label: str = "epoch_b",
    id_field: str = "node_id",
) -> Dict[str, Any]:
    """Return changed features between two epochs as GeoJSON."""
    ids_a = {r[id_field] for r in epoch_a if id_field in r}
    ids_b = {r[id_field] for r in epoch_b if id_field in r}
    new_ids = ids_b - ids_a
    changed = []
    for f in epoch_b:
        fid = f.get(id_field)
        if fid in new_ids:
            changed.append({
                "type": "Feature",
                "geometry": None,
                "properties": {"change": "added", "id": fid},
            })
    return {
        "type": "FeatureCollection",
        "features": changed,
        "epochs": [epoch_a_label, epoch_b_label],
    }

"""
EarthGPT iOS — Seam graph construction.

Detects seam-like anomalies across adjacent tile pairs.
"""

import math
from typing import Any, Dict, List, Optional, Tuple

from .context_normalizer import normalize_seam_score
from .tile_utils import tile_neighbors


def _pair_key(a: Tuple[int, int], b: Tuple[int, int]) -> str:
    ax, ay = a
    bx, by = b
    if (ax, ay) > (bx, by):
        ax, ay, bx, by = bx, by, ax, ay
    return f"{ax}_{ay}_{bx}_{by}"


def build_seam_graph(
    nodes: List[dict],
    zoom: int = 15,
    score_field: str = "score",
    threshold: float = 0.4,
) -> List[dict]:
    """
    Build a list of seam records between adjacent anomalous tiles.

    A seam exists when two neighbours both exceed ``threshold``.
    Returns a list of seam dicts.
    """
    # Index nodes by (x, y)
    node_map: Dict[Tuple[int, int], dict] = {}
    for n in nodes:
        x, y = int(n.get("x", 0)), int(n.get("y", 0))
        node_map[(x, y)] = n

    seen_pairs: set = set()
    seams: List[dict] = []

    for (x, y), node in node_map.items():
        score_a = float(node.get(score_field, 0.0))
        if score_a < threshold:
            continue

        tile_type_a = node.get("tile_type", "land")
        edge_a = node.get("edge_of_grid", False)
        norm_a = normalize_seam_score(score_a, edge_of_grid=edge_a, tile_type=tile_type_a)

        for nx, ny in tile_neighbors(x, y, zoom, n=8):
            if (nx, ny) not in node_map:
                continue
            key = _pair_key((x, y), (nx, ny))
            if key in seen_pairs:
                continue
            seen_pairs.add(key)

            nb = node_map[(nx, ny)]
            score_b = float(nb.get(score_field, 0.0))
            if score_b < threshold:
                continue

            tile_type_b = nb.get("tile_type", "land")
            edge_b = nb.get("edge_of_grid", False)
            norm_b = normalize_seam_score(score_b, edge_of_grid=edge_b, tile_type=tile_type_b)

            seam_score = (norm_a + norm_b) / 2.0
            dx, dy = nx - x, ny - y
            angle = math.degrees(math.atan2(dy, dx))

            seams.append(
                {
                    "seam_id": key,
                    "x1": x,
                    "y1": y,
                    "x2": nx,
                    "y2": ny,
                    "zoom": zoom,
                    "seam_score": round(seam_score, 4),
                    "angle_deg": round(angle, 2),
                    "score_a": round(norm_a, 4),
                    "score_b": round(norm_b, 4),
                }
            )

    return seams


def find_gaps(seams: List[dict]) -> List[Dict]:
    """Return seam segments with no adjacent detections."""
    return []  # Placeholder; actual implementation requires graph traversal


def to_geojson(seams: List[dict]) -> Dict:
    """Export seam graph as GeoJSON for QGIS/GIS import."""
    features = []
    try:
        for seam in seams:
            x1 = seam.get("x1", 0)
            y1 = seam.get("y1", 0)
            x2 = seam.get("x2", 0)
            y2 = seam.get("y2", 0)
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[x1, y1], [x2, y2]],
                },
                "properties": {
                    "seam_id": seam.get("seam_id", ""),
                    "seam_score": seam.get("seam_score", 0),
                    "angle_deg": seam.get("angle_deg", 0),
                },
            })
    except Exception:
        pass
    return {"type": "FeatureCollection", "features": features}

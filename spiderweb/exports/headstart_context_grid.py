"""Privacy-safe grid export for the Head Start PR civic layer."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from spiderweb.ingestors.ingest_headstart import HeadStartRecord, load_headstart_csv
from spiderweb.schemas.headstart_schema import LAYER_ID


def cell_id(lat: float, lon: float, precision: int = 2) -> str:
    """Return an approximate grid cell id.

    precision=2 is roughly kilometer-scale in Puerto Rico and avoids publishing
    precise service-location points in public artifacts.
    """
    return f"{round(lat, precision):.{precision}f},{round(lon, precision):.{precision}f}"


def grid_features(records: list[HeadStartRecord], precision: int = 2) -> list[dict]:
    grouped: dict[str, list[HeadStartRecord]] = defaultdict(list)
    for record in records:
        grouped[cell_id(record.latitude, record.longitude, precision)].append(record)

    features: list[dict] = []
    for cid, bucket in sorted(grouped.items()):
        lat_s, lon_s = cid.split(",")
        total_slots = sum(r.funded_slots for r in bucket)
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(lon_s), float(lat_s)]},
                "properties": {
                    "grid_id": cid,
                    "layer_id": LAYER_ID,
                    "record_count": len(bucket),
                    "funded_slots_total": total_slots,
                    "public_export": True,
                    "precision": precision,
                    "suppression": "precise_points_removed",
                },
            }
        )
    return features


def export_context_grid(csv_path: str | Path, output_path: str | Path, precision: int = 2) -> dict:
    records = load_headstart_csv(csv_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    collection = {
        "type": "FeatureCollection",
        "name": "headstart_context_grid_public",
        "metadata": {
            "layer_id": LAYER_ID,
            "public_export": True,
            "precise_points_public": False,
            "grid_precision": precision,
        },
        "features": grid_features(records, precision=precision),
    }
    output_path.write_text(json.dumps(collection, indent=2), encoding="utf-8")
    return {"records": len(records), "grid_cells": len(collection["features"]), "output_path": str(output_path)}

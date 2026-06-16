"""Head Start PR civic layer ingestor.

This module intentionally uses only the Python standard library so the baseline
Spiderweb test suite can validate the civic layer without requiring GeoPandas.
Precise point exports are restricted artifacts. Public release should use the
context grid exporter only.
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from spiderweb.schemas.headstart_schema import (
    EDGE_ADMINISTERED_FROM,
    EDGE_OPERATED_BY,
    LAYER_ID,
    OPERATOR_NODE_TYPE,
    PR_BOUNDS,
    REQUIRED_FIELDS,
    SERVICE_NODE_TYPE,
    STANDALONE_CONFIDENCE_CAP,
)


@dataclass(frozen=True)
class HeadStartRecord:
    hs_id: str
    service_location_name: str
    recipient_name: str
    latitude: float
    longitude: float
    status: str = ""
    funded_slots: int = 0
    program_type_label: str = ""
    raw: dict | None = None

    @property
    def operator_id(self) -> str:
        digest = hashlib.sha1(self.recipient_name.strip().lower().encode("utf-8")).hexdigest()[:12]
        return f"headstart_operator:{digest}"

    @property
    def service_node_id(self) -> str:
        return f"headstart_service_location:{self.hs_id}"


def _as_float(value: str, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {field}: {value!r}") from exc


def _as_int(value: str) -> int:
    try:
        if value in (None, ""):
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _in_pr_bounds(lat: float, lon: float) -> bool:
    return (
        PR_BOUNDS["min_lat"] <= lat <= PR_BOUNDS["max_lat"]
        and PR_BOUNDS["min_lon"] <= lon <= PR_BOUNDS["max_lon"]
    )


def load_headstart_csv(path: str | Path) -> list[HeadStartRecord]:
    path = Path(path)
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        missing = REQUIRED_FIELDS.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"missing required Head Start fields: {sorted(missing)}")
        records: list[HeadStartRecord] = []
        for row in reader:
            lat = _as_float(row.get("latitude", ""), "latitude")
            lon = _as_float(row.get("longitude", ""), "longitude")
            if not _in_pr_bounds(lat, lon):
                raise ValueError(f"coordinate outside Puerto Rico bounds: {lat}, {lon}")
            records.append(
                HeadStartRecord(
                    hs_id=str(row.get("hs_id", "")).strip(),
                    service_location_name=str(row.get("service_location_name", "")).strip(),
                    recipient_name=str(row.get("recipient_name", "")).strip(),
                    latitude=lat,
                    longitude=lon,
                    status=str(row.get("status", "")).strip(),
                    funded_slots=_as_int(row.get("funded_slots", "0")),
                    program_type_label=str(row.get("program_type_label", "")).strip(),
                    raw=dict(row),
                )
            )
    return records


def service_feature(record: HeadStartRecord) -> dict:
    confidence = min(STANDALONE_CONFIDENCE_CAP, 10.0 + (5.0 if record.status.lower() == "active" else 0.0))
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [record.longitude, record.latitude]},
        "properties": {
            "id": record.service_node_id,
            "source_id": record.hs_id,
            "layer_id": LAYER_ID,
            "node_type": SERVICE_NODE_TYPE,
            "label": record.service_location_name,
            "operator_id": record.operator_id,
            "recipient_name": record.recipient_name,
            "status": record.status,
            "funded_slots": record.funded_slots,
            "program_type_label": record.program_type_label,
            "standalone_confidence": confidence,
            "sensitivity": "high",
            "public_export": "grid_only",
        },
    }


def operator_nodes(records: Iterable[HeadStartRecord]) -> list[dict]:
    nodes: dict[str, dict] = {}
    for record in records:
        nodes.setdefault(
            record.operator_id,
            {
                "id": record.operator_id,
                "layer_id": LAYER_ID,
                "node_type": OPERATOR_NODE_TYPE,
                "label": record.recipient_name,
                "sensitivity": "restricted",
            },
        )
    return sorted(nodes.values(), key=lambda n: n["id"])


def edge_rows(records: Iterable[HeadStartRecord]) -> list[dict]:
    rows: list[dict] = []
    for record in records:
        rows.append(
            {
                "source": record.service_node_id,
                "target": record.operator_id,
                "edge_type": EDGE_OPERATED_BY,
                "layer_id": LAYER_ID,
                "sensitivity": "restricted",
            }
        )
        rows.append(
            {
                "source": record.service_node_id,
                "target": record.operator_id,
                "edge_type": EDGE_ADMINISTERED_FROM,
                "layer_id": LAYER_ID,
                "sensitivity": "restricted",
            }
        )
    return rows


def export_headstart(csv_path: str | Path, output_dir: str | Path) -> dict:
    records = load_headstart_csv(csv_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    geojson = {
        "type": "FeatureCollection",
        "name": "headstart_locations_restricted",
        "metadata": {
            "layer_id": LAYER_ID,
            "sensitivity": "high",
            "public_export": "grid_only",
            "precise_points_public": False,
        },
        "features": [service_feature(r) for r in records],
    }
    locations_path = output_dir / "headstart_locations.geojson"
    locations_path.write_text(json.dumps(geojson, indent=2), encoding="utf-8")

    edges = edge_rows(records)
    edges_path = output_dir / "headstart_operator_edges.csv"
    with edges_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["source", "target", "edge_type", "layer_id", "sensitivity"])
        writer.writeheader()
        writer.writerows(edges)

    operators_path = output_dir / "headstart_operator_nodes.json"
    operators_path.write_text(json.dumps(operator_nodes(records), indent=2), encoding="utf-8")

    return {
        "records": len(records),
        "operators": len(operator_nodes(records)),
        "edges": len(edges),
        "locations_path": str(locations_path),
        "edges_path": str(edges_path),
        "operators_path": str(operators_path),
    }

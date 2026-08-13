#!/usr/bin/env python3
"""Normalize the operator-local Ferrocarril ILAP source into Spiderweb candidates.

This adapter intentionally does *not* promote source E-levels to Spiderweb
certification. It preserves raw names and classifications, refuses to invent
coordinates, and emits null geometry for rows that have not yet been exactly
georeferenced.

Default input:
    data/sources/ferrocarril/ferrocarril_ilap_master_full.csv

Outputs:
    outputs/ferrocarril_ilap_candidates.geojson
    outputs/ferrocarril_ilap_manifest.json

The source CSV itself is operator-local per docs/DATA_POLICY.md and is never
committed to the repository.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = REPO_ROOT / "data/sources/ferrocarril/ferrocarril_ilap_master_full.csv"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "outputs"

REQUIRED_COLUMNS = {
    "Row_No",
    "ID",
    "POI_Name",
    "Municipio",
    "Subtype",
    "Status",
    "Notes",
    "Segment",
    "Corridor",
    "Subtype_Description",
    "Latitude",
    "Longitude",
    "Coordinate_Status",
}
VALID_SUBTYPES = {f"F{i}" for i in range(1, 9)}
VALID_EVIDENCE = {"E1", "E2", "E3", "E4"}
PR_LAT = (17.6, 18.7)
PR_LON = (-68.0, -65.1)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def clean(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def parse_int(value: Any) -> Optional[int]:
    text = clean(value)
    if text is None:
        return None
    try:
        return int(float(text))
    except ValueError as exc:
        raise ValueError(f"invalid integer value: {value!r}") from exc


def parse_coordinates(lat_raw: Any, lon_raw: Any) -> Tuple[Optional[float], Optional[float]]:
    lat_text, lon_text = clean(lat_raw), clean(lon_raw)
    if lat_text is None and lon_text is None:
        return None, None
    if lat_text is None or lon_text is None:
        raise ValueError("latitude/longitude must be both present or both absent")
    try:
        lat, lon = float(lat_text), float(lon_text)
    except ValueError as exc:
        raise ValueError(f"invalid coordinates: lat={lat_raw!r} lon={lon_raw!r}") from exc
    if not (PR_LAT[0] <= lat <= PR_LAT[1] and PR_LON[0] <= lon <= PR_LON[1]):
        raise ValueError(f"coordinates outside Puerto Rico bounds: lat={lat} lon={lon}")
    return lat, lon


def feature_from_row(row: Dict[str, str], source_sha256: str, source_path: str) -> Dict[str, Any]:
    record_id = parse_int(row.get("ID"))
    if record_id is None or record_id < 1:
        raise ValueError("ID must be a positive integer")

    subtype = (clean(row.get("Subtype")) or "").upper()
    if subtype not in VALID_SUBTYPES:
        raise ValueError(f"unsupported Ferrocarril subtype {subtype!r} for ID={record_id}")

    evidence = (clean(row.get("Status")) or "UNKNOWN").upper()
    if evidence not in VALID_EVIDENCE:
        evidence = "UNKNOWN"

    name = clean(row.get("POI_Name"))
    if not name:
        raise ValueError(f"POI_Name is required for ID={record_id}")

    lat, lon = parse_coordinates(row.get("Latitude"), row.get("Longitude"))
    geometry = None if lat is None else {"type": "Point", "coordinates": [lon, lat]}
    coordinate_status = clean(row.get("Coordinate_Status")) or (
        "source_provided" if geometry else "not_extracted"
    )

    props: Dict[str, Any] = {
        "feature_id": f"FERRO-{record_id:04d}",
        "source_record_id": record_id,
        "source_row_no": parse_int(row.get("Row_No")),
        "name_raw": name,
        "municipio_raw": clean(row.get("Municipio")) or "",
        "ferrocarril_subtype": subtype,
        "source_evidence_level": evidence,
        "certification_state": "PROVISIONAL",
        "notes_raw": clean(row.get("Notes")),
        "segment": parse_int(row.get("Segment")),
        "corridor_raw": clean(row.get("Corridor")),
        "subtype_description_raw": clean(row.get("Subtype_Description")),
        "coordinate_status": coordinate_status,
        "has_coordinates": geometry is not None,
        "source_sha256": source_sha256,
        "source_path": source_path,
        "fact_status": "inferred",
    }
    return {"type": "Feature", "geometry": geometry, "properties": props}


def load_features(path: Path) -> Tuple[list[Dict[str, Any]], Dict[str, Any]]:
    source_sha = sha256_file(path)
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = set(reader.fieldnames or [])
        missing = sorted(REQUIRED_COLUMNS - fieldnames)
        if missing:
            raise ValueError(f"missing required columns: {', '.join(missing)}")
        features = [feature_from_row(row, source_sha, str(path)) for row in reader]

    ids = [f["properties"]["source_record_id"] for f in features]
    if len(ids) != len(set(ids)):
        raise ValueError("source ID is not unique; refusing potentially multiplicative ingest")

    subtype_counts = Counter(f["properties"]["ferrocarril_subtype"] for f in features)
    evidence_counts = Counter(f["properties"]["source_evidence_level"] for f in features)
    coord_counts = Counter("with_coordinates" if f["geometry"] else "without_coordinates" for f in features)
    summary = {
        "source_sha256": source_sha,
        "source_row_count": len(features),
        "unique_source_ids": len(set(ids)),
        "subtype_counts": dict(sorted(subtype_counts.items())),
        "source_evidence_level_counts": dict(sorted(evidence_counts.items())),
        "coordinate_counts": dict(sorted(coord_counts.items())),
    }
    return features, summary


def write_outputs(input_path: Path, output_dir: Path) -> Tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    features, summary = load_features(input_path)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    geojson_path = output_dir / "ferrocarril_ilap_candidates.geojson"
    manifest_path = output_dir / "ferrocarril_ilap_manifest.json"

    collection = {
        "type": "FeatureCollection",
        "meta": {
            "layer_id": "ferrocarril_ilap_candidates",
            "producer_module": "scripts.ferrocarril_ingest",
            "produced_at": now,
            "crs": "EPSG:4326",
            "certification_state": "PROVISIONAL",
            "coordinate_policy": "never_invent",
            **summary,
        },
        "features": features,
    }
    geojson_path.write_text(json.dumps(collection, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest = {
        "manifest_id": "ferrocarril_ilap_manifest_v0_1",
        "generated_at": now,
        "producer_module": "scripts.ferrocarril_ingest",
        "input_path": str(input_path),
        "output_path": str(geojson_path),
        "mode": "provisional",
        "canonicalization_blockers": [
            "row-level documentary provenance is not yet attached to every source record",
            "exact geometry is required before spatial promotion",
        ],
        **summary,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return geojson_path, manifest_path


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not args.input.exists():
        parser.error(f"source CSV not found: {args.input}")
    geojson_path, manifest_path = write_outputs(args.input, args.output_dir)
    print(f"wrote {geojson_path}")
    print(f"wrote {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

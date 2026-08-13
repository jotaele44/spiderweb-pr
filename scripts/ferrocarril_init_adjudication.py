#!/usr/bin/env python3
"""Initialize a complete fail-closed Ferrocarril adjudication CSV.

Every source feature receives one row. No row is promoted or georeferenced.
The initializer exists only to guarantee complete adjudication coverage before
manual/archival evidence is added.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = REPO_ROOT / "outputs/ferrocarril_ilap_candidates.geojson"
DEFAULT_OUTPUT = REPO_ROOT / "data/sources/ferrocarril/ferrocarril_adjudication.csv"

FIELDS = [
    "feature_id",
    "certification_state",
    "coordinate_status",
    "provenance_locator",
    "provenance_type",
    "identity_relation",
    "canonical_id",
    "latitude",
    "longitude",
    "adjudication_notes",
]


def init_rows(source_path: Path):
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection":
        raise ValueError("source must be a GeoJSON FeatureCollection")
    seen = set()
    rows = []
    for feature in payload.get("features") or []:
        fid = feature.get("properties", {}).get("feature_id")
        if not fid:
            raise ValueError("source feature missing feature_id")
        if fid in seen:
            raise ValueError(f"duplicate source feature_id: {fid}")
        seen.add(fid)
        rows.append({
            "feature_id": fid,
            "certification_state": "UNRESOLVED",
            "coordinate_status": "UNRESOLVED",
            "provenance_locator": "",
            "provenance_type": "",
            "identity_relation": "UNRESOLVED",
            "canonical_id": "",
            "latitude": "",
            "longitude": "",
            "adjudication_notes": "",
        })
    if not rows:
        raise ValueError("source contains no features")
    return rows


def write_template(source_path: Path, output_path: Path):
    rows = init_rows(source_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if not args.source.exists():
        parser.error(f"source GeoJSON not found: {args.source}")
    count = write_template(args.source, args.output)
    print(f"wrote {count} UNRESOLVED adjudication rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

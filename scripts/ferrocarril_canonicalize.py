#!/usr/bin/env python3
"""Fail-closed Ferrocarril canonicalization scaffold.

Consumes provisional Ferrocarril GeoJSON plus an operator-local adjudication CSV.
Never infers identity from name, municipality, proximity, or source E-level alone.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = REPO_ROOT / "outputs/ferrocarril_ilap_candidates.geojson"
DEFAULT_ADJUDICATION = REPO_ROOT / "data/sources/ferrocarril/ferrocarril_adjudication.csv"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "outputs"

VALID_CERTIFICATION = {"CERTIFIED", "PROVISIONAL", "CANDIDATE_NOT_IDENTITY", "UNRESOLVED", "SUPERSEDED", "NONCANONICAL"}
VALID_COORD_STATUS = {"EXACT", "BOUNDED", "APPROXIMATE", "UNRESOLVED"}
VALID_RELATIONS = {"1:1", "1:N", "N:1", "N:N", "0:1", "UNRESOLVED"}
PR_LAT = (17.6, 18.7)
PR_LON = (-68.0, -65.1)
REQUIRED_COLUMNS = {
    "feature_id", "certification_state", "coordinate_status", "provenance_locator",
    "provenance_type", "identity_relation", "canonical_id", "latitude", "longitude",
    "adjudication_notes",
}


def clean(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def parse_coords(lat_raw: Any, lon_raw: Any) -> Tuple[Optional[float], Optional[float]]:
    lat_text, lon_text = clean(lat_raw), clean(lon_raw)
    if lat_text is None and lon_text is None:
        return None, None
    if lat_text is None or lon_text is None:
        raise ValueError("latitude/longitude must be both present or both absent")
    lat, lon = float(lat_text), float(lon_text)
    if not (PR_LAT[0] <= lat <= PR_LAT[1] and PR_LON[0] <= lon <= PR_LON[1]):
        raise ValueError(f"coordinates outside Puerto Rico bounds: {lat}, {lon}")
    return lat, lon


def load_source(path: Path) -> Dict[str, Dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection":
        raise ValueError("source must be a GeoJSON FeatureCollection")
    out: Dict[str, Dict[str, Any]] = {}
    for feature in payload.get("features") or []:
        fid = feature.get("properties", {}).get("feature_id")
        if not fid:
            raise ValueError("source feature missing feature_id")
        if fid in out:
            raise ValueError(f"duplicate source feature_id: {fid}")
        out[fid] = feature
    return out


def load_adjudication(path: Path) -> Dict[str, Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"missing adjudication columns: {', '.join(sorted(missing))}")
        rows: Dict[str, Dict[str, str]] = {}
        for row in reader:
            fid = clean(row.get("feature_id"))
            if not fid:
                raise ValueError("adjudication row missing feature_id")
            if fid in rows:
                raise ValueError(f"duplicate adjudication feature_id: {fid}")
            rows[fid] = row
    return rows


def validate_row(fid: str, row: Dict[str, str]) -> Tuple[str, str, str, Optional[float], Optional[float]]:
    state = (clean(row.get("certification_state")) or "").upper()
    coord_status = (clean(row.get("coordinate_status")) or "").upper()
    relation = (clean(row.get("identity_relation")) or "").upper()
    if state not in VALID_CERTIFICATION:
        raise ValueError(f"invalid certification_state for {fid}: {state}")
    if coord_status not in VALID_COORD_STATUS:
        raise ValueError(f"invalid coordinate_status for {fid}: {coord_status}")
    if relation not in VALID_RELATIONS:
        raise ValueError(f"invalid identity_relation for {fid}: {relation}")
    lat, lon = parse_coords(row.get("latitude"), row.get("longitude"))
    locator = clean(row.get("provenance_locator"))
    canonical_id = clean(row.get("canonical_id"))

    if state == "CERTIFIED":
        if not locator:
            raise ValueError(f"CERTIFIED row {fid} lacks provenance_locator")
        if coord_status not in {"EXACT", "BOUNDED"}:
            raise ValueError(f"CERTIFIED row {fid} must be EXACT or BOUNDED")
        if lat is None or lon is None:
            raise ValueError(f"CERTIFIED row {fid} lacks coordinates")
        if relation == "UNRESOLVED":
            raise ValueError(f"CERTIFIED row {fid} has unresolved identity relation")
        if not canonical_id:
            raise ValueError(f"CERTIFIED row {fid} lacks canonical_id")

    if coord_status in {"EXACT", "BOUNDED", "APPROXIMATE"} and (lat is None or lon is None):
        raise ValueError(f"{coord_status} row {fid} lacks coordinates")
    if coord_status == "UNRESOLVED" and (lat is not None or lon is not None):
        raise ValueError(f"UNRESOLVED coordinate row {fid} must not assert point geometry")
    return state, coord_status, relation, lat, lon


def canonicalize(source_path: Path, adjudication_path: Path):
    source = load_source(source_path)
    adjudication = load_adjudication(adjudication_path)
    unknown = sorted(set(adjudication) - set(source))
    if unknown:
        raise ValueError(f"adjudication contains unknown feature IDs: {unknown[:5]}")
    missing = sorted(set(source) - set(adjudication))
    if missing:
        raise ValueError(f"adjudication does not cover all source features; missing {len(missing)}")

    source_out, canonical_out, analytical_out, crosswalk = [], [], [], []
    canonical_ids = []
    for fid in sorted(source):
        feature = json.loads(json.dumps(source[fid]))
        row = adjudication[fid]
        state, coord_status, relation, lat, lon = validate_row(fid, row)
        feature["geometry"] = None if lat is None else {"type": "Point", "coordinates": [lon, lat]}
        props = feature["properties"]
        props.update({
            "certification_state": state,
            "coordinate_status": coord_status,
            "identity_relation": relation,
            "canonical_id": clean(row.get("canonical_id")),
            "provenance_locator": clean(row.get("provenance_locator")),
            "provenance_type": clean(row.get("provenance_type")),
            "adjudication_notes": clean(row.get("adjudication_notes")),
        })
        source_out.append(feature)
        cid = props.get("canonical_id")
        if cid:
            canonical_ids.append(cid)
        if state == "CERTIFIED":
            canonical_out.append(feature)
        elif state in {"NONCANONICAL", "CANDIDATE_NOT_IDENTITY"}:
            analytical_out.append(feature)
        crosswalk.append({
            "source_feature_id": fid,
            "canonical_id": cid or "",
            "identity_relation": relation,
            "certification_state": state,
            "coordinate_status": coord_status,
            "provenance_locator": props.get("provenance_locator") or "",
        })

    counts = Counter(canonical_ids)
    for cid, count in counts.items():
        if count <= 1:
            continue
        rows = [r for r in crosswalk if r["canonical_id"] == cid]
        if any(r["identity_relation"] not in {"N:1", "N:N"} for r in rows):
            raise ValueError(f"canonical_id collision without N:1/N:N adjudication: {cid}")

    state_counts = Counter(f["properties"]["certification_state"] for f in source_out)
    coord_counts = Counter(f["properties"]["coordinate_status"] for f in source_out)
    summary = {
        "source_count": len(source_out),
        "canonical_feature_count": len(canonical_out),
        "analytical_feature_count": len(analytical_out),
        "crosswalk_count": len(crosswalk),
        "state_counts": dict(sorted(state_counts.items())),
        "coordinate_status_counts": dict(sorted(coord_counts.items())),
        "row_conservation_pass": len(source_out) == len(crosswalk) == len(source),
    }
    if not summary["row_conservation_pass"]:
        raise AssertionError("row conservation failed")
    return source_out, canonical_out, analytical_out, crosswalk, summary


def write_outputs(source_path: Path, adjudication_path: Path, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    source, canonical, analytical, crosswalk, summary = canonicalize(source_path, adjudication_path)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def fc(features, layer_id):
        return {"type": "FeatureCollection", "meta": {"layer_id": layer_id, "produced_at": now, "crs": "EPSG:4326", **summary}, "features": features}

    paths = {
        "source": output_dir / "ferrocarril_source.geojson",
        "canonical": output_dir / "ferrocarril_canonical.geojson",
        "analytical": output_dir / "ferrocarril_analytical.geojson",
        "crosswalk": output_dir / "ferrocarril_crosswalk.csv",
        "manifest": output_dir / "ferrocarril_canonicalization_manifest.json",
    }
    paths["source"].write_text(json.dumps(fc(source, "FERROCARRIL_SOURCE"), ensure_ascii=False, indent=2), encoding="utf-8")
    paths["canonical"].write_text(json.dumps(fc(canonical, "FERROCARRIL_CANONICAL"), ensure_ascii=False, indent=2), encoding="utf-8")
    paths["analytical"].write_text(json.dumps(fc(analytical, "FERROCARRIL_ANALYTICAL"), ensure_ascii=False, indent=2), encoding="utf-8")
    with paths["crosswalk"].open("w", encoding="utf-8", newline="") as fh:
        fieldnames = list(crosswalk[0].keys()) if crosswalk else ["source_feature_id"]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader(); writer.writerows(crosswalk)
    manifest = {"generated_at": now, "producer_module": "scripts.ferrocarril_canonicalize", "source_path": str(source_path), "adjudication_path": str(adjudication_path), "promotion_policy": "fail_closed", **summary}
    paths["manifest"].write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return paths


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--adjudication", type=Path, default=DEFAULT_ADJUDICATION)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(list(argv) if argv is not None else None)
    if not args.source.exists(): parser.error(f"source GeoJSON not found: {args.source}")
    if not args.adjudication.exists(): parser.error(f"adjudication CSV not found: {args.adjudication}")
    for path in write_outputs(args.source, args.adjudication, args.output_dir).values(): print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

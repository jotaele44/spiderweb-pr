"""Provenance manifests and deterministic KML/KMZ/CSV/GeoJSON exports."""

from __future__ import annotations

import csv
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import zipfile
from xml.sax.saxutils import escape

from shapely import wkt
from shapely.geometry import mapping

from .aoi import FrozenAOI
from .evidence import EvidenceRecord, validate_records


def _jsonable_record(record: EvidenceRecord) -> dict:
    obj = asdict(record)
    obj["evidence_tier"] = record.evidence_tier.name
    obj["spatial_state"] = record.spatial_state.value
    obj["certification"] = record.certification.value
    return obj


def write_manifest(
    path: str | Path,
    *,
    aoi: FrozenAOI,
    records: list[EvidenceRecord],
    source_manifest: list[dict] | None = None,
    dispatch_plan: list[dict] | None = None,
) -> Path:
    counts = validate_records(records)
    manifest = {
        "schema": "spiderweb.subsurface.manifest.v1",
        "aoi": asdict(aoi),
        "source_manifest": list(source_manifest or []),
        "dispatch_plan": list(dispatch_plan or []),
        "invariants": counts,
        "rules": {
            "proximity_is_discovery_only": True,
            "identity_requires_independent_binding": True,
            "missing_handler_is_not_negative_evidence": True,
            "invalid_geometry_fails_closed": True,
            "tied_top_scores_require_review": True,
        },
    }
    out = Path(path)
    out.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return out


def export_geojson(path: str | Path, records: list[EvidenceRecord]) -> Path:
    validate_records(records)
    features = []
    for record in records:
        geom = None if record.geometry_wkt is None else mapping(wkt.loads(record.geometry_wkt))
        props = _jsonable_record(record)
        props.pop("geometry_wkt", None)
        features.append({"type": "Feature", "geometry": geom, "properties": props})
    payload = {"type": "FeatureCollection", "features": features}
    out = Path(path)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return out


def export_csv(path: str | Path, records: list[EvidenceRecord]) -> Path:
    validate_records(records)
    out = Path(path)
    fieldnames = [
        "record_id",
        "source_id",
        "layer_family",
        "source_uri",
        "source_sha256",
        "retrieved_utc",
        "evidence_tier",
        "basis",
        "spatial_state",
        "distance_to_aoi",
        "geometry_wkt",
        "attributes_json",
        "certification",
        "score",
        "tied_top_score",
    ]
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    **{k: v for k, v in _jsonable_record(record).items() if k not in {"attributes", "basis"}},
                    "basis": "|".join(record.basis),
                    "attributes_json": json.dumps(record.attributes, sort_keys=True),
                }
            )
    return out


def _coord_text(coords) -> str:
    return " ".join(",".join(str(v) for v in coord) for coord in coords)


def _polygon_kml(poly) -> str:
    outer = _coord_text(poly.exterior.coords)
    inners = "".join(
        "<innerBoundaryIs><LinearRing><coordinates>"
        + _coord_text(ring.coords)
        + "</coordinates></LinearRing></innerBoundaryIs>"
        for ring in poly.interiors
    )
    return (
        "<Polygon><outerBoundaryIs><LinearRing><coordinates>"
        + outer
        + "</coordinates></LinearRing></outerBoundaryIs>"
        + inners
        + "</Polygon>"
    )


def _geometry_kml(geom) -> str:
    if geom.geom_type == "Polygon":
        return _polygon_kml(geom)
    if geom.geom_type == "MultiPolygon":
        return "<MultiGeometry>" + "".join(_polygon_kml(p) for p in geom.geoms) + "</MultiGeometry>"
    if geom.geom_type == "Point":
        return f"<Point><coordinates>{_coord_text([geom.coords[0]])}</coordinates></Point>"
    if geom.geom_type == "LineString":
        return f"<LineString><coordinates>{_coord_text(geom.coords)}</coordinates></LineString>"
    return ""


def export_kml(path: str | Path, records: list[EvidenceRecord]) -> Path:
    validate_records(records)
    placemarks = []
    for record in records:
        if record.geometry_wkt is None:
            continue
        geom = wkt.loads(record.geometry_wkt)
        geometry_xml = _geometry_kml(geom)
        if not geometry_xml:
            continue
        data = _jsonable_record(record)
        extended = "".join(
            f'<Data name="{escape(str(key))}"><value>{escape(json.dumps(value, ensure_ascii=False))}</value></Data>'
            for key, value in data.items()
            if key != "geometry_wkt"
        )
        placemarks.append(
            f"<Placemark><name>{escape(record.record_id)}</name><ExtendedData>{extended}</ExtendedData>{geometry_xml}</Placemark>"
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        + "".join(placemarks)
        + "</Document></kml>"
    )
    out = Path(path)
    out.write_text(xml, encoding="utf-8")
    return out


def export_kmz(path: str | Path, records: list[EvidenceRecord]) -> Path:
    out = Path(path)
    kml_bytes = export_kml(out.with_suffix(".kml"), records).read_bytes()
    out.with_suffix(".kml").unlink()
    info = zipfile.ZipInfo("doc.kml", date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr(info, kml_bytes)
    return out


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

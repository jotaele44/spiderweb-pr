"""Spiderweb-pr spatial/operational intake lane.

Consumes the Contract-Sweeper PR-intake router's spiderweb-pr lane export
(``spiderweb_pr_derivatives.csv``) and normalizes it into the spatial/operational
tables, candidate geojsons, and review queues defined by
``docs/pr_intake_router_spiderweb_lane.md``. This module does not import
Contract-Sweeper; it treats the router as an external producer.

Degrade-gracefully contract: the router derivative does not yet carry
geometry/location/asset/agency fields (producer enrichment is a held follow-up).
Those normalized fields are therefore emitted empty, every coordinate-less record
is marked ``manual_geocode_required`` and listed in the geocode queue, and the
candidate geojsons stay empty until the producer carries coordinates. Routing,
Contract-Sweeper backlink, topic domain, layer class, tier, and provenance are
populated now and the structure is ready to absorb the richer fields unchanged.

Extension fields beyond the spec's 34 (``final_status``, ``title``,
``summary_own_words``, ``all_domains``) are retained to avoid information loss.
Routing is single-table by domain priority, so a multi-domain record's secondary
domains are visible only in ``all_domains``.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import csv
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator

REPO_ROOT = Path(__file__).resolve().parents[1]
INPUT_FILENAME = "spiderweb_pr_derivatives.csv"
INPUT_SCHEMA_PATH = REPO_ROOT / "schemas" / "pr_intake_derivative.schema.json"
LAYER_ID = "spiderweb_spatial_lane"
EXPORT_CONTRACT_VERSION = "0.1.0"

# The 34 normalized fields mandated by docs/pr_intake_router_spiderweb_lane.md.
NORMALIZED_FIELDS = (
    "record_id", "source_item_id", "canonical_repo", "related_contract_sweeper_record_id",
    "source_name", "source_url", "published_at", "discovered_at",
    "topic_domain", "spiderweb_layer_class",
    "municipality_name", "municipality_geoid", "location_text",
    "latitude", "longitude", "geometry_type", "geometry_confidence", "manual_geocode_required",
    "asset_or_feature_name", "asset_type", "dataset_type", "file_format", "crs", "temporal_coverage",
    "agency_entity", "federal_entity", "operational_entity", "activity_type",
    "evidence_tier", "confidence_level", "source_hash", "content_hash", "dedupe_group_id",
    "review_reason",
)
# Extension fields retained beyond the spec to avoid information loss.
EXTENSION_FIELDS = ("final_status", "title", "summary_own_words", "all_domains")
TABLE_FIELDS = NORMALIZED_FIELDS + EXTENSION_FIELDS

NORMALIZED_TABLES = (
    "spatial_intake_items.csv", "infrastructure_assets.csv", "aviation_activity_items.csv",
    "maritime_activity_items.csv", "hydro_environment_items.csv", "science_dataset_items.csv",
)
CANDIDATE_GEOJSONS = ("poi_candidates.geojson", "aoi_candidates.geojson", "corridor_candidates.geojson")
REPORT_FILENAME = "spiderweb_spatial_lane_report.json"
DEFAULT_TABLE = "spatial_intake_items.csv"

# domain -> (spiderweb_layer_class, target table)
DOMAIN_ROUTING = {
    "infrastructure_footprint": ("infrastructure_asset", "infrastructure_assets.csv"),
    "subsurface_hydro": ("hydro_environment", "hydro_environment_items.csv"),
    "aviation_activity": ("aviation_activity", "aviation_activity_items.csv"),
    "maritime_activity": ("maritime_activity", "maritime_activity_items.csv"),
    "environment_weather": ("science_dataset", "science_dataset_items.csv"),
    "science_dataset": ("science_dataset", "science_dataset_items.csv"),
    "geography_gis": ("gis_dataset", "spatial_intake_items.csv"),
    "federal_military_activity": ("federal_military_activity", "spatial_intake_items.csv"),
    "physical_observation": ("physical_observation", "spatial_intake_items.csv"),
    "poi_aoi_corridor_candidate": ("candidate", "spatial_intake_items.csv"),
}
# When a record carries several domains, the primary signal is the first match here.
DOMAIN_PRIORITY = (
    "infrastructure_footprint", "subsurface_hydro", "aviation_activity", "maritime_activity",
    "science_dataset", "environment_weather", "poi_aoi_corridor_candidate", "geography_gis",
    "federal_military_activity", "physical_observation",
)


class SpiderwebSpatialLaneError(ValueError):
    """Raised when the spatial/operational lane cannot be built safely."""


def _validator() -> Draft7Validator:
    try:
        schema = json.loads(INPUT_SCHEMA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SpiderwebSpatialLaneError(f"missing input schema: {INPUT_SCHEMA_PATH.name}") from exc
    return Draft7Validator(schema)


def _parse_json_array(raw: str, field: str) -> tuple[list[Any] | None, str | None]:
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None, f"{field} is not valid JSON: {raw!r}"
    if not isinstance(value, list):
        return None, f"{field} is not a JSON array: {raw!r}"
    return value, None


def _primary_domain(domains: list[str]) -> str:
    for candidate in DOMAIN_PRIORITY:
        if candidate in domains:
            return candidate
    return domains[0] if domains else ""


def _format_error(err) -> str:
    loc = ".".join(str(p) for p in err.absolute_path) or "<row>"
    return f"{loc}: {err.message}"


def _empty_record() -> dict[str, str]:
    return {field: "" for field in TABLE_FIELDS}


def _normalize_row(row: dict[str, str], validator: Draft7Validator):
    """Return (record, table, errors, needs_geocode)."""
    errors = [_format_error(e) for e in validator.iter_errors(row)]
    if errors:
        return None, None, errors, False

    domains, derr = _parse_json_array(row.get("domains", ""), "domains")
    if derr:
        return None, None, [derr], False
    if not domains:
        return None, None, ["domains parsed to an empty array"], False
    _, oerr = _parse_json_array(row.get("output_tables", "") or "[]", "output_tables")
    if oerr:
        return None, None, [oerr], False

    primary = _primary_domain(domains)
    layer_class, table = DOMAIN_ROUTING.get(primary, ("unclassified_spatial", DEFAULT_TABLE))

    lat = (row.get("latitude") or "").strip()
    lon = (row.get("longitude") or "").strip()
    has_coords = bool(lat and lon)

    rec = _empty_record()
    rec.update({
        "record_id": row.get("record_id", ""),
        "source_item_id": row.get("source_item_id", ""),
        "canonical_repo": row.get("canonical_repo", ""),
        "related_contract_sweeper_record_id": row.get("related_repo_record_id", ""),
        "source_name": row.get("source_name", ""),
        "source_url": row.get("source_url", ""),
        "published_at": row.get("published_at", ""),
        "discovered_at": row.get("discovered_at", ""),
        "topic_domain": primary,
        "spiderweb_layer_class": layer_class,
        "latitude": lat,
        "longitude": lon,
        "geometry_type": "Point" if has_coords else "",
        "crs": "EPSG:4326" if has_coords else "",
        "manual_geocode_required": "false" if has_coords else "true",
        "evidence_tier": row.get("evidence_tier", ""),
        "confidence_level": row.get("confidence_level", ""),
        "source_hash": row.get("source_hash", ""),
        "content_hash": row.get("content_hash", ""),
        "dedupe_group_id": row.get("dedupe_group_id", ""),
        "review_reason": "" if has_coords else "manual_geocode_required",
        # extension fields
        "final_status": row.get("final_status", ""),
        "title": row.get("title", ""),
        "summary_own_words": row.get("summary_own_words", ""),
        "all_domains": json.dumps(domains),
    })
    return rec, table, [], (not has_coords)


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: tuple[str, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_geojson(path: Path, features: list[dict[str, Any]]) -> None:
    payload = {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4326"}},
        "features": features,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _point_feature(rec: dict[str, str]) -> dict[str, Any]:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [float(rec["longitude"]), float(rec["latitude"])]},
        "properties": {k: rec[k] for k in ("record_id", "source_item_id", "topic_domain",
                                           "spiderweb_layer_class", "evidence_tier", "final_status")},
    }


def _daily_report(report: dict[str, Any]) -> str:
    lines = [
        "# Spiderweb-PR Spatial / Operational Update",
        "",
        f"Generated at: {report['generated_at']}",
        f"Producer: {report['producer']} (export contract {report['export_contract_version']})",
        f"Status: {report['status']} — zero-loss: {'PASS' if report['zero_loss_pass'] else 'FAIL'}",
        "",
        "## Normalized records by table",
    ]
    for name, count in sorted(report["by_table"].items()):
        lines.append(f"- `{name}`: {count}")
    lines += [
        "",
        "## Review queues",
        f"- geocode_queue (manual_geocode_required): {report['review']['geocode_queue']}",
        f"- discrepancy_queue (schema/gate failures): {report['review']['discrepancy_queue']}",
        "",
        "Geometry/location/asset fields are empty pending Contract-Sweeper producer "
        "enrichment; candidate geojsons populate once derivatives carry coordinates.",
        "",
    ]
    return "\n".join(lines)


def build_spiderweb_spatial_lane(input_dir: str | Path, output_dir: str | Path | None = None) -> dict[str, Any]:
    """Normalize the router's spiderweb-pr derivatives into the spatial/operational lane.

    Reads ``spiderweb_pr_derivatives.csv`` from *input_dir* and writes the spec'd
    normalized tables, candidate geojsons, review queues, daily report, and a
    layer report. Returns the report dict.
    """
    root = Path(input_dir)
    out = Path(output_dir) if output_dir else root
    source = root / INPUT_FILENAME
    if not source.exists():
        raise SpiderwebSpatialLaneError(f"missing required input: {INPUT_FILENAME}")

    with source.open("r", encoding="utf-8", newline="") as f:
        rows = [dict(r) for r in csv.DictReader(f)]

    validator = _validator()
    tables: dict[str, list[dict[str, Any]]] = {name: [] for name in NORMALIZED_TABLES}
    geocode_queue: list[dict[str, Any]] = []
    discrepancy_queue: list[dict[str, Any]] = []
    poi_features: list[dict[str, Any]] = []
    by_tier: Counter = Counter()
    by_layer_class: Counter = Counter()

    for row in rows:
        record, table, errors, needs_geocode = _normalize_row(row, validator)
        if errors:
            discrepancy_queue.append({
                "source_item_id": row.get("source_item_id", ""),
                "record_id": row.get("record_id", ""),
                "review_reason": "; ".join(errors),
            })
            continue
        tables[table].append(record)
        by_tier[record["evidence_tier"] or "UNSET"] += 1
        by_layer_class[record["spiderweb_layer_class"]] += 1
        if needs_geocode:
            geocode_queue.append({
                "record_id": record["record_id"],
                "source_item_id": record["source_item_id"],
                "topic_domain": record["topic_domain"],
                "spiderweb_layer_class": record["spiderweb_layer_class"],
                "location_text": record["location_text"],
            })
        elif record["spiderweb_layer_class"] == "candidate":
            poi_features.append(_point_feature(record))

    normalized_dir = out / "data" / "normalized"
    exports_dir = out / "data" / "exports"
    review_dir = out / "data" / "review"
    daily_dir = out / "reports" / "daily"
    for d in (normalized_dir, exports_dir, review_dir, daily_dir):
        d.mkdir(parents=True, exist_ok=True)

    for name in NORMALIZED_TABLES:
        _write_csv(normalized_dir / name, sorted(tables[name], key=lambda r: r["record_id"]), TABLE_FIELDS)

    _write_geojson(exports_dir / "poi_candidates.geojson", sorted(poi_features, key=lambda f: f["properties"]["record_id"]))
    _write_geojson(exports_dir / "aoi_candidates.geojson", [])
    _write_geojson(exports_dir / "corridor_candidates.geojson", [])

    _write_csv(review_dir / "geocode_queue.csv", geocode_queue,
               ("record_id", "source_item_id", "topic_domain", "spiderweb_layer_class", "location_text"))
    _write_csv(review_dir / "discrepancy_queue.csv", discrepancy_queue,
               ("source_item_id", "record_id", "review_reason"))

    normalized_count = sum(len(v) for v in tables.values())
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "layer_id": LAYER_ID,
        "input_dir": str(root),
        "producer": "pr-intake-router",
        "export_contract_version": EXPORT_CONTRACT_VERSION,
        "status": "READY" if normalized_count else "EMPTY",
        "input_rows": len(rows),
        "record_count": normalized_count,
        "by_table": {name: len(tables[name]) for name in NORMALIZED_TABLES},
        "by_tier": dict(sorted(by_tier.items())),
        "by_layer_class": dict(sorted(by_layer_class.items())),
        "candidate_features": len(poi_features),
        "review": {"geocode_queue": len(geocode_queue), "discrepancy_queue": len(discrepancy_queue)},
        "zero_loss_pass": normalized_count + len(discrepancy_queue) == len(rows),
        "outputs": {
            "normalized": [f"data/normalized/{n}" for n in NORMALIZED_TABLES],
            "candidates": [f"data/exports/{g}" for g in CANDIDATE_GEOJSONS],
            "review": ["data/review/geocode_queue.csv", "data/review/discrepancy_queue.csv"],
            "daily_report": "reports/daily/spiderweb_spatial_operational_update_report.md",
            "layer_report": REPORT_FILENAME,
        },
    }
    (daily_dir / "spiderweb_spatial_operational_update_report.md").write_text(_daily_report(report), encoding="utf-8")
    (out / REPORT_FILENAME).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report

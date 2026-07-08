"""
Materialize the newer, previously-unwired real datasets into spiderweb's export
streams (extends what `scripts/build_real_spatial_streams.py` already emits).

Two real, committed datasets are surfaced here:

  * `data/usgs_ofr_98_038/derived/usgs_ofr_98_038_metallic_occurrences_wgs84.geojson`
    — 364 real WGS84 point features (lab-digitized from the USGS OFR 98-038
    ARC/INFO E00 coverage). Real, verified geometry; attribute extraction is
    explicitly still pending (`conversion_status:
    derived_from_lab_coordinates_attributes_pending` on every row), so these
    project as `spiderweb_observation` rows (`observation_type:
    usgs_metallic_occurrence`) with a moderate, documented confidence — real
    location, incomplete characterization — under one shared dataset source.

  * `configs/master_pin_registry.yaml`'s `layer_index` entries flagged `WIRED`
    (50 of 80) — pipeline-wired GIS layers with no geometry bound yet
    (`geometry_type: unknown` on every row; the catalog itself documents
    "labels only... no geometry/coordinates bound"). These project as
    `spiderweb_source` rows (`kind: gis_layer_reference`) — deliberately NOT
    `observations`, since there is no observed record to attach, just a
    catalog reference — each carrying the registry's own per-entry
    `evidence_tier` (uniformly T3 for the WIRED set) as their confidence, so
    they read as low-evidence catalog metadata rather than verified
    observations.

Both datasets are additive: `federation_export.py` discriminates
`observation_type`/`kind` to project them onto new canonical entity_types
(`mineral_occurrence`, `gis_layer_reference`) without touching the existing
`airspace_observation`/`sensor_source` projection for pre-existing rows.

This script MERGES with whatever `--real-dir` already holds (normally the
output of `build_real_spatial_streams.py`) rather than overwriting it, so the
two emitters compose: run `build_real_spatial_streams.py` first, then this.

Row ids are computed with `scripts.validate_export.compute_row_id`, exactly as
`build_real_spatial_streams.py` does, so the validator's deterministic-id gate
passes.

Usage:
    python scripts/build_real_spatial_streams.py --out exports/real
    python scripts/build_dataset_catalog_streams.py --real-dir exports/real
    python scripts/build_export_package.py --out /tmp/pkg --source-dir exports/real --mode production
    python scripts/validate_export.py --package /tmp/pkg --mode production
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.validate_export import compute_row_id  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

USGS_GEOJSON = (
    REPO_ROOT / "data" / "usgs_ofr_98_038" / "derived"
    / "usgs_ofr_98_038_metallic_occurrences_wgs84.geojson"
)
USGS_MANIFEST = REPO_ROOT / "data" / "usgs_ofr_98_038" / "registry" / "usgs_ofr_98_038_manifest.json"
PIN_REGISTRY = REPO_ROOT / "configs" / "master_pin_registry.yaml"

OUT_FILENAMES = {
    "events": "airspace_events.jsonl",
    "observations": "observations.jsonl",
    "tracks": "tracks.jsonl",
    "sources": "sources.jsonl",
}

# WIRED evidence_tier (uniformly T3 across the current registry) -> a
# documented, conservative confidence score. Not a general T1-T4 scale — just
# the one tier actually present today; extend if the registry ever carries
# other tiers for WIRED rows.
_TIER_SCORE = {"T1": 0.85, "T2": 0.65, "T3": 0.4, "T4": 0.25}


def _finalize(row: dict) -> dict:
    row["id"] = compute_row_id(row)
    return row


def build_usgs_rows(geojson_path: Path, manifest_path: Path) -> tuple[dict, list[dict]]:
    """One shared dataset source + one observation per real metallic-occurrence point."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    as_of = manifest["generated_utc"]
    geojson = json.loads(geojson_path.read_text(encoding="utf-8"))
    features = geojson["features"]

    source_id = "src_usgs_ofr_98_038_metallic"
    lineage = [
        {"actor": "USGS", "step": "survey", "ts": as_of},
        {"actor": "build_dataset_catalog_streams@v1", "step": "e00_lab_coordinate_conversion", "ts": as_of},
    ]
    # Real, lab-digitized geometry (high) blended with pending attribute
    # extraction (low) — the file-level conversion_status is the same on
    # every point, so one documented score applies to all of them.
    confidence = {
        "score": 0.65,
        "method": "usgs_ofr_98_038_lab_coordinate_digitization",
        "components": {"geometry_verified": 0.9, "attribute_completeness": 0.4},
    }

    source = _finalize({
        "source_id": source_id,
        "kind": "usgs_ofr_98_038_report",
        "first_seen_at": as_of,
        "last_seen_at": as_of,
        "lineage": lineage,
        "confidence": confidence,
        "attributes": {
            "title": manifest["title"],
            "source_agency": manifest["source_agency"],
            "source_url": manifest["source_url"],
            "point_count": manifest["metallic_occurrence_point_count"],
        },
        "is_synthetic": False,
    })

    observations = []
    for feat in features:
        props = feat["properties"]
        lon, lat = feat["geometry"]["coordinates"]
        observations.append(_finalize({
            "source_id": source_id,
            # No subject_id: federation_export.py treats any subject_id/callsign as an
            # aircraft-callsign indicator and mints a spurious "aircraft" entity for it —
            # a mineral occurrence point isn't a subject being tracked. The point's own
            # USGS record id is preserved below, under attributes, instead.
            "observation_type": "usgs_metallic_occurrence",
            "observed_at": as_of,
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "lineage": lineage,
            "confidence": confidence,
            "attributes": {
                "usgs_point_id": props["source_id"],
                "source_report": props["source_report"],
                "source_file": props["source_file"],
                "geometry_source": props["geometry_source"],
                "conversion_status": props["conversion_status"],
            },
            "is_synthetic": False,
        }))
    return source, observations


def build_layer_catalog_rows(registry_path: Path) -> list[dict]:
    """One source per WIRED layer_index entry — a catalog reference, not an observation."""
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    as_of = registry["generated_at"]
    wired = [row for row in registry["layer_index"] if row.get("flag") == "WIRED"]

    sources = []
    for row in wired:
        tier = row.get("evidence_tier")
        score = _TIER_SCORE.get(tier, 0.25)
        lineage = [
            {"actor": registry["producer_module"], "step": "pin_registry_catalog", "ts": as_of},
        ]
        confidence = {
            "score": score,
            "method": f"master_pin_registry_evidence_tier_{(tier or 'unknown').lower()}",
        }
        sources.append(_finalize({
            # The layer's own readable label becomes the raw source_id — federation_export.py
            # names source entities from this raw string, so this reads as "Hydro Points
            # Normalized" rather than an opaque hash.
            "source_id": row["label"],
            "kind": "gis_layer_reference",
            "first_seen_at": as_of,
            "last_seen_at": as_of,
            "lineage": lineage,
            "confidence": confidence,
            "attributes": {
                "pin_layer": row.get("pin_layer"),
                "domain": row.get("domain"),
                "pin_group": row.get("pin_group"),
                "visibility": row.get("visibility"),
                "geometry_type": row.get("geometry_type"),
                "evidence_tier": tier,
            },
            "is_synthetic": False,
        }))
    return sources


def _read_existing(real_dir: Path, stream: str) -> list[dict]:
    path = real_dir / OUT_FILENAMES[stream]
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def build_streams(
    real_dir: Path,
    usgs_geojson: Path = USGS_GEOJSON,
    usgs_manifest: Path = USGS_MANIFEST,
    pin_registry: Path = PIN_REGISTRY,
) -> dict[str, list[dict]]:
    """Existing real-dir streams, plus the new USGS + layer-catalog rows merged in."""
    usgs_source, usgs_obs = build_usgs_rows(usgs_geojson, usgs_manifest)
    layer_sources = build_layer_catalog_rows(pin_registry)

    existing_obs = _read_existing(real_dir, "observations")
    existing_sources = _read_existing(real_dir, "sources")

    # This emitter owns (and must fully REPLACE, not append to) exactly the rows it
    # itself writes: usgs_metallic_occurrence observations, and usgs_ofr_98_038_report /
    # gis_layer_reference sources. Naively concatenating existing_obs/existing_sources
    # with the freshly-built rows would duplicate everything on every rerun against an
    # already-merged --real-dir (the whole point of this script, since its output is
    # committed back into exports/real/). Filtering the owned rows out of "existing"
    # before concatenating makes reruns a true no-op AND correctly picks up upstream
    # edits/deletions in the USGS geojson or master_pin_registry.yaml — unlike plain
    # dedupe-by-id, which would leave a stale row behind whenever its content (and thus
    # its content-hash id) changes upstream. Rows owned by other emitters (e.g.
    # build_real_spatial_streams.py's structure_sighting/airport_reference_location
    # observations) are left untouched.
    other_obs = [r for r in existing_obs if r.get("observation_type") != "usgs_metallic_occurrence"]
    other_sources = [r for r in existing_sources if r.get("kind") not in ("usgs_ofr_98_038_report", "gis_layer_reference")]

    return {
        "events": _read_existing(real_dir, "events"),
        "observations": other_obs + usgs_obs,
        "tracks": _read_existing(real_dir, "tracks"),
        "sources": other_sources + [usgs_source] + layer_sources,
    }


def write_streams(streams: dict[str, list[dict]], out_dir: Path) -> dict[str, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for stream, rows in streams.items():
        path = out_dir / OUT_FILENAMES[stream]
        with open(path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        counts[stream] = len(rows)
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Merge the USGS metallic-occurrence + layer-catalog datasets into a real-streams dir."
    )
    parser.add_argument("--real-dir", default=str(REPO_ROOT / "exports" / "real"),
                        help="Directory to read existing real streams from and write the merged result to")
    parser.add_argument("--usgs-geojson", default=str(USGS_GEOJSON))
    parser.add_argument("--usgs-manifest", default=str(USGS_MANIFEST))
    parser.add_argument("--pin-registry", default=str(PIN_REGISTRY))
    args = parser.parse_args(argv)

    real_dir = Path(args.real_dir)
    streams = build_streams(
        real_dir=real_dir,
        usgs_geojson=Path(args.usgs_geojson),
        usgs_manifest=Path(args.usgs_manifest),
        pin_registry=Path(args.pin_registry),
    )
    synthetic = [r for rows in streams.values() for r in rows if r.get("is_synthetic")]
    if synthetic:
        raise SystemExit(f"emitter bug: {len(synthetic)} rows flagged synthetic")
    counts = write_streams(streams, real_dir)
    print(f"merged dataset-catalog streams into {real_dir} — {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

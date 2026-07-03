"""
Materialize REAL (non-synthetic) spiderweb export streams from committed data.

This is the missing "last mile" between the retained producer datasets and the
federation export contract: `scripts/build_export_package.py` packages stream
files but (by design) only ships synthetic samples; nothing previously emitted
`spiderweb_*` envelope rows from real data. This script reads two real,
committed datasets and writes the four contract streams with
`is_synthetic: false`:

  * `data/sites/SITE_RI_20260522_001/site_record.json` — a georeferenced,
    user-captured structure observation (WGS84 coordinates, capture lineage)
    → one `spiderweb_observation` + its capture `spiderweb_source`.
  * `configs/airport_registry.yaml` — the canonical PR airport registry
    (real FAA-derived locations) → one `spiderweb_observation` per airport
    (observation_type `airport_reference_location`) + one registry
    `spiderweb_source`. The registry's git commit date is used as the
    observed/seen timestamp so provenance stays truthful.

`airspace_events.jsonl` and `tracks.jsonl` are written empty but declared:
no real event/track data exists in-repo (FR24 live capture belongs to
skywatcher-pr), and the export contract requires all four streams present
while allowing zero-row streams.

Row ids are computed with `scripts.validate_export.compute_row_id` so the
validator's deterministic-id gate passes.

Usage:
    python scripts/build_real_spatial_streams.py --out exports/real
    python scripts/build_export_package.py --out /tmp/pkg --source-dir exports/real --mode production
    python scripts/validate_export.py --package /tmp/pkg --mode production
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.validate_export import compute_row_id  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

SITE_RECORD = REPO_ROOT / "data" / "sites" / "SITE_RI_20260522_001" / "site_record.json"
AIRPORT_REGISTRY = REPO_ROOT / "configs" / "airport_registry.yaml"

OUT_FILENAMES = {
    "events": "airspace_events.jsonl",
    "observations": "observations.jsonl",
    "tracks": "tracks.jsonl",
    "sources": "sources.jsonl",
}


def _finalize(row: dict) -> dict:
    row["id"] = compute_row_id(row)
    return row


def _registry_commit_ts(path: Path) -> str:
    """Committer date of the registry file — the honest 'as of' timestamp."""
    out = subprocess.run(
        ["git", "log", "-1", "--format=%cI", "--", str(path)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    ts = out.stdout.strip()
    if not ts:
        raise RuntimeError(f"no git history for {path}; cannot derive provenance timestamp")
    return ts


def build_site_rows(site_record_path: Path) -> tuple[dict, dict]:
    """One real capture source + one real structure observation."""
    site = json.loads(site_record_path.read_text(encoding="utf-8"))
    lineage_meta = site["source_lineage"]
    captured_at = site["visible_timestamp"]
    source_id = f"src_{site['site_id'].lower()}"

    lineage = [
        {
            "actor": f"{lineage_meta['platform']} / {lineage_meta['basemap']}",
            "step": "capture",
            "ts": captured_at,
        },
        {"actor": "operator", "step": "human_review", "ts": captured_at},
        {"actor": "build_real_spatial_streams@v1", "step": "export", "ts": captured_at},
    ]
    # coordinate_confidence is high but the record's own classification ceiling
    # is low-to-moderate; the blended score reflects the weaker of the two.
    confidence = {
        "score": 0.55,
        "method": "human_review",
        "components": {"coordinate_confidence": 0.9, "classification_ceiling": 0.5},
    }

    source = _finalize(
        {
            "source_id": source_id,
            "kind": lineage_meta["capture_type"],
            "first_seen_at": captured_at,
            "last_seen_at": captured_at,
            "lineage": lineage,
            "confidence": confidence,
            "attributes": {
                "platform": lineage_meta["platform"],
                "basemap": lineage_meta["basemap"],
                "coordinate_source": lineage_meta["coordinate_source"],
            },
            "is_synthetic": False,
        }
    )
    observation = _finalize(
        {
            "source_id": source_id,
            "subject_id": site["site_id"],
            "observation_type": "structure_sighting",
            "observed_at": captured_at,
            "geometry": {"type": "Point", "coordinates": [site["longitude"], site["latitude"]]},
            "lineage": lineage,
            "confidence": confidence,
            "attributes": {
                "name": site["name"],
                "feature_type": site["feature_type"],
                "initial_classification": site["initial_classification"],
                "municipality": site["municipality"],
                "region": site["region"],
                "status": site["status"],
                "evidence_status": site["evidence_status"],
            },
            "is_synthetic": False,
        }
    )
    return source, observation


def build_airport_rows(registry_path: Path, as_of: str) -> tuple[dict, list[dict]]:
    """One registry source + one reference observation per airport."""
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    source_id = f"src_{registry['version']}"
    lineage = [
        {"actor": registry["version"], "step": "ingest", "ts": as_of},
        {"actor": "build_real_spatial_streams@v1", "step": "export", "ts": as_of},
    ]
    confidence = {"score": 0.95, "method": "manifest_attested"}

    source = _finalize(
        {
            "source_id": source_id,
            "kind": "reference_registry",
            "first_seen_at": as_of,
            "last_seen_at": as_of,
            "lineage": lineage,
            "confidence": confidence,
            "attributes": {
                "registry_version": registry["version"],
                "airport_count": len(registry["airports"]),
            },
            "is_synthetic": False,
        }
    )
    observations = [
        _finalize(
            {
                "source_id": source_id,
                "subject_id": airport["airport_id"],
                "observation_type": "airport_reference_location",
                "observed_at": as_of,
                "geometry": {"type": "Point", "coordinates": [airport["lon"], airport["lat"]]},
                "lineage": lineage,
                "confidence": confidence,
                "attributes": {
                    "canonical_name": airport["canonical_name"],
                    "iata": airport.get("iata"),
                    "icao": airport.get("icao"),
                    "municipality": airport.get("municipality"),
                },
                "is_synthetic": False,
            }
        )
        for airport in registry["airports"]
    ]
    return source, observations


def build_streams(
    site_record_path: Path = SITE_RECORD,
    registry_path: Path = AIRPORT_REGISTRY,
    registry_as_of: str | None = None,
) -> dict[str, list[dict]]:
    as_of = registry_as_of or _registry_commit_ts(registry_path)
    site_source, site_obs = build_site_rows(site_record_path)
    reg_source, airport_obs = build_airport_rows(registry_path, as_of)
    return {
        "events": [],
        "observations": [site_obs, *airport_obs],
        "tracks": [],
        "sources": [site_source, reg_source],
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
        description="Emit real (non-synthetic) spiderweb export streams from committed data."
    )
    parser.add_argument("--out", default=str(REPO_ROOT / "exports" / "real"))
    parser.add_argument("--site-record", default=str(SITE_RECORD))
    parser.add_argument("--airport-registry", default=str(AIRPORT_REGISTRY))
    parser.add_argument(
        "--registry-as-of",
        default=None,
        help="Override the registry provenance timestamp (default: git commit date)",
    )
    args = parser.parse_args(argv)

    streams = build_streams(
        site_record_path=Path(args.site_record),
        registry_path=Path(args.airport_registry),
        registry_as_of=args.registry_as_of,
    )
    synthetic = [r for rows in streams.values() for r in rows if r.get("is_synthetic")]
    if synthetic:
        raise SystemExit(f"emitter bug: {len(synthetic)} rows flagged synthetic")
    counts = write_streams(streams, Path(args.out))
    print(f"wrote real streams to {args.out} — {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

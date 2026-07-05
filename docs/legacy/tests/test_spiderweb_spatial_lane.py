"""Tests for readiness/spiderweb_spatial_lane.py.

Conforms the cross-repo consumer to docs/pr_intake_router_spiderweb_lane.md:
domain->table routing, the 34 normalized fields, manual_geocode_required for
coordinate-less records, zero-loss accounting, layer-registry registration, and
a real round-trip against the moneysweep-pr router.
"""

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

from readiness.spiderweb_spatial_lane import (
    NORMALIZED_FIELDS,
    SpiderwebSpatialLaneError,
    build_spiderweb_spatial_lane,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
MONEYSWEEP = REPO_ROOT.parent / "moneysweep-pr"
OUTPUT_SCHEMA = json.loads((REPO_ROOT / "schemas" / "spiderweb_spatial_lane_record.schema.json").read_text())


# ── Fixtures mirroring the producer's on-disk CSV ──────────────────────────────

def _write_derivatives(d: Path, rows) -> None:
    flat = []
    for r in rows:
        fr = {}
        for k, v in r.items():
            if isinstance(v, (dict, list, tuple, set)):
                fr[k] = json.dumps(v, ensure_ascii=False, sort_keys=True)
            elif v is None:
                fr[k] = ""
            else:
                fr[k] = v
        flat.append(fr)
    fieldnames = sorted({k for fr in flat for k in fr})
    with (d / "spiderweb_pr_derivatives.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(flat)


def _row(record_id, domains, **over):
    base = {
        "record_id": record_id, "source_item_id": "RAW-X", "target_repo": "spiderweb-pr",
        "canonical_repo": "spiderweb-pr", "related_repo_record_id": None,
        "source_name": "USGS", "source_url": "https://example.test/x",
        "published_at": "2026-05-27", "discovered_at": "2026-05-27T12:00:00Z",
        "title": "PR spatial item", "summary_own_words": "summary",
        "domains": domains, "final_status": "routed_spiderweb_pr", "output_tables": [],
        "evidence_tier": "T2", "confidence_level": "High",
        "source_hash": "abc", "content_hash": "def", "dedupe_group_id": None,
    }
    base.update(over)
    return base


def _mixed_rows():
    return [
        _row("SW-PRINTAKE-00000000a001", ["infrastructure_footprint"]),
        _row("SW-PRINTAKE-00000000a002", ["subsurface_hydro"]),
        _row("SW-PRINTAKE-00000000a003", ["aviation_activity"]),
        _row("SW-PRINTAKE-00000000a004", ["maritime_activity"]),
        _row("SW-PRINTAKE-00000000a005", ["science_dataset"]),
        _row("SW-PRINTAKE-00000000a006", ["geography_gis"]),
        _row("SW-PRINTAKE-00000000a007", ["geography_gis", "infrastructure_footprint"]),  # priority→infra
        _row("SW-PRINTAKE-00000000a008", ["poi_aoi_corridor_candidate"],
             latitude="18.45", longitude="-66.10"),  # has coords → poi candidate
        _row("SW-PRINTAKE-00000000a009", ["federal_military_activity"]),  # → dedicated fed-mil table
        _row("BAD-ID", ["geography_gis"]),            # invalid record_id → discrepancy
        _row("SW-PRINTAKE-00000000b002", []),         # empty domains → discrepancy
    ]


def _read_table(out: Path, name):
    with (out / "data" / "normalized" / name).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ── Routing + required fields ──────────────────────────────────────────

def test_domain_routing_to_tables(tmp_path):
    _write_derivatives(tmp_path, _mixed_rows())
    report = build_spiderweb_spatial_lane(str(tmp_path), str(tmp_path))
    bt = report["by_table"]
    assert bt["infrastructure_assets.csv"] == 2     # a001 + a007 (priority)
    assert bt["hydro_environment_items.csv"] == 1
    assert bt["aviation_activity_items.csv"] == 1
    assert bt["maritime_activity_items.csv"] == 1
    assert bt["science_dataset_items.csv"] == 1
    assert bt["federal_military_activity_items.csv"] == 1  # a009 fed-mil
    assert bt["spatial_intake_items.csv"] == 2      # a006 gis + a008 candidate


def test_normalized_records_carry_all_34_fields(tmp_path):
    _write_derivatives(tmp_path, _mixed_rows())
    build_spiderweb_spatial_lane(str(tmp_path), str(tmp_path))
    rows = _read_table(tmp_path, "infrastructure_assets.csv")
    assert rows
    for field in NORMALIZED_FIELDS:
        assert field in rows[0], f"missing normalized field: {field}"
    # backlink + classification populated from the derivative
    assert rows[0]["spiderweb_layer_class"] == "infrastructure_asset"
    assert rows[0]["topic_domain"] == "infrastructure_footprint"


def test_records_validate_against_output_schema(tmp_path):
    _write_derivatives(tmp_path, _mixed_rows())
    build_spiderweb_spatial_lane(str(tmp_path), str(tmp_path))
    validator = Draft7Validator(OUTPUT_SCHEMA)
    for name in ("infrastructure_assets.csv", "spatial_intake_items.csv"):
        for rec in _read_table(tmp_path, name):
            assert list(validator.iter_errors(rec)) == [], f"{name}: {rec}"


def test_manual_geocode_required_and_queue(tmp_path):
    _write_derivatives(tmp_path, _mixed_rows())
    report = build_spiderweb_spatial_lane(str(tmp_path), str(tmp_path))
    # 8 valid no-coord records → geocode queue; the coord-bearing candidate is excluded
    assert report["review"]["geocode_queue"] == 8
    hydro = _read_table(tmp_path, "hydro_environment_items.csv")[0]
    assert hydro["manual_geocode_required"] == "true"
    cand = _read_table(tmp_path, "spatial_intake_items.csv")
    coord_rec = [r for r in cand if r["record_id"] == "SW-PRINTAKE-00000000a008"][0]
    assert coord_rec["manual_geocode_required"] == "false"
    assert coord_rec["geometry_type"] == "Point"


def test_coordinate_record_emits_poi_candidate(tmp_path):
    _write_derivatives(tmp_path, _mixed_rows())
    build_spiderweb_spatial_lane(str(tmp_path), str(tmp_path))
    poi = json.loads((tmp_path / "data" / "exports" / "poi_candidates.geojson").read_text())
    assert len(poi["features"]) == 1
    assert poi["features"][0]["geometry"]["coordinates"] == [-66.10, 18.45]
    aoi = json.loads((tmp_path / "data" / "exports" / "aoi_candidates.geojson").read_text())
    assert aoi["features"] == []


def test_invalid_rows_routed_to_discrepancy_and_zero_loss(tmp_path):
    rows = _mixed_rows()
    _write_derivatives(tmp_path, rows)
    report = build_spiderweb_spatial_lane(str(tmp_path), str(tmp_path))
    assert report["review"]["discrepancy_queue"] == 2
    assert report["record_count"] == len(rows) - 2
    assert report["record_count"] + report["review"]["discrepancy_queue"] == report["input_rows"]
    assert report["zero_loss_pass"] is True
    with (tmp_path / "data" / "review" / "discrepancy_queue.csv").open(encoding="utf-8") as f:
        ids = {r["record_id"] for r in csv.DictReader(f)}
    assert ids == {"BAD-ID", "SW-PRINTAKE-00000000b002"}


def test_all_tables_written_even_when_empty(tmp_path):
    _write_derivatives(tmp_path, [_row("SW-PRINTAKE-00000000a001", ["aviation_activity"])])
    build_spiderweb_spatial_lane(str(tmp_path), str(tmp_path))
    for name in ("spatial_intake_items.csv", "infrastructure_assets.csv", "aviation_activity_items.csv",
                 "maritime_activity_items.csv", "hydro_environment_items.csv", "science_dataset_items.csv",
                 "federal_military_activity_items.csv"):
        assert (tmp_path / "data" / "normalized" / name).exists()


def test_missing_input_raises(tmp_path):
    with pytest.raises(SpiderwebSpatialLaneError):
        build_spiderweb_spatial_lane(str(tmp_path), str(tmp_path))


def test_registered_in_layer_registry():
    from federation.hub.layer_registry import get_layer_entry
    entry = get_layer_entry("spiderweb_spatial_lane")
    assert entry.engine_module == "readiness.spiderweb_spatial_lane"
    assert entry.producer == "pr-intake-router"
    assert "spiderweb_pr_derivatives.csv" in entry.input_artifacts


# ── End-to-end round-trip against the real moneysweep-pr router ────────────

@pytest.mark.skipif(
    not (MONEYSWEEP / "run_pr_intake_router.py").exists(),
    reason="moneysweep-pr sibling repo not present",
)
def test_round_trip_zero_loss_across_the_seam(tmp_path):
    pytest.importorskip("yaml", reason="router requires PyYAML")
    fixture = MONEYSWEEP / "tests" / "fixtures" / "pr_intake_router_sample.jsonl"
    if not fixture.exists():
        pytest.skip("router sample fixture missing")

    export_dir = tmp_path / "export"
    proc = subprocess.run(
        [sys.executable, "run_pr_intake_router.py", "--input", str(fixture), "--out-dir", str(export_dir)],
        cwd=str(MONEYSWEEP), capture_output=True, text=True,
    )
    if proc.returncode != 0:
        pytest.skip(f"router export unavailable: {proc.stderr.strip()[:300]}")

    summary = json.loads((export_dir / "routing_summary.json").read_text())
    exported = summary["spiderweb_pr_derivative_count"]
    assert exported > 0

    report = build_spiderweb_spatial_lane(str(export_dir), str(tmp_path / "out"))
    assert report["input_rows"] == exported
    assert report["record_count"] + report["review"]["discrepancy_queue"] == exported
    assert report["zero_loss_pass"] is True
    assert report["review"]["discrepancy_queue"] == 0  # real router output is schema-valid


def test_descriptive_enrichment_fields_pass_through(tmp_path):
    """Producer-enriched descriptive fields (location_text/municipality_name/
    asset_type/dataset_type/file_format/agency_entity) flow into the normalized
    record, and lat/lon place the item on the map (no geocode queue)."""
    rows = [
        _row(
            "SW-PRINTAKE-00000000e001",
            ["infrastructure_footprint"],
            latitude="18.0111",
            longitude="-66.6141",
            location_text="Ponce, Puerto Rico",
            municipality_name="Ponce",
            asset_type="hydrology_dataset",
            dataset_type="lidar_dem",
            file_format="GeoTIFF",
            agency_entity="USGS",
        )
    ]
    _write_derivatives(tmp_path, rows)
    report = build_spiderweb_spatial_lane(str(tmp_path), str(tmp_path))

    assert report["review"]["geocode_queue"] == 0
    rec = _read_table(tmp_path, "infrastructure_assets.csv")[0]
    assert rec["location_text"] == "Ponce, Puerto Rico"
    assert rec["municipality_name"] == "Ponce"
    assert rec["asset_type"] == "hydrology_dataset"
    assert rec["dataset_type"] == "lidar_dem"
    assert rec["file_format"] == "GeoTIFF"
    assert rec["agency_entity"] == "USGS"
    assert rec["manual_geocode_required"] == "false"
    assert rec["latitude"] == "18.0111" and rec["longitude"] == "-66.6141"

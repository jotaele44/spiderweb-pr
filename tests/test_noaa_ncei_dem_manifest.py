"""Guardrails for NOAA/NCEI coastal DEM source registration.

These tests validate source manifests and repo hygiene only. They do not fetch
or commit NOAA/NCEI raster data.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "data_sources" / "noaa" / "ncei_coastal_dems.yml"
SCHEMA_PATH = REPO_ROOT / "schemas" / "raster_source_manifest.schema.json"
SCRIPT_PATH = REPO_ROOT / "scripts" / "acquire" / "noaa_ncei_opendap.py"
DOC_PATH = REPO_ROOT / "docs" / "sources" / "noaa_ncei_coastal_dems.md"


def load_manifest() -> dict:
    # ncei_coastal_dems.yml is JSON-compatible YAML to avoid adding a parser dependency.
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_noaa_ncei_required_files_exist() -> None:
    assert MANIFEST_PATH.exists()
    assert SCHEMA_PATH.exists()
    assert SCRIPT_PATH.exists()
    assert DOC_PATH.exists()


def test_manifest_is_json_compatible_yaml() -> None:
    manifest = load_manifest()
    assert manifest["source_family"] == "NOAA_NCEI_COASTAL_DEM"
    assert manifest["evidence_tier"] == "T1"
    assert isinstance(manifest["datasets"], list)
    assert len(manifest["datasets"]) >= 8


def test_schema_is_valid_json() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["title"] == "Spiderweb raster source manifest"
    assert "datasets" in schema["properties"]


def test_san_juan_opendap_metadata_registered() -> None:
    manifest = load_manifest()
    datasets = {item["dataset_key"]: item for item in manifest["datasets"]}
    san_juan = datasets["san_juan_19_prvd02_2015"]

    assert san_juan["opendap_url"] == (
        "https://www.ngdc.noaa.gov/thredds/dodsC/regional/san_juan_19_prvd02_2015.nc"
    )
    assert san_juan["vertical_datum"] == "Puerto Rico Vertical Datum of 2002"
    assert san_juan["horizontal_datum"] == "WGS84"
    assert san_juan["grid_shape"] == {"lat": 5185, "lon": 10369}

    bounds = san_juan["bounds_wgs84"]
    assert bounds["min_lat"] == 18.379984568
    assert bounds["max_lat"] == 18.540014408
    assert bounds["min_lon"] == -66.230015432
    assert bounds["max_lon"] == -65.909986616


def test_san_juan_actual_range_contradiction_resolved() -> None:
    manifest = load_manifest()
    san_juan = next(
        item for item in manifest["datasets"] if item["dataset_key"] == "san_juan_19_prvd02_2015"
    )
    band1 = san_juan["variables"]["Band1"]

    # The OPeNDAP-form snapshot value stays recorded as historical fact, but the
    # contradiction is resolved by a live raster sample (min < 0 < max, not flat zero).
    assert band1["actual_range_from_opendap_form"] == [0.0, 0.0]
    assert band1["actual_range_status"] == "resolved_live_raster_sampled_2026-07-16"
    assert band1["live_sample_min"] < 0 < band1["live_sample_max"]
    assert san_juan["validation"]["raster_minmax_status"].startswith("validated")
    assert san_juan["validation"]["promotion_status"] == "source_raster_validated"


def test_pr_wide_cudem_ninth_registered() -> None:
    manifest = load_manifest()
    datasets = {item["dataset_key"]: item for item in manifest["datasets"]}
    cudem = datasets["puerto_rico_cudem_ninth_9525"]

    # PR-wide 1/9 arc-second CUDEM sourced from the NOAA Coastal LiDAR PDS.
    assert cudem["year"] == 2022
    assert cudem["spatial_resolution"] == "1/9 arc-second"
    assert cudem["integrated_topobathy"] is True
    # PRVD02 vertical datum matches the existing primary so the layers compose.
    assert cudem["vertical_datum"] == "Puerto Rico Vertical Datum of 2002"
    assert cudem["horizontal_datum"] == "NAD83"
    assert cudem["horizontal_crs_epsg"] == 4269

    # Distributed as GeoTIFF via S3 (not the THREDDS regional .nc catalog), so it
    # carries source_url/s3_prefix instead of an opendap_url.
    assert cudem["format"] == "GeoTIFF"
    assert "opendap_url" not in cudem
    assert cudem["s3_prefix"].startswith("s3://noaa-nos-coastal-lidar-pds/")
    assert cudem["url_list"].endswith("urllist9525.txt")
    assert cudem["tile_count"] == 25

    bounds = cudem["bounds_wgs84"]
    assert bounds["min_lat"] == 17.75
    assert bounds["max_lat"] == 18.75
    assert bounds["min_lon"] == -68.0
    assert bounds["max_lon"] == -65.25
    assert bounds["min_lat"] < bounds["max_lat"]
    assert bounds["min_lon"] < bounds["max_lon"]

    # Registered from provider metadata; live raster QA still pending.
    assert cudem["validation"]["promotion_status"] == "source_metadata_registered"


def test_pr_wide_gap_mitigated_without_disturbing_snapshot_ledger() -> None:
    manifest = load_manifest()

    gaps = {gap["gap_id"]: gap for gap in manifest["gaps"]}
    gap_001 = gaps["NOAA_NCEI_DEM_GAP_001"]
    assert gap_001["status"] == "mitigated_2026-07-20"
    assert "puerto_rico_cudem_ninth_9525" in gap_001["mitigation"]

    # The CUDEM is a live-catalog addition beyond the uploaded snapshot, so the
    # snapshot-scoped ledger counts must stay untouched.
    coverage = manifest["catalog_coverage"]
    assert coverage["pr_relevant_rows_located"] == 8
    assert len(coverage["located_dataset_keys"]) == 8
    assert "puerto_rico_cudem_ninth_9525" not in coverage["located_dataset_keys"]
    additions = {item["dataset_key"] for item in coverage["live_catalog_additions"]}
    assert "puerto_rico_cudem_ninth_9525" in additions


def test_repo_policy_blocks_raster_artifacts() -> None:
    manifest = load_manifest()
    blocked = set(manifest["repo_policy"]["do_not_commit"])
    assert "*.nc" in blocked
    assert "*.tif" in blocked
    assert "*.tiff" in blocked
    assert "tile_cache/" in blocked
    assert "outputs/" in blocked
    assert "cache/" in blocked


def test_catalog_coverage_ledger_present() -> None:
    manifest = load_manifest()
    coverage = manifest["catalog_coverage"]
    assert coverage["snapshot_rows_reviewed"] == 150
    assert coverage["pr_relevant_rows_located"] == 8
    assert coverage["coverage_percent_against_uploaded_snapshot"] == 100
    assert coverage["coverage_percent_against_live_ncei_catalog"] is None


def test_script_imports_and_metadata_only_report() -> None:
    spec = importlib.util.spec_from_file_location("noaa_ncei_opendap", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    report = module.build_report(
        module.parse_args(
            [
                "--manifest",
                str(MANIFEST_PATH),
                "--dataset",
                "san_juan_19_prvd02_2015",
                "--metadata-only",
            ]
        )
    )

    assert report["manifest_validation"]["status"] == "ok"
    assert report["dataset_validation"]["dataset_key"] == "san_juan_19_prvd02_2015"
    assert report["dataset_validation"]["promotion_status"] == "source_raster_validated"

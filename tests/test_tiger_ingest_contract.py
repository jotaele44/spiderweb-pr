"""
test_tiger_ingest_contract.py — Contract tests for the TIGER ingest pipeline.

Three tiers:
  - Unit       (no marker): in-memory, no fixtures from disk, no network.
  - Smoke      (@pytest.mark.smoke): reads artifacts produced by a prior
                ingest run (data/*.geojson, manifest.json). Skips cleanly
                if those don't exist.
  - Integration (@pytest.mark.integration): exercises the live Census
                download path. Excluded from default pytest runs (see
                pyproject.toml addopts). Run explicitly with:
                    pytest -m integration

Default CI runs `pytest` and never touches Census servers.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
INGEST_DIR = REPO_ROOT / "server" / "ingestion"

# Add server/ingestion to sys.path so we can import migrations + the script.
sys.path.insert(0, str(INGEST_DIR))


# ── migrations.ensure_sites_geoid_columns ────────────────────────────────────

def test_ensure_sites_geoid_columns_is_idempotent(tmp_path):
    """Run the migration twice; second call must be a no-op."""
    from migrations import ensure_sites_geoid_columns

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE sites ("
        " id TEXT PRIMARY KEY, name TEXT, lat REAL, lng REAL)"
    )

    first = ensure_sites_geoid_columns(conn)
    assert first == {
        "municipio_geoid": True, "tract_geoid": True, "zcta_geoid": True
    }

    second = ensure_sites_geoid_columns(conn)
    assert second == {
        "municipio_geoid": False, "tract_geoid": False, "zcta_geoid": False
    }

    # Verify the columns actually exist after migration.
    cols = {r[1] for r in conn.execute("PRAGMA table_info(sites)")}
    assert "municipio_geoid" in cols
    assert "tract_geoid" in cols
    assert "zcta_geoid" in cols

    conn.close()


def test_ensure_sites_geoid_columns_handles_fresh_db(tmp_path):
    """Empty DB (no sites table yet) must not error."""
    from migrations import ensure_sites_geoid_columns

    db_path = tmp_path / "empty.db"
    conn = sqlite3.connect(db_path)
    result = ensure_sites_geoid_columns(conn)
    assert result == {
        "municipio_geoid": False, "tract_geoid": False, "zcta_geoid": False
    }
    conn.close()


# ── manifest shape ───────────────────────────────────────────────────────────

EXPECTED_INGEST_LAYERS = {
    "state", "municipios", "barrios", "tracts",
    "block_groups", "places", "zctas",
}


MIN_INGESTOR_VERSION = "1.1.0"


@pytest.mark.smoke
def test_manifest_includes_all_layers():
    """If the ingest has been run AT this contract version or newer, the
    2025 manifest must list all wired layers with both source AND output
    provenance (sha256 + bytes + feature_count). Older manifests skip — the
    ingestor needs to be re-run to pick up the new layers."""
    manifest_path = REPO_ROOT / "data" / "tiger" / "2025" / "manifest.json"
    if not manifest_path.exists():
        pytest.skip(
            "manifest.json not present — run "
            "`python server/ingestion/ingest_tiger_pr.py` first."
        )
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("ingestor_version", "0.0.0") < MIN_INGESTOR_VERSION:
        pytest.skip(
            f"manifest from older ingestor ({manifest.get('ingestor_version')}); "
            f"re-run ingest_tiger_pr.py to pick up state/block_groups/zctas."
        )
    assert manifest["ingestor"] == "ingest_tiger_pr.py"
    assert manifest["year"] == 2025
    layers = {e["layer"] for e in manifest["layers"]}
    assert layers == EXPECTED_INGEST_LAYERS
    # Each entry has provenance for both the input zip and the output GeoJSON.
    for entry in manifest["layers"]:
        src = entry["source"]
        out = entry["output"]
        assert len(src["sha256"]) == 64 and src["bytes"] > 0
        assert len(out["sha256"]) == 64 and out["bytes"] > 0
        assert out["feature_count"] > 0
        assert "oversized_warning" in out  # explicit flag for frontend


# ── LAYER_SPECS shape ───────────────────────────────────────────────────────

def test_layer_specs_covers_all_wired_layers():
    """The frontend POLYGON_LAYERS and backend allowlist both expect these
    layer keys; LAYER_SPECS is the source of truth on the ingest side."""
    pytest.importorskip("geopandas")  # module import guard requires the dep
    from ingest_tiger_pr import LAYER_SPECS

    expected = {
        "state", "municipios", "barrios", "tracts",
        "block_groups", "places", "zctas",
    }
    assert set(LAYER_SPECS.keys()) == expected

    # Every spec carries the contract fields the pipeline relies on.
    required = {
        "archive_template", "expected_min", "expected_max",
        "simplify_tolerance_initial", "max_bytes", "on_oversize",
        "filter_statefp",
    }
    for name, spec in LAYER_SPECS.items():
        missing = required - spec.keys()
        assert not missing, f"{name}: missing required fields {missing}"
        assert spec["on_oversize"] in {"abort", "warn_continue"}, name


def test_zcta_layer_spec_uses_pr_prefix_filter():
    """The nationwide ZCTA file has no STATEFP column, so the zctas layer
    must opt into the prefix-based filter explicitly."""
    pytest.importorskip("geopandas")
    from ingest_tiger_pr import LAYER_SPECS

    spec = LAYER_SPECS["zctas"]
    assert spec["filter_statefp"] is False
    assert spec.get("filter_zcta_pr") is True


# ── ZCTA prefix filter ──────────────────────────────────────────────────────

def test_zcta_prefix_filter_against_in_memory_gdf(monkeypatch, tmp_path):
    """Exercise the actual filter path in _read_layer with an in-memory
    GeoDataFrame containing PR (006/007/009), USVI (008), and mainland ZCTAs.

    Verifies that:
      - USVI rows are dropped (the bug we explicitly guard against)
      - PR + mainland 006xx ZCTAs are kept
      - GEOID20 / ZCTA5CE20 are renamed to GEOID / NAME for downstream use

    Bypasses zip I/O by monkeypatching gpd.read_file in the ingest module."""
    pytest.importorskip("geopandas")
    import geopandas as gpd
    from shapely.geometry import Polygon
    import ingest_tiger_pr as ingest

    rows = [
        {"GEOID20": "00601", "ZCTA5CE20": "00601",  # PR (Adjuntas)
         "ALAND20": 1, "AWATER20": 0,
         "INTPTLAT20": "18.18", "INTPTLON20": "-66.72"},
        {"GEOID20": "00802", "ZCTA5CE20": "00802",  # USVI — must drop
         "ALAND20": 1, "AWATER20": 0,
         "INTPTLAT20": "18.34", "INTPTLON20": "-64.93"},
        {"GEOID20": "00820", "ZCTA5CE20": "00820",  # USVI — must drop
         "ALAND20": 1, "AWATER20": 0,
         "INTPTLAT20": "17.74", "INTPTLON20": "-64.70"},
        {"GEOID20": "00901", "ZCTA5CE20": "00901",  # PR (San Juan)
         "ALAND20": 1, "AWATER20": 0,
         "INTPTLAT20": "18.46", "INTPTLON20": "-66.10"},
    ]
    geoms = [Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]) for _ in rows]
    sample = gpd.GeoDataFrame(rows, geometry=geoms, crs=4326)

    def fake_read_file(_path, engine=None):
        return sample.copy()

    monkeypatch.setattr(ingest.gpd, "read_file", fake_read_file)
    out = ingest._read_layer(
        tmp_path / "ignored.zip",
        filter_statefp=False,
        filter_zcta_pr=True,
    )

    # USVI dropped, PR kept.
    keep_codes = set(out["NAME"].tolist())
    assert keep_codes == {"00601", "00901"}, f"unexpected keep set: {keep_codes}"

    # Column rename applied — GEOID present, GEOID20 gone.
    assert "GEOID" in out.columns
    assert "GEOID20" not in out.columns
    assert "ALAND" in out.columns and "AWATER" in out.columns
    assert "INTPTLAT" in out.columns and "INTPTLON" in out.columns


def test_zcta_prefix_constants_exclude_usvi():
    """Cheap sanity check on the prefix tuple itself — guards against a
    typo-level regression where someone "extends" the tuple to include 008."""
    pytest.importorskip("geopandas")
    from ingest_tiger_pr import PR_ZCTA_PREFIXES

    assert "008" not in PR_ZCTA_PREFIXES, "USVI prefix must not be present"
    assert set(PR_ZCTA_PREFIXES) == {"006", "007", "009"}


# ── coordinate-order validator ──────────────────────────────────────────────

def test_coord_validator_rejects_swapped_lat_lng(tmp_path):
    """A site row with lat/lng swapped (i.e. positive lng > 0) must be skipped."""
    pytest.importorskip("geopandas")  # heavy dep; only required if installed

    from ingest_tiger_pr import _load_site_points

    db_path = tmp_path / "swap.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE sites ("
        " id TEXT PRIMARY KEY, name TEXT, lat REAL, lng REAL,"
        " municipio_geoid TEXT, tract_geoid TEXT)"
    )
    conn.executemany(
        "INSERT INTO sites (id, name, lat, lng) VALUES (?,?,?,?)",
        [
            ("ok-1", "valid PR point", 18.4, -66.0),
            ("swapped", "lat/lng swapped", -66.0, 18.4),  # positive lng → invalid
            ("ocean", "way off coast", 40.0, -100.0),
            ("nullc", "missing coords", None, None),
        ],
    )
    conn.commit()

    sites_gdf, skipped = _load_site_points(conn)
    conn.close()

    assert len(sites_gdf) == 1
    assert sites_gdf.iloc[0]["id"] == "ok-1"

    skipped_ids = {s["id"] for s in skipped}
    assert skipped_ids == {"swapped", "ocean", "nullc"}
    reasons = {s["reason"] for s in skipped}
    assert "missing_lat_lng" in reasons
    # The swapped row + the ocean row both fail bbox check on lat or lng.
    assert any("bbox" in r for r in reasons)


# ── size-budget gate ────────────────────────────────────────────────────────

def test_size_budget_gate_trips_when_payload_exceeds_max(monkeypatch):
    """Force a tiny --max-bytes; with on_oversize='abort' the serializer
    must raise."""
    pytest.importorskip("geopandas")

    import geopandas as gpd
    from shapely.geometry import Polygon

    import ingest_tiger_pr as ingest

    gdf = gpd.GeoDataFrame(
        {"GEOID": ["72001"], "NAME": ["Test"]},
        geometry=[Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])],
        crs=4326,
    )

    monkeypatch.setitem(ingest.LAYER_SPECS["municipios"], "max_bytes", 100)
    monkeypatch.setitem(
        ingest.LAYER_SPECS["municipios"], "simplify_tolerance_initial", 0.0005
    )
    monkeypatch.setitem(
        ingest.LAYER_SPECS["municipios"], "on_oversize", "abort"
    )

    with pytest.raises(RuntimeError, match="GeoJSON still"):
        ingest._serialize_with_size_check(gdf, "municipios")


def test_size_budget_warn_continue_returns_oversized_flag(monkeypatch):
    """With on_oversize='warn_continue', the serializer must return the
    payload anyway with oversized=True so callers can flag the manifest."""
    pytest.importorskip("geopandas")

    import geopandas as gpd
    from shapely.geometry import Polygon

    import ingest_tiger_pr as ingest

    gdf = gpd.GeoDataFrame(
        {"GEOID": ["72001"], "NAME": ["Test"]},
        geometry=[Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])],
        crs=4326,
    )

    monkeypatch.setitem(ingest.LAYER_SPECS["tracts"], "max_bytes", 100)
    monkeypatch.setitem(
        ingest.LAYER_SPECS["tracts"], "simplify_tolerance_initial", 0.0005
    )
    monkeypatch.setitem(
        ingest.LAYER_SPECS["tracts"], "on_oversize", "warn_continue"
    )

    payload, tol, oversized = ingest._serialize_with_size_check(gdf, "tracts")
    assert oversized is True
    assert payload  # non-empty
    assert tol > 0


# ── integration: live Census download (opt-in only) ─────────────────────────

@pytest.mark.integration
def test_dry_run_against_live_census(tmp_path):
    """Run `ingest_tiger_pr.py --dry-run` end-to-end against Census servers.

    Validates the script's CLI surface, retry behavior, count assertions, and
    serialization budget gate without mutating any committed state. Skipped
    by default; run explicitly with:  pytest -m integration
    """
    pytest.importorskip("geopandas")
    pytest.importorskip("requests")

    # Allow override of which TIGER vintage to hit (defaults to current).
    year = os.environ.get("PRIIS_TIGER_TEST_YEAR", "2025")

    script = INGEST_DIR / "ingest_tiger_pr.py"
    cmd = [
        sys.executable, str(script),
        "--year", year,
        "--dry-run",
        "--cache-dir", str(tmp_path / "tiger-cache"),
        "--data-dir", str(tmp_path / "geojson-out"),
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        pytest.fail(
            f"ingest dry-run failed (exit {result.returncode}):\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )

    # Script prints one indented JSON object to stdout; logs go to stderr.
    summary = json.loads(result.stdout)
    assert summary["dry_run"] is True
    assert set(summary["layers_written"]) == EXPECTED_INGEST_LAYERS
    assert summary["sites_municipio_matched"] >= 0
    assert summary["sites_tract_matched"] >= 0
    assert summary["sites_zcta_matched"] >= 0

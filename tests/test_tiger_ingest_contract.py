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
    assert first == {"municipio_geoid": True, "tract_geoid": True}

    second = ensure_sites_geoid_columns(conn)
    assert second == {"municipio_geoid": False, "tract_geoid": False}

    # Verify the columns actually exist after migration.
    cols = {r[1] for r in conn.execute("PRAGMA table_info(sites)")}
    assert "municipio_geoid" in cols
    assert "tract_geoid" in cols

    conn.close()


def test_ensure_sites_geoid_columns_handles_fresh_db(tmp_path):
    """Empty DB (no sites table yet) must not error."""
    from migrations import ensure_sites_geoid_columns

    db_path = tmp_path / "empty.db"
    conn = sqlite3.connect(db_path)
    result = ensure_sites_geoid_columns(conn)
    assert result == {"municipio_geoid": False, "tract_geoid": False}
    conn.close()


# ── manifest shape ───────────────────────────────────────────────────────────

@pytest.mark.smoke
def test_manifest_includes_all_four_layers():
    """If the ingest has been run, the 2025 manifest must list all 4 layers
    with both source AND output provenance (sha256 + bytes + feature_count)."""
    manifest_path = REPO_ROOT / "data" / "tiger" / "2025" / "manifest.json"
    if not manifest_path.exists():
        pytest.skip(
            "manifest.json not present — run "
            "`python server/ingestion/ingest_tiger_pr.py` first."
        )
    manifest = json.loads(manifest_path.read_text())
    assert manifest["ingestor"] == "ingest_tiger_pr.py"
    assert manifest["year"] == 2025
    layers = {e["layer"] for e in manifest["layers"]}
    assert layers == {"municipios", "tracts", "places", "barrios"}
    # Each entry has provenance for both the input zip and the output GeoJSON.
    for entry in manifest["layers"]:
        src = entry["source"]
        out = entry["output"]
        assert len(src["sha256"]) == 64 and src["bytes"] > 0
        assert len(out["sha256"]) == 64 and out["bytes"] > 0
        assert out["feature_count"] > 0
        assert "oversized_warning" in out  # explicit flag for frontend


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
    assert set(summary["layers_written"]) == {
        "municipios", "tracts", "places", "barrios"
    }
    assert summary["sites_municipio_matched"] >= 0
    assert summary["sites_tract_matched"] >= 0

"""Tests for ILAP and AASB bridge file outputs (5 bridge files)."""

import csv
import json
from pathlib import Path

import pytest

from integration.aasb_airspace_bridge import AASBAirspaceBridge
from integration.ilap_airspace_bridge import ILAPAirspaceBridge, infra_alignment_score


def test_ilap_creates_three_geojson_files(populated_db, tmp_output):
    bridge = ILAPAirspaceBridge(populated_db, str(tmp_output))
    bridge.export_all()

    expected = [
        "airspace_pin_candidates.geojson",
        "airspace_ilap_candidates.geojson",
        "airspace_corridor_candidates.geojson",
    ]
    for fname in expected:
        assert (tmp_output / fname).exists(), f"Missing: {fname}"


def test_ilap_geojson_are_valid(populated_db, tmp_output):
    ILAPAirspaceBridge(populated_db, str(tmp_output)).export_all()
    for fname in [
        "airspace_pin_candidates.geojson",
        "airspace_ilap_candidates.geojson",
        "airspace_corridor_candidates.geojson",
    ]:
        data = json.loads((tmp_output / fname).read_text())
        assert data["type"] == "FeatureCollection"
        assert "features" in data
        assert "4326" in data.get("crs", {}).get("properties", {}).get("name", "")


def test_aasb_creates_edge_csv(populated_db, tmp_output):
    AASBAirspaceBridge(populated_db, str(tmp_output)).export_all()
    edge_path = tmp_output / "aasb_airspace_edges.csv"
    assert edge_path.exists()


def test_aasb_edge_csv_has_correct_columns(populated_db, tmp_output):
    AASBAirspaceBridge(populated_db, str(tmp_output)).export_all()
    with open(tmp_output / "aasb_airspace_edges.csv", newline="") as f:
        reader = csv.DictReader(f)
        expected_cols = {
            "edge_id", "from_node", "to_node",
            "from_lat", "from_lon", "to_lat", "to_lon",
            "weight", "flight_count", "avg_duration_min",
            "dominant_callsign", "confidence_score",
            "aasb_mbil_corridor_flag",
        }
        assert set(reader.fieldnames) == expected_cols


def test_aasb_corridor_flag_is_boolean_string(populated_db, tmp_output):
    """aasb_mbil_corridor_flag must be a CSV boolean ('True' or 'False')."""
    AASBAirspaceBridge(populated_db, str(tmp_output)).export_all()
    with open(tmp_output / "aasb_airspace_edges.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        assert row["aasb_mbil_corridor_flag"] in ("True", "False"), (
            f"unexpected flag value: {row['aasb_mbil_corridor_flag']!r}"
        )


def test_aasb_creates_manifest(populated_db, tmp_output):
    AASBAirspaceBridge(populated_db, str(tmp_output)).export_all()
    manifest_path = tmp_output / "spiderweb_ingest_manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert "generated_at" in manifest
    assert "files" in manifest
    assert manifest["schema_version"] == "1.0"


def test_ilap_identity_note_in_poi_properties(populated_db, tmp_output):
    ILAPAirspaceBridge(populated_db, str(tmp_output)).export_all()
    data = json.loads((tmp_output / "airspace_pin_candidates.geojson").read_text())
    for feature in data.get("features", []):
        note = feature["properties"].get("identity_note", "")
        assert "not standalone evidence" in note


def test_combined_export_produces_five_bridge_files(populated_db, tmp_output):
    ILAPAirspaceBridge(populated_db, str(tmp_output)).export_all()
    AASBAirspaceBridge(populated_db, str(tmp_output)).export_all()

    bridge_files = [
        "airspace_pin_candidates.geojson",
        "airspace_ilap_candidates.geojson",
        "airspace_corridor_candidates.geojson",
        "aasb_airspace_edges.csv",
        "spiderweb_ingest_manifest.json",
    ]
    for fname in bridge_files:
        assert (tmp_output / fname).exists(), f"Missing bridge file: {fname}"


# ── T3-26 MBIL in producer outputs ───────────────────────────────────────────

def test_ilap_poi_candidates_have_mbil_class(populated_db, tmp_output):
    """Every POI candidate GeoJSON feature must carry a valid mbil_class (T3-26)."""
    ILAPAirspaceBridge(populated_db, str(tmp_output)).export_all()
    data = json.loads((tmp_output / "airspace_pin_candidates.geojson").read_text())
    valid_classes = {"MBIL-0", "MBIL-1", "MBIL-2", "MBIL-3", "MBIL-X"}
    for feat in data.get("features", []):
        cls = feat["properties"].get("mbil_class")
        assert cls in valid_classes, f"mbil_class missing or invalid: {cls!r}"


def test_ilap_corridor_candidates_have_mbil_class(populated_db, tmp_output):
    """Corridor candidates must carry mbil_class based on corridor midpoint (T3-26)."""
    ILAPAirspaceBridge(populated_db, str(tmp_output)).export_all()
    data = json.loads((tmp_output / "airspace_corridor_candidates.geojson").read_text())
    valid_classes = {"MBIL-0", "MBIL-1", "MBIL-2", "MBIL-3", "MBIL-X"}
    for feat in data.get("features", []):
        cls = feat["properties"].get("mbil_class")
        assert cls in valid_classes, f"corridor mbil_class missing or invalid: {cls!r}"


# ── T3-30 Terrain hook unit tests ────────────────────────────────────────────

def test_terrain_hook_urban_sju():
    from pipeline.terrain_hook import get_terrain_context
    assert get_terrain_context(18.43, -66.10) == "urban"


def test_terrain_hook_inland():
    from pipeline.terrain_hook import get_terrain_context
    assert get_terrain_context(18.28, -66.45) == "inland"


def test_terrain_hook_offshore():
    from pipeline.terrain_hook import get_terrain_context
    assert get_terrain_context(20.0, -66.0) == "offshore"  # lat outside PR band


def test_terrain_hook_coastal_west():
    from pipeline.terrain_hook import get_terrain_context
    assert get_terrain_context(18.49, -67.35) == "coastal"  # west of PR_LON_WEST


def test_terrain_hook_unknown_on_none():
    from pipeline.terrain_hook import get_terrain_context
    assert get_terrain_context(None, None) == "unknown"


# ── infra_alignment_score: geometry-derived directional-coherence proxy ───────
# Replaces the former hardcoded `infra_align = 0.3` placeholder. Pure logic —
# no DB, no network — so these pin the covariance-eigenvalue computation.

def _pts(coords):
    return [{"latitude": lat, "longitude": lon} for lat, lon in coords]


def test_infra_alignment_collinear_points_score_high():
    """A perfectly collinear cluster (points along one axis) → linearity 1.0."""
    pts = _pts([(18.40, -66.10), (18.42, -66.10), (18.44, -66.10), (18.46, -66.10)])
    assert infra_alignment_score(pts) == pytest.approx(1.0, abs=1e-9)


def test_infra_alignment_collinear_diagonal_scores_high():
    """Collinearity is orientation-independent (diagonal line also → 1.0)."""
    pts = _pts([(18.40, -66.10), (18.42, -66.12), (18.44, -66.14), (18.46, -66.16)])
    assert infra_alignment_score(pts) == pytest.approx(1.0, abs=1e-9)


def test_infra_alignment_isotropic_cluster_scores_low():
    """A symmetric square cloud is isotropic (lambda1 == lambda2) → ~0.0."""
    pts = _pts([(18.40, -66.10), (18.40, -66.12), (18.42, -66.10), (18.42, -66.12)])
    assert infra_alignment_score(pts) == pytest.approx(0.0, abs=1e-9)


def test_infra_alignment_elongated_between_the_extremes():
    """An elongated-but-not-collinear cloud lands strictly inside (0, 1)."""
    pts = _pts([(18.40, -66.10), (18.50, -66.105), (18.60, -66.10), (18.50, -66.095)])
    score = infra_alignment_score(pts)
    assert 0.0 < score < 1.0


def test_infra_alignment_returns_bounded_float():
    """Output is always a float clamped to [0, 1]."""
    for pts in (
        _pts([(18.40, -66.10), (18.42, -66.10), (18.44, -66.10)]),
        _pts([(18.40, -66.10), (18.40, -66.12), (18.42, -66.10), (18.42, -66.12)]),
    ):
        score = infra_alignment_score(pts)
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0


def test_infra_alignment_degenerate_inputs_return_zero():
    """Fewer than 2 usable points, or zero spread, yields 0.0 (no evidence)."""
    assert infra_alignment_score([]) == 0.0
    assert infra_alignment_score(_pts([(18.40, -66.10)])) == 0.0
    # Coincident points → zero spatial spread → 0.0
    assert infra_alignment_score(_pts([(18.40, -66.10), (18.40, -66.10)])) == 0.0
    # (0, 0) sentinels are filtered out as missing coordinates.
    assert infra_alignment_score(_pts([(0.0, 0.0), (0.0, 0.0)])) == 0.0


def test_infra_alignment_ignores_missing_coordinates():
    """None lat/lon rows are skipped; the remaining collinear pair scores 1.0."""
    pts = _pts([(18.40, -66.10), (18.44, -66.10)])
    pts.append({"latitude": None, "longitude": None})
    assert infra_alignment_score(pts) == pytest.approx(1.0, abs=1e-9)

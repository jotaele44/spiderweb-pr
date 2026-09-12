"""Federation spatial index: resolver, georeference certification, and gates.

The negative cases matter more than the positive ones here. A gate that cannot
be made to fail is decorative, so every gate is exercised against a deliberately
broken registry as well as the real one.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from federation import spatial_resolver as resolver
from pipeline import grid_georeference as georef
import scripts.validate_spatial_registry as gates

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFESTATIONS = json.loads(
    (REPO_ROOT / "registry/spatial/source_manifestations.json").read_text(encoding="utf-8")
)
TRANSFORM = json.loads(
    (REPO_ROOT / "registry/spatial/geometry/pr_grid_transform.json").read_text(encoding="utf-8")
)

# The Trujillo Alto golden fixture. These four zone-19 objects are the canonical
# D24 coverage of the AOI; the byte total is asserted exactly because a silent
# change in provider bytes must break the build, not the download.
TRUJILLO_ALTO_CANONICAL = {
    "USGS_1M_19_x81y203_PR_PuertoRicoUSVI_D24",
    "USGS_1M_19_x81y204_PR_PuertoRicoUSVI_D24",
    "USGS_1M_19_x82y203_PR_PuertoRicoUSVI_D24",
    "USGS_1M_19_x82y204_PR_PuertoRicoUSVI_D24",
}
TRUJILLO_ALTO_CANONICAL_BYTES = 1_648_841_112


# ---------------------------------------------------------------- cell identity


def test_cell_id_round_trips_across_the_whole_grid() -> None:
    for row, column in ((0, 0), (255, 383), (123, 217), (73, 203)):
        assert resolver.parse_cell_id(resolver.cell_id(row, column)) == (row, column)


@pytest.mark.parametrize(
    "value", ["R000_C000", "R01_C2", "R0_C0384", "RX_C1", "R256_C0", "R0_C384", "r0_c0", ""]
)
def test_non_canonical_cell_ids_are_rejected(value: str) -> None:
    """Two spellings of one address would silently split every cross-repo join."""
    with pytest.raises(resolver.SpatialResolverError):
        resolver.parse_cell_id(value)


def test_cell_set_content_address_is_order_and_duplicate_invariant() -> None:
    assert resolver.cell_set_sha256(["R2_C3", "R1_C1"]) == resolver.cell_set_sha256(
        ["R1_C1", "R2_C3", "R1_C1"]
    )


def test_cell_set_address_changes_when_membership_changes() -> None:
    assert resolver.cell_set_sha256(["R1_C1"]) != resolver.cell_set_sha256(["R1_C1", "R2_C3"])


# -------------------------------------------------------------------- resolver


def test_bbox_resolution_partitions_boundary_and_interior() -> None:
    transform = resolver.GridTransform.load()
    cell_set = resolver.resolve_bbox((-66.15, 18.40, -66.05, 18.48), transform)
    assert cell_set.member_count > 0
    assert cell_set.member_count == len(cell_set.boundary_cells) + len(cell_set.interior_cells)
    assert not set(cell_set.boundary_cells) & set(cell_set.interior_cells)


def test_resolver_results_carry_certification_state_and_identity_default() -> None:
    """A caller can never receive a coordinate answer without its provenance."""
    cell_set = resolver.resolve_point(-66.105, 18.466)
    assert cell_set.certification_state == TRANSFORM["certification_state"]
    assert cell_set.identity_default == "CANDIDATE_NOT_IDENTITY"


def test_point_outside_the_canvas_resolves_to_nothing_rather_than_clamping() -> None:
    assert resolver.resolve_point(-80.0, 40.0).member_count == 0


def test_degenerate_bbox_is_rejected() -> None:
    with pytest.raises(resolver.SpatialResolverError):
        resolver.resolve_bbox((-65.0, 18.5, -66.0, 18.0))


def test_polygon_resolution_is_contained_by_its_bounding_box() -> None:
    transform = resolver.GridTransform.load()
    polygon = {
        "type": "Polygon",
        "coordinates": [[[-66.15, 18.40], [-66.05, 18.40], [-66.05, 18.48], [-66.15, 18.48], [-66.15, 18.40]]],
    }
    inside = resolver.resolve_polygon(polygon, transform)
    envelope = resolver.resolve_bbox((-66.15, 18.40, -66.05, 18.48), transform)
    assert set(inside.cell_ids) <= set(envelope.cell_ids)


# ------------------------------------------------------- georeference certification


def test_documented_bounds_are_rejected_by_the_island_dimension_assertion() -> None:
    """Regression: the authored bounds squash the archipelago to half height.

    Applied to the 1536x1024 canvas they imply ~1.9x anisotropic pixels and a
    0.297 deg north-south island against a true ~0.633 deg. Aggregate residual
    alone understates this, because Puerto Rico's long east-west coasts stay near
    some reference point when compressed, so the dimension check is what catches it.
    """
    cells = georef.load_coastline_cells()
    reference = georef.load_reference_coast()
    documented = georef.PlateCarree.from_bounds(-67.30, 17.92, -65.20, 18.65)
    metrics = georef.evaluate(documented, cells, reference)
    state, failures = georef.certify(metrics, georef.PROVENANCE_SUPPLIED)

    assert state == georef.CERTIFICATION_PROVISIONAL
    assert metrics["lat_span_error"] > 0.5
    assert any("ISLAND_DIMENSION" in failure for failure in failures)


def test_a_fitted_transform_can_never_certify_itself() -> None:
    """Fitting to the cells then scoring against them is circular, not evidence."""
    metrics = dict(TRANSFORM["metrics"])
    state, failures = georef.certify(metrics, georef.PROVENANCE_FITTED)
    assert state == georef.CERTIFICATION_PROVISIONAL
    assert any("PROVENANCE" in failure for failure in failures)


def test_shipped_transform_is_provisional_and_says_why() -> None:
    assert TRANSFORM["certification_state"] == "PROVISIONAL"
    assert TRANSFORM["certification_failures"]
    assert TRANSFORM["documented_bounds"]["status"] == "DOCUMENTED_UNVERIFIED"


def test_transform_model_is_uniform_scale_as_authored() -> None:
    """The image was authored to scale on WGS84; the fit must not contradict that."""
    assert TRANSFORM["metrics"]["anisotropy"] == pytest.approx(1.0, abs=0.02)


# ------------------------------------------------- Trujillo Alto golden fixture


def test_trujillo_alto_resolves_to_four_unique_canonical_provider_objects() -> None:
    canonical = [
        m for m in MANIFESTATIONS["manifestations"] if m["Manifestation_Class"] == "CANONICAL"
    ]
    assert {m["Provider_Object_ID"] for m in canonical} == TRUJILLO_ALTO_CANONICAL
    assert len(canonical) == 4, "provider objects must be deduplicated, not repeated per cell"


def test_canonical_download_plan_byte_total_is_frozen() -> None:
    canonical = [
        m for m in MANIFESTATIONS["manifestations"] if m["Manifestation_Class"] == "CANONICAL"
    ]
    assert sum(m["Expected_Bytes"] for m in canonical) == TRUJILLO_ALTO_CANONICAL_BYTES


def test_zone_20_is_preserved_as_alternate_complete_never_merged() -> None:
    alternates = [
        m for m in MANIFESTATIONS["manifestations"] if m["Manifestation_Class"] == "ALTERNATE_COMPLETE"
    ]
    assert len(alternates) == 4
    assert {m["Provider_CRS"] for m in alternates} == {"EPSG:26920"}


def test_canonical_manifestations_share_one_projection() -> None:
    canonical = [
        m for m in MANIFESTATIONS["manifestations"] if m["Manifestation_Class"] == "CANONICAL"
    ]
    assert {m["Provider_CRS"] for m in canonical} == {"EPSG:26919"}


def test_footprints_come_from_provider_headers_not_filenames() -> None:
    for manifestation in MANIFESTATIONS["manifestations"]:
        if manifestation["Manifestation_Class"] in {"CANONICAL", "ALTERNATE_COMPLETE"}:
            assert manifestation["Footprint_Source"] == "PROVIDER_HEADER_RANGE_READ"
            west, south, east, north = manifestation["Footprint_BBox_Native"]
            assert east > west and north > south


def test_historical_manifestations_are_retained_not_discarded() -> None:
    historical = [
        m for m in MANIFESTATIONS["manifestations"] if m["Manifestation_Class"] == "HISTORICAL"
    ]
    assert historical, "superseded manifestations are evidence and must be preserved"


# ------------------------------------------------------------- gate discrimination


def _rewrite(monkeypatch, tmp_path: Path, attribute: str, payload: dict) -> None:
    path = tmp_path / f"{attribute.lower()}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(gates, attribute, path)


def test_all_gates_pass_on_the_committed_registries() -> None:
    assert gates.run() == 0


def test_transform_gate_rejects_a_promoted_binding_under_provisional(monkeypatch, tmp_path) -> None:
    _rewrite(
        monkeypatch,
        tmp_path,
        "BINDINGS",
        {
            "bindings": [
                {
                    "Cell_ID": "R123_C217",
                    "Capability": "DEM",
                    "Manifestation_ID": "x",
                    "Binding_State": "CANONICAL",
                    "Is_Default": True,
                }
            ]
        },
    )
    failures = gates.gate_transform_certification()
    assert any("PROVISIONAL" in failure for failure in failures)


def test_canonical_uniqueness_gate_rejects_two_defaults(monkeypatch, tmp_path) -> None:
    binding = {
        "Cell_ID": "R123_C217",
        "Capability": "DEM",
        "Binding_State": "UNVERIFIED",
        "Is_Default": True,
    }
    _rewrite(monkeypatch, tmp_path, "BINDINGS", {"bindings": [dict(binding), dict(binding)]})
    assert gates.gate_canonical_uniqueness()


def test_duplicate_provider_gate_rejects_a_repeated_object(monkeypatch, tmp_path) -> None:
    record = {
        "Manifestation_ID": "dupe",
        "Provider_Object_ID": "dupe",
        "Manifestation_Class": "CANONICAL",
        "Provider_CRS": "EPSG:26919",
        "Capability": "DEM",
    }
    _rewrite(
        monkeypatch,
        tmp_path,
        "MANIFESTATIONS",
        {"manifestation_count": 2, "manifestations": [dict(record), dict(record)]},
    )
    assert gates.gate_no_duplicate_provider()


def test_duplicate_provider_gate_rejects_canonical_crs_split(monkeypatch, tmp_path) -> None:
    """Two canonical projections for one dataset is the multi-zone failure."""
    _rewrite(
        monkeypatch,
        tmp_path,
        "MANIFESTATIONS",
        {
            "manifestation_count": 2,
            "manifestations": [
                {"Manifestation_ID": "a", "Provider_Object_ID": "a", "Manifestation_Class": "CANONICAL", "Provider_CRS": "EPSG:26919", "Capability": "DEM"},
                {"Manifestation_ID": "b", "Provider_Object_ID": "b", "Manifestation_Class": "CANONICAL", "Provider_CRS": "EPSG:26920", "Capability": "DEM"},
            ],
        },
    )
    assert any("multiple CRSs" in failure for failure in gates.gate_no_duplicate_provider())


def test_coverage_gate_rejects_a_fraction_above_one(monkeypatch, tmp_path) -> None:
    _rewrite(
        monkeypatch,
        tmp_path,
        "BINDINGS",
        {"bindings": [{"Cell_ID": "R1_C1", "Cell_Coverage_Fraction": 1.4}]},
    )
    assert gates.gate_coverage_arithmetic()


def test_capability_gate_rejects_an_undeclared_capability(monkeypatch, tmp_path) -> None:
    _rewrite(
        monkeypatch,
        tmp_path,
        "MANIFESTATIONS",
        {"manifestation_count": 1, "manifestations": [{"Manifestation_ID": "a", "Provider_Object_ID": "a", "Capability": "TELEPATHY", "Manifestation_Class": "CANONICAL"}]},
    )
    assert any("undeclared" in failure for failure in gates.gate_capability_policy())


def test_geometry_cardinality_gate_rejects_a_short_layer(monkeypatch, tmp_path) -> None:
    _rewrite(
        monkeypatch,
        tmp_path,
        "GEOMETRY_MANIFEST",
        {
            "cell_count": 98_303,
            "duplicate_cell_ids": 0,
            "orphan_geometries": 0,
            "missing_geometries": 0,
            "sha256": "0" * 64,
        },
    )
    assert any("98303" in failure for failure in gates.gate_geometry_cardinality())


def test_gates_fail_closed_when_a_registry_is_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(gates, "BINDINGS", tmp_path / "absent.json")
    assert gates.run(["TRANSFORM_CERTIFICATION_GATE"]) == 1

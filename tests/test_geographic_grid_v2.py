"""Native certification gates for PR_GRID_GEOGRAPHIC_V2 RC1."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from spiderweb.geographic_grid_v2 import (
    CRS,
    EXTENT_X_MAX,
    EXTENT_X_MIN,
    EXTENT_Y_MAX,
    EXTENT_Y_MIN,
    GRID_ID,
    GRID_VERSION,
    LEVEL_ORDER,
    LEVELS,
    BoundaryState,
    Cell,
    GridV2Error,
    NullState,
    assert_compatibility,
    bind_point,
    children,
    expected_full_counts,
    iter_cells,
    make_cell_id,
    manifest_sha256,
    neighbors,
    parent,
    parse_cell_id,
    validate_crs,
    validate_null_state,
)

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "registry/spatial/v2/pr_grid_geographic_v2.manifest.json"
SOURCE = REPO / "registry/spatial/v2/pr_grid_geographic_v2.source.json"
CELL_SCHEMA = REPO / "schemas/pr_grid_geographic_v2_cell.schema.json"
BINDING_SCHEMA = REPO / "schemas/pr_grid_geographic_v2_binding.schema.json"
MASK_SCHEMA = REPO / "schemas/pr_grid_geographic_v2_mask.schema.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_exact_full_domain_cardinality():
    assert expected_full_counts() == {
        "L0": 11_457,
        "L1": 45_828,
        "L2": 183_312,
        "L3": 733_248,
    }
    for level in LEVEL_ORDER:
        assert sum(1 for _ in iter_cells(level)) == LEVELS[level].cell_count


@pytest.mark.parametrize("level", LEVEL_ORDER)
def test_full_domain_cell_ids_are_unique_and_roundtrip(level):
    seen = set()
    for cell in iter_cells(level):
        identifier = cell.cell_id
        assert identifier not in seen
        seen.add(identifier)
        assert parse_cell_id(identifier) == cell
    assert len(seen) == LEVELS[level].cell_count


@pytest.mark.parametrize("level", LEVEL_ORDER)
def test_full_domain_cells_are_exact_square_partition(level):
    spec = LEVELS[level]
    total_area = 0
    for cell in iter_cells(level):
        xmin, ymin, xmax, ymax = cell.bounds
        assert xmax - xmin == spec.resolution_m
        assert ymax - ymin == spec.resolution_m
        assert cell.area_m2 == spec.resolution_m**2
        assert xmin == EXTENT_X_MIN + cell.column * spec.resolution_m
        assert ymin == EXTENT_Y_MIN + cell.row * spec.resolution_m
        total_area += cell.area_m2
    assert total_area == (
        (EXTENT_X_MAX - EXTENT_X_MIN) * (EXTENT_Y_MAX - EXTENT_Y_MIN)
    )


@pytest.mark.parametrize("parent_level", LEVEL_ORDER[:-1])
def test_exact_parent_child_closure(parent_level):
    for p in iter_cells(parent_level):
        cs = children(p)
        assert len(cs) == 4
        assert all(parent(child) == p for child in cs)
        assert sum(child.area_m2 for child in cs) == p.area_m2

        px0, py0, px1, py1 = p.bounds
        child_bounds = [child.bounds for child in cs]
        assert min(b[0] for b in child_bounds) == px0
        assert min(b[1] for b in child_bounds) == py0
        assert max(b[2] for b in child_bounds) == px1
        assert max(b[3] for b in child_bounds) == py1


def test_interior_neighbor_arithmetic():
    cell = Cell("L1", 75, 234)
    assert {n.cell_id for n in neighbors(cell)} == {
        make_cell_id("L1", 75, 233),
        make_cell_id("L1", 75, 235),
        make_cell_id("L1", 74, 234),
        make_cell_id("L1", 76, 234),
    }


def test_boundary_semantics_are_exact_in_native_projected_coordinates():
    interior = bind_point(246_500, 255_500, level="L1", crs=CRS)
    assert interior.state is BoundaryState.INTERIOR
    assert interior.cell_ids == (make_cell_id("L1", 75, 234),)

    edge = bind_point(247_000, 255_500, level="L1", crs=CRS)
    assert edge.state is BoundaryState.EDGE_SHARED
    assert edge.cell_ids == (
        make_cell_id("L1", 75, 234),
        make_cell_id("L1", 75, 235),
    )

    corner = bind_point(247_000, 256_000, level="L1", crs=CRS)
    assert corner.state is BoundaryState.CORNER_SHARED
    assert corner.cell_ids == (
        make_cell_id("L1", 75, 234),
        make_cell_id("L1", 75, 235),
        make_cell_id("L1", 76, 234),
        make_cell_id("L1", 76, 235),
    )


@pytest.mark.parametrize("crs", [None, "", "EPSG:4326", "EPSG:26919"])
def test_wrong_or_missing_crs_fails_closed(crs):
    with pytest.raises(GridV2Error):
        validate_crs(crs)


def test_wrong_grid_version_and_hash_fail_closed():
    with pytest.raises(GridV2Error):
        assert_compatibility(
            grid_id=GRID_ID,
            grid_version="1.0.0",
            grid_manifest_sha256="a" * 64,
            expected_manifest_sha256="a" * 64,
        )
    with pytest.raises(GridV2Error):
        assert_compatibility(
            grid_id=GRID_ID,
            grid_version=GRID_VERSION,
            grid_manifest_sha256="a" * 64,
            expected_manifest_sha256="b" * 64,
        )


def test_null_states_are_distinct_and_unknown_values_fail():
    assert NullState.NO_DATA != NullState.ZERO_RECORDS
    assert validate_null_state("NO_DATA") is NullState.NO_DATA
    assert validate_null_state("ZERO_RECORDS") is NullState.ZERO_RECORDS
    with pytest.raises(GridV2Error):
        validate_null_state("")


def test_manifest_hash_and_schema_pins_are_self_consistent():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["Grid_ID"] == GRID_ID
    assert manifest["Grid_Version"] == GRID_VERSION
    assert manifest["CRS"] == CRS
    assert manifest["Source_Manifest_SHA256"] == _sha(SOURCE)
    assert manifest["Cell_Schema_SHA256"] == _sha(CELL_SCHEMA)
    assert manifest["Binding_Schema_SHA256"] == _sha(BINDING_SCHEMA)
    assert manifest["Mask_Schema_SHA256"] == _sha(MASK_SCHEMA)
    assert manifest["Grid_Manifest_SHA256"] == manifest_sha256(manifest)

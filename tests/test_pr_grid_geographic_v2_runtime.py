"""Certification tests for the shared PR Grid V2 runtime contract."""

from __future__ import annotations

import copy

import pytest

from federation.spatial.pr_grid_geographic_v2_runtime import (
    AUTHORITY_COMMIT,
    BINDING_SCHEMA_SHA256,
    CELL_SCHEMA_SHA256,
    CRS,
    GRID_ID,
    GRID_MANIFEST_SHA256,
    GRID_VERSION,
    MASK_SCHEMA_SHA256,
    GridV2RuntimeError,
    attach_runtime_identity,
    build_grid_deep_link,
    load_pin,
    runtime_identity,
    validate_cell_id,
    validate_level,
    validate_pin,
)

PIN = {
    "schema_version": "pr_grid_geographic_v2_consumer_pin/1.0",
    "consumer": "runtime-contract-fixture",
    "geometry_authority": "spiderweb-pr",
    "authority_repository": "jotaele44/spiderweb-pr",
    "authority_commit": AUTHORITY_COMMIT,
    "authority_manifest_path": "registry/spatial/v2/pr_grid_geographic_v2.manifest.json",
    "grid_id": GRID_ID,
    "grid_version": GRID_VERSION,
    "crs": CRS,
    "grid_manifest_sha256": GRID_MANIFEST_SHA256,
    "cell_schema_sha256": CELL_SCHEMA_SHA256,
    "binding_schema_sha256": BINDING_SCHEMA_SHA256,
    "binding_schema_version": "pr-grid-v2-binding/1.0",
    "mask_schema_sha256": MASK_SCHEMA_SHA256,
    "mask_schema_version": "pr-grid-v2-mask/1.0",
    "default_level": "L1",
    "allowed_levels": ["L0", "L1", "L2", "L3"],
    "geometry_mode": "REFERENCE_ONLY",
    "local_geometry_copy": False,
    "v1_coexistence": "PRESERVE_UNCHANGED",
    "compatibility_policy": "FAIL_CLOSED",
    "external_provider_blockers": [
        {"id": "QA-D24-001", "affects_grid_identity": False},
        {"id": "QA-D24-003", "affects_grid_identity": False},
    ],
}


def test_authority_pin_is_runtime_valid():
    validate_pin(PIN)


@pytest.mark.parametrize(
    ("key", "bad"),
    [
        ("authority_commit", "0" * 40),
        ("grid_id", "PR_GRID_LOGICAL_V1"),
        ("grid_version", "2.0.0"),
        ("crs", "EPSG:4326"),
        ("grid_manifest_sha256", "0" * 64),
        ("cell_schema_sha256", "0" * 64),
        ("binding_schema_sha256", "0" * 64),
        ("mask_schema_sha256", "0" * 64),
        ("geometry_mode", "LOCAL_COPY"),
        ("local_geometry_copy", True),
        ("v1_coexistence", "REPLACED"),
        ("compatibility_policy", "BEST_EFFORT"),
    ],
)
def test_pin_mismatch_fails_closed(key, bad):
    candidate = copy.deepcopy(PIN)
    candidate[key] = bad
    with pytest.raises(GridV2RuntimeError):
        validate_pin(candidate)


def test_wrong_or_missing_levels_fail_closed():
    for level in ("", "L4", "l1", None):
        with pytest.raises(GridV2RuntimeError):
            validate_level(PIN, level)  # type: ignore[arg-type]


def test_cell_id_level_identity_is_fail_closed():
    valid = "PRG2:L1:R075:C0234"
    assert validate_cell_id(PIN, valid, level="L1") == valid
    for bad in (
        "R75_C234",
        "PRG2:L1:R75:C234",
        "PRG2:L2:R075:C0234",
        "PRG2:L4:R075:C0234",
    ):
        with pytest.raises(GridV2RuntimeError):
            validate_cell_id(PIN, bad, level="L1")


def test_runtime_identity_is_complete_and_hash_bound():
    identity = runtime_identity(PIN, level="L1", cell_id="PRG2:L1:R075:C0234")
    assert identity == {
        "Grid_ID": GRID_ID,
        "Grid_Version": GRID_VERSION,
        "Grid_Level": "L1",
        "Cell_ID": "PRG2:L1:R075:C0234",
        "CRS": CRS,
        "Grid_Manifest_SHA256": GRID_MANIFEST_SHA256,
        "Cell_Schema_SHA256": CELL_SCHEMA_SHA256,
        "Binding_Schema_SHA256": BINDING_SCHEMA_SHA256,
        "Mask_Schema_SHA256": MASK_SCHEMA_SHA256,
        "Geometry_Authority": "spiderweb-pr",
    }


def test_attach_runtime_identity_preserves_payload():
    payload = {"Record_Count": 0, "Data_State": "ZERO_RECORDS"}
    out = attach_runtime_identity(
        payload,
        PIN,
        level="L1",
        cell_id="PRG2:L1:R075:C0234",
    )
    assert out["Record_Count"] == 0
    assert out["Data_State"] == "ZERO_RECORDS"
    assert out["Grid_Identity"]["Grid_ID"] == GRID_ID


def test_deep_link_contract():
    assert build_grid_deep_link(
        PIN,
        level="L1",
        cell_id="PRG2:L1:R075:C0234",
    ) == (
        "/grid/PR_GRID_GEOGRAPHIC_V2/2.0.0-rc1/"
        "L1/PRG2:L1:R075:C0234"
    )
    assert build_grid_deep_link(
        PIN,
        level="L1",
        cell_id="PRG2:L1:R075:C0234",
        base_path="/hub",
        as_of="2026-10-09T00:00:00Z",
    ).endswith("?as_of=2026-10-09T00:00:00Z")


def test_runtime_constants_remain_bound_to_merged_authority():
    assert AUTHORITY_COMMIT == "0c66e13d14232c0d7cbcbc179b3655904777dc71"


def test_load_pin_fails_closed(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("[]", encoding="utf-8")
    with pytest.raises(GridV2RuntimeError):
        load_pin(bad)

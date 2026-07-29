"""Gate: the spatial boundary and layer-binding registries stay honest.

configs/spatial_boundaries.yaml and configs/spatial_layer_bindings.yaml carry the
rendering/spatial metadata that configs/layer_catalog.yaml deliberately excludes
(see tests/test_layer_catalog.py::test_catalog_is_labels_only). These tests pin:

  - structure validates against their JSON Schemas when jsonschema is installed,
  - every layer_id in the binding registry exists in the labels catalog (no orphans),
  - a boundary marked unresolved never carries fabricated geometry,
  - the context-buffer policy's min/default/max are internally consistent,
  - the additive /spatial/* endpoints serve these registries without disturbing
    /geo/{layer}.geojson or /catalog.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from pipeline.config_loader import load_yaml_config

REPO = Path(__file__).resolve().parents[1]
BOUNDARY_REGISTRY = REPO / "configs" / "spatial_boundaries.yaml"
LAYER_BINDING_REGISTRY = REPO / "configs" / "spatial_layer_bindings.yaml"
LAYER_CATALOG = REPO / "configs" / "layer_catalog.yaml"
BOUNDARY_SCHEMA = REPO / "schemas" / "spatial_boundary.schema.json"
LAYER_BINDING_SCHEMA = REPO / "schemas" / "spatial_layer_binding.schema.json"

sys.path.insert(0, str(REPO))


def _boundaries():
    return load_yaml_config(
        BOUNDARY_REGISTRY, required_keys=["version", "boundaries", "context_buffer"]
    )


def _bindings():
    return load_yaml_config(
        LAYER_BINDING_REGISTRY, required_keys=["version", "bindings"]
    )


def _catalog_layer_ids() -> set[str]:
    cat = load_yaml_config(LAYER_CATALOG, required_keys=["families"])
    return {layer["layer_id"] for fam in cat["families"] for layer in fam["layers"]}


# ─── Boundary registry ──────────────────────────────────────────────────────────


def test_boundary_registry_has_all_four_kinds():
    reg = _boundaries()
    kinds = {b["kind"] for b in reg["boundaries"]}
    assert kinds == {"core", "eez_legal", "analytical_domain"}, kinds


def test_unresolved_boundaries_carry_no_geometry():
    """A boundary that hasn't been sourced yet must not carry fabricated geometry."""
    reg = _boundaries()
    for b in reg["boundaries"]:
        if b["status"] == "unresolved":
            assert (
                b["geometry"] is None
            ), f"{b['boundary_id']} is unresolved but has geometry"
            assert b[
                "notes"
            ].strip(), (
                f"{b['boundary_id']} is unresolved but has no notes explaining why"
            )


def test_resolved_or_provisional_boundaries_carry_geometry():
    reg = _boundaries()
    for b in reg["boundaries"]:
        if b["status"] in ("provisional", "resolved"):
            assert (
                b["geometry"] is not None
            ), f"{b['boundary_id']} is {b['status']} but has no geometry"


def test_analytical_domain_is_not_marked_as_a_legal_boundary():
    reg = _boundaries()
    domain = next(b for b in reg["boundaries"] if b["kind"] == "analytical_domain")
    assert domain["status"] != "resolved", (
        "SPIDERWEB_ANALYTICAL_DOMAIN is a technical extent, not a legal boundary — "
        "it should never reach 'resolved' status the way PR_CORE_BOUNDARY/"
        "PR_EEZ_LEGAL_BOUNDARY can"
    )


def test_context_buffer_bounds_are_consistent():
    reg = _boundaries()
    buf = reg["context_buffer"]
    assert buf["min_km"] <= buf["default_km"] <= buf["max_km"]
    assert buf[
        "overrides"
    ], "context buffer should document at least one per-layer override"


def test_boundary_validates_against_json_schema_if_available():
    try:
        import jsonschema  # noqa: F401
    except ImportError:
        return
    schema = json.loads(BOUNDARY_SCHEMA.read_text())
    jsonschema.validate(instance=_boundaries(), schema=schema)


# ─── Layer binding registry ─────────────────────────────────────────────────────


def test_every_binding_layer_id_is_catalogued():
    catalogued = _catalog_layer_ids()
    bound = {b["layer_id"] for b in _bindings()["bindings"]}
    orphans = bound - catalogued
    assert not orphans, (
        f"spatial_layer_bindings.yaml references un-catalogued layer(s): "
        f"{sorted(orphans)}"
    )


def test_no_binding_claims_cesium_support_yet():
    """No CesiumRegionalRuntime exists in either frontend yet (Phase 0 shipped a
    MapLibre-only runtime seam) — a binding claiming cesium_enabled=true here
    would be aspirational, not descriptive."""
    for b in _bindings()["bindings"]:
        assert (
            b["runtime"]["cesium_enabled"] is False
        ), f"{b['layer_id']} claims cesium_enabled=true but no Cesium runtime ships yet"


def test_binding_validates_against_json_schema_if_available():
    try:
        import jsonschema  # noqa: F401
    except ImportError:
        return
    schema = json.loads(LAYER_BINDING_SCHEMA.read_text())
    jsonschema.validate(instance=_bindings(), schema=schema)


# ─── Backend endpoints ───────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from server.backend.main import app

    with TestClient(app) as c:
        yield c


@pytest.mark.smoke
def test_spatial_capabilities_reports_cesium_false(client):
    resp = client.get("/spatial/capabilities")
    assert resp.status_code == 200
    body = resp.json()
    assert body["runtimes"] == {"maplibre": True, "cesium": False}


@pytest.mark.smoke
def test_spatial_scene_serves_boundary_registry(client):
    resp = client.get("/spatial/scene")
    assert resp.status_code == 200
    body = resp.json()
    assert {b["kind"] for b in body["boundaries"]} == {
        "core",
        "eez_legal",
        "analytical_domain",
    }


@pytest.mark.smoke
def test_spatial_layers_serves_binding_registry(client):
    resp = client.get("/spatial/layers")
    assert resp.status_code == 200
    body = resp.json()
    assert any(b["layer_id"] == "municipios" for b in body["bindings"])


@pytest.mark.smoke
def test_existing_geo_and_catalog_routes_still_work(client):
    """/spatial/* is additive — it must not disturb the existing routes."""
    assert client.get("/catalog").status_code == 200
    resp = client.get("/geo/not_a_real_layer.geojson")
    assert resp.status_code == 400

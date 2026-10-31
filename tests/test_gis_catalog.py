"""gis-layer-catalog/1.0 derivation from the three spiderweb layer registries."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
import yaml

from spiderweb.gis_catalog import GisCatalogError, build_gis_catalog

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = ROOT / "schemas"


def _yaml(name: str) -> dict:
    return yaml.safe_load((ROOT / "configs" / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def registries():
    return (
        _yaml("layer_catalog.yaml"),
        _yaml("spatial_layer_bindings.yaml"),
        _yaml("gis_layer_interaction.yaml"),
    )


def _schema(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "name",
    [
        "gis_layer_catalog_v1.schema.json",
        "gis_query_v1.schema.json",
        "gis_scenario_result_v1.schema.json",
    ],
)
def test_gis_schemas_are_valid_draft_2020_12(name):
    jsonschema.Draft202012Validator.check_schema(_schema(name))


def test_interaction_registry_only_names_catalogued_layers(registries):
    catalog, _bindings, interaction = registries
    known = {
        layer["layer_id"] for fam in catalog["families"] for layer in fam["layers"]
    }
    assert set(interaction["layers"]) <= known


def test_built_catalog_validates_and_covers_every_catalogued_layer(registries):
    catalog, bindings, interaction = registries
    document = build_gis_catalog(
        catalog, bindings, interaction, data_available=lambda _layer: False
    )
    jsonschema.validate(document, _schema("gis_layer_catalog_v1.schema.json"))
    expected = [
        layer["layer_id"] for fam in catalog["families"] for layer in fam["layers"]
    ]
    assert [layer["layer_id"] for layer in document["layers"]] == expected


def test_only_public_layers_are_exportable(registries):
    document = build_gis_catalog(*registries)
    by_id = {layer["layer_id"]: layer for layer in document["layers"]}
    assert (
        by_id["municipios"]["access_default"] == "PUBLIC"
        and by_id["municipios"]["exportable"] is True
    )
    assert (
        by_id["sites"]["access_default"] == "RESTRICTED"
        and by_id["sites"]["exportable"] is False
    )
    assert (
        by_id["anomalies"]["access_default"] == "OBSERVE_ONLY"
        and by_id["anomalies"]["exportable"] is False
    )


def test_zoom_thresholds_stay_unset_until_measured(registries):
    document = build_gis_catalog(*registries)
    assert all(
        layer["min_zoom"] is None and layer["max_zoom"] is None
        for layer in document["layers"]
    )


def test_unknown_interaction_layer_is_rejected(registries):
    catalog, bindings, _interaction = registries
    with pytest.raises(GisCatalogError):
        build_gis_catalog(catalog, bindings, {"layers": {"not_a_layer": {}}})


def test_query_request_and_scenario_examples_validate():
    query_schema = _schema("gis_query_v1.schema.json")
    jsonschema.validate(
        {
            "geometry": {
                "type": "bbox",
                "west": -66.2,
                "south": 18.2,
                "east": -66.0,
                "north": 18.4,
            },
            "layers": ["municipios"],
        },
        query_schema,
    )
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"geometry": {"type": "bbox"}, "layers": []}, query_schema)
    scenario = {
        "contract_version": "gis-scenario-result/1.0",
        "producer_repo": "aguayluz-pr",
        "scenario_id": "0" * 64,
        "inputs": {
            "selected": [{"layer_id": "assets", "feature_id": "A1"}],
            "parameters": {"out_of_service": True},
        },
        "impacted": [{"feature_id": "A2", "hops": 1, "relation": "FLOWS_TO"}],
        "affected_areas": [
            {"area_type": "municipio", "area_id": "72127", "name": "San Juan"}
        ],
        "evidence_state": "HYPOTHESIS",
        "persisted": False,
    }
    jsonschema.validate(scenario, _schema("gis_scenario_result_v1.schema.json"))
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            {**scenario, "evidence_state": "FACT"},
            _schema("gis_scenario_result_v1.schema.json"),
        )

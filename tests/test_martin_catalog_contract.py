from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts.build_martin_config import compile_config

ROOT = Path(__file__).parent.parent
LAYER_CATALOG = ROOT / "configs" / "layer_catalog.yaml"
DELIVERY = ROOT / "configs" / "martin_delivery.yaml"
MARTIN_CONFIG = ROOT / "martin" / "config.yaml"
TIGER_MANIFEST = ROOT / "data" / "tiger" / "2025" / "manifest.json"


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _catalog_layers() -> dict[str, dict]:
    cat = _yaml(LAYER_CATALOG)
    out: dict[str, dict] = {}
    for family in cat.get("families", []):
        visibility = family.get("visibility")
        for layer in family.get("layers", []):
            out[layer["layer_id"]] = {**layer, "visibility": visibility}
    return out


def _tiger_output(layer_id: str) -> dict:
    manifest = json.loads(TIGER_MANIFEST.read_text(encoding="utf-8"))
    for layer in manifest["layers"]:
        if layer["layer"] == layer_id:
            return layer["output"]
    raise AssertionError(f"{layer_id} absent from TIGER manifest")


def test_delivery_registry_is_noncanonical_and_explicit_only():
    delivery = _yaml(DELIVERY)
    assert delivery["authority"] == "noncanonical_delivery_only"
    assert delivery["catalog_source_of_truth"] == "configs/layer_catalog.yaml"
    assert delivery["publication_policy"] == "explicit_named_sources_only"


def test_only_municipios_is_in_canary_delivery_registry():
    delivery = _yaml(DELIVERY)
    assert set(delivery["sources"]) == {"municipios"}


def test_validated_source_exists_in_authoritative_layer_catalog_and_is_public():
    source = _yaml(DELIVERY)["sources"]["municipios"]
    catalog = _catalog_layers()
    layer = catalog[source["source_layer"]]
    assert layer["visibility"] == source["visibility_required"] == "V3"
    assert layer.get("pipeline_wired") is True


def test_delivery_binding_matches_frozen_tiger_manifest():
    source = _yaml(DELIVERY)["sources"]["municipios"]
    output = _tiger_output("municipios")
    assert output["crs"] == source["expected_crs"] == "EPSG:4326"
    assert output["feature_count"] == source["expected_feature_count"] == 78
    assert output["sha256"] == source["expected_artifact_sha256"]
    assert output["path"] == Path(source["artifact_path"]).name


def test_committed_martin_config_is_zero_source_bootstrap_without_autodiscovery():
    config = _yaml(MARTIN_CONFIG)
    geojson = config["geojson"]
    assert "paths" not in geojson, (
        "geojson.paths would make filesystem presence equivalent to publication; "
        "Spiderweb requires explicit generated named sources"
    )
    assert geojson["sources"] == {}, (
        "committed Martin config must not be an independent publication surface"
    )


def test_generated_certification_source_matches_delivery_registry():
    rendered, manifest = compile_config("certification")
    config = yaml.safe_load(rendered)
    source = _yaml(DELIVERY)["sources"]["municipios"]
    assert manifest["admitted_sources"] == ["municipios"]
    assert config["geojson"]["sources"][source["martin_source_id"]] == source["martin_artifact_path"]


def test_generated_production_config_admits_published_source():
    rendered, manifest = compile_config("production")
    config = yaml.safe_load(rendered)
    source = _yaml(DELIVERY)["sources"]["municipios"]
    assert manifest["admitted_sources"] == ["municipios"]
    assert (
        config["geojson"]["sources"][source["martin_source_id"]]
        == source["martin_artifact_path"]
    )


def test_municipios_is_published():
    source = _yaml(DELIVERY)["sources"]["municipios"]
    assert source["publication_state"] == "published"


def test_zoom_bounds_close():
    source = _yaml(DELIVERY)["sources"]["municipios"]
    assert 0 <= source["minzoom"] <= source["maxzoom"] <= 30

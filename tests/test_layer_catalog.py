"""Gate: the Layer Catalog stays consistent and nothing surfaces unlabeled.

`configs/layer_catalog.yaml` (built by scripts/build_layer_catalog.py) is the single
source of truth for map-layer folder labels and their visibility class. These tests pin
the "natural gate / no misnamed groups" contract:

  - structure validates (against schemas/layer_catalog.schema.json when jsonschema is
    installed; otherwise an equivalent pure-Python check),
  - every layer_id is globally unique and labels are unique within a family,
  - every family declares a canonical V1/V2/V3 visibility class,
  - every backend-served layer (_ALLOWED_LAYERS) is catalogued (no orphans),
  - when the pipeline manifest exists, every emitted layer is catalogued too.
"""

import json
import re
from pathlib import Path

from pipeline.config_loader import load_yaml_config

REPO = Path(__file__).resolve().parents[1]
CATALOG = REPO / "configs" / "layer_catalog.yaml"
SCHEMA = REPO / "schemas" / "layer_catalog.schema.json"
BACKEND_MAIN = REPO / "server" / "backend" / "main.py"
MANIFEST = REPO / "data" / "_manifests" / "gis_layers_manifest.json"

ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _catalog():
    return load_yaml_config(CATALOG, required_keys=["version", "visibility_classes", "families"])


def _all_layers(cat):
    for fam in cat["families"]:
        for layer in fam["layers"]:
            yield fam, layer


def _allowed_layers():
    # The live _ALLOWED_LAYERS is derived from the catalog; _FALLBACK_LAYERS is the
    # backend's stable baseline of layers the geo API must keep serving.
    txt = BACKEND_MAIN.read_text(encoding="utf-8")
    m = re.search(r"_FALLBACK_LAYERS\s*=\s*\{(.*?)\}", txt, re.DOTALL)
    return set(re.findall(r'"([^"]+)"', m.group(1))) if m else set()


def test_catalog_is_labels_only():
    cat = _catalog()
    assert cat["binding"] == "labels_only"
    for _, layer in _all_layers(cat):
        assert layer["status"] == "deferred", f"{layer['layer_id']} must be deferred (labels only)"
        # No geometry/coordinates may leak into a labels-only catalog.
        assert not ({"lat", "lon", "lng", "geometry", "coordinates"} & set(layer)), layer


def test_visibility_classes_are_the_canonical_ladder():
    cat = _catalog()
    assert set(cat["visibility_classes"]) == {"V1", "V2", "V3"}
    for fam in cat["families"]:
        assert fam["visibility"] in cat["visibility_classes"], fam["id"]


def test_family_and_layer_ids_well_formed():
    cat = _catalog()
    for fam in cat["families"]:
        assert ID_RE.match(fam["id"]), f"bad family id {fam['id']}"
        assert fam["label"].strip(), fam["id"]
        for layer in fam["layers"]:
            assert ID_RE.match(layer["layer_id"]), f"bad layer_id {layer['layer_id']}"
            assert layer["label"].strip(), layer["layer_id"]


def test_layer_ids_globally_unique():
    cat = _catalog()
    ids = [layer["layer_id"] for _, layer in _all_layers(cat)]
    dupes = {i for i in ids if ids.count(i) > 1}
    assert not dupes, f"duplicate layer_id(s): {sorted(dupes)}"


def test_family_ids_unique_and_labels_unique_within_family():
    cat = _catalog()
    fam_ids = [f["id"] for f in cat["families"]]
    assert len(fam_ids) == len(set(fam_ids)), "duplicate family id"
    for fam in cat["families"]:
        labels = [layer["label"] for layer in fam["layers"]]
        assert len(labels) == len(set(labels)), f"duplicate label in family {fam['id']}"


def test_every_backend_served_layer_is_catalogued():
    cat = _catalog()
    catalogued = {layer["layer_id"] for _, layer in _all_layers(cat)}
    orphans = _allowed_layers() - catalogued
    assert not orphans, f"backend serves un-catalogued layer(s): {sorted(orphans)}"


def test_manifest_layers_catalogued_when_present():
    if not MANIFEST.exists():
        return  # pipeline output absent on a fresh checkout — cross-check skipped
    cat = _catalog()
    catalogued = {layer["layer_id"] for _, layer in _all_layers(cat)}
    emitted = {e["layer_id"] for e in json.loads(MANIFEST.read_text())["layers"] if e.get("layer_id")}
    orphans = emitted - catalogued
    assert not orphans, f"pipeline emits un-catalogued layer(s): {sorted(orphans)}"


def test_validates_against_json_schema_if_available():
    try:
        import jsonschema  # noqa: F401
    except ImportError:
        return  # optional dependency; pure-Python tests above cover the contract
    schema = json.loads(SCHEMA.read_text())
    jsonschema.validate(instance=_catalog(), schema=schema)

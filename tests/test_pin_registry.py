"""Gate: the Pin model stays consistent with the Layer Catalog and stays orphan-free.

`configs/pin_taxonomy.yaml` and `configs/master_pin_registry.yaml` (built by
scripts/build_pin_registry.py) re-express the Layer Catalog under the canonical Pin
hierarchy. These tests pin the contract:

  - taxonomy hierarchy is the canonical V-class -> domain -> pin_group -> pin_class ->
    pin_layer -> pin chain,
  - every catalog layer maps to exactly one Pin Layer in the registry (bijection — no
    orphan, no duplicate): OUTPUT_ZERO_ORPHAN_PIN_SCHEMA,
  - every Pin Layer carries a valid lifecycle flag and a planned status (labels-only),
  - the registry binds zero atomic pins,
  - pin / pin_link schemas validate representative records (when jsonschema is installed).
"""

import json
import re
from pathlib import Path

from pipeline.config_loader import load_yaml_config

REPO = Path(__file__).resolve().parents[1]
CATALOG = REPO / "configs" / "layer_catalog.yaml"
TAXONOMY = REPO / "configs" / "pin_taxonomy.yaml"
REGISTRY = REPO / "configs" / "master_pin_registry.yaml"
PIN_SCHEMA = REPO / "schemas" / "pin.schema.json"
PIN_LINK_SCHEMA = REPO / "schemas" / "pin_link.schema.json"

FLAGS = {"WIRED", "GHOST", "PLANNED", "DEPRECATED"}
GEOMS = {"point", "line", "polygon", "raster", "table", "unknown"}
UID_PREFIX_RE = re.compile(r"^PIN_[A-Z0-9]+(_[A-Z0-9]+)*$")


def _catalog_layers():
    cat = load_yaml_config(CATALOG, required_keys=["families"])
    return [layer["layer_id"] for fam in cat["families"] for layer in fam["layers"]]


def _taxonomy():
    return load_yaml_config(TAXONOMY, required_keys=["version", "hierarchy", "visibility_classes"])


def _registry():
    return load_yaml_config(REGISTRY, required_keys=["version", "layer_index", "pins"])


def _taxonomy_layers(tax):
    for vc in tax["visibility_classes"]:
        for dom in vc["domains"]:
            for grp in dom["pin_groups"]:
                for cls in grp["pin_classes"]:
                    for pl in cls["pin_layers"]:
                        yield vc, dom, grp, cls, pl


def test_hierarchy_is_canonical():
    tax = _taxonomy()
    assert tax["hierarchy"] == [
        "visibility_class", "domain", "pin_group", "pin_class", "pin_layer", "pin"]
    assert tax["root"] == "SPIDERWEB_PR"


def test_registry_is_labels_only():
    reg = _registry()
    assert reg["binding"] == "labels_only"
    assert reg["pin_count"] == 0
    assert reg["pins"] == []
    for row in reg["layer_index"]:
        assert row["status"] == "planned", row["pin_layer"]


def test_every_catalog_layer_maps_exactly_once():
    """Bijection between catalog layers and registry Pin Layers — zero orphans, no dupes."""
    catalog = _catalog_layers()
    indexed = [row["pin_layer"] for row in _registry()["layer_index"]]
    assert sorted(indexed) == sorted(catalog), (
        f"orphans={sorted(set(catalog) - set(indexed))} "
        f"extra={sorted(set(indexed) - set(catalog))}")
    dupes = {l for l in indexed if indexed.count(l) > 1}
    assert not dupes, f"duplicate Pin Layer(s): {sorted(dupes)}"


def test_taxonomy_and_registry_cover_the_same_layers():
    tax_layers = {pl["pin_layer"] for *_, pl in _taxonomy_layers(_taxonomy())}
    reg_layers = {row["pin_layer"] for row in _registry()["layer_index"]}
    assert tax_layers == reg_layers


def test_flags_and_geometry_valid():
    for row in _registry()["layer_index"]:
        assert row["flag"] in FLAGS, f"{row['pin_layer']}: bad flag {row['flag']}"
        assert row["geometry_type"] in GEOMS, f"{row['pin_layer']}: bad geom {row['geometry_type']}"
        assert UID_PREFIX_RE.match(row["pin_uid_prefix"]), row["pin_uid_prefix"]
        assert row["evidence_tier"] in {"T1", "T2", "T3", "T4"}


def test_visibility_classes_match_catalog():
    cat = load_yaml_config(CATALOG, required_keys=["visibility_classes"])
    tax_vc = {vc["visibility_class"] for vc in _taxonomy()["visibility_classes"]}
    assert tax_vc <= set(cat["visibility_classes"])


def test_pin_schema_validates_sample_when_available():
    try:
        import jsonschema
    except ImportError:
        return
    pin_schema = json.loads(PIN_SCHEMA.read_text())
    link_schema = json.loads(PIN_LINK_SCHEMA.read_text())
    sample_pin = {
        "pin_uid": "PIN_EDU_PUBSCH_000001",
        "pin_name": "Escuela Ejemplo",
        "domain": "institutional_civic",
        "pin_group": "civic_social",
        "pin_class": "public_schools",
        "pin_layer": "public_school_points",
        "geometry_type": "point",
        "status": "planned",
    }
    jsonschema.validate(sample_pin, pin_schema)
    jsonschema.validate(
        {"from_pin_uid": "PIN_EDU_PUBSCH_000001", "to_pin_uid": "PIN_GOV_AGENCY_000007",
         "relation": "operated_by"}, link_schema)

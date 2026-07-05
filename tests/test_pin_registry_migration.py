"""Gate: the POI -> Pin registry rename (stage 1) and its compatibility alias.

`configs/poi_registry.yaml` was renamed to `configs/pin_registry.yaml` with a
value-preserving key rename (poi_taxonomy/poi_records/poi_id/poi_class -> pin_*).
`pipeline.config_loader` carries a loader-level alias so the deprecated path and
the legacy keys keep resolving (with a DeprecationWarning) during the migration.

These tests pin that contract:
  - the new file exists with canonical keys/version and no legacy top-level keys,
  - record field keys are renamed but their VALUES (source ids) are preserved,
  - the deprecated path resolves to the new file and warns,
  - legacy top-level keys are mirrored to canonical keys (and vice versa).
"""

import warnings
from pathlib import Path

import yaml

from pipeline.config_loader import load_yaml_config

REPO = Path(__file__).resolve().parents[1]
PIN_REGISTRY = REPO / "configs" / "pin_registry.yaml"
DEPRECATED_PATH = REPO / "configs" / "poi_registry.yaml"


def test_old_registry_file_is_gone_new_one_present():
    assert PIN_REGISTRY.exists(), "configs/pin_registry.yaml must exist"
    assert not DEPRECATED_PATH.exists(), "configs/poi_registry.yaml must be removed"


def test_canonical_keys_and_version_no_legacy_residue():
    data = yaml.safe_load(PIN_REGISTRY.read_text(encoding="utf-8"))
    assert data["version"] == "rlsm_pin_registry_v1_0"
    assert "pin_taxonomy" in data and "pin_records" in data
    assert "poi_taxonomy" not in data and "poi_records" not in data


def test_record_keys_renamed_but_values_preserved():
    data = yaml.safe_load(PIN_REGISTRY.read_text(encoding="utf-8"))
    records = data["pin_records"]
    assert records, "expected populated pin_records"
    for rec in records:
        assert "pin_id" in rec and "pin_class" in rec
        assert "poi_id" not in rec and "poi_class" not in rec
    # Value integrity: the external source ids survived the key-only rename.
    ids = [r["pin_id"] for r in records]
    assert any(str(i).startswith("CSWDB") for i in ids), "source id values must be preserved"


def test_deprecated_path_resolves_to_new_file_with_warning():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        data = load_yaml_config(DEPRECATED_PATH, required_keys=["pin_taxonomy", "pin_records"])
    assert data["version"] == "rlsm_pin_registry_v1_0"
    assert any(issubclass(w.category, DeprecationWarning) for w in caught)


def test_legacy_keys_are_mirrored_both_directions():
    # New file exposes legacy keys back to legacy callers (silently).
    data = load_yaml_config(PIN_REGISTRY)
    assert data["poi_taxonomy"] is data["pin_taxonomy"]
    assert data["poi_records"] is data["pin_records"]

    # A legacy-shaped mapping exposes the canonical keys, with a warning.
    from pipeline.config_loader import _normalize_deprecated_keys

    legacy = {"poi_taxonomy": {"X": 1}, "poi_records": [{"poi_id": "A"}]}
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _normalize_deprecated_keys(legacy)
    assert legacy["pin_taxonomy"] == {"X": 1}
    assert legacy["pin_records"] == [{"poi_id": "A"}]
    assert any(issubclass(w.category, DeprecationWarning) for w in caught)

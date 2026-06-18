"""Contract validation tests for the civic Head Start PR layer schemas.

Mirrors tests/test_new_schemas.py. Locks the privacy invariants of the public
grid (``public_export``/``suppression``/``layer_id`` are const gates) and the
restricted precise-point feature (confidence cap, sensitivity, grid-only).
"""

import json
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")
Draft7Validator = jsonschema.Draft7Validator

SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"
GOLDEN_SAMPLE = Path(__file__).parent / "fixtures" / "headstart_context_grid.sample.jsonl"


def _load(name):
    return json.loads((SCHEMAS_DIR / f"{name}.schema.json").read_text())


def _validate(schema, doc):
    return list(Draft7Validator(schema).iter_errors(doc))


# ── headstart_context_grid (public, CI-gated) ─────────────────────────────────

class TestHeadstartContextGrid:
    SCHEMA = _load("headstart_context_grid")

    def _valid(self):
        return {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [-66.07, 18.45]},
            "properties": {
                "grid_id": "18.45,-66.07",
                "layer_id": "civic_headstart_pr",
                "record_count": 3,
                "funded_slots_total": 120,
                "public_export": True,
                "precision": 2,
                "suppression": "precise_points_removed",
            },
        }

    def test_schema_itself_is_valid(self):
        Draft7Validator.check_schema(self.SCHEMA)

    def test_valid_feature_passes(self):
        assert _validate(self.SCHEMA, self._valid()) == []

    def test_rejects_missing_grid_id(self):
        doc = self._valid()
        del doc["properties"]["grid_id"]
        assert len(_validate(self.SCHEMA, doc)) >= 1

    def test_rejects_missing_record_count(self):
        doc = self._valid()
        del doc["properties"]["record_count"]
        assert len(_validate(self.SCHEMA, doc)) >= 1

    def test_rejects_missing_suppression(self):
        doc = self._valid()
        del doc["properties"]["suppression"]
        assert len(_validate(self.SCHEMA, doc)) >= 1

    def test_rejects_public_export_false(self):
        # Privacy invariant: a public grid cell must self-declare public_export=true.
        doc = self._valid()
        doc["properties"]["public_export"] = False
        assert len(_validate(self.SCHEMA, doc)) >= 1

    def test_rejects_other_suppression_value(self):
        # Privacy invariant: precise points must always be removed.
        doc = self._valid()
        doc["properties"]["suppression"] = "none"
        assert len(_validate(self.SCHEMA, doc)) >= 1

    def test_rejects_wrong_layer_id(self):
        doc = self._valid()
        doc["properties"]["layer_id"] = "something_else"
        assert len(_validate(self.SCHEMA, doc)) >= 1

    def test_rejects_zero_record_count(self):
        doc = self._valid()
        doc["properties"]["record_count"] = 0
        assert len(_validate(self.SCHEMA, doc)) >= 1

    def test_rejects_point_outside_pr_bounds(self):
        doc = self._valid()
        doc["geometry"]["coordinates"] = [-80.19, 25.76]  # Miami, FL
        assert len(_validate(self.SCHEMA, doc)) >= 1

    def test_rejects_extra_property_leak(self):
        # additionalProperties:false guards against accidentally leaking a
        # precise coordinate field into the public grid.
        doc = self._valid()
        doc["properties"]["precise_lat"] = 18.4567
        assert len(_validate(self.SCHEMA, doc)) >= 1

    def test_golden_sample_lines_validate(self):
        # Every line of the checked-in golden sample (real exporter output) must
        # satisfy the schema. Guards the documented public-grid shape.
        lines = [l for l in GOLDEN_SAMPLE.read_text().splitlines() if l.strip()]
        assert lines, "golden sample is empty"
        for i, line in enumerate(lines):
            assert _validate(self.SCHEMA, json.loads(line)) == [], f"line {i + 1} invalid"


# ── headstart_service_location (RESTRICTED — no public sample) ─────────────────

class TestHeadstartServiceLocation:
    SCHEMA = _load("headstart_service_location")

    def _valid(self):
        return {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [-66.5901, 18.2201]},
            "properties": {
                "id": "headstart_service_location:HS-001",
                "source_id": "HS-001",
                "layer_id": "civic_headstart_pr",
                "node_type": "headstart_service_location",
                "label": "Centro Head Start A",
                "operator_id": "headstart_operator:abc123def456",
                "recipient_name": "Operator Alpha",
                "status": "Active",
                "funded_slots": 40,
                "program_type_label": "Head Start",
                "standalone_confidence": 15.0,
                "sensitivity": "high",
                "public_export": "grid_only",
            },
        }

    def test_schema_itself_is_valid(self):
        Draft7Validator.check_schema(self.SCHEMA)

    def test_valid_feature_passes(self):
        assert _validate(self.SCHEMA, self._valid()) == []

    def test_standalone_confidence_cap_enforced(self):
        doc = self._valid()
        doc["properties"]["standalone_confidence"] = 25.0  # > STANDALONE_CONFIDENCE_CAP
        assert len(_validate(self.SCHEMA, doc)) >= 1

    def test_sensitivity_must_be_high(self):
        doc = self._valid()
        doc["properties"]["sensitivity"] = "low"
        assert len(_validate(self.SCHEMA, doc)) >= 1

    def test_public_export_must_be_grid_only(self):
        doc = self._valid()
        doc["properties"]["public_export"] = "public"
        assert len(_validate(self.SCHEMA, doc)) >= 1

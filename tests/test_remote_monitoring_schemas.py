"""Contract validation for the remote_monitoring backbone schemas."""

import json
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")
Draft7Validator = jsonschema.Draft7Validator

SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"


def _load(name):
    return json.loads((SCHEMAS_DIR / f"{name}.schema.json").read_text())


def _errs(schema, doc):
    return list(Draft7Validator(schema).iter_errors(doc))


class TestMonitoringAOI:
    SCHEMA = _load("monitoring_aoi")

    def _valid(self):
        return {
            "aoi_uid": "rm_aoi_carraizo_reservoir",
            "name": "Carraizo Reservoir",
            "aoi_class": "reservoir",
            "monitoring_objective": "track shoreline and turbidity",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-66.02, 18.31],
                        [-66.02, 18.34],
                        [-65.98, 18.34],
                        [-65.98, 18.31],
                        [-66.02, 18.31],
                    ]
                ],
            },
        }

    def test_valid_passes(self):
        assert _errs(self.SCHEMA, self._valid()) == []

    def test_rejects_missing_objective(self):
        doc = self._valid()
        del doc["monitoring_objective"]
        assert len(_errs(self.SCHEMA, doc)) >= 1

    def test_rejects_coordinate_outside_pr(self):
        doc = self._valid()
        doc["geometry"]["coordinates"][0][0] = [-80.0, 40.0]  # not Puerto Rico
        assert len(_errs(self.SCHEMA, doc)) >= 1

    def test_rejects_priority_out_of_range(self):
        doc = self._valid()
        doc["priority"] = 9
        assert len(_errs(self.SCHEMA, doc)) >= 1


class TestSourceScene:
    SCHEMA = _load("source_scene")

    def _valid(self):
        return {
            "scene_uid": "S1A_IW_20240101",
            "provider": "copernicus",
            "collection": "sentinel-1-grd",
            "platform": "Sentinel-1A",
            "sensor": "C-SAR",
            "acquisition_start": "2024-01-01T10:00:00Z",
            "crs": "EPSG:4326",
            "ingest_status": "discovered",
        }

    def test_valid_passes(self):
        assert _errs(self.SCHEMA, self._valid()) == []

    def test_rejects_missing_platform(self):
        doc = self._valid()
        del doc["platform"]
        assert len(_errs(self.SCHEMA, doc)) >= 1

    def test_rejects_bad_ingest_status(self):
        doc = self._valid()
        doc["ingest_status"] = "maybe"
        assert len(_errs(self.SCHEMA, doc)) >= 1

    def test_rejects_bad_orbit_direction(self):
        doc = self._valid()
        doc["orbit_direction"] = "sideways"
        assert len(_errs(self.SCHEMA, doc)) >= 1


class TestRemoteObservation:
    SCHEMA = _load("remote_observation")

    def _valid(self):
        return {
            "observation_uid": "a" * 32,
            "aoi_uid": "rm_aoi_carraizo_reservoir",
            "scene_uids": ["S2_x"],
            "detector_name": "turbidity_proxy",
            "detector_version": "0.1",
            "evidence_tier": "radar_change_candidate",
            "geometry": {"type": "Point", "coordinates": [-66.0, 18.32]},
            "candidate_status": "candidate",
        }

    def test_valid_passes(self):
        assert _errs(self.SCHEMA, self._valid()) == []

    def test_rejects_bad_uid_pattern(self):
        doc = self._valid()
        doc["observation_uid"] = "not-hex"
        assert len(_errs(self.SCHEMA, doc)) >= 1

    def test_rejects_unknown_evidence_tier(self):
        doc = self._valid()
        doc["evidence_tier"] = "definitely_dredging"
        assert len(_errs(self.SCHEMA, doc)) >= 1

    def test_rejects_unknown_signal(self):
        doc = self._valid()
        doc["signals"] = ["telepathy"]
        assert len(_errs(self.SCHEMA, doc)) >= 1

    def test_rejects_confidence_over_100(self):
        doc = self._valid()
        doc["confidence"] = 101
        assert len(_errs(self.SCHEMA, doc)) >= 1

    def test_rejects_empty_scene_uids(self):
        doc = self._valid()
        doc["scene_uids"] = []
        assert len(_errs(self.SCHEMA, doc)) >= 1


class TestAdjudicationEvent:
    SCHEMA = _load("adjudication_event")

    def _valid(self):
        return {
            "adjudication_uid": "b" * 32,
            "observation_uid": "a" * 32,
            "decision": "confirm",
            "previous_status": "supported_candidate",
            "new_status": "confirmed",
            "analyst_or_rule": "analyst:jl",
            "decision_datetime": "2024-06-01T00:00:00Z",
        }

    def test_valid_passes(self):
        assert _errs(self.SCHEMA, self._valid()) == []

    def test_rejects_unknown_decision(self):
        doc = self._valid()
        doc["decision"] = "vaporize"
        assert len(_errs(self.SCHEMA, doc)) >= 1

    def test_rejects_missing_analyst(self):
        doc = self._valid()
        del doc["analyst_or_rule"]
        assert len(_errs(self.SCHEMA, doc)) >= 1


class TestPhysicalContractCrosswalk:
    SCHEMA = _load("physical_contract_crosswalk")

    def _valid(self):
        return {
            "crosswalk_uid": "c" * 32,
            "contract_node_uid": "ms:node:99",
            "observation_uid": "a" * 32,
            "reconciliation_status": "NO_SIGNAL_DETECTED",
        }

    def test_valid_passes(self):
        assert _errs(self.SCHEMA, self._valid()) == []

    def test_rejects_unknown_reconciliation_status(self):
        doc = self._valid()
        doc["reconciliation_status"] = "WORK_DID_NOT_HAPPEN"
        assert len(_errs(self.SCHEMA, doc)) >= 1

    def test_rejects_bad_spatial_relationship(self):
        doc = self._valid()
        doc["spatial_relationship"] = "somewhere"
        assert len(_errs(self.SCHEMA, doc)) >= 1


def test_all_schemas_discovered_by_validator():
    """The shared SchemaValidator auto-discovers the five new schemas."""
    from integration.schema_validation import SchemaValidator

    names = set(SchemaValidator().available_schemas())
    if not names:  # jsonschema not installed → validator is a no-op
        pytest.skip("jsonschema unavailable")
    for expected in (
        "monitoring_aoi",
        "source_scene",
        "remote_observation",
        "adjudication_event",
        "physical_contract_crosswalk",
    ):
        assert expected in names

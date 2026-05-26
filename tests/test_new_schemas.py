"""Contract validation tests for Phase 2 schemas (tasks 26-29)."""

import json
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")
Draft7Validator = jsonschema.Draft7Validator

SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"


def _load(name):
    return json.loads((SCHEMAS_DIR / f"{name}.schema.json").read_text())


def _validate(schema, doc):
    return list(Draft7Validator(schema).iter_errors(doc))


# ── spiderweb_intake_manifest ─────────────────────────────────────────────────

class TestSpiderwebIntakeManifest:
    SCHEMA = _load("spiderweb_intake_manifest")

    def _valid(self):
        return {
            "schema_version": "1.0",
            "generated_at": "2024-03-15T10:00:00Z",
            "export_dir": "/data/spiderweb_export",
            "candidate_count": 42,
            "missing_files": [],
        }

    def test_valid_manifest_passes(self):
        assert _validate(self.SCHEMA, self._valid()) == []

    def test_rejects_missing_schema_version(self):
        doc = self._valid()
        del doc["schema_version"]
        assert len(_validate(self.SCHEMA, doc)) >= 1

    def test_rejects_negative_candidate_count(self):
        doc = self._valid()
        doc["candidate_count"] = -1
        assert len(_validate(self.SCHEMA, doc)) >= 1

    def test_rejects_non_integer_candidate_count(self):
        doc = self._valid()
        doc["candidate_count"] = "many"
        assert len(_validate(self.SCHEMA, doc)) >= 1

    def test_valid_with_sources_array(self):
        doc = self._valid()
        doc["sources"] = [{"source_file": "ilap.csv", "records_loaded": 10}]
        assert _validate(self.SCHEMA, doc) == []

    def test_rejects_source_missing_records_loaded(self):
        doc = self._valid()
        doc["sources"] = [{"source_file": "ilap.csv"}]
        assert len(_validate(self.SCHEMA, doc)) >= 1


# ── calibration_report ────────────────────────────────────────────────────────

class TestCalibrationReport:
    SCHEMA = _load("calibration_report")

    def _valid(self):
        return {
            "generated_at": "2024-03-15T10:00:00Z",
            "export_dir": "/data/export",
            "baseline_mode": "fixture",
            "status": "PASS",
            "missing_inputs": [],
            "candidate_count": 0,
            "tier_distribution": {},
            "mbil_distribution": {},
            "signal_rates": {"hydro_yes_pct": 0.1, "utility_yes_pct": 0.2},
            "terrain_distribution": {},
            "dedup_rate": 0.05,
            "calibration_flags": [],
        }

    def test_valid_report_passes(self):
        assert _validate(self.SCHEMA, self._valid()) == []

    def test_rejects_invalid_status(self):
        doc = self._valid()
        doc["status"] = "UNKNOWN"
        assert len(_validate(self.SCHEMA, doc)) >= 1

    def test_rejects_invalid_baseline_mode(self):
        doc = self._valid()
        doc["baseline_mode"] = "production"
        assert len(_validate(self.SCHEMA, doc)) >= 1

    def test_rejects_dedup_rate_above_one(self):
        doc = self._valid()
        doc["dedup_rate"] = 1.5
        assert len(_validate(self.SCHEMA, doc)) >= 1

    def test_rejects_hydro_pct_above_one(self):
        doc = self._valid()
        doc["signal_rates"]["hydro_yes_pct"] = 1.1
        assert len(_validate(self.SCHEMA, doc)) >= 1

    def test_valid_with_calibration_flags(self):
        doc = self._valid()
        doc["calibration_flags"] = [
            {"metric": "pct_T4", "value": 0.8, "action": "investigate", "expected_max": 0.7}
        ]
        assert _validate(self.SCHEMA, doc) == []

    def test_flag_missing_action_rejected(self):
        doc = self._valid()
        doc["calibration_flags"] = [{"metric": "pct_T4", "value": 0.8}]
        assert len(_validate(self.SCHEMA, doc)) >= 1


# ── prii_readiness_report ─────────────────────────────────────────────────────

class TestPRIIReadinessReport:
    SCHEMA = _load("prii_readiness_report")

    def _valid(self):
        return {
            "generated_at": "2024-03-15T10:00:00Z",
            "status": "READY",
            "gates": {
                "prii":        {"status": "PASS"},
                "calibration": {"status": "WARN", "message": "fixture mode"},
            },
        }

    def test_valid_report_passes(self):
        assert _validate(self.SCHEMA, self._valid()) == []

    def test_rejects_invalid_status(self):
        doc = self._valid()
        doc["status"] = "UNKNOWN"
        assert len(_validate(self.SCHEMA, doc)) >= 1

    def test_rejects_invalid_gate_status(self):
        doc = self._valid()
        doc["gates"]["prii"]["status"] = "ERROR"
        assert len(_validate(self.SCHEMA, doc)) >= 1

    def test_minimal_report_no_gates(self):
        doc = {"generated_at": "2024-03-15T10:00:00Z", "status": "NOT_READY", "gates": {}}
        assert _validate(self.SCHEMA, doc) == []

    def test_rejects_missing_generated_at(self):
        doc = self._valid()
        del doc["generated_at"]
        assert len(_validate(self.SCHEMA, doc)) >= 1


# ── operational_alert ─────────────────────────────────────────────────────────

class TestOperationalAlert:
    SCHEMA = _load("operational_alert")

    def _valid(self):
        return {
            "alert_id": "UNKN_FLT_001",
            "flight_id": "FLT_001",
            "callsign": "N5854Z",
            "category": "Unknown/Unidentified Aircraft",
            "severity": "MEDIUM",
            "title": "Unknown aircraft detected",
            "description": "Callsign not in known operator database",
            "evidence": ["No registration found"],
            "timestamp": "2024-03-15T08:00:00",
            "recommended_action": "Research N-number via FAA registry",
        }

    def test_valid_alert_passes(self):
        assert _validate(self.SCHEMA, self._valid()) == []

    def test_rejects_invalid_severity(self):
        doc = self._valid()
        doc["severity"] = "EXTREME"
        assert len(_validate(self.SCHEMA, doc)) >= 1

    def test_rejects_invalid_category(self):
        doc = self._valid()
        doc["category"] = "Alien Sighting"
        assert len(_validate(self.SCHEMA, doc)) >= 1

    def test_rejects_missing_alert_id(self):
        doc = self._valid()
        del doc["alert_id"]
        assert len(_validate(self.SCHEMA, doc)) >= 1

    def test_rejects_empty_evidence(self):
        doc = self._valid()
        doc["evidence"] = "not a list"
        assert len(_validate(self.SCHEMA, doc)) >= 1

    def test_valid_with_escalation_fields(self):
        doc = self._valid()
        doc["escalation_count"] = 3
        doc["auto_resolved_reason"] = "Pattern normalized"
        assert _validate(self.SCHEMA, doc) == []

    def test_rejects_negative_escalation_count(self):
        doc = self._valid()
        doc["escalation_count"] = -1
        assert len(_validate(self.SCHEMA, doc)) >= 1

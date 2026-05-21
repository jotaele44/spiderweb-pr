"""
PRII READINESS ENGINE
Aggregates PRII gate results and calibration status into a single
prii_readiness_report.json with a tri-state readiness verdict.

Reads from an export directory that contains artifacts produced by:
  --export-pr-intel  →  integration_report.json
  --calibrate-scoring → calibration_report.json

Readiness contract:
  READY      All PRII gates PASS + calibration PASS (or absent)
  DEGRADED   No hard failures but at least one warning
             (calibration WARN, missing integration_report,
             PRII NO_DATA export, etc.)
  NOT_READY  Any PRII gate FAIL  OR  calibration FAIL

This module is a pure assessment layer: it reads existing artifacts and
writes prii_readiness_report.json.  It does not run the pipeline itself
and has no CLI surface (added in a later phase).
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


READINESS_STATUS_READY     = "READY"
READINESS_STATUS_DEGRADED  = "DEGRADED"
READINESS_STATUS_NOT_READY = "NOT_READY"

REQUIRED_REPORT_KEYS = [
    "generated_at",
    "export_dir",
    "readiness_status",
    "blockers",
    "warnings",
    "missing_inputs",
    "gate_summary",
]


class PRIIReadinessEngine:
    """
    Aggregates PRII integration and calibration reports into a readiness verdict.

    Usage:
        engine = PRIIReadinessEngine("/path/to/export_dir")
        report = engine.assess()
        print(report["readiness_status"])   # READY | DEGRADED | NOT_READY
    """

    def __init__(self, export_dir: str):
        self.export_dir = Path(export_dir)

    def assess(self) -> Dict[str, Any]:
        integration = self._load_json("integration_report.json")
        calibration  = self._load_json("calibration_report.json")

        missing_inputs: List[str] = []
        blockers: List[Dict[str, Any]] = []
        warnings: List[Dict[str, Any]] = []

        # ── PRII gate assessment ──────────────────────────────────────────────
        prii_overall: Optional[str] = None
        prii_gates:   Dict[str, Any] = {}

        if integration is None:
            missing_inputs.append("integration_report.json")
            warnings.append({
                "source": "prii_report",
                "detail": "integration_report.json not found — PRII gates unverified",
            })
        else:
            prii_overall = integration.get("overall_status")
            prii_gates   = integration.get("gates", {})
            for gate_name, gate in prii_gates.items():
                if gate.get("status") == "FAIL":
                    blockers.append({
                        "source":  "prii_gate",
                        "gate":    gate_name,
                        "detail":  self._gate_detail(gate_name, gate),
                    })
            # A NO_DATA export means the PRII gates had no records to assess
            # (e.g. run against an empty database). That is not a hard failure,
            # but it cannot count as a genuine PASS — flag it as a warning so
            # an empty-DB export resolves to DEGRADED rather than READY.
            if prii_overall == "NO_DATA":
                warnings.append({
                    "source": "prii_report",
                    "detail": "PRII export reported NO_DATA — gates had no records "
                              "to assess (empty database); readiness unverified",
                })

        # ── Calibration assessment ────────────────────────────────────────────
        cal_status:  Optional[str] = None
        cal_mode:    Optional[str] = None
        cal_flags:   List[dict]    = []
        cal_count:   Optional[int] = None

        if calibration is None:
            missing_inputs.append("calibration_report.json")
            # Missing calibration is a warning only: the pipeline may not have
            # been run yet.  It is not a hard blocker.
            warnings.append({
                "source": "calibration",
                "detail": "calibration_report.json not found — scoring baseline unverified",
            })
        else:
            cal_status = calibration.get("status")
            cal_mode   = calibration.get("baseline_mode")
            cal_flags  = calibration.get("calibration_flags", [])
            cal_count  = calibration.get("candidate_count")

            if cal_status == "FAIL":
                for flag in cal_flags:
                    blockers.append({
                        "source": "calibration",
                        "flag":   flag.get("metric", "unknown"),
                        "detail": (
                            f"value={flag.get('value')} outside range, "
                            f"action: {flag.get('action', '')}"
                        ),
                    })
            elif cal_status == "WARN":
                warnings.append({
                    "source": "calibration",
                    "detail": (
                        f"status=WARN (mode={cal_mode}) — "
                        "calibration flags present but suppressed in fixture mode"
                    ),
                })

        # ── Derive overall readiness ──────────────────────────────────────────
        if blockers:
            readiness_status = READINESS_STATUS_NOT_READY
        elif warnings:
            readiness_status = READINESS_STATUS_DEGRADED
        else:
            readiness_status = READINESS_STATUS_READY

        report = {
            "generated_at":    datetime.utcnow().isoformat() + "Z",
            "export_dir":      str(self.export_dir),
            "readiness_status": readiness_status,
            "blockers":        blockers,
            "warnings":        warnings,
            "missing_inputs":  missing_inputs,
            "gate_summary": {
                "prii_overall":       prii_overall,
                "prii_gates":         prii_gates,
                "calibration_status": cal_status,
                "calibration_flags":  cal_flags,
                "candidate_count":    cal_count,
                "baseline_mode":      cal_mode,
            },
        }

        self._write_report(report)
        return report

    # ── helpers ───────────────────────────────────────────────────────────────

    def _load_json(self, filename: str) -> Optional[Dict[str, Any]]:
        path = self.export_dir / filename
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    @staticmethod
    def _gate_detail(gate_name: str, gate: Dict[str, Any]) -> str:
        if gate_name == "coordinate_coverage":
            return (
                f"pct_with_coords={gate.get('pct_with_coords')} "
                f"< threshold={gate.get('threshold')}"
            )
        if gate_name == "ocr_confidence_gate":
            return (
                f"avg_confidence={gate.get('avg_confidence')} "
                f"< threshold={gate.get('threshold')}"
            )
        if gate_name == "evidence_chain_coverage":
            return (
                f"pct_with_screenshot={gate.get('pct_with_screenshot')} "
                f"< threshold={gate.get('threshold')}"
            )
        if gate_name == "schema_validation":
            return f"invalid={gate.get('invalid')} records failed schema validation"
        if gate_name == "export_completeness":
            return f"missing files: {gate.get('missing', [])}"
        if gate_name == "temporal_integrity":
            return f"violations={gate.get('violations')}"
        return f"gate {gate_name} failed"

    def _write_report(self, report: Dict[str, Any]) -> None:
        self.export_dir.mkdir(parents=True, exist_ok=True)
        (self.export_dir / "prii_readiness_report.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )

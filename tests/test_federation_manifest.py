import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_federation_manifest_does_not_declare_stale_z2_geometry_blocker():
    manifest = json.loads((REPO_ROOT / "federation.json").read_text())
    gate = manifest["federation_readiness_gate"]
    blockers = "\n".join(gate.get("blocking_conditions", []))
    resolved = "\n".join(gate.get("resolved_conditions", []))
    exporter = (REPO_ROOT / "scripts" / "federation_export.py").read_text()

    assert "Z2: project a representative point" in exporter
    assert "geometry is not yet carried" not in blockers
    assert "correlate_spatial has no entity geometry" not in blockers
    assert "Z2 geometry projection complete" in resolved


def test_federation_manifest_live_execution_blockers_are_current():
    manifest = json.loads((REPO_ROOT / "federation.json").read_text())
    gate = manifest["federation_readiness_gate"]

    assert gate["ready_for_hub_discovery"] is True
    assert gate["ready_for_hub_live_execution"] is True
    assert gate["blocking_conditions"] == []
    # The promotion trail (real rows, hub validation, operator approval) is
    # resolved, not dropped.
    resolved = "\n".join(gate["resolved_conditions"])
    assert "build_real_spatial_streams.py" in resolved
    assert "hub validate-package" in resolved
    assert "operator approved" in resolved
    assert manifest["production_status"] == "PRODUCTION"

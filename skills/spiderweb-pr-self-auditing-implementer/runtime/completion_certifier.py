from __future__ import annotations
REQUIRED = ("implementation_present", "acceptance_tests_pass", "regression_tests_pass", "schema_contracts_pass", "boundary_audit_pass", "documentation_reconciled", "ci_equivalent_pass")

def certify(evidence: dict) -> dict:
    missing = [k for k in REQUIRED if not evidence.get(k)]
    contradictions = int(evidence.get("material_contradictions", 0))
    unresolved = int(evidence.get("unresolved_required_inputs", 0))
    if contradictions or unresolved or missing:
        state = "AUDIT_FAILED" if contradictions else "VALIDATION_FAILED"
        return {"certified": False, "state": state, "missing": missing, "material_contradictions": contradictions, "unresolved_required_inputs": unresolved}
    return {"certified": True, "state": "TASK_VERIFIED_COMPLETE", "missing": [], "material_contradictions": 0, "unresolved_required_inputs": 0}

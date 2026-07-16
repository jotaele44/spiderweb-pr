from runtime.activation import decide
from runtime.backlog_reconciler import TaskEvidence, classify
from runtime.pr_collision_auditor import audit_collision
from runtime.impact_analyzer import analyze
from runtime.self_auditor import audit_text
from runtime.completion_certifier import certify

def test_positive_activation():
    assert decide("Finish spiderweb-pr backlog")["activate"] is True

def test_negative_activation():
    assert decide("Implement thehub-pr correlation")["activate"] is False

def test_boundary_violation():
    assert not audit_text("Spiderweb is the active FR24 ingestion owner").passed

def test_clean_boundary():
    assert audit_text("Spiderweb emits spatial review exports; Skywatcher owns active airspace ingestion.").passed

def test_stale_ledger_detection():
    assert classify(TaskEvidence(implementation=True, tests=True, documentation=True)) == "VERIFIED_COMPLETE"
    assert classify(TaskEvidence(documentation=True)) == "DOCUMENTED_NOT_IMPLEMENTED"

def test_pr_collision():
    r = audit_collision({"a.py", "b.py"}, {160: {"b.py"}, 153: {"x.py"}})
    assert not r["passed"] and r["collisions"][0]["pr"] == 160

def test_product_code_blocked():
    r = analyze(["pipeline/core.py"])
    assert not r["passed"] and r["product_code"]

def test_allowed_skill_scope():
    assert analyze(["skills/spiderweb-pr-self-auditing-implementer/SKILL.md"])["passed"]

def test_test_weakening_coverage_regression():
    assert not audit_text("set cov-fail-under=10").passed

def test_raw_data_commit_blocked():
    assert not audit_text("commit raw payload data").passed

def test_false_certification_blocked():
    e = {k: True for k in ("implementation_present","acceptance_tests_pass","regression_tests_pass","schema_contracts_pass","boundary_audit_pass","documentation_reconciled")}
    r = certify(e)
    assert not r["certified"] and "ci_equivalent_pass" in r["missing"]

def test_certification_success():
    keys=("implementation_present","acceptance_tests_pass","regression_tests_pass","schema_contracts_pass","boundary_audit_pass","documentation_reconciled","ci_equivalent_pass")
    r=certify({**{k:True for k in keys},"material_contradictions":0,"unresolved_required_inputs":0})
    assert r["certified"] and r["state"] == "TASK_VERIFIED_COMPLETE"

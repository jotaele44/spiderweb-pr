from __future__ import annotations
import re
from .models import AuditResult, Finding

FORBIDDEN_BOUNDARY_PATTERNS = {
    "fr24_reownership": r"(?:active|canonical).{0,30}fr24.{0,30}(?:owner|ingest)",
    "hub_correlation_duplication": r"(?:cross[- ]producer|hub[- ]level).{0,30}correlation.{0,30}(?:owned|implemented).{0,20}spiderweb",
}

def audit_text(text: str) -> AuditResult:
    findings = []
    lower = text.lower()
    for gate, pattern in FORBIDDEN_BOUNDARY_PATTERNS.items():
        hit = bool(re.search(pattern, lower, re.I | re.S))
        findings.append(Finding(gate, not hit, "blocker", "forbidden ownership claim" if hit else "clear"))
    gate_weakening = bool(re.search(r"cov-fail-under\s*[=:]\s*(?:0|[1-5]?\d)(?:\D|$)", lower))
    findings.append(Finding("no_gate_weakening", not gate_weakening, "blocker", "coverage floor weakening" if gate_weakening else "clear"))
    raw_commit = bool(re.search(r"commit\s+(?:raw|extracted)\s+(?:payload|data)", lower))
    findings.append(Finding("no_raw_data_commit", not raw_commit, "blocker", "raw payload commit instruction" if raw_commit else "clear"))
    return AuditResult("PASS" if all(f.passed for f in findings) else "AUDIT_FAILED", findings)

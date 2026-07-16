from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

TASK_STATES = {"VERIFIED_COMPLETE","IMPLEMENTED_UNTESTED","TESTED_UNDOCUMENTED","DOCUMENTED_NOT_IMPLEMENTED","PARTIAL","BLOCKED_INTERNAL","BLOCKED_EXTERNAL","SUPERSEDED","STALE_LEDGER_ENTRY","NOT_STARTED"}
CERT_STATES = {"HOLD_REPOSITORY_UNRESOLVED","HOLD_BASELINE_FAILED","HOLD_STALE_OR_CONFLICTING_PR","HOLD_EXTERNAL_DEPENDENCY","IMPLEMENTATION_IN_PROGRESS","VALIDATION_FAILED","AUDIT_FAILED","TASK_VERIFIED_COMPLETE","THEME_VERIFIED_COMPLETE","REPOSITORY_RELEASE_CANDIDATE"}

@dataclass(frozen=True)
class Finding:
    gate: str
    passed: bool
    severity: str
    detail: str

@dataclass
class AuditResult:
    status: str
    findings: list[Finding] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(f.passed for f in self.findings if f.severity in {"blocker", "major"})

from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class TaskEvidence:
    implementation: bool = False
    tests: bool = False
    documentation: bool = False
    external_blocker: bool = False
    superseded: bool = False

def classify(e: TaskEvidence) -> str:
    if e.superseded: return "SUPERSEDED"
    if e.external_blocker and not (e.implementation and e.tests): return "BLOCKED_EXTERNAL"
    if e.implementation and e.tests and e.documentation: return "VERIFIED_COMPLETE"
    if e.implementation and not e.tests: return "IMPLEMENTED_UNTESTED"
    if e.tests and not e.documentation: return "TESTED_UNDOCUMENTED"
    if e.documentation and not e.implementation: return "DOCUMENTED_NOT_IMPLEMENTED"
    if any((e.implementation, e.tests, e.documentation)): return "PARTIAL"
    return "NOT_STARTED"

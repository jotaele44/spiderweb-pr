"""Shared Spiderweb ↔ Subsurface Void Tracing v0.4 execution contract.

Spiderweb is the execution/control plane; SVT is the domain-reasoning layer.  These
constants intentionally mirror the portable skill package so source/run/exhaustion,
identity, provenance, and connectivity semantics cannot drift.
"""
from __future__ import annotations

MANIFESTATION_STATUS = frozenset({"VERIFIED_QUERYABLE", "VERIFIED_REFERENCE", "DISCOVERY_ONLY", "OPEN", "SUPERSEDED"})
RUN_STATES = frozenset({"PASS", "ZERO", "FAIL", "OPEN", "NOT_RUN"})
EXHAUSTION_STATES = frozenset({"PASS", "OPEN", "FINAL_PUBLIC_GAP"})
EVIDENCE_RELATIONSHIPS = frozenset({"DIRECT", "SUPPORTING", "CANDIDATE", "CONTRADICTED", "UNRESOLVED"})
SPATIAL_STATES = frozenset({"FULLY_WITHIN", "PARTIAL", "TOUCH_ONLY", "OUTSIDE", "NULL_EMPTY", "UNRESOLVED"})
CARDINALITIES = frozenset({"1:1", "1:N", "N:1", "N:N", "0:1", "UNRESOLVED"})
TRANSPORT_FAILURES = frozenset({"TRANSPORT_BLOCKED", "SERVICE_UNAVAILABLE", "TLS_FAILURE", "SCHEMA_FAILURE", "PAGING_FAILURE", "COUNT_FAILURE"})
NON_PROMOTION_BASES = frozenset({"proximity_only", "nearest_only", "name_only", "normalized_name_only", "same_category", "same_system", "source_absence", "shared_provenance"})
CONNECTIVITY_BINDINGS = frozenset({"SURVEYED_PASSAGE", "TRACER_CONFIRMED", "AS_BUILT_CONNECTION", "HYDRAULIC_TEST", "DOCUMENTED_TUNNEL_LINK"})


def run_state_is_terminal(state: str) -> bool:
    """Only an executed PASS or certified ZERO is terminal for public exhaustion."""
    if state not in RUN_STATES:
        raise ValueError(state)
    return state in {"PASS", "ZERO"}


def identity_basis_can_bind(basis) -> bool:
    basis = set(basis or ())
    hard = {"stable_id", "authoritative_binding", "exact_authoritative_relation", "certified_geometry_identifier", "strong_geometry_name"}
    return bool(basis & hard) and not (basis and basis.issubset(NON_PROMOTION_BASES))


def final_public_gap_allows_negative_evidence() -> bool:
    return False

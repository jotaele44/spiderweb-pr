"""Conservative identity evaluation for postal route candidates.

String equality, postal type, municipality, and spatial proximity are not
sufficient to bind canonical USPS route identities.
"""
from __future__ import annotations
from dataclasses import dataclass
from .parser import Classification, DesignationCandidate

@dataclass(frozen=True)
class RouteContext:
    postal_system: str | None = None
    servicing_zip: str | None = None
    facility_id: str | None = None
    authoritative_route_id: str | None = None
    source_id: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None

def binding_eligible(candidate: DesignationCandidate, context: RouteContext) -> bool:
    """Eligibility for *review*, not a certified binding decision.

    This minimal gate requires an actual authoritative route ID and source.
    It intentionally rejects the mixed RR/HC map label and all unsupported
    candidate-only match keys.
    """
    return (
        candidate.classification == Classification.CANDIDATE
        and bool(context.authoritative_route_id and context.authoritative_route_id.strip())
        and bool(context.source_id and context.source_id.strip())
        and context.postal_system == "USPS"
    )

def reconcile_candidates(
    left: DesignationCandidate, left_context: RouteContext,
    right: DesignationCandidate, right_context: RouteContext,
) -> str:
    """Return CANDIDATE_NOT_IDENTITY unless both authority IDs agree.

    Different nonempty authoritative IDs are CONTRADICTION, not a fuzzy tie.
    Even matching IDs are marked REVIEW until source scope and dates are
    independently validated by a downstream review gate.
    """
    if not binding_eligible(left, left_context) or not binding_eligible(right, right_context):
        return "UNRESOLVED"
    if left_context.authoritative_route_id != right_context.authoritative_route_id:
        return "CONTRADICTION"
    if left.route_type != right.route_type or left.route_number != right.route_number:
        return "CONTRADICTION"
    return "REVIEW"

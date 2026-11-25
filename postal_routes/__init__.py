"""Non-publishing Puerto Rico postal designation discovery tools.

No USPS route, address, contract, or geometry authority is inferred here.
"""
from .parser import Classification, DesignationCandidate, parse_designation
from .identity import RouteContext, binding_eligible, reconcile_candidates

__all__ = ["Classification", "DesignationCandidate", "parse_designation",
           "RouteContext", "binding_eligible", "reconcile_candidates"]

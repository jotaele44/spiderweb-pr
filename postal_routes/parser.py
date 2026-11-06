"""Conservative USPS HC/RR designation discovery parser.

This module is *not* USPS address validation. Its outputs never establish
a delivery route, geolocation, postal contract, or currently valid address.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import re

class Classification(str, Enum):
    CANDIDATE = "CANDIDATE_NOT_IDENTITY"
    AMBIGUOUS = "UNRESOLVED"
    UNRECOGNIZED = "NOT_APPLICABLE"

@dataclass(frozen=True)
class DesignationCandidate:
    raw: str
    route_type: str | None
    route_number: str | None
    box_number: str | None
    normalized_candidate: str | None
    classification: Classification
    warning: str | None = None

# Require an explicit HC or RR route designator. Never interpret a bare
# street number, ZIP, or contract number as a postal-route identity.
_ADDRESS = re.compile(
    r"^(?P<kind>HC|RR)\s+(?P<route>[0-9]+[A-Z]?)"
    r"(?:\s+BOX\s+(?P<box>[0-9]+[A-Z]?))?$",
    re.IGNORECASE,
)
# Map sources sometimes prepend 'Rural Route' to an HC address and omit BOX.
_MAP_LABEL = re.compile(
    r"^RURAL\s+ROUTE\s+HC\s+(?P<route>[0-9]+[A-Z]?)"
    r"(?:\s+(?P<box>[0-9]+[A-Z]?))?$",
    re.IGNORECASE,
)

def parse_designation(raw: str) -> DesignationCandidate:
    if not isinstance(raw, str):
        raise TypeError("raw designation must be str")
    if len(raw) > 512:
        raise ValueError("raw designation exceeds 512 characters")
    cleaned = re.sub(r"\s+", " ", raw.strip()).upper()
    match = _ADDRESS.fullmatch(cleaned)
    if match:
        kind, route, box = match.group("kind", "route", "box")
        normalized = f"{kind} {route}" + (f" BOX {box}" if box else "")
        return DesignationCandidate(raw, kind, route, box, normalized,
                                    Classification.CANDIDATE,
                                    "Syntax only; USPS identity and current validity unverified")
    match = _MAP_LABEL.fullmatch(cleaned)
    if match:
        route, box = match.group("route", "box")
        normalized = f"HC {route}" + (f" BOX {box}" if box else "")
        return DesignationCandidate(raw, "HC", route, box, normalized,
                                    Classification.AMBIGUOUS,
                                    "Contradictory Rural Route/HC label; BOX token inferred, not verified")
    return DesignationCandidate(raw, None, None, None, None,
                                Classification.UNRECOGNIZED,
                                "Not a supported standalone HC/RR designation")

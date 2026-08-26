"""Fail-closed adjudication primitives for PR archipelago geometry evidence.

This module separates existence of a geometry representation from resolution of
canonical footprint/extent. A GNIS representative point is real source-native
geometry; proximity to NOAA/CUSP line or point evidence is corroboration only.
Neither can silently become a canonical polygon or identity binding.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FootprintState(str, Enum):
    SOURCE_POINT_ONLY = "SOURCE_POINT_ONLY"
    LINE_CORROBORATED_CANDIDATE = "LINE_CORROBORATED_CANDIDATE"
    POLYGON_CANDIDATE = "POLYGON_CANDIDATE"
    FOOTPRINT_RESOLVED = "FOOTPRINT_RESOLVED"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class GeometryEvidenceSummary:
    """Evidence state for one already-stable source manifestation.

    Distances may rank or describe evidence, but never establish identity or
    footprint. ``hard_footprint_binding`` must come from a separately audited
    source/geometry binding process.
    """

    stable_source_feature_id: str
    has_source_native_point: bool
    has_line_corroboration: bool = False
    has_polygon_candidate: bool = False
    hard_footprint_binding: bool = False


def adjudicate_footprint(evidence: GeometryEvidenceSummary) -> FootprintState:
    """Return the strongest defensible geometry state without heuristic promotion."""
    if evidence.hard_footprint_binding:
        return FootprintState.FOOTPRINT_RESOLVED
    if evidence.has_polygon_candidate:
        return FootprintState.POLYGON_CANDIDATE
    if evidence.has_line_corroboration:
        return FootprintState.LINE_CORROBORATED_CANDIDATE
    if evidence.has_source_native_point:
        return FootprintState.SOURCE_POINT_ONLY
    return FootprintState.UNRESOLVED


def footprint_certification(*, resolved: int, unresolved: int, candidate_only: int) -> bool:
    """True only when the supplied footprint denominator has zero nonresolved residue."""
    if min(resolved, unresolved, candidate_only) < 0:
        raise ValueError("counts must be non-negative")
    return unresolved == 0 and candidate_only == 0 and resolved > 0

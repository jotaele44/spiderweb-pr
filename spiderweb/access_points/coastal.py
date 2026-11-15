"""Which side of the coast a geometry lies on -- per coastline version.

A coastline is not one line.  It depends on the tidal datum that defines it
(a mean-high-water shoreline is landward of a mean-lower-low-water one) and on
the survey date.  Every coastline is therefore kept as a dated, sourced
version, and a geometry is classified against each version separately.  The
results are reported side by side and never collapsed into one answer.

Classification uses the existing :func:`spiderweb.subsurface.evidence.spatial_state`
predicate and its six-value vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping, Sequence

from shapely.geometry.base import BaseGeometry

from spiderweb.subsurface.evidence import SpatialState, spatial_state

from .namespaces import Namespace
from .vertical import VerticalDatum

COASTAL_VERSION = "access-point-coastal-relation/1.0"


@dataclass(frozen=True)
class CoastlineVersion:
    """Land area as defined by one source, one tidal datum and one date."""

    version_id: str
    source_id: str
    shoreline_datum: VerticalDatum
    survey_date: str
    land: BaseGeometry
    crs: str

    def __post_init__(self) -> None:
        for name in ("version_id", "source_id", "survey_date", "crs"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} is required")
        if self.land is None or self.land.is_empty:
            raise ValueError("a coastline version needs a land geometry")
        if not self.land.is_valid:
            raise ValueError("land geometry is invalid; repair it at the source, not here")


class CoastalSide(StrEnum):
    LAND = "LAND"
    SEA = "SEA"
    STRADDLES_COAST = "STRADDLES_COAST"
    ON_COASTLINE = "ON_COASTLINE"
    UNRESOLVED = "UNRESOLVED"


_SIDE: dict[SpatialState, CoastalSide] = {
    SpatialState.FULLY_WITHIN: CoastalSide.LAND,
    SpatialState.OUTSIDE: CoastalSide.SEA,
    SpatialState.PARTIAL: CoastalSide.STRADDLES_COAST,
    SpatialState.TOUCH_ONLY: CoastalSide.ON_COASTLINE,
    SpatialState.NULL_EMPTY: CoastalSide.UNRESOLVED,
    SpatialState.UNRESOLVED: CoastalSide.UNRESOLVED,
}

_REGISTRY: dict[CoastalSide, Namespace | None] = {
    CoastalSide.LAND: Namespace.ACCESS_POINT_INLAND,
    CoastalSide.SEA: Namespace.ACCESS_POINT_OFFSHORE,
    CoastalSide.STRADDLES_COAST: None,
    CoastalSide.ON_COASTLINE: None,
    CoastalSide.UNRESOLVED: None,
}


@dataclass(frozen=True, slots=True)
class CoastalRelation:
    version_id: str
    source_id: str
    shoreline_datum: VerticalDatum
    survey_date: str
    state: SpatialState
    side: CoastalSide


@dataclass(frozen=True)
class CoastalAssessment:
    """One geometry against every coastline version on record."""

    relations: tuple[CoastalRelation, ...]

    @property
    def sides(self) -> frozenset[CoastalSide]:
        return frozenset(r.side for r in self.relations)

    @property
    def is_stable(self) -> bool:
        """True if every coastline version gives the same answer."""

        return len(self.sides) == 1

    @property
    def registry(self) -> Namespace | None:
        """The registry the geometry belongs in, or ``None`` if that is not settled.

        A geometry that straddles or touches the coast, or that changes side
        between coastline versions, is not assigned by geometry alone.
        """

        if not self.is_stable:
            return None
        return _REGISTRY[next(iter(self.sides))]


def classify(geometry: BaseGeometry | None, coastline: CoastlineVersion, *, crs: str) -> CoastalRelation:
    if crs != coastline.crs:
        raise ValueError(
            f"geometry is in {crs} but the coastline is in {coastline.crs}; "
            "reproject explicitly before testing"
        )
    state = spatial_state(coastline.land, geometry)
    return CoastalRelation(
        version_id=coastline.version_id,
        source_id=coastline.source_id,
        shoreline_datum=coastline.shoreline_datum,
        survey_date=coastline.survey_date,
        state=state,
        side=_SIDE[state],
    )


def assess(
    geometry: BaseGeometry | None, coastlines: Sequence[CoastlineVersion], *, crs: str
) -> CoastalAssessment:
    if not coastlines:
        raise ValueError("at least one coastline version is required")
    ids = [c.version_id for c in coastlines]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate coastline version id")
    ordered = sorted(coastlines, key=lambda c: (c.survey_date, c.version_id))
    return CoastalAssessment(tuple(classify(geometry, c, crs=crs) for c in ordered))


def side_changes(assessment: CoastalAssessment) -> Mapping[str, tuple[str, str]]:
    """Consecutive coastline versions between which the side differs."""

    changes: dict[str, tuple[str, str]] = {}
    for earlier, later in zip(assessment.relations, assessment.relations[1:]):
        if earlier.side is not later.side:
            changes[f"{earlier.version_id}->{later.version_id}"] = (
                earlier.side.value,
                later.side.value,
            )
    return changes

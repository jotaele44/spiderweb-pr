"""Vertical-reference contract for land elevation and seabed depth.

Land elevation and seabed depth are published against different vertical
references and with opposite signs.  This module is the only place where the
access-point code decides whether two vertical values may be combined.

Rules
-----
* A vertical datum must be a member of :class:`VerticalDatum`.  Placeholder
  strings that sources publish in the datum field ("Not Provided", "User
  Specified", "Unknown", ``source_dependent`` ...) are *not* datums and fail
  closed.
* Sign is explicit.  Values are normalised to "elevation, positive up" only by
  :func:`elevation_up_m`; nothing else flips a sign.
* Two values on different references may be combined only through an explicit
  :class:`CertifiedTransform` that names its authority.  This module ships no
  numeric offsets: the separation between a tidal datum and an orthometric
  datum is station-specific and must come from a cited source.
* Without a transform, land and sea surfaces may be shown side by side, each
  labelled with its own reference.  They are never merged into one surface and
  no difference between them is computed.

The quantitative comparison itself is delegated to
:func:`gebco.marine_evidence.compare_depths`; this module adds the controlled
vocabulary and closes the placeholder-string gap in front of it.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable, Sequence

from gebco.marine_evidence import (
    VERTICAL_REFERENCE_PLACEHOLDERS,
    DepthTransform,
    VerticalCompatibilityError,
    VerticalReference,
)

__all__ = [
    "BoundVertical",
    "CertifiedTransform",
    "DatumKind",
    "JoinDecision",
    "JoinState",
    "UnknownVerticalDatumError",
    "VerticalCompatibilityError",
    "VerticalDatum",
    "bind",
    "combined_uncertainty_m",
    "decide_join",
    "elevation_up_m",
    "is_placeholder",
    "normalize_datum",
    "to_common_elevation_m",
]


class UnknownVerticalDatumError(VerticalCompatibilityError):
    """The vertical datum is missing, a placeholder, or not in the vocabulary."""


class DatumKind(StrEnum):
    ORTHOMETRIC = "ORTHOMETRIC"
    TIDAL = "TIDAL"
    ELLIPSOIDAL = "ELLIPSOIDAL"
    ASSUMED = "ASSUMED"


class VerticalDatum(StrEnum):
    PRVD02 = "PRVD02"                      # Puerto Rico Vertical Datum of 2002
    VIVD09 = "VIVD09"                      # Virgin Islands Vertical Datum of 2009
    NAVD88 = "NAVD88"
    MLLW = "MLLW"
    MLW = "MLW"
    MSL = "MSL"
    MTL = "MTL"
    MHW = "MHW"
    MHHW = "MHHW"
    LAT = "LAT"
    NAD83_ELLIPSOID = "NAD83_ELLIPSOID"
    WGS84_ELLIPSOID = "WGS84_ELLIPSOID"
    # GEBCO grids are referenced to mean sea level only nominally; the existing
    # GEBCO code labels this "mean_sea_level_assumed".  It is kept distinct from
    # MSL so it can never be treated as a tidal-datum measurement.
    MSL_ASSUMED = "MSL_ASSUMED"


DATUM_KIND: dict[VerticalDatum, DatumKind] = {
    VerticalDatum.PRVD02: DatumKind.ORTHOMETRIC,
    VerticalDatum.VIVD09: DatumKind.ORTHOMETRIC,
    VerticalDatum.NAVD88: DatumKind.ORTHOMETRIC,
    VerticalDatum.MLLW: DatumKind.TIDAL,
    VerticalDatum.MLW: DatumKind.TIDAL,
    VerticalDatum.MSL: DatumKind.TIDAL,
    VerticalDatum.MTL: DatumKind.TIDAL,
    VerticalDatum.MHW: DatumKind.TIDAL,
    VerticalDatum.MHHW: DatumKind.TIDAL,
    VerticalDatum.LAT: DatumKind.TIDAL,
    VerticalDatum.NAD83_ELLIPSOID: DatumKind.ELLIPSOIDAL,
    VerticalDatum.WGS84_ELLIPSOID: DatumKind.ELLIPSOIDAL,
    VerticalDatum.MSL_ASSUMED: DatumKind.ASSUMED,
}

# Strings that sources put in a datum field without naming a datum.  The set is
# owned by :mod:`gebco.marine_evidence`, where the same rule guards
# ``VerticalReference.is_fully_bound``.
_PLACEHOLDERS = VERTICAL_REFERENCE_PLACEHOLDERS

# Spellings observed in the repository's registries and receipts, plus the
# standard short forms.  Keys are compared after :func:`_fold`.
_ALIASES: dict[str, VerticalDatum] = {
    "prvd02": VerticalDatum.PRVD02,
    "prvd 02": VerticalDatum.PRVD02,
    "prvd 2002": VerticalDatum.PRVD02,
    "puerto rico vertical datum of 2002": VerticalDatum.PRVD02,
    "puerto rico vertical datum 2002": VerticalDatum.PRVD02,
    "epsg 6641": VerticalDatum.PRVD02,
    "vivd09": VerticalDatum.VIVD09,
    "virgin islands vertical datum of 2009": VerticalDatum.VIVD09,
    "navd88": VerticalDatum.NAVD88,
    "navd 88": VerticalDatum.NAVD88,
    "north american vertical datum of 1988": VerticalDatum.NAVD88,
    "epsg 5703": VerticalDatum.NAVD88,
    "mllw": VerticalDatum.MLLW,
    "mean lower low water": VerticalDatum.MLLW,
    "epsg 5866": VerticalDatum.MLLW,
    "mlw": VerticalDatum.MLW,
    "mean low water": VerticalDatum.MLW,
    "msl": VerticalDatum.MSL,
    "mean sea level": VerticalDatum.MSL,
    "local mean sea level": VerticalDatum.MSL,
    "lmsl": VerticalDatum.MSL,
    "epsg 5714": VerticalDatum.MSL,
    "epsg 5715": VerticalDatum.MSL,
    "mtl": VerticalDatum.MTL,
    "mean tide level": VerticalDatum.MTL,
    "mhw": VerticalDatum.MHW,
    "mean high water": VerticalDatum.MHW,
    "mhhw": VerticalDatum.MHHW,
    "mean higher high water": VerticalDatum.MHHW,
    "lat": VerticalDatum.LAT,
    "lowest astronomical tide": VerticalDatum.LAT,
    "nad83 ellipsoid": VerticalDatum.NAD83_ELLIPSOID,
    "nad83 ellipsoidal height": VerticalDatum.NAD83_ELLIPSOID,
    "grs80 ellipsoid": VerticalDatum.NAD83_ELLIPSOID,
    "wgs84 ellipsoid": VerticalDatum.WGS84_ELLIPSOID,
    "wgs84 ellipsoidal height": VerticalDatum.WGS84_ELLIPSOID,
    "mean sea level assumed": VerticalDatum.MSL_ASSUMED,
    "msl assumed": VerticalDatum.MSL_ASSUMED,
}

# EPSG vertical codes whose *axis direction* is fixed by the code itself.
_EPSG_DEPTH_CODES = frozenset({"epsg 5866", "epsg 5715"})
_EPSG_HEIGHT_CODES = frozenset({"epsg 6641", "epsg 5703", "epsg 5714"})

_FOLD_RE = re.compile(r"[^a-z0-9]+")


def _fold(value: str) -> str:
    return _FOLD_RE.sub(" ", value.strip().lower()).strip()


def is_placeholder(value: str | None) -> bool:
    """True for a missing value or a string that names no datum."""

    if value is None:
        return True
    if not isinstance(value, str):
        return True
    return _fold(value) in _PLACEHOLDERS


def normalize_datum(value: str | None) -> VerticalDatum:
    """Map a source spelling to the controlled vocabulary, or fail closed."""

    if is_placeholder(value):
        raise UnknownVerticalDatumError(
            f"vertical datum is not stated ({value!r}); it cannot be assumed"
        )
    assert value is not None
    folded = _fold(value)
    for member in VerticalDatum:
        if folded == _fold(member.value):
            return member
    if folded in _ALIASES:
        return _ALIASES[folded]
    raise UnknownVerticalDatumError(
        f"vertical datum {value!r} is not in the controlled vocabulary"
    )


@dataclass(frozen=True, slots=True)
class BoundVertical:
    """A vertical reference whose datum and sign are both known."""

    datum: VerticalDatum
    positive: str  # "up" or "down"
    horizontal_crs: str

    def __post_init__(self) -> None:
        if self.positive not in {"up", "down"}:
            raise ValueError("positive must be 'up' or 'down'")
        if not self.horizontal_crs or not self.horizontal_crs.strip():
            raise ValueError("horizontal_crs is required")

    @property
    def kind(self) -> DatumKind:
        return DATUM_KIND[self.datum]

    def to_reference(self) -> VerticalReference:
        tidal = self.datum.value if self.kind is DatumKind.TIDAL else None
        return VerticalReference(
            horizontal_crs=self.horizontal_crs,
            vertical_crs=None,
            vertical_datum=self.datum.value,
            tidal_datum=tidal,
            depth_positive=self.positive,
        )


def bind(reference: VerticalReference | None) -> BoundVertical:
    """Resolve a :class:`VerticalReference` to a known datum and sign.

    Every stated field must agree.  A reference whose fields name two
    different datums is a contradiction, not a choice, and fails closed.
    """

    if reference is None:
        raise UnknownVerticalDatumError("no vertical reference was supplied")
    stated = [
        value
        for value in (reference.vertical_datum, reference.tidal_datum, reference.vertical_crs)
        if not is_placeholder(value)
    ]
    if not stated:
        raise UnknownVerticalDatumError(
            "vertical reference carries only placeholders; the datum is unknown"
        )
    resolved = {normalize_datum(value) for value in stated}
    if len(resolved) != 1:
        raise UnknownVerticalDatumError(
            "vertical reference names conflicting datums: "
            + ", ".join(sorted(d.value for d in resolved))
        )
    for value in stated:
        folded = _fold(value)
        if folded in _EPSG_DEPTH_CODES and reference.depth_positive != "down":
            raise VerticalCompatibilityError(
                f"{value} is a depth (positive-down) reference but the value is declared positive-up"
            )
        if folded in _EPSG_HEIGHT_CODES and reference.depth_positive != "up":
            raise VerticalCompatibilityError(
                f"{value} is a height (positive-up) reference but the value is declared positive-down"
            )
    return BoundVertical(
        datum=next(iter(resolved)),
        positive=reference.depth_positive,
        horizontal_crs=reference.horizontal_crs,
    )


def elevation_up_m(value_m: float, reference: VerticalReference | BoundVertical) -> float:
    """Express a value as elevation, positive up, *on its own datum*.

    This changes the sign convention only.  It does not move the value to
    another datum.
    """

    if value_m is None or not math.isfinite(value_m):
        raise ValueError("value_m must be a finite number; no-data is not a height")
    bound = reference if isinstance(reference, BoundVertical) else bind(reference)
    return float(value_m) if bound.positive == "up" else -float(value_m)


@dataclass(frozen=True, slots=True)
class CertifiedTransform:
    """An offset between two datums at a stated place, with its authority.

    ``offset_m`` is added to an elevation (positive up) on ``source`` to obtain
    the elevation on ``target``.
    """

    source: VerticalDatum
    target: VerticalDatum
    offset_m: float
    authority: str
    uncertainty_m: float | None = None
    valid_bbox: tuple[float, float, float, float] | None = None

    def __post_init__(self) -> None:
        if not self.authority or not self.authority.strip():
            raise ValueError("a vertical transform must name its authority")
        if is_placeholder(self.authority):
            raise ValueError("a placeholder is not an authority")
        if self.source is self.target:
            raise ValueError("source and target datums are identical")
        if not math.isfinite(self.offset_m):
            raise ValueError("offset_m must be finite")
        if DatumKind.ASSUMED in {DATUM_KIND[self.source], DATUM_KIND[self.target]}:
            raise ValueError("an assumed datum cannot be an end of a certified transform")
        if self.uncertainty_m is not None and (
            not math.isfinite(self.uncertainty_m) or self.uncertainty_m < 0
        ):
            raise ValueError("uncertainty_m must be finite and non-negative")
        if self.valid_bbox is not None:
            w, s, e, n = self.valid_bbox
            if not (w < e and s < n):
                raise ValueError("valid_bbox must be (west, south, east, north)")

    def covers(self, lon: float | None, lat: float | None) -> bool:
        if self.valid_bbox is None:
            return True
        if lon is None or lat is None:
            return False
        w, s, e, n = self.valid_bbox
        return w <= lon <= e and s <= lat <= n

    def as_depth_transform(self, source: BoundVertical, target: BoundVertical) -> DepthTransform:
        """Express this offset for :func:`gebco.marine_evidence.compare_depths`."""

        if source.datum is not self.source or target.datum is not self.target:
            raise ValueError("references do not match this transform")
        sign_in = 1.0 if source.positive == "up" else -1.0
        sign_out = 1.0 if target.positive == "up" else -1.0
        return DepthTransform(
            source=source.to_reference(),
            target=target.to_reference(),
            scale=sign_in * sign_out,
            offset_m=self.offset_m * sign_out,
            authority=self.authority,
        )


def _find(
    source: VerticalDatum,
    target: VerticalDatum,
    transforms: Iterable[CertifiedTransform],
    lon: float | None,
    lat: float | None,
) -> CertifiedTransform | None:
    matches = [
        t for t in transforms if t.source is source and t.target is target and t.covers(lon, lat)
    ]
    if len(matches) > 1:
        raise VerticalCompatibilityError(
            f"more than one transform from {source.value} to {target.value} applies here; "
            "the choice must be made explicitly"
        )
    return matches[0] if matches else None


def combined_uncertainty_m(*parts: float | None) -> float | None:
    """Root-sum-square.  Any unknown part makes the total unknown."""

    if not parts or any(p is None for p in parts):
        return None
    values = [float(p) for p in parts if p is not None]
    if any(not math.isfinite(v) or v < 0 for v in values):
        raise ValueError("uncertainties must be finite and non-negative")
    return math.sqrt(sum(v * v for v in values))


@dataclass(frozen=True, slots=True)
class CommonElevation:
    elevation_m: float
    datum: VerticalDatum
    uncertainty_m: float | None
    transform_authority: str | None


def to_common_elevation_m(
    value_m: float,
    reference: VerticalReference | BoundVertical,
    target: VerticalDatum,
    *,
    transforms: Sequence[CertifiedTransform] = (),
    uncertainty_m: float | None = None,
    lon: float | None = None,
    lat: float | None = None,
) -> CommonElevation:
    """Move one value to ``target`` as elevation, positive up -- or refuse."""

    bound = reference if isinstance(reference, BoundVertical) else bind(reference)
    up = elevation_up_m(value_m, bound)
    if bound.datum is target:
        if bound.kind is DatumKind.ASSUMED:
            raise VerticalCompatibilityError(
                "an assumed datum cannot be used as a common reference"
            )
        return CommonElevation(up, target, uncertainty_m, None)
    transform = _find(bound.datum, target, transforms, lon, lat)
    if transform is None:
        raise VerticalCompatibilityError(
            f"no certified transform from {bound.datum.value} to {target.value} "
            "applies at this location; the values cannot be combined"
        )
    return CommonElevation(
        up + transform.offset_m,
        target,
        combined_uncertainty_m(uncertainty_m, transform.uncertainty_m),
        transform.authority,
    )


class JoinState(StrEnum):
    SAME_REFERENCE = "SAME_REFERENCE"
    TRANSFORMED = "TRANSFORMED"
    SEPARATE_SURFACES_ONLY = "SEPARATE_SURFACES_ONLY"
    BLOCKED_UNKNOWN_DATUM = "BLOCKED_UNKNOWN_DATUM"


@dataclass(frozen=True, slots=True)
class JoinDecision:
    """Whether a land surface and a seabed surface may share one vertical axis."""

    state: JoinState
    common_datum: VerticalDatum | None
    authority: str | None
    reason: str

    @property
    def may_difference(self) -> bool:
        return self.state in {JoinState.SAME_REFERENCE, JoinState.TRANSFORMED}


def decide_join(
    land: VerticalReference | None,
    sea: VerticalReference | None,
    *,
    transforms: Sequence[CertifiedTransform] = (),
    lon: float | None = None,
    lat: float | None = None,
) -> JoinDecision:
    """Decide how a land surface and a seabed surface may be shown together."""

    try:
        land_bound = bind(land)
        sea_bound = bind(sea)
    except UnknownVerticalDatumError as exc:
        return JoinDecision(JoinState.BLOCKED_UNKNOWN_DATUM, None, None, str(exc))
    if DatumKind.ASSUMED in {land_bound.kind, sea_bound.kind}:
        return JoinDecision(
            JoinState.SEPARATE_SURFACES_ONLY,
            None,
            None,
            "one surface is on an assumed datum; show each on its own reference",
        )
    if land_bound.datum is sea_bound.datum:
        return JoinDecision(
            JoinState.SAME_REFERENCE, land_bound.datum, None, "both surfaces state the same datum"
        )
    transform = _find(sea_bound.datum, land_bound.datum, transforms, lon, lat)
    if transform is not None:
        return JoinDecision(
            JoinState.TRANSFORMED,
            land_bound.datum,
            transform.authority,
            f"seabed values moved to {land_bound.datum.value}",
        )
    return JoinDecision(
        JoinState.SEPARATE_SURFACES_ONLY,
        None,
        None,
        f"no certified transform between {sea_bound.datum.value} and "
        f"{land_bound.datum.value}; show each on its own reference",
    )

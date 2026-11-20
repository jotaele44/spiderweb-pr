"""Candidate discovery from terrain and bathymetric surfaces.

Detection finds *shapes*.  It emits evidence for two dimensions only --
EXISTENCE and MORPHOLOGY -- and never for a physical opening, accessibility,
function or connectivity.  A high discovery score ranks candidates for review;
it does not establish that an opening is real.

Inland and off-shore detection share the processing core in
:mod:`spiderweb.access_points.raster` and differ in interpretation:

* inland analysis needs a bare-earth model; a first-return surface carries
  buildings and canopy and is refused;
* a land basin is a ``CLOSED_DEPRESSION`` unless an evidenced geological
  context supports the karst reading ``SINKHOLE``;
* a seabed basin is a ``SEAFLOOR_DEPRESSION``; a steep, deep, round one is a
  ``BLUE_HOLE_CANDIDATE`` -- still a candidate;
* shapes that coincide with a survey seam or lie mostly on interpolated cells
  are reported as possible artefacts, not dropped.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Mapping, Sequence

import numpy as np
from skimage import measure

from .models import EvidenceAssertion, SourceManifestation
from .namespaces import Namespace
from .raster import (
    DepressionRegion,
    Seam,
    SurfaceGrid,
    SurfaceKind,
    delineate_depressions,
    detect_seams,
    seam_mask,
    slope_degrees,
)
from .vocabulary import (
    ClaimClass,
    EvidenceDimension,
    EvidenceTier,
    InlandFeatureClass,
    OffshoreFeatureClass,
    Origin,
    SpatialState,
)

DETECTION_METHOD = "closed-basin-delineation"
DETECTION_VERSION = "access-point-detection/1.0"
ESCARPMENT_METHOD = "slope-band-delineation"
RECTANGULARITY_THRESHOLD = 0.88

_SHAPE_BASIS = ("terrain_derivative", "depression_shape")
_SEABED_BASIS = ("bathymetric_anomaly", "depression_shape")


class DetectionFlag(StrEnum):
    SEAM_OVERLAP = "SEAM_OVERLAP"
    MOSTLY_INTERPOLATED = "MOSTLY_INTERPOLATED"
    PARTLY_INTERPOLATED = "PARTLY_INTERPOLATED"
    BELOW_UNCERTAINTY = "BELOW_UNCERTAINTY"
    UNCERTAINTY_UNKNOWN = "UNCERTAINTY_UNKNOWN"
    ADJOINS_EDGE = "ADJOINS_EDGE"
    # Informational: the basin lies inside a larger closed basin.  It says
    # nothing about quality and never lowers a tier.
    NESTED = "NESTED"


ARTIFACT_FLAGS = frozenset(
    {DetectionFlag.SEAM_OVERLAP, DetectionFlag.MOSTLY_INTERPOLATED}
)


@dataclass(frozen=True, slots=True)
class DetectionParameters:
    min_depth_m: float
    min_area_m2: float
    significance_floor: float = 3.0
    interpolated_artifact_fraction: float = 0.5
    max_regions: int | None = None
    # Also report basins nested inside a larger closed basin.  On by default
    # since 2026-11-18, by the owner's decision after it was measured against
    # a published map.  The outer basins and their identifiers are the same
    # with or without it; a run made before the change pins ``nested: false``.
    nested: bool = True
    nested_level_step_m: float = 0.5
    # Optional second rule for one pit under a broad bowl: the factor by which
    # the wet area must fall in a single level step.  ``None`` leaves it off.
    pit_area_jump: float | None = None

    def __post_init__(self) -> None:
        if self.min_depth_m <= 0 or self.min_area_m2 <= 0:
            raise ValueError("min_depth_m and min_area_m2 must be positive")
        if self.significance_floor <= 0:
            raise ValueError("significance_floor must be positive")
        if not 0 < self.interpolated_artifact_fraction <= 1:
            raise ValueError("interpolated_artifact_fraction must be within (0, 1]")
        if self.nested_level_step_m <= 0:
            raise ValueError("nested_level_step_m must be positive")
        if self.pit_area_jump is not None:
            if not self.nested:
                raise ValueError("pit_area_jump applies only with nested basins on")
            if self.pit_area_jump <= 1:
                raise ValueError("pit_area_jump must be greater than 1")


@dataclass(frozen=True, slots=True)
class GeologicalContext:
    """An evidenced statement that the analysed ground lies in a mapped unit.

    The relation must come from a geometry test against a registered source.
    ``PARTIAL`` or ``TOUCH_ONLY`` does not support a karst reading.
    """

    source_id: str
    unit_name: str
    is_karst_prone: bool
    spatial_state: SpatialState


@dataclass(frozen=True)
class Detection:
    """One candidate shape with the evidence the method can honestly offer."""

    namespace: Namespace
    proposed_class: str
    native_record_id: str
    region: DepressionRegion | None
    centroid_xy: tuple[float, float]
    crs: str
    discovery_score: float
    flags: tuple[DetectionFlag, ...]
    assertions: tuple[EvidenceAssertion, ...]
    method: str
    method_version: str
    measurements: Mapping[str, float | None] = field(default_factory=dict)
    # For a nested basin, the identifier of the basin it lies inside.  This is
    # containment of one shape in another.  It is not a connection and is
    # never written to the relationship ledger.
    parent_native_record_id: str | None = None

    @property
    def hierarchy_level(self) -> int:
        return 0 if self.region is None else self.region.hierarchy_level

    @property
    def possible_artifact(self) -> bool:
        return bool(set(self.flags) & ARTIFACT_FLAGS)


def _flags(
    region: DepressionRegion, on_seam: bool, params: DetectionParameters
) -> tuple[DetectionFlag, ...]:
    flags: list[DetectionFlag] = []
    if on_seam:
        flags.append(DetectionFlag.SEAM_OVERLAP)
    if region.interpolated_fraction is not None:
        if region.interpolated_fraction >= params.interpolated_artifact_fraction:
            flags.append(DetectionFlag.MOSTLY_INTERPOLATED)
        elif region.interpolated_fraction > 0:
            flags.append(DetectionFlag.PARTLY_INTERPOLATED)
    if region.significance is None:
        flags.append(DetectionFlag.UNCERTAINTY_UNKNOWN)
    elif region.significance < params.significance_floor:
        flags.append(DetectionFlag.BELOW_UNCERTAINTY)
    if region.adjoins_edge:
        flags.append(DetectionFlag.ADJOINS_EDGE)
    if region.hierarchy_level > 0:
        flags.append(DetectionFlag.NESTED)
    return tuple(flags)


def _shape_tier(flags: Sequence[DetectionFlag]) -> EvidenceTier:
    """How far shape evidence may go before provenance is even considered."""

    weak = set(flags) & {
        DetectionFlag.SEAM_OVERLAP,
        DetectionFlag.MOSTLY_INTERPOLATED,
        DetectionFlag.BELOW_UNCERTAINTY,
        DetectionFlag.UNCERTAINTY_UNKNOWN,
    }
    return EvidenceTier.CANDIDATE if weak else EvidenceTier.SUPPORTING


def discovery_score(region: DepressionRegion, flags: Sequence[DetectionFlag]) -> float:
    """Review-priority score in [0, 100].  Ranking only, never evidence."""

    significance = (
        0.0 if region.significance is None else min(region.significance / 10.0, 1.0)
    )
    relief = min(region.depth_to_diameter / 0.3, 1.0)
    wall = (
        0.0
        if region.mean_wall_slope_deg is None
        else min(region.mean_wall_slope_deg / 35.0, 1.0)
    )
    score = (
        35.0 * significance + 25.0 * relief + 15.0 * region.circularity + 10.0 * wall
    )
    score += 15.0 if not (region.adjoins_edge or region.adjoins_nodata) else 0.0
    if DetectionFlag.SEAM_OVERLAP in flags:
        score *= 0.25
    if DetectionFlag.MOSTLY_INTERPOLATED in flags:
        score *= 0.25
    elif DetectionFlag.PARTLY_INTERPOLATED in flags:
        score *= 0.75
    return round(max(0.0, min(100.0, score)), 2)


def _measurements(region: DepressionRegion) -> dict[str, float | None]:
    return {
        "area_m2": region.area_m2,
        "max_depth_m": region.max_depth_m,
        "mean_depth_m": region.mean_depth_m,
        "volume_m3": region.volume_m3,
        "equivalent_diameter_m": region.equivalent_diameter_m,
        "depth_to_diameter": region.depth_to_diameter,
        "circularity": region.circularity,
        "elongation": region.elongation,
        "rectangularity": region.rectangularity,
        "solidity": region.solidity,
        "mean_wall_slope_deg": region.mean_wall_slope_deg,
        "flat_floor_fraction": region.flat_floor_fraction,
        "interpolated_fraction": region.interpolated_fraction,
        "depth_uncertainty_m": region.depth_uncertainty_m,
        "significance": region.significance,
        "spill_elevation_m": region.spill_elevation_m,
        "floor_elevation_m": region.floor_elevation_m,
        **(
            {
                "hierarchy_level": float(region.hierarchy_level),
                "depth_resolution_m": region.depth_resolution_m,
            }
            if region.hierarchy_level > 0
            else {}
        ),
    }


def _basin_id(xy: tuple[float, float], level: int) -> str:
    # Stable for a given source grid: derived from the deepest cell, not from
    # the order regions happened to be labelled in.  A nested basin can share
    # its deepest cell with the basin around it, so it carries its level; an
    # outer basin's identifier is exactly what it always was.
    base = f"{DETECTION_METHOD}@{xy[0]:.6f},{xy[1]:.6f}"
    return base if level == 0 else f"{base}/n{level}"


def _native_id(grid: SurfaceGrid, region: DepressionRegion) -> str:
    return _basin_id(region.deepest_xy, region.hierarchy_level)


def _parent_id(region: DepressionRegion) -> str | None:
    if region.hierarchy_level == 0 or region.parent_deepest_xy is None:
        return None
    return _basin_id(region.parent_deepest_xy, region.hierarchy_level - 1)


def _shape_assertions(
    source: SourceManifestation,
    tier: EvidenceTier,
    basis: tuple[str, ...],
    region: DepressionRegion,
    shape_statement: str,
) -> list[EvidenceAssertion]:
    common = dict(
        claim_class=ClaimClass.COMPUTED,
        basis=basis,
        source_ids=(source.source_id,),
        method=DETECTION_METHOD,
        method_version=DETECTION_VERSION,
    )
    return [
        EvidenceAssertion(
            dimension=EvidenceDimension.EXISTENCE,
            tier=tier,
            statement=(
                f"closed basin {region.max_depth_m:.2f} m deep over {region.area_m2:.0f} m2 "
                "in the source surface"
            ),
            **common,
        ),
        EvidenceAssertion(
            dimension=EvidenceDimension.MORPHOLOGY,
            tier=tier,
            statement=shape_statement,
            **common,
        ),
    ]


def _seam_hits(grid: SurfaceGrid, seams: Sequence[Seam]) -> np.ndarray | None:
    return seam_mask(grid, seams) if seams else None


def detect_inland(
    grid: SurfaceGrid,
    source: SourceManifestation,
    params: DetectionParameters,
    *,
    geology: GeologicalContext | None = None,
) -> list[Detection]:
    """Closed-basin candidates on a bare-earth terrain model."""

    if grid.kind is not SurfaceKind.TERRAIN_BARE_EARTH:
        raise ValueError(
            "inland detection needs a bare-earth terrain model; "
            f"{grid.kind.value} still carries buildings and vegetation or is not land terrain"
        )
    karst = (
        geology is not None
        and geology.is_karst_prone
        and geology.spatial_state is SpatialState.FULLY_WITHIN
    )
    seams = detect_seams(grid)
    on_seam = _seam_hits(grid, seams)
    detections: list[Detection] = []
    for region in delineate_depressions(
        grid,
        min_depth_m=params.min_depth_m,
        min_area_m2=params.min_area_m2,
        max_regions=params.max_regions,
        nested=params.nested,
        nested_level_step_m=params.nested_level_step_m,
        pit_area_jump=params.pit_area_jump,
    ):
        hit = bool(on_seam is not None and on_seam[region.slices].any())
        flags = _flags(region, hit, params)
        tier = _shape_tier(flags)
        # A disc fills pi/4 (0.785) of its bounding box; an axis-aligned
        # rectangle fills all of it.  The threshold sits between the two.
        rectangular = (
            region.rectangularity >= RECTANGULARITY_THRESHOLD
            and region.flat_floor_fraction is not None
            and region.flat_floor_fraction >= 0.5
        )
        extra: list[EvidenceAssertion] = []
        if set(flags) & ARTIFACT_FLAGS:
            proposed = InlandFeatureClass.UNCLASSIFIED_ANOMALY
            shape = "basin coincides with a survey seam or interpolated cells; may be an artefact"
        elif rectangular:
            proposed = InlandFeatureClass.SURFACE_EXCAVATION
            shape = (
                f"rectilinear flat-floored basin (rectangularity {region.rectangularity:.2f}, "
                f"flat floor {region.flat_floor_fraction:.0%})"
            )
            extra.append(
                EvidenceAssertion(
                    dimension=EvidenceDimension.NATURAL_OR_ARTIFICIAL_ORIGIN,
                    tier=EvidenceTier.CANDIDATE,
                    claim_class=ClaimClass.HYPOTHESIS,
                    basis=("depression_shape",),
                    statement="rectilinear outline and flat floor are consistent with excavation",
                    source_ids=(source.source_id,),
                    origin=Origin.ARTIFICIAL,
                )
            )
        elif karst and region.circularity >= 0.6:
            assert geology is not None
            proposed = InlandFeatureClass.SINKHOLE
            shape = (
                f"near-circular closed basin (circularity {region.circularity:.2f}) "
                f"within mapped unit {geology.unit_name!r}"
            )
            extra.append(
                EvidenceAssertion(
                    dimension=EvidenceDimension.NATURAL_OR_ARTIFICIAL_ORIGIN,
                    tier=EvidenceTier.CANDIDATE,
                    claim_class=ClaimClass.INFERENCE,
                    basis=("depression_shape", "mapped_geological_unit"),
                    statement=(
                        f"round closed basin inside karst-prone unit {geology.unit_name!r}; "
                        "a dissolution origin is plausible, not established"
                    ),
                    source_ids=(source.source_id, geology.source_id),
                    origin=Origin.NATURAL,
                )
            )
        else:
            proposed = InlandFeatureClass.CLOSED_DEPRESSION
            shape = (
                f"closed basin, circularity {region.circularity:.2f}, "
                f"depth/diameter {region.depth_to_diameter:.3f}"
            )
        assertions = (
            _shape_assertions(source, tier, _SHAPE_BASIS, region, shape) + extra
        )
        detections.append(
            Detection(
                namespace=Namespace.ACCESS_POINT_INLAND,
                proposed_class=proposed.value,
                native_record_id=_native_id(grid, region),
                region=region,
                centroid_xy=region.centroid_xy,
                crs=grid.crs,
                discovery_score=discovery_score(region, flags),
                flags=flags,
                assertions=tuple(assertions),
                method=DETECTION_METHOD,
                method_version=DETECTION_VERSION,
                measurements=_measurements(region),
                parent_native_record_id=_parent_id(region),
            )
        )
    return detections


def detect_offshore(
    grid: SurfaceGrid,
    source: SourceManifestation,
    params: DetectionParameters,
) -> list[Detection]:
    """Closed-basin candidates on a bathymetric or topobathymetric surface."""

    if grid.kind not in {SurfaceKind.BATHYMETRY, SurfaceKind.TOPOBATHYMETRY}:
        raise ValueError(
            f"off-shore detection needs a measured bathymetric surface, not {grid.kind.value}"
        )
    seams = detect_seams(grid)
    on_seam = _seam_hits(grid, seams)
    detections: list[Detection] = []
    for region in delineate_depressions(
        grid,
        min_depth_m=params.min_depth_m,
        min_area_m2=params.min_area_m2,
        max_regions=params.max_regions,
        nested=params.nested,
        nested_level_step_m=params.nested_level_step_m,
        pit_area_jump=params.pit_area_jump,
    ):
        hit = bool(on_seam is not None and on_seam[region.slices].any())
        flags = _flags(region, hit, params)
        tier = _shape_tier(flags)
        steep_round = (
            region.circularity >= 0.7
            and region.depth_to_diameter >= 0.15
            and region.mean_wall_slope_deg is not None
            and region.mean_wall_slope_deg >= 20.0
        )
        if set(flags) & ARTIFACT_FLAGS:
            proposed = OffshoreFeatureClass.SURVEY_ARTIFACT
            shape = "basin coincides with a survey seam or interpolated cells; may be an artefact"
        elif steep_round:
            proposed = OffshoreFeatureClass.BLUE_HOLE_CANDIDATE
            shape = (
                f"steep round basin (circularity {region.circularity:.2f}, depth/diameter "
                f"{region.depth_to_diameter:.2f}, wall slope {region.mean_wall_slope_deg:.0f} deg); "
                "an opening is not established by shape"
            )
        else:
            proposed = OffshoreFeatureClass.SEAFLOOR_DEPRESSION
            shape = (
                f"closed seabed basin, circularity {region.circularity:.2f}, "
                f"depth/diameter {region.depth_to_diameter:.3f}"
            )
        detections.append(
            Detection(
                namespace=Namespace.ACCESS_POINT_OFFSHORE,
                proposed_class=proposed.value,
                native_record_id=_native_id(grid, region),
                region=region,
                centroid_xy=region.centroid_xy,
                crs=grid.crs,
                discovery_score=discovery_score(region, flags),
                flags=flags,
                assertions=tuple(
                    _shape_assertions(source, tier, _SEABED_BASIS, region, shape)
                ),
                method=DETECTION_METHOD,
                method_version=DETECTION_VERSION,
                measurements=_measurements(region),
                parent_native_record_id=_parent_id(region),
            )
        )
    return detections


def detect_escarpments(
    grid: SurfaceGrid,
    source: SourceManifestation,
    *,
    min_slope_deg: float,
    min_length_m: float,
    min_elongation: float = 3.0,
) -> list[Detection]:
    """Long steep bands on a seabed surface: escarpments and shelf-edge breaks."""

    if grid.kind not in {SurfaceKind.BATHYMETRY, SurfaceKind.TOPOBATHYMETRY}:
        raise ValueError("escarpment detection needs a measured bathymetric surface")
    if not 0 < min_slope_deg < 90 or min_length_m <= 0:
        raise ValueError(
            "min_slope_deg must be within (0, 90) and min_length_m positive"
        )
    slope = slope_degrees(grid)
    steep = np.where(np.isfinite(slope), slope >= min_slope_deg, False)
    labels = measure.label(steep, connectivity=2)
    cell = math.sqrt(grid.cell_area_m2)
    on_seam = _seam_hits(grid, detect_seams(grid))
    detections: list[Detection] = []
    for prop in measure.regionprops(labels):
        length = float(prop.axis_major_length) * cell
        width = max(float(prop.axis_minor_length) * cell, cell)
        if length < min_length_m or length / width < min_elongation:
            continue
        r0, c0, r1, c1 = prop.bbox
        window = (slice(r0, r1), slice(c0, c1))
        member = labels[window] == prop.label
        band = slope[window][member]
        heights = grid.values[window][member]
        relief = float(np.nanmax(heights) - np.nanmin(heights))
        seam_hit = bool(on_seam is not None and on_seam[window][member].mean() > 0.5)
        flags = (DetectionFlag.SEAM_OVERLAP,) if seam_hit else ()
        tier = EvidenceTier.CANDIDATE if seam_hit else EvidenceTier.SUPPORTING
        cy, cx = prop.centroid
        centre = grid.xy(cy + 0.5, cx + 0.5)
        common = dict(
            claim_class=ClaimClass.COMPUTED,
            basis=("bathymetric_anomaly", "terrain_derivative"),
            source_ids=(source.source_id,),
            method=ESCARPMENT_METHOD,
            method_version=DETECTION_VERSION,
        )
        assertions = (
            EvidenceAssertion(
                dimension=EvidenceDimension.EXISTENCE,
                tier=tier,
                statement=f"steep band {length:.0f} m long with {relief:.1f} m of relief",
                **common,
            ),
            EvidenceAssertion(
                dimension=EvidenceDimension.MORPHOLOGY,
                tier=tier,
                statement=(
                    f"linear steep band, mean slope {float(np.mean(band)):.0f} deg, "
                    f"length/width {length / width:.1f}"
                ),
                **common,
            ),
        )
        detections.append(
            Detection(
                namespace=Namespace.ACCESS_POINT_OFFSHORE,
                proposed_class=(
                    OffshoreFeatureClass.SURVEY_ARTIFACT
                    if seam_hit
                    else OffshoreFeatureClass.ESCARPMENT
                ).value,
                native_record_id=f"{ESCARPMENT_METHOD}@{centre[0]:.6f},{centre[1]:.6f}",
                region=None,
                centroid_xy=centre,
                crs=grid.crs,
                discovery_score=round(
                    min(
                        100.0,
                        40.0 * min(relief / 50.0, 1.0)
                        + 30.0 * min(float(np.mean(band)) / 45.0, 1.0),
                    ),
                    2,
                ),
                flags=flags,
                assertions=assertions,
                method=ESCARPMENT_METHOD,
                method_version=DETECTION_VERSION,
                measurements={
                    "length_m": length,
                    "width_m": width,
                    "relief_m": relief,
                    "mean_slope_deg": float(np.mean(band)),
                },
            )
        )
    detections.sort(key=lambda d: (-d.discovery_score, d.native_record_id))
    return detections


class TruthKind(StrEnum):
    SYNTHETIC_CONTROL = "SYNTHETIC_CONTROL"
    # A published map or inventory compiled by someone else.  Independent of
    # this method, but itself an interpretation with its own positional error;
    # it is a reference to compare with, not ground that was visited.
    PUBLISHED_MAP_REFERENCE = "PUBLISHED_MAP_REFERENCE"
    INDEPENDENT_FIELD_TRUTH = "INDEPENDENT_FIELD_TRUTH"


class EvaluationState(StrEnum):
    SOFTWARE_CONTROL = "SOFTWARE_CONTROL"  # synthetic surfaces: verifies code only
    EXPLORATORY = "EXPLORATORY"  # no independent truth: no accuracy claim
    REFERENCE_COMPARED = "REFERENCE_COMPARED"  # compared with a published map
    MEASURED = "MEASURED"  # scored against independent field truth


_EVALUATION_OUTCOME: dict[TruthKind, tuple[EvaluationState, str]] = {
    TruthKind.SYNTHETIC_CONTROL: (
        EvaluationState.SOFTWARE_CONTROL,
        "scored against synthetic controls: verifies the software, not field accuracy",
    ),
    TruthKind.PUBLISHED_MAP_REFERENCE: (
        EvaluationState.REFERENCE_COMPARED,
        "compared with a published map: agreement with another interpretation, "
        "not field-verified accuracy",
    ),
    TruthKind.INDEPENDENT_FIELD_TRUTH: (
        EvaluationState.MEASURED,
        "scored against independent field truth",
    ),
}


@dataclass(frozen=True, slots=True)
class ReferenceLabel:
    label_id: str
    feature_class: str
    xy: tuple[float, float]
    match_radius: float
    truth_kind: TruthKind
    source_id: str | None = None


@dataclass(frozen=True, slots=True)
class ClassScore:
    feature_class: str
    true_positives: int
    false_positives: int
    false_negatives: int

    @property
    def precision(self) -> float | None:
        total = self.true_positives + self.false_positives
        return None if total == 0 else self.true_positives / total

    @property
    def recall(self) -> float | None:
        total = self.true_positives + self.false_negatives
        return None if total == 0 else self.true_positives / total


@dataclass(frozen=True)
class EvaluationReport:
    state: EvaluationState
    scores: tuple[ClassScore, ...]
    matched: tuple[tuple[str, str], ...]
    unmatched_detections: tuple[str, ...]
    unmatched_labels: tuple[str, ...]
    statement: str


def evaluate(
    detections: Sequence[Detection],
    labels: Sequence[ReferenceLabel],
    *,
    class_sensitive: bool = True,
) -> EvaluationReport:
    """Score detections against reference labels, class by class.

    Matching is one-to-one and nearest-first, so one detection can never
    satisfy two labels and one label can never excuse two detections.  With no
    labels the result is ``EXPLORATORY`` and carries no precision or recall.
    Coordinates must be in the detections' CRS; ``match_radius`` is in CRS
    units.
    """

    if not labels:
        return EvaluationReport(
            state=EvaluationState.EXPLORATORY,
            scores=(),
            matched=(),
            unmatched_detections=tuple(d.native_record_id for d in detections),
            unmatched_labels=(),
            statement=(
                "no reference labels exist; detections are exploratory and no precision "
                "or recall can be stated"
            ),
        )
    kinds = {label.truth_kind for label in labels}
    if len(kinds) != 1:
        raise ValueError(
            "synthetic controls, map references and field truth must be scored separately"
        )
    ids = [label.label_id for label in labels]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate reference label id")

    pairs: list[tuple[float, int, int]] = []
    for i, detection in enumerate(detections):
        for j, label in enumerate(labels):
            if class_sensitive and detection.proposed_class != label.feature_class:
                continue
            dist = math.hypot(
                detection.centroid_xy[0] - label.xy[0],
                detection.centroid_xy[1] - label.xy[1],
            )
            if dist <= label.match_radius:
                pairs.append((dist, i, j))
    pairs.sort()
    used_d: set[int] = set()
    used_l: set[int] = set()
    matched: list[tuple[str, str]] = []
    for _, i, j in pairs:
        if i in used_d or j in used_l:
            continue
        used_d.add(i)
        used_l.add(j)
        matched.append((detections[i].native_record_id, labels[j].label_id))

    classes = sorted(
        {d.proposed_class for d in detections}
        | {label.feature_class for label in labels}
    )
    scores = []
    for name in classes:
        tp = (
            sum(1 for i in used_d if detections[i].proposed_class == name)
            if class_sensitive
            else 0
        )
        if not class_sensitive:
            tp = sum(1 for j in used_l if labels[j].feature_class == name)
        fp = sum(
            1
            for i, d in enumerate(detections)
            if d.proposed_class == name and i not in used_d
        )
        fn = sum(
            1
            for j, label in enumerate(labels)
            if label.feature_class == name and j not in used_l
        )
        scores.append(ClassScore(name, tp, fp, fn))
    state, statement = _EVALUATION_OUTCOME[next(iter(kinds))]
    return EvaluationReport(
        state=state,
        scores=tuple(scores),
        matched=tuple(matched),
        unmatched_detections=tuple(
            d.native_record_id for i, d in enumerate(detections) if i not in used_d
        ),
        unmatched_labels=tuple(
            label.label_id for j, label in enumerate(labels) if j not in used_l
        ),
        statement=statement,
    )

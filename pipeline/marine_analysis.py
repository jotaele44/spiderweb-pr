"""Spiderweb marine/coastal analysis orchestration.

This is the pipeline-facing adapter over :mod:`gebco.marine_evidence`.  It keeps
existing terrestrial terrain-context behavior unchanged while allowing marine
candidate features to be assessed with lineage, coverage, artifact and vertical
reference gates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from gebco.marine_evidence import (
    DepthComparison,
    DepthTransform,
    EvidenceState,
    GeomorphologyClass,
    MarineObservation,
    classify_feature_evidence,
    compare_depths,
    independent_root_ids,
    validate_lineage,
)


@dataclass(frozen=True, slots=True)
class MarineFeatureCandidate:
    feature_id: str
    morphology: GeomorphologyClass
    observation_ids: tuple[str, ...]
    artifact_flags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.feature_id.strip():
            raise ValueError("feature_id must not be empty")
        if not self.observation_ids:
            raise ValueError("candidate must reference at least one observation")
        if len(set(self.observation_ids)) != len(self.observation_ids):
            raise ValueError("candidate observation_ids must be unique")


@dataclass(frozen=True, slots=True)
class MarineFeatureAssessment:
    feature_id: str
    morphology: GeomorphologyClass
    evidence_state: EvidenceState
    observation_count: int
    direct_observation_count: int
    independent_root_count: int
    sensor_types: tuple[str, ...]
    artifact_flags: tuple[str, ...]


def validate_observation_universe(
    observations: Iterable[MarineObservation],
) -> dict[str, MarineObservation]:
    """Build a unique, lineage-valid observation universe.

    Duplicate stable IDs fail closed; whole observations are preserved rather
    than aggregated, so no synthetic record can be manufactured by grouping.
    """

    records: dict[str, MarineObservation] = {}
    for observation in observations:
        if observation.observation_id in records:
            raise ValueError(
                f"duplicate marine observation_id: {observation.observation_id}"
            )
        records[observation.observation_id] = observation
    validate_lineage(records)
    return records


def assess_marine_feature(
    candidate: MarineFeatureCandidate,
    observations: Mapping[str, MarineObservation],
) -> MarineFeatureAssessment:
    """Assess a candidate against the complete supplied observation universe."""

    missing = [item for item in candidate.observation_ids if item not in observations]
    if missing:
        raise KeyError(f"candidate references unknown observation(s): {missing}")

    selected = tuple(observations[item] for item in candidate.observation_ids)
    state = classify_feature_evidence(selected, artifact_flags=candidate.artifact_flags)
    direct = tuple(item for item in selected if item.is_direct_sensor_observation)

    return MarineFeatureAssessment(
        feature_id=candidate.feature_id,
        morphology=candidate.morphology,
        evidence_state=state,
        observation_count=len(selected),
        direct_observation_count=len(direct),
        independent_root_count=len(independent_root_ids(direct)),
        sensor_types=tuple(sorted({item.sensor.value for item in selected})),
        artifact_flags=candidate.artifact_flags,
    )


def compare_temporal_observations(
    earlier: MarineObservation,
    later: MarineObservation,
    *,
    transforms: Iterable[DepthTransform] = (),
) -> DepthComparison:
    """Datum-safe temporal depth comparison for already spatially aligned samples.

    A timestamp on both observations is mandatory and ordering must be strict.
    Horizontal colocation/grid alignment remains an upstream spatial invariant.
    """

    if earlier.observed_at is None or later.observed_at is None:
        raise ValueError("temporal comparison requires observed_at on both observations")
    if later.observed_at <= earlier.observed_at:
        raise ValueError("later observation must be strictly newer than earlier")
    return compare_depths(earlier, later, transforms=transforms)

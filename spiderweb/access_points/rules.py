"""Evidence rules: what a set of assertions is allowed to establish.

These functions are the single place where the registries decide how strong a
statement is.  They only ever lower what a caller asserts; nothing here can
raise a tier, and nothing here reads a name, a count, a distance or a category
as evidence.

The ladder
----------
::

    ANOMALY  ->  FEATURE  ->  OPENING  ->  PASSAGE  ->  CONNECTION

* a geographic anomaly is not automatically a feature;
* a feature is not automatically an access point (it needs a directly observed
  physical opening -- shape alone cannot provide one);
* an access point is not automatically a passage (it needs directly observed
  accessibility);
* a passage is not automatically connected to anything (it needs directly
  observed connectivity of a stated kind).
"""

from __future__ import annotations

from typing import Iterable, Mapping

from .models import EvidenceAssertion, Feature, Observation, SourceManifestation
from .vocabulary import (
    DISCOVERY_ONLY_BASES,
    MORPHOLOGY_ONLY_BASES,
    AdjudicationStatus,
    AssertionRung,
    ClaimClass,
    EvidenceDimension,
    EvidenceTier,
    GeometryBasis,
    ProvenanceState,
    RegistryStatus,
)

RULES_VERSION = "access-point-evidence-rules/1.0"

# Dimensions that shape (terrain / bathymetric morphology) can speak to.
_SHAPE_DIMENSIONS = frozenset(
    {EvidenceDimension.EXISTENCE, EvidenceDimension.MORPHOLOGY}
)

_SPECULATIVE_CLAIMS = frozenset(
    {ClaimClass.HYPOTHESIS, ClaimClass.ASSUMPTION, ClaimClass.UNKNOWN}
)

# What each rung needs, in order.
_RUNG_REQUIREMENTS: tuple[
    tuple[AssertionRung, EvidenceDimension, frozenset[EvidenceTier]], ...
] = (
    (
        AssertionRung.FEATURE,
        EvidenceDimension.EXISTENCE,
        frozenset({EvidenceTier.SUPPORTING, EvidenceTier.DIRECT}),
    ),
    (
        AssertionRung.OPENING,
        EvidenceDimension.PHYSICAL_OPENING,
        frozenset({EvidenceTier.DIRECT}),
    ),
    (
        AssertionRung.PASSAGE,
        EvidenceDimension.ACCESSIBILITY,
        frozenset({EvidenceTier.DIRECT}),
    ),
    (
        AssertionRung.CONNECTION,
        EvidenceDimension.CONNECTIVITY,
        frozenset({EvidenceTier.DIRECT}),
    ),
)


def _cap(tier: EvidenceTier, ceiling: EvidenceTier) -> EvidenceTier:
    return tier if tier <= ceiling else ceiling


def lineage_roots(
    source_ids: Iterable[str], sources: Mapping[str, SourceManifestation]
) -> frozenset[str]:
    """Independent sensor-lineage roots behind a set of sources.

    Derived products inherit the roots of their parents, so two grids built
    from one survey count once.  A source with no root and no parents
    contributes nothing: an unrooted product cannot corroborate anything.
    Unknown source ids contribute nothing and cyclic parent links are ignored.
    """

    roots: set[str] = set()
    seen: set[str] = set()
    stack = list(source_ids)
    while stack:
        sid = stack.pop()
        if sid in seen:
            continue
        seen.add(sid)
        source = sources.get(sid)
        if source is None:
            continue
        if source.parent_source_ids:
            stack.extend(source.parent_source_ids)
            continue
        if source.lineage_root_id and source.lineage_root_id.strip():
            roots.add(source.lineage_root_id.strip())
    return frozenset(roots)


def effective_tier(
    assertion: EvidenceAssertion, sources: Mapping[str, SourceManifestation]
) -> EvidenceTier:
    """The tier an assertion is actually worth.  Never above what was asserted."""

    tier = assertion.tier
    if tier in {EvidenceTier.UNRESOLVED, EvidenceTier.CONTRADICTED}:
        return tier

    bases = {b.strip().lower() for b in assertion.basis}
    if not bases:
        tier = _cap(tier, EvidenceTier.CANDIDATE)
    if bases & DISCOVERY_ONLY_BASES:
        tier = _cap(tier, EvidenceTier.CANDIDATE)
    if (
        bases
        and bases <= MORPHOLOGY_ONLY_BASES
        and assertion.dimension not in _SHAPE_DIMENSIONS
    ):
        tier = _cap(tier, EvidenceTier.CANDIDATE)
    if assertion.claim_class in _SPECULATIVE_CLAIMS:
        tier = _cap(tier, EvidenceTier.CANDIDATE)
    elif assertion.claim_class is ClaimClass.INFERENCE:
        tier = _cap(tier, EvidenceTier.SUPPORTING)

    cited = [sources[s] for s in assertion.source_ids if s in sources]
    if len(cited) != len(assertion.source_ids):
        # An assertion that cites a source the registry does not hold is
        # treated as citing nothing.
        cited = []
    if not any(s.provenance_state is not ProvenanceState.UNREGISTERED for s in cited):
        tier = _cap(tier, EvidenceTier.CANDIDATE)
    if not any(s.is_direct_measurement for s in cited):
        tier = _cap(tier, EvidenceTier.SUPPORTING)
    return tier


def dimension_tiers(
    feature: Feature, sources: Mapping[str, SourceManifestation]
) -> dict[EvidenceDimension, EvidenceTier]:
    """Per-dimension state.  A contradiction is preserved, never averaged away."""

    result = {dimension: EvidenceTier.UNRESOLVED for dimension in EvidenceDimension}
    for assertion in feature.assertions:
        tier = effective_tier(assertion, sources)
        if tier > result[assertion.dimension]:
            result[assertion.dimension] = tier
    return result


def assertion_rung(
    feature: Feature, sources: Mapping[str, SourceManifestation]
) -> AssertionRung:
    tiers = dimension_tiers(feature, sources)
    rung = AssertionRung.ANOMALY
    for candidate, dimension, accepted in _RUNG_REQUIREMENTS:
        if tiers[dimension] not in accepted:
            break
        rung = candidate
    return rung


def contradicted_dimensions(
    feature: Feature, sources: Mapping[str, SourceManifestation]
) -> tuple[EvidenceDimension, ...]:
    tiers = dimension_tiers(feature, sources)
    return tuple(d for d in EvidenceDimension if tiers[d] is EvidenceTier.CONTRADICTED)


def promotion_blockers(
    feature: Feature,
    sources: Mapping[str, SourceManifestation],
    observations: Mapping[str, Observation],
    *,
    producer_identity: str,
) -> tuple[str, ...]:
    """Reasons a feature may not carry ``VERIFIED``.  Empty means permitted.

    ``producer_identity`` is whoever (or whatever process) created the
    evidence.  Acceptance by that same identity is self-certification and does
    not count.
    """

    if not producer_identity or not producer_identity.strip():
        raise ValueError("producer_identity is required to rule out self-certification")
    blockers: list[str] = []

    rung = assertion_rung(feature, sources)
    if rung < AssertionRung.OPENING:
        blockers.append(
            f"evidence reaches {rung.name}; a verified access point needs a directly "
            "observed physical opening"
        )
    contradicted = contradicted_dimensions(feature, sources)
    if contradicted:
        blockers.append(
            "contradicted dimensions: " + ", ".join(d.value for d in contradicted)
        )

    held = [observations[o] for o in feature.observation_ids if o in observations]
    if len(held) != len(feature.observation_ids):
        blockers.append("feature cites observations the registry does not hold")
    if not any(
        o.geometry is not None
        and o.geometry_basis
        not in {GeometryBasis.LOCALITY_LABEL_ONLY, GeometryBasis.NONE}
        for o in held
    ):
        blockers.append("no observation carries source-backed coordinates")

    required = (EvidenceDimension.EXISTENCE, EvidenceDimension.PHYSICAL_OPENING)
    for dimension in required:
        carrying = [
            a
            for a in feature.assertions
            if a.dimension is dimension
            and effective_tier(a, sources)
            in {EvidenceTier.SUPPORTING, EvidenceTier.DIRECT}
        ]
        if not carrying:
            continue  # already reported through the rung
        independent = [
            a
            for a in carrying
            if a.adjudication is AdjudicationStatus.ACCEPTED
            and a.adjudicated_by
            and a.adjudicated_by.strip() != producer_identity.strip()
        ]
        if not independent:
            blockers.append(
                f"{dimension.value} has no assertion accepted by a reviewer independent "
                "of the producer"
            )
        for assertion in carrying:
            for sid in assertion.source_ids:
                source = sources.get(sid)
                if (
                    source is None
                    or source.provenance_state is not ProvenanceState.REGISTERED
                ):
                    blockers.append(
                        f"{dimension.value} cites source {sid} whose exact bytes are not registered"
                    )
    return tuple(dict.fromkeys(blockers))


def permitted_status(
    feature: Feature,
    sources: Mapping[str, SourceManifestation],
    observations: Mapping[str, Observation],
    *,
    producer_identity: str,
) -> RegistryStatus:
    """The strongest status the evidence allows for a non-terminal feature.

    * ``PROVISIONAL_DISCOVERY`` while no cited source is at least referenced by
      a stable identifier (for example an operator screenshot that was never
      attached);
    * ``CANDIDATE`` once it is source-backed;
    * ``VERIFIED`` only with no promotion blockers.
    """

    cited: set[str] = set()
    for assertion in feature.assertions:
        cited.update(assertion.source_ids)
    for oid in feature.observation_ids:
        observation = observations.get(oid)
        if observation is not None:
            cited.add(observation.source_id)
    backed = any(
        sid in sources
        and sources[sid].provenance_state is not ProvenanceState.UNREGISTERED
        for sid in cited
    )
    if not backed:
        return RegistryStatus.PROVISIONAL_DISCOVERY
    if not promotion_blockers(
        feature, sources, observations, producer_identity=producer_identity
    ):
        return RegistryStatus.VERIFIED
    return RegistryStatus.CANDIDATE


_STATUS_ORDER = {
    RegistryStatus.PROVISIONAL_DISCOVERY: 0,
    RegistryStatus.CANDIDATE: 1,
    RegistryStatus.UNDER_REVIEW: 1,
    RegistryStatus.VERIFIED: 2,
}


def status_is_permitted(
    feature: Feature,
    sources: Mapping[str, SourceManifestation],
    observations: Mapping[str, Observation],
    *,
    producer_identity: str,
) -> bool:
    """True if ``feature.status`` does not claim more than the evidence allows."""

    if feature.status in {RegistryStatus.REJECTED, RegistryStatus.SUPERSEDED}:
        return True
    ceiling = permitted_status(
        feature, sources, observations, producer_identity=producer_identity
    )
    return _STATUS_ORDER[feature.status] <= _STATUS_ORDER[ceiling]

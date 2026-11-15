"""Builders shared by the access-point test modules.

Every record built here is synthetic test data.  Identifiers are deliberately
artificial (``TEST-...``) so nothing can be mistaken for a real survey.
"""

from __future__ import annotations

from gebco.marine_evidence import CoverageState, ProductStage, SensorType

from spiderweb.access_points import models as m
from spiderweb.access_points import namespaces as ns
from spiderweb.access_points import vocabulary as v
from spiderweb.access_points.registry import AccessPointRegistry

INLAND = ns.Namespace.ACCESS_POINT_INLAND
OFFSHORE = ns.Namespace.ACCESS_POINT_OFFSHORE
PRODUCER = "test-pipeline"
REVIEWER = "independent-reviewer"
UTC = "2026-11-15T00:00:00Z"
SHA = "a" * 64


def direct_source(root: str = "TEST-SURVEY-001", *, sensor=SensorType.MULTIBEAM_ECHOSOUNDER,
                  parents: tuple[str, ...] = ()) -> m.SourceManifestation:
    """A held, hashed, rooted sensor product: the only kind that is 'direct'."""

    return m.SourceManifestation(
        source_id=ns.source_id("TEST_PROVIDER", root, None, SHA),
        provider="TEST_PROVIDER",
        title=f"synthetic survey {root}",
        native_identifier=root,
        manifestation_sha256=SHA,
        retrieved_utc=UTC,
        lineage_root_id=None if parents else root,
        parent_source_ids=parents,
        product_stage=ProductStage.PROCESSED_OBSERVATION,
        sensor_type=sensor,
        coverage_state=CoverageState.DIRECTLY_OBSERVED,
        provenance_state=v.ProvenanceState.REGISTERED,
    )


def derived_source(name: str, parents: tuple[str, ...]) -> m.SourceManifestation:
    """A grid derived from other sources: registered, but never direct."""

    return m.SourceManifestation(
        source_id=ns.source_id("TEST_PROVIDER", name, None, "b" * 64),
        provider="TEST_PROVIDER",
        title=f"synthetic derived grid {name}",
        native_identifier=name,
        manifestation_sha256="b" * 64,
        retrieved_utc=UTC,
        parent_source_ids=parents,
        product_stage=ProductStage.GRID,
        coverage_state=CoverageState.INTERPOLATED,
        provenance_state=v.ProvenanceState.REGISTERED,
    )


def referenced_source(name: str = "TEST-INVENTORY-001") -> m.SourceManifestation:
    return m.SourceManifestation(
        source_id=ns.source_id("TEST_INVENTORY", name, None, None),
        provider="TEST_INVENTORY",
        title=f"synthetic inventory row {name}",
        native_identifier=name,
        lineage_root_id=name,
        provenance_state=v.ProvenanceState.REFERENCED_ONLY,
    )


def unregistered_source(name: str = "TEST-SCREENSHOT-001") -> m.SourceManifestation:
    return m.SourceManifestation(
        source_id=ns.source_id("TEST_OPERATOR", name, None, None),
        provider="TEST_OPERATOR",
        title=f"synthetic unattached note {name}",
        native_identifier=name,
    )


def point_observation(namespace, source: m.SourceManifestation, native: str,
                      lon: float = -66.0, lat: float = 18.0, **extra) -> m.Observation:
    return m.Observation(
        observation_id=ns.observation_id(namespace, source.source_id, native),
        namespace=namespace,
        source_id=source.source_id,
        native_record_id=native,
        geometry_basis=extra.pop("geometry_basis", v.GeometryBasis.MEASURED),
        geometry={"type": "Point", "coordinates": [lon, lat]},
        horizontal_crs=m.HORIZONTAL_INTERCHANGE_CRS,
        **extra,
    )


def assertion(dimension, tier, source: m.SourceManifestation | None = None, *,
              claim=v.ClaimClass.FACT, basis=("field_survey",), **extra) -> m.EvidenceAssertion:
    if claim is v.ClaimClass.COMPUTED:
        extra.setdefault("method", "test-method")
        extra.setdefault("method_version", "1")
    if dimension is v.EvidenceDimension.CONNECTIVITY:
        extra.setdefault("connectivity_kind", v.ConnectivityKind.HYDRAULIC_CONNECTION)
    return m.EvidenceAssertion(
        dimension=dimension,
        tier=tier,
        claim_class=claim,
        basis=basis,
        statement=extra.pop("statement", f"synthetic statement about {dimension.value}"),
        source_ids=(source.source_id,) if source is not None else (),
        **extra,
    )


def accepted(a: m.EvidenceAssertion, reviewer: str = REVIEWER) -> m.EvidenceAssertion:
    from dataclasses import replace

    return replace(
        a, adjudication=v.AdjudicationStatus.ACCEPTED, adjudicated_by=reviewer, adjudicated_utc=UTC
    )


def registry_with_direct_feature(namespace=OFFSHORE, *, reviewer: str | None = REVIEWER,
                                 feature_class: str | None = None):
    """A registry holding one feature whose opening is directly observed.

    With an independent ``reviewer`` the feature is promotable; with ``None``
    the assertions stay unreviewed.
    """

    registry = AccessPointRegistry(namespace, producer_identity=PRODUCER)
    source = direct_source()
    registry.add_source(source)
    observation = point_observation(namespace, source, "TEST-RECORD-1")
    registry.add_observation(observation)
    existence = assertion(v.EvidenceDimension.EXISTENCE, v.EvidenceTier.DIRECT, source)
    opening = assertion(v.EvidenceDimension.PHYSICAL_OPENING, v.EvidenceTier.DIRECT, source)
    if reviewer is not None:
        existence, opening = accepted(existence, reviewer), accepted(opening, reviewer)
    default = "CAVE_ENTRANCE" if namespace is INLAND else "SUBMARINE_CAVE_ENTRANCE"
    feature = registry.register_candidate(
        feature_class or default,
        observation_ids=(observation.observation_id,),
        assertions=(existence, opening),
        created_utc=UTC,
    )
    return registry, source, observation, feature

"""Identity, evidence and governance controls for the access-point registries.

Each group pairs a positive control (the legitimate thing works) with negative
controls that assert the exact failure.
"""

from __future__ import annotations

import itertools
import json
from dataclasses import replace

import pytest

from federation.spatial_core import canonical_json_sha256
from spiderweb.access_points import identity as ident
from spiderweb.access_points import models as m
from spiderweb.access_points import namespaces as ns
from spiderweb.access_points import relationships as rel
from spiderweb.access_points import rules
from spiderweb.access_points import vocabulary as v
from spiderweb.access_points.registry import (
    AccessPointRegistry,
    PromotionError,
    RegistryConflictError,
    RegistryIntegrityError,
)
from tests import access_points_support as sup

N = ns.Namespace
D = v.EvidenceDimension
T = v.EvidenceTier
INLAND, OFFSHORE = sup.INLAND, sup.OFFSHORE


# ── Terminology collision ────────────────────────────────────────────────────

LEGACY = [
    ("ILAP_AREA_NORTH_001", N.INVESTIGATION_ILAP_AREA),
    ("ILAP_CLUSTER_NORTH_001", N.INVESTIGATION_ILAP_CLUSTER),
    ("ILAP_AREA_UNASSIGNED_000", N.INVESTIGATION_ILAP_AREA),
    ("ILAP_FL12345", N.AVIATION_ILAP_PATH),
    ("ilap", N.AVIATION_ILAP_PATH),
    ("airspace_ilap_candidates.geojson", N.AVIATION_ILAP_PATH),
    ("ilap_corridor_candidate", N.AVIATION_ILAP_PATH),
    ("ILAP-WEIGHT-RECURRENCE", N.AVIATION_ILAP_PATH),
    ("ILAP-GRID-0.05DEG", N.AVIATION_ILAP_PATH),
    ("ilap_status", N.AVIATION_ILAP_PATH),
    ("SW-ALL-0000012", N.ANALYTIC_ILAP_INFRASTRUCTURE_LINKED),
    ("ilap_master_nodes", N.ANALYTIC_ILAP_INFRASTRUCTURE_LINKED),
    ("ILAP-Hydro-Karst", N.ANALYTIC_ILAP_INFRASTRUCTURE_LINKED),
    ("ilap_type", N.ANALYTIC_ILAP_INFRASTRUCTURE_LINKED),
    ("PIN_AC_ILAPMASTER_000001", N.ANALYTIC_ILAP_INFRASTRUCTURE_LINKED),
    ("fic_osap_final_set_v3", N.SOURCE_FIC_OSAP),
    ("FIC_OSAP_ILAP_Links_v4", N.SOURCE_FIC_OSAP),
    ("OSAP_to_ILAP", N.SOURCE_FIC_OSAP),
    ("OSAP_Primary_Ring", N.SOURCE_FIC_OSAP),
    ("PIN_AC_FICOSAPILA_000007", N.SOURCE_FIC_OSAP),
    ("ILAP_SCORE", N.TERRAIN_ILAP_SCORE),
    ("ilap_dem_anomalies", N.TERRAIN_ILAP_SCORE),
    ("FERRO-0042", N.SOURCE_FERROCARRIL_ILAP),
    ("ferrocarril_ilap_candidates", N.SOURCE_FERROCARRIL_ILAP),
    ("ilap_context", N.ENRICHMENT_ILAP_CONTEXT),
    ("ilap_context_distance_m", N.ENRICHMENT_ILAP_CONTEXT),
]


@pytest.mark.parametrize("identifier, namespace", LEGACY)
def test_legacy_spelling_keeps_its_own_meaning(identifier, namespace):
    found = ns.classify_identifier(identifier)
    assert found is not None
    assert found.namespace is namespace
    assert found.namespace not in ns.REGISTRY_NAMESPACES
    assert found.kind is ns.IdentifierKind.LEGACY


@pytest.mark.parametrize("bare", ["ILAP", "OSAP", "Ilap", "osap", "FIC", "fic"])
def test_bare_acronym_is_refused_as_ambiguous(bare):
    with pytest.raises(ns.NamespaceCollisionError):
        ns.classify_identifier(bare)


def test_registry_identifiers_classify_to_their_own_registry_only():
    for sequence in range(1, 400, 7):
        inland = ns.feature_id(INLAND, sequence)
        offshore = ns.feature_id(OFFSHORE, sequence)
        assert ns.classify_identifier(inland).namespace is INLAND
        assert ns.classify_identifier(offshore).namespace is OFFSHORE
        assert not ns.is_feature_id(inland, OFFSHORE)
        assert not ns.is_feature_id(offshore, INLAND)
        # Same sequence number, different registry: never the same thing.
        assert not ns.same_identity(
            ns.TypedRef(INLAND, inland), ns.TypedRef(OFFSHORE, offshore)
        )


def test_same_spelling_in_two_namespaces_is_not_one_identity():
    a = ns.TypedRef(INLAND, "INAP-PR-000001")
    b = ns.TypedRef(N.AVIATION_ILAP_PATH, "INAP-PR-000001")
    assert not ns.same_identity(a, b)
    with pytest.raises(ns.NamespaceCollisionError):
        ns.require_same_namespace(a, b)
    assert ns.same_identity(a, ns.TypedRef(INLAND, "INAP-PR-000001"))


def test_provisional_label_is_a_label_not_an_identity():
    found = ns.classify_identifier("OSAP-SEED-003")
    assert found.namespace is OFFSHORE
    assert found.kind is ns.IdentifierKind.PROVISIONAL_LABEL
    assert not ns.is_feature_id("OSAP-SEED-003", OFFSHORE)
    with pytest.raises(ns.NamespaceCollisionError):
        ns.feature_sequence("OSAP-SEED-003", OFFSHORE)


def test_typed_ref_refuses_a_namespace_the_spelling_contradicts():
    assert ns.typed_ref("OFAP-PR-000004").namespace is OFFSHORE
    with pytest.raises(ns.NamespaceCollisionError):
        ns.typed_ref("OFAP-PR-000004", INLAND)
    with pytest.raises(ns.NamespaceCollisionError):
        ns.typed_ref("ILAP_AREA_X_001", INLAND)
    with pytest.raises(ns.NamespaceCollisionError):
        ns.typed_ref("an-unknown-thing")


@pytest.mark.parametrize(
    "bad",
    [
        "inland_ilap_nodes",
        "ILAP_nodes",
        "osap_candidates",
        "fic_layer",
        "fic_osap_new",
        "aasb_x",
        "access-osap-points",
        "my.fic.layer",
    ],
)
def test_new_machine_identifier_refuses_reserved_tokens(bad):
    with pytest.raises(ns.ReservedTokenError):
        ns.validate_new_machine_identifier(bad)


@pytest.mark.parametrize(
    "ok",
    [
        "inap_candidate_nodes",
        "ofap_evidence_links",
        "official_records",
        "pacific_shelf",
        "access_point_registry",
        "traffic_layer",
    ],
)
def test_new_machine_identifier_accepts_lookalikes(ok):
    assert ns.validate_new_machine_identifier(ok) == ok


def test_package_and_committed_artefacts_use_no_reserved_token():
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    names = [p.stem for p in (root / "spiderweb" / "access_points").glob("*.py")]
    names += [p.name for p in (root / "registry" / "access_points").glob("*")]
    names += [p.stem for p in (root / "schemas").glob("access_point*")]
    for name in names:
        ns.validate_new_machine_identifier(name)
    for member in (
        list(v.InlandFeatureClass)
        + list(v.OffshoreFeatureClass)
        + list(v.RelationshipType)
    ):
        ns.validate_new_machine_identifier(member.value)


def test_feature_id_is_opaque_and_bounded():
    assert ns.feature_id(INLAND, 1) == "INAP-PR-000001"
    for bad in (0, 1_000_000, -3):
        with pytest.raises(ValueError):
            ns.feature_id(INLAND, bad)
    with pytest.raises(TypeError):
        ns.feature_id(INLAND, True)
    with pytest.raises(ns.NamespaceCollisionError):
        ns.feature_id(N.AVIATION_ILAP_PATH, 1)


def test_source_and_observation_identity_follow_content():
    a = ns.source_id("P", "X", None, "a" * 64)
    assert a == ns.source_id("P", "X", None, "a" * 64)
    assert a != ns.source_id(
        "P", "X", None, "b" * 64
    )  # revised bytes, new manifestation
    with pytest.raises(ValueError):
        ns.source_id("P", None, None, None)
    assert ns.observation_id(INLAND, a, "r1") != ns.observation_id(OFFSHORE, a, "r1")
    with pytest.raises(ValueError):
        ns.observation_id(INLAND, a, "  ")


# ── Models ───────────────────────────────────────────────────────────────────


def test_locality_label_observation_cannot_carry_coordinates():
    source = sup.unregistered_source()
    oid = ns.observation_id(OFFSHORE, source.source_id, "OSAP-SEED-001")
    ok = m.Observation(
        oid,
        OFFSHORE,
        source.source_id,
        "OSAP-SEED-001",
        v.GeometryBasis.LOCALITY_LABEL_ONLY,
        locality_label="Northwest Aguadilla",
    )
    assert ok.geometry is None
    with pytest.raises(ValueError, match="locality-label"):
        m.Observation(
            oid,
            OFFSHORE,
            source.source_id,
            "OSAP-SEED-001",
            v.GeometryBasis.LOCALITY_LABEL_ONLY,
            locality_label="x",
            geometry={"type": "Point", "coordinates": [-67.2, 18.5]},
            horizontal_crs="OGC:CRS84",
        )
    with pytest.raises(ValueError):
        m.Observation(
            oid,
            OFFSHORE,
            source.source_id,
            "OSAP-SEED-001",
            v.GeometryBasis.LOCALITY_LABEL_ONLY,
        )  # locality label required
    with pytest.raises(ValueError):
        m.Observation(
            oid, OFFSHORE, source.source_id, "OSAP-SEED-001", v.GeometryBasis.MEASURED
        )


def test_observation_refuses_undeclared_crs_bad_coordinates_and_orphan_values():
    source = sup.direct_source()
    with pytest.raises(ValueError, match="OGC:CRS84"):
        (
            sup.point_observation(OFFSHORE, source, "r", horizontal_crs=None)
            if False
            else m.Observation(
                ns.observation_id(OFFSHORE, source.source_id, "r"),
                OFFSHORE,
                source.source_id,
                "r",
                v.GeometryBasis.MEASURED,
                geometry={"type": "Point", "coordinates": [-66, 18]},
            )
        )
    for coords in ([-200.0, 18.0], [-66.0, 95.0], [float("nan"), 18.0]):
        with pytest.raises(ValueError):
            sup.point_observation(OFFSHORE, source, "r", lon=coords[0], lat=coords[1])
    with pytest.raises(ValueError, match="not a measurement"):
        sup.point_observation(OFFSHORE, source, "r", value_m=12.0)
    with pytest.raises(ValueError):
        sup.point_observation(OFFSHORE, source, "r", horizontal_uncertainty_m=-1.0)


def test_registered_source_needs_hash_and_feature_class_is_per_registry():
    with pytest.raises(ValueError, match="SHA-256"):
        m.SourceManifestation(
            ns.source_id("P", "x", None, None),
            "P",
            "t",
            native_identifier="x",
            provenance_state=v.ProvenanceState.REGISTERED,
        )
    with pytest.raises(ValueError):
        m.Feature(ns.feature_id(INLAND, 1), INLAND, "SEAFLOOR_DEPRESSION")
    with pytest.raises(ValueError):
        m.Feature(ns.feature_id(INLAND, 1), OFFSHORE, "SEAFLOOR_DEPRESSION")
    assert m.Feature(
        ns.feature_id(OFFSHORE, 1), OFFSHORE, "SEAFLOOR_DEPRESSION"
    ).status is (v.RegistryStatus.PROVISIONAL_DISCOVERY)


def test_temporal_contradiction_and_connectivity_kind_are_enforced():
    with pytest.raises(ValueError, match="valid_from"):
        sup.assertion(
            D.EXISTENCE, T.CANDIDATE, valid_from="2026-02-01", valid_to="2026-01-01"
        )
    with pytest.raises(ValueError, match="which kind"):
        m.EvidenceAssertion(
            D.CONNECTIVITY, T.CANDIDATE, v.ClaimClass.HYPOTHESIS, ("x",), "s"
        )
    with pytest.raises(ValueError):
        sup.assertion(
            D.EXISTENCE,
            T.CANDIDATE,
            connectivity_kind=v.ConnectivityKind.HYDRAULIC_CONNECTION,
        )
    with pytest.raises(ValueError, match="method"):
        m.EvidenceAssertion(
            D.EXISTENCE, T.CANDIDATE, v.ClaimClass.COMPUTED, ("x",), "s"
        )


# ── Evidence rules ───────────────────────────────────────────────────────────


def _feature(*assertions, namespace=OFFSHORE):
    return m.Feature(
        ns.feature_id(namespace, 1),
        namespace,
        "UNCLASSIFIED_ANOMALY",
        assertions=tuple(assertions),
    )


def test_effective_tier_never_exceeds_the_asserted_tier():
    direct = sup.direct_source()
    grid = sup.derived_source("grid", (direct.source_id,))
    held = {direct.source_id: direct, grid.source_id: grid}
    bases = [
        (),
        ("field_survey",),
        ("proximity_only",),
        ("morphology",),
        ("name_only", "field_survey"),
        ("contract_record",),
        ("depression_shape", "terrain_derivative"),
    ]
    for dimension, tier, claim, basis, source in itertools.product(
        D, T, v.ClaimClass, bases, (None, direct, grid)
    ):
        a = sup.assertion(dimension, tier, source, claim=claim, basis=basis)
        assert rules.effective_tier(a, held) <= tier


@pytest.mark.parametrize(
    "dimension",
    [
        D.PHYSICAL_OPENING,
        D.ACCESSIBILITY,
        D.FUNCTION,
        D.CONNECTIVITY,
        D.NATURAL_OR_ARTIFICIAL_ORIGIN,
    ],
)
def test_shape_alone_cannot_establish_more_than_shape(dimension):
    source = sup.direct_source()
    held = {source.source_id: source}
    for basis in (
        ("morphology",),
        ("bathymetric_anomaly", "depression_shape"),
        ("discovery_score",),
        ("acoustic_reflector",),
        ("backscatter_texture",),
    ):
        a = sup.assertion(dimension, T.DIRECT, source, basis=basis)
        assert rules.effective_tier(a, held) is T.CANDIDATE
    # Positive control: shape does speak to existence and morphology.
    for shape_dimension in (D.EXISTENCE, D.MORPHOLOGY):
        a = sup.assertion(
            shape_dimension, T.DIRECT, source, basis=("bathymetric_anomaly",)
        )
        assert rules.effective_tier(a, held) is T.DIRECT


@pytest.mark.parametrize("basis", sorted(v.DISCOVERY_ONLY_BASES))
def test_discovery_only_bases_never_support_anything(basis):
    source = sup.direct_source()
    a = sup.assertion(D.EXISTENCE, T.DIRECT, source, basis=(basis, "field_survey"))
    assert rules.effective_tier(a, {source.source_id: source}) is T.CANDIDATE


def test_claim_class_and_provenance_caps():
    direct = sup.direct_source()
    referenced = sup.referenced_source()
    unregistered = sup.unregistered_source()
    held = {s.source_id: s for s in (direct, referenced, unregistered)}
    for claim in (
        v.ClaimClass.HYPOTHESIS,
        v.ClaimClass.ASSUMPTION,
        v.ClaimClass.UNKNOWN,
    ):
        assert (
            rules.effective_tier(
                sup.assertion(D.EXISTENCE, T.DIRECT, direct, claim=claim), held
            )
            is T.CANDIDATE
        )
    assert (
        rules.effective_tier(
            sup.assertion(D.EXISTENCE, T.DIRECT, direct, claim=v.ClaimClass.INFERENCE),
            held,
        )
        is T.SUPPORTING
    )
    assert (
        rules.effective_tier(sup.assertion(D.EXISTENCE, T.DIRECT, referenced), held)
        is T.SUPPORTING
    )
    assert (
        rules.effective_tier(sup.assertion(D.EXISTENCE, T.DIRECT, unregistered), held)
        is T.CANDIDATE
    )
    assert (
        rules.effective_tier(sup.assertion(D.EXISTENCE, T.DIRECT, None), held)
        is T.CANDIDATE
    )
    assert (
        rules.effective_tier(
            sup.assertion(D.EXISTENCE, T.DIRECT, direct, basis=()), held
        )
        is T.CANDIDATE
    )
    # A source the registry does not hold is worth nothing.
    assert (
        rules.effective_tier(sup.assertion(D.EXISTENCE, T.DIRECT, direct), {})
        is T.CANDIDATE
    )
    assert (
        rules.effective_tier(sup.assertion(D.EXISTENCE, T.DIRECT, direct), held)
        is T.DIRECT
    )


def test_the_ladder_requires_every_rung_below():
    source = sup.direct_source()
    held = {source.source_id: source}
    direct = lambda d: sup.assertion(d, T.DIRECT, source)  # noqa: E731
    assert rules.assertion_rung(_feature(), held) is v.AssertionRung.ANOMALY
    assert (
        rules.assertion_rung(_feature(direct(D.EXISTENCE)), held)
        is v.AssertionRung.FEATURE
    )
    assert (
        rules.assertion_rung(
            _feature(direct(D.EXISTENCE), direct(D.PHYSICAL_OPENING)), held
        )
        is v.AssertionRung.OPENING
    )
    assert (
        rules.assertion_rung(
            _feature(
                direct(D.EXISTENCE), direct(D.PHYSICAL_OPENING), direct(D.ACCESSIBILITY)
            ),
            held,
        )
        is v.AssertionRung.PASSAGE
    )
    assert (
        rules.assertion_rung(
            _feature(
                direct(D.EXISTENCE),
                direct(D.PHYSICAL_OPENING),
                direct(D.ACCESSIBILITY),
                direct(D.CONNECTIVITY),
            ),
            held,
        )
        is v.AssertionRung.CONNECTION
    )
    # An opening without established existence is still only an anomaly.
    assert (
        rules.assertion_rung(_feature(direct(D.PHYSICAL_OPENING)), held)
        is v.AssertionRung.ANOMALY
    )
    # Accessibility and connectivity without an opening do not skip rungs.
    assert (
        rules.assertion_rung(
            _feature(
                direct(D.EXISTENCE), direct(D.ACCESSIBILITY), direct(D.CONNECTIVITY)
            ),
            held,
        )
        is v.AssertionRung.FEATURE
    )
    # Supporting evidence of an opening is not a directly observed opening.
    assert (
        rules.assertion_rung(
            _feature(
                direct(D.EXISTENCE),
                sup.assertion(D.PHYSICAL_OPENING, T.SUPPORTING, source),
            ),
            held,
        )
        is v.AssertionRung.FEATURE
    )


def test_contradiction_is_preserved_and_blocks_the_rung():
    source = sup.direct_source()
    held = {source.source_id: source}
    feature = _feature(
        sup.assertion(D.EXISTENCE, T.DIRECT, source),
        sup.assertion(D.PHYSICAL_OPENING, T.DIRECT, source),
        sup.assertion(
            D.PHYSICAL_OPENING,
            T.CONTRADICTED,
            source,
            statement="diver found solid rock",
        ),
    )
    assert rules.dimension_tiers(feature, held)[D.PHYSICAL_OPENING] is T.CONTRADICTED
    assert rules.assertion_rung(feature, held) is v.AssertionRung.FEATURE
    assert rules.contradicted_dimensions(feature, held) == (D.PHYSICAL_OPENING,)


def test_derived_products_of_one_survey_are_one_lineage_root():
    root = sup.direct_source("TEST-SURVEY-A")
    other = sup.direct_source("TEST-SURVEY-B")
    dem = sup.derived_source("dem", (root.source_id,))
    hillshade = sup.derived_source("hillshade", (dem.source_id,))
    fused = sup.derived_source("fused", (dem.source_id, other.source_id))
    rootless = sup.unregistered_source()
    held = {s.source_id: s for s in (root, other, dem, hillshade, fused, rootless)}
    assert rules.lineage_roots(
        [root.source_id, dem.source_id, hillshade.source_id], held
    ) == {"TEST-SURVEY-A"}
    assert rules.lineage_roots([fused.source_id], held) == {
        "TEST-SURVEY-A",
        "TEST-SURVEY-B",
    }
    assert rules.lineage_roots([rootless.source_id], held) == frozenset()
    assert rules.lineage_roots(["APSRC-" + "0" * 16], held) == frozenset()
    # A cyclic parent link terminates and manufactures no root.
    a = replace(
        dem, source_id="APSRC-" + "1" * 16, parent_source_ids=("APSRC-" + "2" * 16,)
    )
    b = replace(
        dem, source_id="APSRC-" + "2" * 16, parent_source_ids=("APSRC-" + "1" * 16,)
    )
    assert (
        rules.lineage_roots([a.source_id], {a.source_id: a, b.source_id: b})
        == frozenset()
    )


# ── Registry ─────────────────────────────────────────────────────────────────


def test_candidates_are_never_promoted_automatically():
    registry, _, _, feature = sup.registry_with_direct_feature()
    assert feature.status is v.RegistryStatus.CANDIDATE
    assert registry.rung(feature.feature_id) is v.AssertionRung.OPENING
    assert registry.blockers(feature.feature_id) == ()


def test_independent_reviewer_can_promote_fully_evidenced_feature():
    registry, _, _, feature = sup.registry_with_direct_feature()
    promoted = registry.promote(feature.feature_id, reviewer=sup.REVIEWER, utc=sup.UTC)
    assert promoted.status is v.RegistryStatus.VERIFIED
    assert registry.counts()["features_by_status"]["VERIFIED"] == 1


def test_producer_cannot_certify_its_own_evidence():
    registry, _, _, feature = sup.registry_with_direct_feature()
    with pytest.raises(PromotionError, match="own evidence"):
        registry.promote(feature.feature_id, reviewer=sup.PRODUCER, utc=sup.UTC)
    # Acceptance recorded by the producer itself does not count either.
    self_reviewed, _, _, f2 = sup.registry_with_direct_feature(reviewer=sup.PRODUCER)
    with pytest.raises(PromotionError) as caught:
        self_reviewed.promote(f2.feature_id, reviewer=sup.REVIEWER, utc=sup.UTC)
    assert any("independent" in b for b in caught.value.blockers)
    unreviewed, _, _, f3 = sup.registry_with_direct_feature(reviewer=None)
    with pytest.raises(PromotionError):
        unreviewed.promote(f3.feature_id, reviewer=sup.REVIEWER, utc=sup.UTC)
    with pytest.raises(PromotionError):
        registry.promote(feature.feature_id, reviewer="  ", utc=sup.UTC)


def test_morphology_only_candidate_cannot_be_verified():
    registry = AccessPointRegistry(OFFSHORE, producer_identity=sup.PRODUCER)
    source = sup.direct_source()
    registry.add_source(source)
    observation = sup.point_observation(OFFSHORE, source, "r1")
    registry.add_observation(observation)
    shape = ("bathymetric_anomaly", "depression_shape")
    feature = registry.register_candidate(
        "BLUE_HOLE_CANDIDATE",
        observation_ids=(observation.observation_id,),
        assertions=(
            sup.accepted(sup.assertion(D.EXISTENCE, T.DIRECT, source, basis=shape)),
            sup.accepted(
                sup.assertion(D.PHYSICAL_OPENING, T.DIRECT, source, basis=shape)
            ),
        ),
    )
    assert registry.rung(feature.feature_id) is v.AssertionRung.FEATURE
    with pytest.raises(PromotionError) as caught:
        registry.promote(feature.feature_id, reviewer=sup.REVIEWER, utc=sup.UTC)
    assert any("physical opening" in b for b in caught.value.blockers)


def test_status_cannot_claim_more_than_the_evidence():
    registry, _, observation, feature = sup.registry_with_direct_feature(reviewer=None)
    with pytest.raises(PromotionError):
        registry.set_status(feature.feature_id, v.RegistryStatus.VERIFIED, utc=sup.UTC)
    with pytest.raises(PromotionError):
        registry.add_feature(
            replace(
                feature,
                feature_id=ns.feature_id(OFFSHORE, 2),
                status=v.RegistryStatus.VERIFIED,
            )
        )
    rejected = registry.set_status(
        feature.feature_id, v.RegistryStatus.REJECTED, utc=sup.UTC
    )
    assert rejected.status is v.RegistryStatus.REJECTED
    with pytest.raises(PromotionError, match="REJECTED"):
        registry.promote(feature.feature_id, reviewer=sup.REVIEWER, utc=sup.UTC)


def test_provisional_seed_stays_provisional():
    registry = AccessPointRegistry(OFFSHORE, producer_identity=sup.PRODUCER)
    source = sup.unregistered_source("OSAP-SEED-001")
    registry.add_source(source)
    observation = m.Observation(
        ns.observation_id(OFFSHORE, source.source_id, "OSAP-SEED-001"),
        OFFSHORE,
        source.source_id,
        "OSAP-SEED-001",
        v.GeometryBasis.LOCALITY_LABEL_ONLY,
        locality_label="Northwest Aguadilla",
    )
    registry.add_observation(observation)
    feature = registry.register_candidate(
        "UNCLASSIFIED_ANOMALY",
        observation_ids=(observation.observation_id,),
        assertions=(
            sup.assertion(
                D.EXISTENCE, T.DIRECT, source, basis=("screenshot_annotation",)
            ),
        ),
        provisional_labels=("OSAP-SEED-001",),
    )
    assert feature.status is v.RegistryStatus.PROVISIONAL_DISCOVERY
    assert registry.rung(feature.feature_id) is v.AssertionRung.ANOMALY
    with pytest.raises(PromotionError) as caught:
        registry.promote(feature.feature_id, reviewer=sup.REVIEWER, utc=sup.UTC)
    assert any("coordinates" in b for b in caught.value.blockers)
    with pytest.raises(PromotionError):
        registry.set_status(feature.feature_id, v.RegistryStatus.CANDIDATE, utc=sup.UTC)


def test_ingestion_is_idempotent_and_conflicts_are_refused():
    registry, source, observation, feature = sup.registry_with_direct_feature()
    before = registry.counts()
    assert registry.add_source(source) is False
    assert registry.add_observation(observation) is False
    assert registry.add_feature(feature) is False
    assert registry.counts() == before
    with pytest.raises(RegistryConflictError):
        registry.add_source(replace(source, title="a different title"))
    with pytest.raises(RegistryConflictError):
        registry.add_observation(replace(observation, raw_label="changed"))
    with pytest.raises(RegistryConflictError):
        registry.add_feature(replace(feature, notes="changed"))


def test_dangling_references_and_foreign_records_are_refused():
    registry, source, observation, feature = sup.registry_with_direct_feature()
    with pytest.raises(RegistryIntegrityError, match="unknown parent"):
        registry.add_source(sup.derived_source("orphan", ("APSRC-" + "9" * 16,)))
    stranger = sup.direct_source("TEST-SURVEY-ZZZ")
    with pytest.raises(RegistryIntegrityError, match="unknown source"):
        registry.add_observation(sup.point_observation(OFFSHORE, stranger, "x"))
    inland_obs = sup.point_observation(INLAND, source, "x")
    with pytest.raises(ns.NamespaceCollisionError):
        registry.add_observation(inland_obs)
    with pytest.raises(RegistryIntegrityError):
        registry.register_candidate(
            "ESCARPMENT",
            assertions=(sup.assertion(D.EXISTENCE, T.CANDIDATE, stranger),),
        )
    with pytest.raises(ns.NamespaceCollisionError):
        registry.feature("INAP-PR-000001")
    with pytest.raises(KeyError):
        registry.feature("OFAP-PR-000999")


def test_same_name_different_feature_and_duplicate_geometry_stay_separate():
    registry = AccessPointRegistry(INLAND, producer_identity=sup.PRODUCER)
    source = sup.direct_source()
    registry.add_source(source)
    ids = []
    for native in ("TEST-A", "TEST-B"):
        observation = sup.point_observation(
            INLAND, source, native, raw_label="Cueva del Indio"
        )
        registry.add_observation(observation)
        ids.append(
            registry.register_candidate(
                "CAVE_ENTRANCE",
                observation_ids=(observation.observation_id,),
                raw_names=("Cueva del Indio",),
            ).feature_id
        )
    assert len(set(ids)) == 2
    assert registry.counts()["features"] == 2 and registry.counts()["observations"] == 2


def _rich_registry():
    registry, source, observation, feature = sup.registry_with_direct_feature()
    grid = sup.derived_source("grid", (source.source_id,))
    registry.add_source(grid)
    second = sup.point_observation(OFFSHORE, grid, "TEST-RECORD-2", lon=-66.1, lat=17.9)
    registry.add_observation(second)
    registry.register_candidate(
        "SEAFLOOR_DEPRESSION",
        observation_ids=(second.observation_id,),
        assertions=(sup.assertion(D.EXISTENCE, T.SUPPORTING, grid),),
    )
    registry.promote(feature.feature_id, reviewer=sup.REVIEWER, utc=sup.UTC)
    return registry


def test_document_round_trip_is_stable_and_counts_close():
    registry = _rich_registry()
    document = registry.to_document()
    text = json.dumps(document, sort_keys=True)
    again = AccessPointRegistry.from_document(json.loads(text))
    assert json.dumps(again.to_document(), sort_keys=True) == text
    assert (
        json.dumps(_rich_registry().to_document(), sort_keys=True) == text
    )  # deterministic
    assert AccessPointRegistry.counts_close(document["counts"])
    assert document["counts"]["features_by_status"]["VERIFIED"] == 1


def _rehash(document):
    document["content_sha256"] = canonical_json_sha256(
        {k: val for k, val in document.items() if k != "content_sha256"}
    )
    return document


def test_corrupted_documents_do_not_load(tmp_path):
    good = _rich_registry().to_document()

    def mutated(fn, rehash=True):
        copy = json.loads(json.dumps(good))
        fn(copy)
        return _rehash(copy) if rehash else copy

    cases = {
        "edit without rehash": mutated(
            lambda d: d["features"][0].update(notes="x"), rehash=False
        ),
        "wrong schema": mutated(lambda d: d.update(schema="something/9.9")),
        "wrong namespace": mutated(lambda d: d.update(namespace="access_point.inland")),
        "counts edited": mutated(lambda d: d["counts"].update(features=99)),
        "unevidenced verified": mutated(
            lambda d: d["features"][1].update(status="VERIFIED")
        ),
        "dropped source": mutated(lambda d: d["sources"].pop(0)),
        "dangling supersession": mutated(
            lambda d: d["features"][0].update(supersedes=["OFAP-PR-000777"])
        ),
        "legacy namespace": mutated(lambda d: d.update(namespace="aviation.ilap_path")),
    }
    for name, document in cases.items():
        with pytest.raises(RegistryIntegrityError):
            AccessPointRegistry.from_document(document)
            pytest.fail(f"corrupt document accepted: {name}")
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(good)[:-40], encoding="utf-8")
    with pytest.raises(RegistryIntegrityError):
        AccessPointRegistry.load(path)
    saved = _rich_registry().save(tmp_path / "ok.json")
    assert (
        AccessPointRegistry.load(saved).to_document()["content_sha256"]
        == good["content_sha256"]
    )


# ── Identity ─────────────────────────────────────────────────────────────────


def _refs(namespace, prefix, count):
    return [ns.TypedRef(namespace, f"{prefix}-{i:03d}") for i in range(count)]


def test_identity_is_never_proven_by_name_distance_or_count():
    a, b = ns.TypedRef(INLAND, "INAP-PR-000001"), ns.TypedRef(INLAND, "INAP-PR-000002")
    for basis in (
        ("name_only",),
        ("proximity_only",),
        ("equal_count",),
        ("normalized_coordinates",),
        ("same_category",),
        ("normalized_name_only", "proximity_only"),
    ):
        link = ident.Correspondence(
            a,
            b,
            basis,
            "s",
            adjudication=v.AdjudicationStatus.ACCEPTED,
            adjudicated_by=sup.REVIEWER,
        )
        assert (
            ident.identity_semantics(link, producer_identity=sup.PRODUCER)
            == "CANDIDATE_NOT_IDENTITY"
        )
        assert ident.is_discovery_only(link)
    authoritative = ident.Correspondence(a, b, ("field_verified_same_feature",), "s")
    assert (
        ident.identity_semantics(authoritative, producer_identity=sup.PRODUCER)
        == "CANDIDATE_NOT_IDENTITY"
    )
    self_accepted = replace(
        authoritative,
        adjudication=v.AdjudicationStatus.ACCEPTED,
        adjudicated_by=sup.PRODUCER,
    )
    assert (
        ident.identity_semantics(self_accepted, producer_identity=sup.PRODUCER)
        == "CANDIDATE_NOT_IDENTITY"
    )
    accepted = replace(self_accepted, adjudicated_by=sup.REVIEWER)
    assert (
        ident.identity_semantics(accepted, producer_identity=sup.PRODUCER)
        == "IDENTITY_BINDING"
    )


def test_identity_across_namespaces_is_refused():
    with pytest.raises(ns.NamespaceCollisionError):
        ident.Correspondence(
            ns.TypedRef(INLAND, "INAP-PR-000001"),
            ns.TypedRef(N.AVIATION_ILAP_PATH, "ILAP_FL1"),
            ("name_only",),
            "s",
        )
    with pytest.raises(ns.NamespaceCollisionError):
        ident.Correspondence(
            ns.TypedRef(INLAND, "INAP-PR-000001"),
            ns.TypedRef(OFFSHORE, "OFAP-PR-000001"),
            ("proximity_only",),
            "s",
        )


def test_correspondence_cardinalities_are_preserved_without_multiplying_records():
    obs = _refs(INLAND, "obs", 9)
    feat = _refs(INLAND, "feat", 8)
    link = lambda i, j, **kw: ident.Correspondence(
        obs[i], feat[j], ("proximity_only",), "s", **kw
    )  # noqa: E731
    links = [
        link(0, 0),  # 1:1
        link(1, 1),
        link(1, 2),  # one observation, two candidates -> 1:N
        link(2, 3),
        link(3, 3),  # two observations, one feature -> N:1
        link(4, 4),
        link(4, 5),
        link(5, 4),
        link(5, 5),  # N:N
        link(6, 6, adjudication=v.AdjudicationStatus.UNRESOLVED),
    ]
    groups = ident.group_correspondences(obs, feat, links)
    found = sorted(g.cardinality.value for g in groups)
    assert found == sorted(
        ["1:1", "1:N", "N:1", "N:N", "UNRESOLVED", "0:1", "0:1", "0:1"]
    )
    assert ident.counts_close(obs, feat, groups)
    members = [r for g in groups for r in g.left + g.right]
    assert len(members) == len(set(members)) == len(obs) + len(feat)
    with pytest.raises(ValueError):
        ident.group_correspondences(obs + [obs[0]], feat, [])
    with pytest.raises(ValueError):
        ident.group_correspondences(obs[:1], feat[:1], [link(2, 2)])


def test_proximity_proposals_are_candidates_and_not_forced_one_to_one():
    left = [(ns.TypedRef(INLAND, "a"), (-66.0, 18.0))]
    right = [
        (ns.TypedRef(INLAND, "b"), (-66.0001, 18.0)),
        (ns.TypedRef(INLAND, "c"), (-66.0002, 18.0)),
        (ns.TypedRef(INLAND, "far"), (-65.0, 18.0)),
    ]
    proposals = ident.propose_by_proximity(left, right, threshold_m=100.0)
    assert [p.right.identifier for p in proposals] == ["b", "c"]
    assert all(
        ident.identity_semantics(p, producer_identity="x") == "CANDIDATE_NOT_IDENTITY"
        for p in proposals
    )
    with pytest.raises(ValueError):
        ident.propose_by_proximity(left, right, threshold_m=-1)


# ── Relationships and paths ──────────────────────────────────────────────────

A = ns.TypedRef(INLAND, "INAP-PR-000001")
B = ns.TypedRef(OFFSHORE, "OFAP-PR-000001")
C = ns.TypedRef(OFFSHORE, "OFAP-PR-000002")
E = ns.TypedRef(INLAND, "INAP-PR-000002")
VERIFIED_TYPES = {
    v.RelationshipType.DOCUMENTED_ENGINEERED_CONNECTION: v.ConnectivityKind.ENGINEERED_CONNECTIVITY,
    v.RelationshipType.MEASURED_HYDRAULIC_CONNECTION: v.ConnectivityKind.HYDRAULIC_CONNECTION,
    v.RelationshipType.VERIFIED_GEOLOGICAL_CONTINUITY: v.ConnectivityKind.GEOLOGICAL_CONTINUITY,
}


def _ledger():
    ledger = rel.RelationshipLedger(producer_identity=sup.PRODUCER)
    document = sup.direct_source("TEST-ASBUILT-001")
    ledger.add_source(document)
    return ledger, document


def _verified(ledger, source, kind_type, a, b):
    relationship = rel.make_relationship(
        kind_type,
        a,
        b,
        claim_class=v.ClaimClass.FACT,
        tier=T.DIRECT,
        basis=("as_built_drawing",),
        statement="synthetic",
        source_ids=(source.source_id,),
    )
    ledger.add(rel.accept(relationship, reviewer=sup.REVIEWER, utc=sup.UTC))
    return ledger.relationships[relationship.relationship_id]


def test_spatial_adjacency_is_discovery_only():
    ledger, _ = _ledger()
    near = rel.spatial_adjacency(
        A, (-66.1, 17.95), B, (-66.1005, 17.9495), threshold_m=500
    )
    assert near is not None and near.distance_m < 500
    assert (
        rel.spatial_adjacency(A, (-66.1, 17.95), B, (-65.0, 17.95), threshold_m=500)
        is None
    )
    ledger.add(near)
    assert near.tier is T.CANDIDATE and "CANDIDATE_NOT_IDENTITY" in near.statement
    assert not ledger.is_verified(near)
    assert ledger.render_class(near) is rel.RenderClass.CONTEXT
    accepted = rel.accept(
        replace(near, tier=T.DIRECT), reviewer=sup.REVIEWER, utc=sup.UTC
    )
    ledger.revise(accepted)
    assert not ledger.is_verified(accepted)  # adjacency can never be verified
    assert ledger.federation_rows()[0]["identity_semantics"] == "CANDIDATE_NOT_IDENTITY"


@pytest.mark.parametrize(
    "kind_type, kind", sorted(VERIFIED_TYPES.items(), key=lambda kv: kv[0].value)
)
def test_each_connection_type_establishes_one_kind_only(kind_type, kind):
    ledger, source = _ledger()
    relationship = _verified(ledger, source, kind_type, A, B)
    assert relationship.connectivity_kind is kind
    assert ledger.is_verified(relationship)
    wrong = next(k for k in v.ConnectivityKind if k is not kind)
    with pytest.raises(ValueError, match="establishes"):
        rel.make_relationship(
            kind_type,
            A,
            C,
            claim_class=v.ClaimClass.FACT,
            tier=T.DIRECT,
            basis=("x",),
            statement="s",
            connectivity_kind=wrong,
        )


@pytest.mark.parametrize("kind_type", sorted(VERIFIED_TYPES, key=lambda t: t.value))
def test_false_connections_are_not_verified(kind_type):
    ledger, source = _ledger()
    make = lambda **kw: rel.make_relationship(  # noqa: E731
        kind_type,
        A,
        B,
        statement="s",
        **{
            "claim_class": v.ClaimClass.FACT,
            "tier": T.DIRECT,
            "basis": ("survey",),
            "source_ids": (source.source_id,),
            **kw,
        },
    )
    variants = {
        "proximity basis": rel.accept(
            make(basis=("proximity_only",)), reviewer=sup.REVIEWER, utc=sup.UTC
        ),
        "hypothesis": rel.accept(
            make(claim_class=v.ClaimClass.HYPOTHESIS),
            reviewer=sup.REVIEWER,
            utc=sup.UTC,
        ),
        "no source": rel.accept(
            make(source_ids=()), reviewer=sup.REVIEWER, utc=sup.UTC
        ),
        "unreviewed": make(),
        "self reviewed": rel.accept(make(), reviewer=sup.PRODUCER, utc=sup.UTC),
        "supporting only": rel.accept(
            make(tier=T.SUPPORTING), reviewer=sup.REVIEWER, utc=sup.UTC
        ),
    }
    for name, relationship in variants.items():
        fresh, src = _ledger()
        fresh.add(relationship)
        assert not fresh.is_verified(relationship), name
        assert fresh.render_class(relationship) is not rel.RenderClass.VERIFIED, name


def test_legacy_records_cannot_be_merged_or_verified_against_features():
    aviation = ns.TypedRef(N.AVIATION_ILAP_PATH, "ILAP_FL1")
    for kind_type in (
        v.RelationshipType.SAME_VERIFIED_PHYSICAL_FEATURE,
        v.RelationshipType.DOCUMENTED_ENGINEERED_CONNECTION,
        v.RelationshipType.SHARED_GEOLOGICAL_UNIT,
    ):
        with pytest.raises(ns.NamespaceCollisionError):
            rel.make_relationship(
                kind_type,
                A,
                aviation,
                claim_class=v.ClaimClass.FACT,
                tier=T.DIRECT,
                basis=("x",),
                statement="s",
            )
    allowed = rel.make_relationship(
        v.RelationshipType.HYPOTHESIZED_CONNECTION,
        A,
        aviation,
        claim_class=v.ClaimClass.HYPOTHESIS,
        tier=T.CANDIDATE,
        basis=("proximity_only",),
        statement="s",
        connectivity_kind=v.ConnectivityKind.HUMAN_ACCESSIBILITY,
    )
    assert allowed.tier is T.CANDIDATE


def test_relationship_shape_rules():
    with pytest.raises(ValueError, match="which kind"):
        rel.make_relationship(
            v.RelationshipType.HYPOTHESIZED_CONNECTION,
            A,
            B,
            claim_class=v.ClaimClass.HYPOTHESIS,
            tier=T.CANDIDATE,
            basis=("x",),
            statement="s",
        )
    with pytest.raises(ValueError, match="contradicts"):
        rel.make_relationship(
            v.RelationshipType.CONTRADICTORY_RELATIONSHIP,
            A,
            B,
            claim_class=v.ClaimClass.FACT,
            tier=T.DIRECT,
            basis=("x",),
            statement="s",
        )
    with pytest.raises(ValueError, match="distinct"):
        rel.make_relationship(
            v.RelationshipType.SPATIAL_ADJACENCY,
            A,
            A,
            claim_class=v.ClaimClass.COMPUTED,
            tier=T.CANDIDATE,
            basis=("proximity_only",),
            statement="s",
        )
    with pytest.raises(ValueError, match="valid_from"):
        rel.make_relationship(
            v.RelationshipType.SPATIAL_ADJACENCY,
            A,
            B,
            claim_class=v.ClaimClass.COMPUTED,
            tier=T.CANDIDATE,
            basis=("proximity_only",),
            statement="s",
            valid_from="2026-03-01",
            valid_to="2026-01-01",
        )


def test_path_states():
    ledger, source = _ledger()
    hydraulic = v.RelationshipType.MEASURED_HYDRAULIC_CONNECTION
    engineered = v.RelationshipType.DOCUMENTED_ENGINEERED_CONNECTION
    ab = _verified(ledger, source, hydraulic, A, B)
    bc = _verified(ledger, source, hydraulic, B, C)
    assert ledger.best_path_state(A, C) is rel.PathState.VERIFIED
    assessment = ledger.assess_path([ab, bc])
    assert assessment.may_render_as_verified
    assert assessment.connectivity_kind is v.ConnectivityKind.HYDRAULIC_CONNECTION
    assert (
        ledger.best_path_state(A, ns.TypedRef(OFFSHORE, "OFAP-PR-000099"))
        is rel.PathState.NO_PATH
    )
    assert ledger.best_path_state(A, C, max_hops=1) is rel.PathState.NO_PATH

    # Water reaching a place and a pipe reaching it are not one connection.
    mixed, src = _ledger()
    m1 = _verified(mixed, src, hydraulic, A, B)
    m2 = _verified(mixed, src, engineered, B, C)
    state = mixed.assess_path([m1, m2])
    assert state.state is rel.PathState.MIXED_KINDS and not state.may_render_as_verified

    # One hypothesised edge makes the whole path hypothetical.
    hypo, src = _ledger()
    h1 = _verified(hypo, src, hydraulic, A, B)
    h2 = rel.make_relationship(
        v.RelationshipType.HYPOTHESIZED_CONNECTION,
        B,
        C,
        claim_class=v.ClaimClass.HYPOTHESIS,
        tier=T.DIRECT,
        basis=("survey",),
        statement="s",
        connectivity_kind=v.ConnectivityKind.HYDRAULIC_CONNECTION,
    )
    hypo.add(h2)
    result = hypo.assess_path([h1, h2])
    assert (
        result.state is rel.PathState.HYPOTHETICAL and not result.may_render_as_verified
    )
    assert result.unverified_relationship_ids == (h2.relationship_id,)
    assert hypo.best_path_state(A, C) is rel.PathState.HYPOTHETICAL

    unresolved, src = _ledger()
    u1 = _verified(unresolved, src, hydraulic, A, B)
    u2 = rel.make_relationship(
        v.RelationshipType.UNRESOLVED_RELATIONSHIP,
        B,
        C,
        claim_class=v.ClaimClass.UNKNOWN,
        tier=T.UNRESOLVED,
        basis=("x",),
        statement="s",
    )
    unresolved.add(u2)
    assert unresolved.assess_path([u1, u2]).state is rel.PathState.UNRESOLVED
    assert ledger.assess_path([]).state is rel.PathState.NO_PATH


def test_contradiction_removes_verification_and_a_verified_alternative_is_preferred():
    ledger, source = _ledger()
    hydraulic = v.RelationshipType.MEASURED_HYDRAULIC_CONNECTION
    ab = _verified(ledger, source, hydraulic, A, B)
    bc = _verified(ledger, source, hydraulic, B, C)
    ae = _verified(ledger, source, hydraulic, A, E)
    ec = _verified(ledger, source, hydraulic, E, C)
    contradiction = rel.make_relationship(
        v.RelationshipType.CONTRADICTORY_RELATIONSHIP,
        A,
        B,
        claim_class=v.ClaimClass.FACT,
        tier=T.DIRECT,
        basis=("dye_trace",),
        statement="tracer was not recovered",
        source_ids=(source.source_id,),
        contradicts=(ab.relationship_id,),
    )
    ledger.add(contradiction)
    assert not ledger.is_verified(ab)
    assert ledger.render_class(ab) is rel.RenderClass.CONTRADICTED
    assert ledger.assess_path([ab, bc]).state is rel.PathState.CONTRADICTED
    assert ledger.assess_path([ae, ec]).state is rel.PathState.VERIFIED
    assert ledger.best_path_state(A, C) is rel.PathState.VERIFIED
    with pytest.raises(ValueError):
        ledger.add(
            replace(
                contradiction,
                relationship_id="APREL-" + "0" * 16,
                contradicts=("APREL-" + "f" * 16,),
            )
        )


def test_ledger_round_trip_and_tamper_detection():
    ledger, source = _ledger()
    _verified(ledger, source, v.RelationshipType.MEASURED_HYDRAULIC_CONNECTION, A, B)
    ledger.add(
        rel.spatial_adjacency(
            A, (-66.1, 17.95), C, (-66.1005, 17.9495), threshold_m=500
        )
    )
    document = json.loads(json.dumps(ledger.to_document()))
    again = rel.ledger_from_document(document)
    assert again.to_document()["content_sha256"] == document["content_sha256"]
    assert [r["render_class"] for r in again.federation_rows()] == [
        r["render_class"] for r in ledger.federation_rows()
    ]
    document["relationships"][0]["statement"] = "edited"
    with pytest.raises(RegistryIntegrityError):
        rel.ledger_from_document(document)
    with pytest.raises(ValueError):
        ledger.add(
            rel.make_relationship(
                v.RelationshipType.SHARED_GEOLOGICAL_UNIT,
                A,
                B,
                claim_class=v.ClaimClass.FACT,
                tier=T.SUPPORTING,
                basis=("map",),
                statement="s",
                source_ids=("APSRC-" + "c" * 16,),
            )
        )

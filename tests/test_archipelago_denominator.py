import pytest

from spiderweb.spatial.archipelago import GeometryManifestation, GeometryOrigin, GeometryRepresentation, IdentityState
from spiderweb.spatial.archipelago_denominator import (
    CandidateEvidenceKind,
    GeometryCandidateEdge,
    GeometryLedgerEntry,
    GeometryLedgerState,
    candidate_cardinalities,
    partition_geometry_ledger,
    promotable_edges,
)


def geom(gid):
    return GeometryManifestation(
        geometry_manifestation_id=gid,
        source_id="TEST",
        representation=GeometryRepresentation.POINT,
        origin=GeometryOrigin.SOURCE_NATIVE,
        source_geometry_type_raw="Point",
    )


def test_partition_closes_exactly():
    rows = [
        GeometryLedgerEntry(geom("g1"), GeometryLedgerState.RETAINED),
        GeometryLedgerEntry(geom("g2"), GeometryLedgerState.EXCLUDED, exclusion_reason="outside bounded scope"),
        GeometryLedgerEntry(geom("g3"), GeometryLedgerState.CANDIDATE, candidate_target_ids=("GNIS:1",)),
        GeometryLedgerEntry(geom("g4"), GeometryLedgerState.UNRESOLVED, unresolved_reason="no defensible candidate"),
    ]
    p = partition_geometry_ledger(rows)
    assert p.source_total == 4
    assert p.retained == p.excluded == p.candidate == p.unresolved == 1
    assert p.residue == 0
    assert p.arithmetic_closed


def test_duplicate_geometry_ids_fail_closed():
    rows = [
        GeometryLedgerEntry(geom("g1"), GeometryLedgerState.RETAINED),
        GeometryLedgerEntry(geom("g1"), GeometryLedgerState.RETAINED),
    ]
    with pytest.raises(ValueError, match="duplicate geometry_manifestation_id"):
        partition_geometry_ledger(rows)


def test_candidate_requires_full_nonempty_set():
    with pytest.raises(ValueError, match="non-empty candidate set"):
        GeometryLedgerEntry(geom("g1"), GeometryLedgerState.CANDIDATE)


def test_noncandidate_cannot_smuggle_candidate_ids():
    with pytest.raises(ValueError, match="allowed only for CANDIDATE"):
        GeometryLedgerEntry(geom("g1"), GeometryLedgerState.RETAINED, candidate_target_ids=("GNIS:1",))


def test_candidate_cardinality_preserves_1n_n1_nn():
    edges = [
        GeometryCandidateEdge("g1", "t1", (CandidateEvidenceKind.PROXIMITY_ONLY,)),
        GeometryCandidateEdge("g1", "t2", (CandidateEvidenceKind.NAME_ONLY,)),
        GeometryCandidateEdge("g2", "t3", (CandidateEvidenceKind.STABLE_SOURCE_ID,)),
        GeometryCandidateEdge("g3", "t3", (CandidateEvidenceKind.GEOMETRY_OVERLAP_ONLY,)),
        GeometryCandidateEdge("g4", "t4", (CandidateEvidenceKind.STABLE_SOURCE_ID,)),
        GeometryCandidateEdge("g4", "t5", (CandidateEvidenceKind.STABLE_SOURCE_ID,)),
        GeometryCandidateEdge("g5", "t5", (CandidateEvidenceKind.STABLE_SOURCE_ID,)),
    ]
    c = candidate_cardinalities(edges)
    assert c["g1"] == IdentityState.RESOLVED_1_N
    assert c["g2"] == IdentityState.RESOLVED_N_1
    assert c["g3"] == IdentityState.RESOLVED_N_1
    assert c["g4"] == IdentityState.RESOLVED_N_N


def test_heuristic_only_edges_are_not_promotable():
    edges = [
        GeometryCandidateEdge("g1", "t1", (CandidateEvidenceKind.NAME_ONLY, CandidateEvidenceKind.PROXIMITY_ONLY)),
        GeometryCandidateEdge("g2", "t2", (CandidateEvidenceKind.STABLE_SOURCE_ID,)),
    ]
    p = promotable_edges(edges)
    assert [e.geometry_manifestation_id for e in p] == ["g2"]

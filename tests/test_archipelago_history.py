from spiderweb.spatial.archipelago_history import (
    HistoricalRelationEdge,
    TemporalEvidenceKind,
    TemporalRelation,
    assert_no_historical_backfill,
    temporal_relation_counts,
)


def test_historical_edges_never_promote_current_identity():
    edge = HistoricalRelationEdge(
        historical_manifestation_id="USGS1957:LasLavanderasWest",
        current_candidate_id="GNIS:1611372",
        relation=TemporalRelation.CONTINUITY,
        evidence=(TemporalEvidenceKind.AUTHORITATIVE_MAP_LABEL,),
        valid_time="1957",
    )
    assert edge.may_promote_current_identity is False
    assert_no_historical_backfill([edge])


def test_temporal_relation_counts_preserve_split_merge_states():
    edges = [
        HistoricalRelationEdge("h1", "c1", TemporalRelation.CONTINUITY, (TemporalEvidenceKind.STABLE_SOURCE_ID,)),
        HistoricalRelationEdge("h2", "c2", TemporalRelation.SPLIT, (TemporalEvidenceKind.AUTHORITATIVE_GEOMETRY,)),
        HistoricalRelationEdge("h3", "c3", TemporalRelation.MERGED, (TemporalEvidenceKind.EXPLICIT_LINEAGE_STATEMENT,)),
        HistoricalRelationEdge("h4", None, TemporalRelation.HISTORICAL_ONLY, (TemporalEvidenceKind.AUTHORITATIVE_MAP_LABEL,)),
    ]
    c = temporal_relation_counts(edges)
    assert c[TemporalRelation.CONTINUITY] == 1
    assert c[TemporalRelation.SPLIT] == 1
    assert c[TemporalRelation.MERGED] == 1
    assert c[TemporalRelation.HISTORICAL_ONLY] == 1

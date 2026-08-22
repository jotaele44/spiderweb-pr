from spiderweb.spatial.archipelago_history import (
    HistoricalManifestationNode,
    HistoricalRelationEdge,
    TemporalEvidenceKind,
    TemporalRelation,
    assert_components_do_not_backfill,
    assert_no_historical_backfill,
    build_temporal_components,
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


def test_shared_current_candidate_builds_b_only_temporal_component():
    nodes = [
        HistoricalManifestationNode("h1957", "USGS", "1957"),
        HistoricalManifestationNode("h2013", "USGS", "2013"),
    ]
    edges = [
        HistoricalRelationEdge("h1957", "GNIS:1", TemporalRelation.CONTINUITY, (TemporalEvidenceKind.AUTHORITATIVE_MAP_LABEL,)),
        HistoricalRelationEdge("h2013", "GNIS:1", TemporalRelation.CONTINUITY, (TemporalEvidenceKind.AUTHORITATIVE_MAP_LABEL,)),
    ]
    comps = build_temporal_components(nodes, edges)
    assert len(comps) == 1
    assert comps[0].historical_manifestation_ids == ("h1957", "h2013")
    assert comps[0].current_candidate_ids == ("GNIS:1",)
    assert comps[0].valid_times == ("1957", "2013")
    assert comps[0].may_promote_current_identity is False
    assert_components_do_not_backfill(comps)


def test_historical_node_without_edge_survives_as_unresolved_component():
    comps = build_temporal_components(
        [HistoricalManifestationNode("h1", "NOAA", "1969")],
        [],
    )
    assert len(comps) == 1
    assert comps[0].relation_states == (TemporalRelation.UNRESOLVED,)
    assert comps[0].edge_count == 0


def test_historical_only_edge_has_no_current_candidate():
    nodes = [HistoricalManifestationNode("h1", "NOAA", "1969")]
    edges = [
        HistoricalRelationEdge(
            "h1",
            None,
            TemporalRelation.HISTORICAL_ONLY,
            (TemporalEvidenceKind.AUTHORITATIVE_MAP_LABEL,),
        )
    ]
    comp = build_temporal_components(nodes, edges)[0]
    assert comp.current_candidate_ids == ()
    assert comp.relation_states == (TemporalRelation.HISTORICAL_ONLY,)

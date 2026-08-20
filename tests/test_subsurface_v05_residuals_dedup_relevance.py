from spiderweb.subsurface.dedup import canonicalize
from spiderweb.subsurface.relevance import build_relevance_zones
from spiderweb.subsurface.residuals import ResidualState, V05_RESIDUAL_ASSESSMENTS, all_residuals_terminal


def feature(record_id, source_id, x, y, *, family="AQUIFERS_WELLS_SPRINGS", attrs=None, state="FULLY_WITHIN"):
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [x, y]},
        "properties": {
            "record_id": record_id,
            "source_id": source_id,
            "layer_family": family,
            "spatial_state": state,
            "attributes": attrs or {},
        },
    }


def test_v05_residual_states_do_not_turn_public_gap_into_negative_evidence():
    rows = {row.source_id: row for row in V05_RESIDUAL_ASSESSMENTS}
    assert rows["HISTORIC_WORKINGS_NONMAPPED_RESIDUAL"].state == ResidualState.FINAL_PUBLIC_GAP
    assert rows["NON_AAA_PRIVATE_BURIED_NETWORK_RESIDUAL"].state == ResidualState.FINAL_PUBLIC_GAP
    assert rows["FORMER_MILITARY_SUBSURFACE_REPORT_CORPUS_RESIDUAL"].state == ResidualState.OPEN
    assert rows["HISTORICAL_AERIAL_COLLECTION_INDEX_RESIDUAL"].state == ResidualState.OPEN
    assert all(row.negative_evidence_permitted is False for row in rows.values())
    assert all_residuals_terminal() is False


def test_exact_spring_site_id_binds_to_usgs_and_source_duplicate_becomes_n_to_one():
    rows = [
        feature("spring:1", "PRPB_SPRINGS_19", -66.1, 18.1, attrs={"SITE_ID": "123", "STATION_NA": "Test Spring"}),
        feature("spring:2", "PRPB_SPRINGS_19", -66.1, 18.1, attrs={"SITE_ID": "123", "STATION_NA": "Test Spring"}),
        feature("usgs:123", "USGS_MONITORING_LOCATIONS_PR", -66.100001, 18.100001, attrs={"monitoring_location_number": "123", "monitoring_location_name": "Test Spring", "site_type": "Spring"}),
    ]
    assets, edges = canonicalize(rows)
    merged = next(asset for asset in assets if len(asset.member_record_ids) == 3)
    assert merged.relation == "N:1"
    assert merged.confidence == "DIRECT"
    assert any(edge.relation == "AUTHORITATIVE_ID" and edge.binding for edge in edges)
    assert any(edge.relation == "DUPLICATE_SOURCE_ROW" and edge.binding for edge in edges)


def test_nearest_wells_do_not_merge_without_name_binding():
    rows = [
        feature("jca:1", "PRPB_WELLS_JCA_20", -66.1, 18.1, attrs={"Nombre": "Alpha", "ID_Sistema": "1"}),
        feature("aaa:1", "PRPB_WELLS_AAA_21", -66.10001, 18.10001, attrs={"Name": "Completely Different", "PWSID": "1"}),
    ]
    assets, edges = canonicalize(rows)
    assert len(assets) == 2
    assert any(edge.binding is False for edge in edges)


def test_relevance_model_excludes_military_family_and_uses_exact_intersection():
    aoi = {"type": "Polygon", "coordinates": [[[-66.12, 18.08], [-66.08, 18.08], [-66.08, 18.12], [-66.12, 18.08]]]}
    cave = feature("cave:1", "PRPB_CAVES_31", -66.1, 18.1, family="GEOLOGY_KARST_CAVES")
    military = feature("mil:1", "USACE_FUDS_PROJECTS_2", -66.1, 18.1, family="MILITARY_HARDENED_SUBSURFACE")
    zones_a = build_relevance_zones(aoi, [cave], cell_degrees=0.02)
    zones_b = build_relevance_zones(aoi, [cave, military], cell_degrees=0.02)
    assert [(z.score, z.evidence_tier) for z, _ in zones_a] == [(z.score, z.evidence_tier) for z, _ in zones_b]
    assert any(z.cave_features > 0 and z.evidence_tier == "DIRECT" for z, _ in zones_a)

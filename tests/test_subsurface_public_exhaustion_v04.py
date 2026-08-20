from spiderweb.subsurface.public_exhaustion import certify_public_exhaustion
from spiderweb.subsurface.runner import source_ledger
from spiderweb.subsurface.sources import SourceStatus
from spiderweb.subsurface.sources_exhaustion_v04 import (
    SOURCE_DENOMINATOR_V04,
    USGS_OPENING_TYPES,
    USGS_OPENING_WHERE,
)


def test_v04_binds_current_usgs_mine_and_mrds_machine_layers():
    by_id = {source.source_id: source for source in SOURCE_DENOMINATOR_V04}
    points = by_id["USGS_USMIN_CONSOLIDATED_POINTS_17"]
    openings = by_id["USGS_USMIN_EXPLICIT_OPENINGS_17"]
    polygons = by_id["USGS_USMIN_CONSOLIDATED_POLYGONS_18"]
    mrds = by_id["USGS_MRDS_HOSTED_0_PR_AOI"]
    assert points.status == SourceStatus.VERIFIED_QUERYABLE
    assert points.layer_id == 17
    assert points.evidence_role == "SUPPORTING"
    assert openings.status == SourceStatus.VERIFIED_QUERYABLE
    assert openings.layer_id == 17
    assert openings.evidence_role == "DIRECT"
    assert openings.query_dict["where"] == USGS_OPENING_WHERE
    assert USGS_OPENING_TYPES == ("Adit", "Air Shaft", "Mine Shaft")
    assert polygons.status == SourceStatus.VERIFIED_QUERYABLE
    assert polygons.layer_id == 18
    assert mrds.status == SourceStatus.VERIFIED_QUERYABLE
    assert mrds.layer_id == 0


def test_v04_supersedes_old_single_mine_symbol_manifestation():
    ids = {source.source_id for source in SOURCE_DENOMINATOR_V04}
    assert "USGS_USMIN_MINE_SYMBOLS_0" not in ids
    assert "USGS_USMIN_CONSOLIDATED_POINTS_17" in ids
    assert "USGS_USMIN_EXPLICIT_OPENINGS_17" in ids
    assert "USGS_USMIN_CONSOLIDATED_POLYGONS_18" in ids


def test_v04_binds_topoview_as_queryable_map_index():
    by_id = {source.source_id: source for source in SOURCE_DENOMINATOR_V04}
    topo = by_id["USGS_TOPOVIEW_OVERLAY_0"]
    assert topo.status == SourceStatus.VERIFIED_QUERYABLE
    assert topo.layer_id == 0
    assert topo.family == "HISTORICAL_CORROBORATION"


def test_broadband_road_layer_is_discovery_not_buried_network_proof():
    by_id = {source.source_id: source for source in SOURCE_DENOMINATOR_V04}
    road = by_id["PRPB_BROADBAND_SERVICE_ROAD_24"]
    assert road.status == SourceStatus.DISCOVERY_ONLY
    assert road.evidence_role == "CANDIDATE"


def test_former_military_report_indexes_do_not_open_active_asset_vector():
    by_id = {source.source_id: source for source in SOURCE_DENOMINATOR_V04}
    for source_id in (
        "USACE_FUDS_CULEBRA_REPORT_INDEX",
        "USACE_FUDS_DESECHEO_REPORT_INDEX",
        "USACE_FUDS_FORT_BROOKE_REPORT_INDEX",
        "USACE_FUDS_MONITO_REPORT_INDEX",
    ):
        assert by_id[source_id].status == SourceStatus.VERIFIED_REFERENCE
        assert by_id[source_id].evidence_role == "SUPPORTING"
    assert by_id["ACTIVE_MILITARY_HARDENED_ASSET_CLASS"].required is False


def test_v04_records_request_gate_remains_forbidden_without_terminal_public_rows():
    cert = certify_public_exhaustion(
        source_ledger(SOURCE_DENOMINATOR_V04, []),
        scope="PUERTO_RICO_PUBLIC_SUBSURFACE_SOURCE_DENOMINATOR_V04",
    )
    assert cert.scope == "PUERTO_RICO_PUBLIC_SUBSURFACE_SOURCE_DENOMINATOR_V04"
    assert cert.state == "OPEN"
    assert cert.records_request_eligible is False
    assert "HISTORIC_WORKINGS_NONMAPPED_RESIDUAL" in cert.unresolved_sources
    assert "FORMER_MILITARY_SUBSURFACE_REPORT_CORPUS_RESIDUAL" in cert.unresolved_sources
    assert "NON_AAA_PRIVATE_BURIED_NETWORK_RESIDUAL" in cert.unresolved_sources
    assert "HISTORICAL_AERIAL_COLLECTION_INDEX_RESIDUAL" in cert.unresolved_sources

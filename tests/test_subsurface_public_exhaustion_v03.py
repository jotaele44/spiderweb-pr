from spiderweb.subsurface.public_exhaustion import current_public_exhaustion_certificate
from spiderweb.subsurface.sources import SourceStatus
from spiderweb.subsurface.sources_exhaustion_v03 import SOURCE_DENOMINATOR_V03


def test_v03_adds_1930_historical_imagery_and_luma_underground_standard():
    by_id = {source.source_id: source for source in SOURCE_DENOMINATOR_V03}
    assert by_id["PRDRNA_UPR_PORTO_RICO_1930_GEOREF"].status == SourceStatus.VERIFIED_REFERENCE
    assert by_id["LUMA_UNDERGROUND_DISTRIBUTION_MANUAL_2023"].status == SourceStatus.VERIFIED_REFERENCE


def test_mixed_usgs_mine_symbol_layer_is_not_direct_without_type_filter():
    by_id = {source.source_id: source for source in SOURCE_DENOMINATOR_V03}
    symbols = by_id["USGS_USMIN_MINE_SYMBOLS_0"]
    assert symbols.status == SourceStatus.VERIFIED_QUERYABLE
    assert symbols.evidence_role == "SUPPORTING"
    assert "feature-level" in symbols.notes


def test_v03_keeps_records_request_gate_closed_while_public_residue_remains():
    cert = current_public_exhaustion_certificate()
    assert cert.state == "OPEN"
    assert cert.records_request_eligible is False
    assert "HISTORIC_WORKINGS_NONMAPPED_RESIDUAL" in cert.unresolved_sources
    assert "FORMER_MILITARY_SUBSURFACE_REPORT_CORPUS_RESIDUAL" in cert.unresolved_sources
    assert "NON_AAA_PRIVATE_BURIED_NETWORK_RESIDUAL" in cert.unresolved_sources
    assert "HISTORICAL_AERIAL_COLLECTION_INDEX_RESIDUAL" in cert.unresolved_sources

from spiderweb.subsurface.public_exhaustion import certify_public_exhaustion
from spiderweb.subsurface.runner import source_ledger
from spiderweb.subsurface.sources import SourceStatus
from spiderweb.subsurface.sources_exhaustion_v03 import SOURCE_DENOMINATOR_V03


def test_v03_adds_1930_historical_imagery_and_luma_underground_standard():
    by_id = {source.source_id: source for source in SOURCE_DENOMINATOR_V03}
    assert by_id["PRDRNA_UPR_PORTO_RICO_1930_GEOREF"].status == SourceStatus.VERIFIED_REFERENCE
    assert by_id["LUMA_UNDERGROUND_DISTRIBUTION_MANUAL_2023"].status == SourceStatus.VERIFIED_REFERENCE


def test_v03_snapshot_keeps_records_request_gate_closed_while_residue_remains():
    cert = certify_public_exhaustion(
        source_ledger(SOURCE_DENOMINATOR_V03, []),
        scope="PUERTO_RICO_PUBLIC_SUBSURFACE_SOURCE_DENOMINATOR_V03",
    )
    assert cert.state == "OPEN"
    assert cert.records_request_eligible is False
    assert "HISTORIC_WORKINGS_NONMAPPED_RESIDUAL" in cert.unresolved_sources
    assert "FORMER_MILITARY_SUBSURFACE_REPORT_CORPUS_RESIDUAL" in cert.unresolved_sources
    assert "NON_AAA_PRIVATE_BURIED_NETWORK_RESIDUAL" in cert.unresolved_sources
    assert "HISTORICAL_AERIAL_COLLECTION_INDEX_RESIDUAL" in cert.unresolved_sources

from __future__ import annotations

from dataclasses import replace

from spiderweb.subsurface.public_exhaustion import (
    certify_public_exhaustion,
    current_public_exhaustion_certificate,
)
from spiderweb.subsurface.runner import SourceLedgerRow, source_ledger
from spiderweb.subsurface.sources import SourceStatus
from spiderweb.subsurface.sources_exhaustion import (
    SOURCE_DENOMINATOR_V02,
    SUPERSESSION_MAP,
)


def test_v02_supersedes_broad_placeholders_with_narrower_rows():
    ids = {source.source_id for source in SOURCE_DENOMINATOR_V02}
    assert "MINES_SHAFTS_EXACT_GEOMETRY" not in ids
    assert "MILITARY_SUBSURFACE_DENOMINATOR" not in ids
    assert "UNDERGROUND_NON_AAA_UTILITY_DENOMINATOR" not in ids
    assert "HISTORICAL_AERIAL_MAP_DENOMINATOR" not in ids
    for replacement_ids in SUPERSESSION_MAP.values():
        assert set(replacement_ids) <= ids


def test_usgs_mine_symbols_is_machine_queryable_but_residual_stays_open():
    by_id = {source.source_id: source for source in SOURCE_DENOMINATOR_V02}
    symbols = by_id["USGS_USMIN_MINE_SYMBOLS_0"]
    residual = by_id["HISTORIC_WORKINGS_NONMAPPED_RESIDUAL"]
    assert symbols.status == SourceStatus.VERIFIED_QUERYABLE
    assert symbols.layer_id == 0
    assert residual.status == SourceStatus.OPEN


def test_active_military_precise_asset_class_does_not_fake_required_exhaustion():
    by_id = {source.source_id: source for source in SOURCE_DENOMINATOR_V02}
    source = by_id["ACTIVE_MILITARY_HARDENED_ASSET_CLASS"]
    assert source.required is False
    assert source.status == SourceStatus.OPEN


def test_non_aaa_private_buried_network_residual_blocks_utility_exhaustion():
    cert = current_public_exhaustion_certificate()
    utility = next(row for row in cert.families if row.family == "UTILITIES_UNDERGROUND")
    assert utility.state == "OPEN"
    assert "NON_AAA_PRIVATE_BURIED_NETWORK_RESIDUAL" in utility.unresolved_sources
    assert cert.records_request_eligible is False


def test_historical_collection_index_residual_blocks_temporal_exhaustion():
    cert = current_public_exhaustion_certificate()
    history = next(row for row in cert.families if row.family == "HISTORICAL_CORROBORATION")
    assert history.state == "OPEN"
    assert "HISTORICAL_AERIAL_COLLECTION_INDEX_RESIDUAL" in history.unresolved_sources


def test_reference_and_discovery_only_rows_are_not_terminal():
    rows = source_ledger(SOURCE_DENOMINATOR_V02, [])
    by_id = {row.source_id: row for row in rows}
    assert by_id["USGS_EROS_AERIAL_SINGLE_FRAMES_PR"].terminal is False
    assert by_id["USACE_FUDS_PR_INVENTORY"].terminal is False
    assert by_id["PRPB_INFRASTRUCTURE_TELECOM_27"].terminal is False


def test_public_exhaustion_pass_requires_every_required_row_terminal():
    rows = [
        SourceLedgerRow("a", "GEOLOGY_KARST_CAVES", True, "VERIFIED_QUERYABLE", "PASS", True, "ok"),
        SourceLedgerRow("b", "GEOLOGY_KARST_CAVES", True, "VERIFIED_QUERYABLE", "ZERO", True, "ok"),
    ]
    cert = certify_public_exhaustion(rows, families=["GEOLOGY_KARST_CAVES"], scope="fixture")
    assert cert.state == "PASS"
    assert cert.records_request_eligible is True

    failed = replace(rows[1], run_state="OPEN", terminal=False)
    cert2 = certify_public_exhaustion([rows[0], failed], families=["GEOLOGY_KARST_CAVES"], scope="fixture")
    assert cert2.state == "OPEN"
    assert cert2.records_request_eligible is False
    assert cert2.unresolved_sources == ("b",)

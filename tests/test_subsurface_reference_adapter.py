from pathlib import Path

import pytest

from spiderweb.subsurface.reference_adapter import run_reference_source
from spiderweb.subsurface.runner import source_ledger
from spiderweb.subsurface.sources import SourceKind, SourceSpec, SourceStatus


def ref_spec() -> SourceSpec:
    return SourceSpec(
        "REF",
        "HISTORICAL_CORROBORATION",
        "fixture",
        "fixture reference",
        SourceKind.REFERENCE_DOWNLOAD,
        "https://example.test/reference.pdf",
        SourceStatus.VERIFIED_REFERENCE,
        evidence_role="SUPPORTING",
    )


def test_reference_bytes_are_frozen_and_terminal(tmp_path: Path):
    payload = b"exact-public-reference-bytes"
    records, receipt = run_reference_source(
        ref_spec(), fetch=lambda _url: payload, snapshot_dir=tmp_path
    )
    assert records == []
    assert receipt.state == "PASS"
    assert receipt.complete is True
    assert receipt.expected_count == 1
    assert receipt.retained_count == 1
    assert receipt.pages[0].byte_count == len(payload)
    assert len(receipt.pages[0].byte_sha256) == 64
    assert (tmp_path / "REF" / "reference.raw").read_bytes() == payload
    row = source_ledger([ref_spec()], [receipt])[0]
    assert row.terminal is True


def test_verified_reference_without_receipt_is_not_terminal():
    row = source_ledger([ref_spec()], [])[0]
    assert row.run_state == "NOT_RUN"
    assert row.terminal is False


def test_empty_reference_payload_fails_closed():
    with pytest.raises(RuntimeError, match="empty reference payload"):
        run_reference_source(ref_spec(), fetch=lambda _url: b"")


def test_non_https_reference_fails_closed():
    spec = SourceSpec(
        "REF_HTTP",
        "HISTORICAL_CORROBORATION",
        "fixture",
        "fixture",
        SourceKind.REFERENCE_PAGE,
        "http://example.test/reference",
        SourceStatus.VERIFIED_REFERENCE,
    )
    with pytest.raises(ValueError, match="HTTPS"):
        run_reference_source(spec, fetch=lambda _url: b"x")

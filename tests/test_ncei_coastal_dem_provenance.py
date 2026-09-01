from pathlib import Path

from source_adapters.ncei_coastal_dem.provenance import (
    acquisition_context_leads,
    build_source_manifest,
)
from source_adapters.ncei_coastal_dem.registry import load_registry

FIXTURE = Path("tests/fixtures/ncei_coastal_dem/priority_datasets_fixture.csv")


def test_source_manifest_is_metadata_only_without_cache() -> None:
    manifest = build_source_manifest(
        load_registry(FIXTURE), accessed_at="2026-01-01T00:00:00Z"
    )

    assert manifest["adapter"] == "ncei_coastal_dem"
    assert manifest["sources"][0]["review_status"] == "metadata_only"
    assert manifest["sources"][0]["raw_commit_allowed"] is False
    assert manifest["sources"][0]["sha256"] is None


def test_acquisition_context_is_non_authoritative_lead() -> None:
    leads = acquisition_context_leads()

    assert leads[0]["ref_id"] == "140G0218F0171"
    assert leads[0]["confidence"] == "medium"
    assert "do not claim" in leads[0]["notes"]

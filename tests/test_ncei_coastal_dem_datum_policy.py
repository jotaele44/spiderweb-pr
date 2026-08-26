from pathlib import Path

from source_adapters.ncei_coastal_dem.datum_policy import evaluate_datum_policy
from source_adapters.ncei_coastal_dem.registry import load_registry, select_datasets

FIXTURE = Path("tests/fixtures/ncei_coastal_dem/priority_datasets_fixture.csv")


def test_same_datum_passes_without_normalization() -> None:
    records = select_datasets(load_registry(FIXTURE), dataset_id="arecibo_13_mhw_2007")
    result = evaluate_datum_policy(records)

    assert result.review_status == "pass"
    assert result.requires_vertical_normalization is False
    assert result.datum_merge_policy == "same_datum_only"


def test_mixed_datums_require_review() -> None:
    result = evaluate_datum_policy(load_registry(FIXTURE))

    assert result.review_status == "review_required"
    assert result.requires_vertical_normalization is True
    assert "separate_layers" in result.datum_merge_policy

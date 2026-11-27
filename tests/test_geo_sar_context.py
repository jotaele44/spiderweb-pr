import pytest

from spiderweb.geo_sar.context import resolve_context, validate_bbox


@pytest.mark.parametrize(
    "bbox",
    [
        [0, 0, 0, 1],
        [1, 0, 0, 1],
        [0, 0, 1, 91],
        [0, 0, float("nan"), 1],
        [True, 0, 2, 1],
        [0, 1, 2],
    ],
)
def test_invalid_bbox(bbox):
    with pytest.raises(ValueError):
        validate_bbox(bbox)


def test_pilot_versions_and_missing_evidence():
    result = resolve_context([-66.05, 18.3, -65.95, 18.4])
    assert result["extent_within_pilot"]
    assert result["catalog_assets_examined"] == 28
    assert len(result["options"]) == 2
    assert len({o["dataset_version_id"] for o in result["options"]}) == 2
    assert all(o["valid_data_coverage"] == "UNVERIFIED" for o in result["options"])
    assert all(
        a["acquisition_status"] == "NOT_ACQUIRED"
        for o in result["options"]
        for a in o["assets"]
    )


def test_outside_is_not_global_absence():
    result = resolve_context([-70, 10, -69, 11])
    assert not result["extent_within_pilot"]
    assert result["options"] == []
    assert result["catalog_scope"] == "PILOT_ONLY"


def test_context_identity_changes_with_extent():
    a = resolve_context([-66.05, 18.3, -65.95, 18.4])
    b = resolve_context([-66.05, 18.3, -66.0, 18.4])
    assert a["context_id"] != b["context_id"]

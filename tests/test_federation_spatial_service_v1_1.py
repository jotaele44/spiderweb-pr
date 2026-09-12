from pathlib import Path
import pytest

from federation.spatial_service_v1_1 import distance_evidence, join_evidence, validate_point


def test_validate_point_preserves_lon_lat_order():
    out = validate_point(-66.1057, 18.4655)
    assert out["coordinates"] == [-66.1057, 18.4655]
    assert out["crs"] == "OGC:CRS84"


def test_invalid_coordinate_fails_closed():
    with pytest.raises(ValueError):
        validate_point(-181, 18)


def test_distance_is_evidence_not_identity():
    out = distance_evidence(-66.1, 18.4, -66.2, 18.5)
    assert out["distance_m"] > 0
    assert out["identity_semantics"] == "CANDIDATE_NOT_IDENTITY"


def test_unknown_relation_fails_before_io(tmp_path: Path):
    with pytest.raises(ValueError):
        join_evidence(tmp_path / "a.geojson", tmp_path / "b.geojson", "NEAREST")

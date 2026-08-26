from __future__ import annotations

import pytest

from pipeline.marine_reference_run import (
    GUAYAMA_PUNTA_TUNA_DISCOVERY_V0_1,
    GeometryRole,
    ReferenceAOI,
    SpatialRelation,
    build_reference_queries,
    classify_bbox_relation,
    esri_feature_envelope,
)
from pipeline.marine_sources import BoundingBox


def test_discovery_corridor_is_not_certified_visualization() -> None:
    aoi = GUAYAMA_PUNTA_TUNA_DISCOVERY_V0_1
    assert aoi.role is GeometryRole.DISCOVERY_CORRIDOR
    assert aoi.certified is False
    with pytest.raises(ValueError, match="certified registered visualization"):
        aoi.require_visualization_certification()


def test_discovery_corridor_cannot_be_marked_certified() -> None:
    with pytest.raises(ValueError, match="discovery corridor"):
        ReferenceAOI(
            aoi_id="bad",
            bbox=BoundingBox(-66.2, 17.5, -65.8, 18.05),
            role=GeometryRole.DISCOVERY_CORRIDOR,
            provenance="test",
            certified=True,
        )


def test_certified_registered_visualization_passes_gate() -> None:
    aoi = ReferenceAOI(
        aoi_id="registered",
        bbox=BoundingBox(-66.1, 17.6, -65.9, 17.9),
        role=GeometryRole.REGISTERED_VISUALIZATION,
        provenance="control-point registration artifact sha256=abc",
        certified=True,
    )
    aoi.require_visualization_certification()


def test_reference_queries_cover_required_source_families() -> None:
    queries = build_reference_queries(GUAYAMA_PUNTA_TUNA_DISCOVERY_V0_1)
    assert set(queries) == {
        "ncei_multibeam",
        "ncei_sounding",
        "nos_bag",
        "usiei_topobathy",
        "usiei_bathymetric",
        "usiei_other_bathymetric",
    }
    assert all("-66.2" in url and "17.5" in url for url in queries.values())


def test_bbox_relation_fully_within() -> None:
    aoi = BoundingBox(-66.2, 17.5, -65.8, 18.05)
    feature = BoundingBox(-66.1, 17.6, -65.9, 17.9)
    assert classify_bbox_relation(aoi, feature) is SpatialRelation.FULLY_WITHIN


def test_bbox_relation_partial() -> None:
    aoi = BoundingBox(-66.2, 17.5, -65.8, 18.05)
    feature = BoundingBox(-66.3, 17.6, -65.9, 17.9)
    assert classify_bbox_relation(aoi, feature) is SpatialRelation.PARTIAL


def test_bbox_relation_touch_only() -> None:
    aoi = BoundingBox(-66.2, 17.5, -65.8, 18.05)
    feature = BoundingBox(-66.4, 17.7, -66.2, 17.9)
    assert classify_bbox_relation(aoi, feature) is SpatialRelation.TOUCH_ONLY


def test_bbox_relation_outside() -> None:
    aoi = BoundingBox(-66.2, 17.5, -65.8, 18.05)
    feature = BoundingBox(-67.0, 17.6, -66.5, 17.9)
    assert classify_bbox_relation(aoi, feature) is SpatialRelation.OUTSIDE


def test_bbox_relation_null_empty() -> None:
    aoi = BoundingBox(-66.2, 17.5, -65.8, 18.05)
    assert classify_bbox_relation(aoi, None) is SpatialRelation.NULL_EMPTY


def test_esri_feature_envelope() -> None:
    feature = {
        "attributes": {"OBJECTID": 1},
        "geometry": {
            "rings": [
                [[-66.1, 17.6], [-65.9, 17.6], [-65.9, 17.8], [-66.1, 17.8], [-66.1, 17.6]]
            ]
        },
    }
    envelope = esri_feature_envelope(feature)
    assert envelope == BoundingBox(-66.1, 17.6, -65.9, 17.8)


def test_esri_feature_null_geometry_is_null_empty_candidate() -> None:
    assert esri_feature_envelope({"attributes": {"OBJECTID": 1}, "geometry": None}) is None


def test_esri_feature_rejects_malformed_coordinates() -> None:
    with pytest.raises(ValueError, match="numeric"):
        esri_feature_envelope({"geometry": {"rings": [[[-66.1, "bad"]]]}})

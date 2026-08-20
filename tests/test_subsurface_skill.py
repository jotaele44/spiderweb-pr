from __future__ import annotations

import json
from pathlib import Path
import zipfile

import pytest
from shapely.geometry import Point, Polygon

from spiderweb.subsurface.aoi import freeze_aoi
from spiderweb.subsurface.dispatcher import LAYER_FAMILIES, SubsurfaceDispatcher
from spiderweb.subsurface.evidence import (
    EvidenceTier,
    SpatialState,
    adjudicate_feature,
    mark_top_score_ties,
    validate_records,
)


KML = b'''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark><Polygon>
<outerBoundaryIs><LinearRing><coordinates>
-66.1,18.0,5 -66.0,18.0,5 -66.0,18.1,5 -66.1,18.0,5
</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark></Document></kml>'''


def test_kml_geojson_equivalent_geometry_freezes_to_same_hash(tmp_path: Path):
    kml = tmp_path / "aoi.kml"
    kml.write_bytes(KML)
    geojson = tmp_path / "aoi.geojson"
    geojson.write_text(
        json.dumps(
            {
                "type": "Polygon",
                "coordinates": [[[-66.1, 18.0], [-66.0, 18.0], [-66.0, 18.1], [-66.1, 18.0]]],
            }
        ),
        encoding="utf-8",
    )
    a = freeze_aoi(kml)
    b = freeze_aoi(geojson)
    assert a.canonical_sha256 == b.canonical_sha256
    assert a.source_sha256 != b.source_sha256
    assert a.source_has_z is True
    assert a.analysis_dimension_loss == ("Z",)


def test_kmz_member_hash_and_container_hash_are_separate(tmp_path: Path):
    kmz = tmp_path / "aoi.kmz"
    with zipfile.ZipFile(kmz, "w") as zf:
        zf.writestr("doc.kml", KML)
    frozen = freeze_aoi(kmz)
    assert frozen.kmz_member == "doc.kml"
    assert frozen.kmz_member_sha256
    assert frozen.source_sha256 != frozen.kmz_member_sha256


def test_invalid_polygon_fails_closed(tmp_path: Path):
    path = tmp_path / "invalid.geojson"
    path.write_text(
        json.dumps(
            {
                "type": "Polygon",
                "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid"):
        freeze_aoi(path)


def test_proximity_only_cannot_promote_to_direct():
    aoi = Polygon([(0, 0), (2, 0), (2, 2), (0, 2), (0, 0)])
    record = adjudicate_feature(
        aoi=aoi,
        record_id="r1",
        source_id="s1",
        layer_family="GEOLOGY_KARST_CAVES",
        source_uri="fixture://s1",
        feature=Point(1, 1),
        asserted_tier=EvidenceTier.DIRECT,
        basis=["proximity_only"],
    )
    assert record.evidence_tier == EvidenceTier.CANDIDATE
    assert record.spatial_state == SpatialState.FULLY_WITHIN


def test_null_geometry_is_unresolved_not_negative():
    aoi = Polygon([(0, 0), (2, 0), (2, 2), (0, 2), (0, 0)])
    record = adjudicate_feature(
        aoi=aoi,
        record_id="r1",
        source_id="s1",
        layer_family="AQUIFERS_WELLS_SPRINGS",
        source_uri="fixture://s1",
        feature=None,
        asserted_tier=EvidenceTier.DIRECT,
        basis=["authoritative_id"],
    )
    assert record.evidence_tier == EvidenceTier.UNRESOLVED
    assert record.spatial_state == SpatialState.NULL_EMPTY


def test_touch_only_is_distinct_from_partial():
    aoi = Polygon([(0, 0), (2, 0), (2, 2), (0, 2), (0, 0)])
    record = adjudicate_feature(
        aoi=aoi,
        record_id="r1",
        source_id="s1",
        layer_family="FAULTS_STRUCTURES",
        source_uri="fixture://s1",
        feature=Point(0, 1),
        asserted_tier=EvidenceTier.SUPPORTING,
        basis=["certified_geometry"],
    )
    assert record.spatial_state == SpatialState.TOUCH_ONLY


def test_duplicate_record_ids_fail_closed():
    aoi = Polygon([(0, 0), (2, 0), (2, 2), (0, 2), (0, 0)])
    kwargs = dict(
        aoi=aoi,
        record_id="dup",
        source_id="s1",
        layer_family="FAULTS_STRUCTURES",
        source_uri="fixture://s1",
        feature=Point(1, 1),
        asserted_tier=EvidenceTier.SUPPORTING,
        basis=["certified_geometry"],
    )
    records = [adjudicate_feature(**kwargs), adjudicate_feature(**kwargs)]
    with pytest.raises(ValueError, match="duplicate"):
        validate_records(records)


def test_tied_top_scores_are_review_flags_not_tiebroken():
    aoi = Polygon([(0, 0), (2, 0), (2, 2), (0, 2), (0, 0)])
    records = []
    for record_id in ("a", "b"):
        records.append(
            adjudicate_feature(
                aoi=aoi,
                record_id=record_id,
                source_id=record_id,
                layer_family="HISTORICAL_CORROBORATION",
                source_uri=f"fixture://{record_id}",
                feature=Point(1, 1),
                asserted_tier=EvidenceTier.CANDIDATE,
                basis=["historical_continuity"],
                score=0.8,
            )
        )
    marked = mark_top_score_ties(records)
    assert {r.record_id for r in marked if r.tied_top_score} == {"a", "b"}


def test_dispatch_missing_handler_is_open_not_negative():
    dispatcher = SubsurfaceDispatcher()
    plan = dispatcher.plan()
    assert {task.family for task in plan} == set(LAYER_FAMILIES)
    assert all(task.state == "OPEN" for task in plan)
    assert all("not" in task.reason for task in plan)

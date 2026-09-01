from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from shapely.geometry import Polygon, mapping

from spiderweb.subsurface.aoi import FrozenAOI
from spiderweb.subsurface.adapters import run_arcgis_source, run_ogc_source
from spiderweb.subsurface.runner import certify_families, source_ledger
from spiderweb.subsurface.sources import (
    DEFAULT_SOURCES,
    SourceKind,
    SourceSpec,
    SourceStatus,
    validate_source_denominator,
)


def aoi() -> FrozenAOI:
    geom = Polygon([(-66.2, 18.0), (-66.0, 18.0), (-66.0, 18.2), (-66.2, 18.0)])
    return FrozenAOI(
        source_path="fixture.geojson",
        source_format="GEOJSON",
        source_crs="OGC:CRS84",
        source_sha256="a" * 64,
        source_size=1,
        frozen_at_utc="2026-08-20T00:00:00+00:00",
        source_feature_count=1,
        source_geometry_type="Polygon",
        source_has_z=False,
        analysis_geometry_type="Polygon",
        analysis_dimension_loss=(),
        canonical_geojson=mapping(geom),
        canonical_sha256="b" * 64,
    )


def arcgis_spec() -> SourceSpec:
    return SourceSpec(
        "FIX_ARC", "GEOLOGY_KARST_CAVES", "fixture", "fixture",
        SourceKind.ARCGIS_LAYER, "https://example.test/FeatureServer",
        SourceStatus.VERIFIED_QUERYABLE, layer_id=3,
        stable_id_fields=("OBJECTID",), evidence_role="SUPPORTING",
    )


def test_source_denominator_covers_every_family():
    counts = validate_source_denominator()
    assert counts["sources"] == len(DEFAULT_SOURCES)
    assert all(
        counts[f"{family}:sources"] >= 1
        for family in {source.family for source in DEFAULT_SOURCES}
    )


def test_arcgis_paging_closes_exact_count_and_snapshots(tmp_path: Path):
    def fetch(url: str) -> bytes:
        query = parse_qs(urlparse(url).query)
        if query.get("returnCountOnly") == ["true"]:
            return json.dumps({"count": 3}).encode()
        offset = int(query["resultOffset"][0])
        rows = [
            {
                "type": "Feature",
                "id": n,
                "geometry": {"type": "Point", "coordinates": [-66.1, 18.1]},
                "properties": {"OBJECTID": n},
            }
            for n in range(offset + 1, min(offset + 2, 3) + 1)
        ]
        return json.dumps({"type": "FeatureCollection", "features": rows}).encode()

    records, receipt = run_arcgis_source(
        arcgis_spec(), aoi(), fetch=fetch, snapshot_dir=tmp_path, page_size=2
    )
    assert len(records) == 3
    assert receipt.expected_count == 3
    assert receipt.retained_count == 3
    assert receipt.page_count == 2
    assert receipt.state == "PASS"
    assert receipt.complete is True
    assert sum(page.row_count for page in receipt.pages) == 3
    source_dir = tmp_path / "FIX_ARC"
    assert (source_dir / "page_00000.json").exists()
    assert (source_dir / "count.raw.json").exists()
    count_manifest = json.loads((source_dir / "count_manifest.json").read_text())
    assert count_manifest["count"] == 3
    assert len(count_manifest["byte_sha256"]) == 64
    assert len(count_manifest["logical_sha256"]) == 64
    assert all(len(page.byte_sha256) == 64 for page in receipt.pages)
    assert all(len(page.logical_sha256) == 64 for page in receipt.pages)


def test_arcgis_zero_requires_successful_count_query_not_missing_source():
    def fetch(url: str) -> bytes:
        assert parse_qs(urlparse(url).query).get("returnCountOnly") == ["true"]
        return b'{"count":0}'

    records, receipt = run_arcgis_source(arcgis_spec(), aoi(), fetch=fetch)
    assert records == []
    assert receipt.state == "ZERO"
    assert receipt.complete is True
    assert receipt.expected_count == 0


def test_arcgis_count_without_count_field_fails_closed():
    with pytest.raises(RuntimeError, match="missing count"):
        run_arcgis_source(
            arcgis_spec(), aoi(), fetch=lambda _url: b'{"status":"ok"}'
        )


def test_arcgis_premature_empty_page_fails_closed():
    def fetch(url: str) -> bytes:
        query = parse_qs(urlparse(url).query)
        if query.get("returnCountOnly") == ["true"]:
            return b'{"count":2}'
        return b'{"type":"FeatureCollection","features":[]}'

    with pytest.raises(RuntimeError, match="premature empty"):
        run_arcgis_source(arcgis_spec(), aoi(), fetch=fetch)


def test_arcgis_service_error_is_not_zero():
    def fetch(_url: str) -> bytes:
        return b'{"error":{"code":500,"message":"failure"}}'

    with pytest.raises(RuntimeError, match="count query failed"):
        run_arcgis_source(arcgis_spec(), aoi(), fetch=fetch)


def test_ogc_follows_next_links_and_closes_number_matched():
    spec = SourceSpec(
        "FIX_OGC", "AQUIFERS_WELLS_SPRINGS", "fixture", "fixture",
        SourceKind.OGC_FEATURES, "https://example.test/items",
        SourceStatus.VERIFIED_QUERYABLE,
        stable_id_fields=("id",), evidence_role="DIRECT",
    )
    calls = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        if len(calls) == 1:
            obj = {
                "type": "FeatureCollection",
                "numberMatched": 2,
                "features": [
                    {
                        "type": "Feature",
                        "id": "a",
                        "geometry": {"type": "Point", "coordinates": [-66.1, 18.1]},
                        "properties": {},
                    }
                ],
                "links": [{"rel": "next", "href": "https://example.test/page2"}],
            }
        else:
            obj = {
                "type": "FeatureCollection",
                "numberMatched": 2,
                "features": [
                    {
                        "type": "Feature",
                        "id": "b",
                        "geometry": {"type": "Point", "coordinates": [-66.1, 18.1]},
                        "properties": {},
                    }
                ],
                "links": [],
            }
        return json.dumps(obj).encode()

    records, receipt = run_ogc_source(spec, aoi(), fetch=fetch)
    assert len(records) == 2
    assert receipt.state == "PASS"
    assert receipt.complete is True
    assert receipt.page_count == 2


def test_ogc_pagination_cycle_fails_closed():
    spec = SourceSpec(
        "FIX_OGC", "AQUIFERS_WELLS_SPRINGS", "fixture", "fixture",
        SourceKind.OGC_FEATURES, "https://example.test/items",
        SourceStatus.VERIFIED_QUERYABLE,
    )

    def fetch(url: str) -> bytes:
        obj = {
            "type": "FeatureCollection",
            "numberMatched": 2,
            "features": [],
            "links": [{"rel": "next", "href": url}],
        }
        return json.dumps(obj).encode()

    with pytest.raises(RuntimeError, match="pagination cycle"):
        run_ogc_source(spec, aoi(), fetch=fetch)


def test_unexecuted_queryable_source_is_not_negative_evidence():
    rows = source_ledger([arcgis_spec()], [])
    assert rows[0].run_state == "NOT_RUN"
    assert rows[0].terminal is False


def test_open_required_source_blocks_family_certification():
    sources = [
        SourceSpec(
            "OPEN_REQUIRED", "FAULTS_STRUCTURES", "UNRESOLVED", "missing",
            SourceKind.PLACEHOLDER, "", SourceStatus.OPEN,
        )
    ]
    cert = certify_families(source_ledger(sources, []))
    faults = next(row for row in cert if row.family == "FAULTS_STRUCTURES")
    assert faults.state == "OPEN"
    assert faults.open_sources == ("OPEN_REQUIRED",)


def test_reference_source_is_not_terminal_until_exact_payload_is_frozen():
    source = SourceSpec(
        "REF", "HISTORICAL_CORROBORATION", "USGS", "reference",
        SourceKind.REFERENCE_PAGE, "https://example.test/reference",
        SourceStatus.VERIFIED_REFERENCE,
    )
    row = source_ledger([source], [])[0]
    assert row.run_state == "NOT_RUN"
    assert row.terminal is False
    assert "byte-frozen" in row.reason

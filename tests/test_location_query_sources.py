from __future__ import annotations

from spiderweb.location_query_sources import build_request_specs, query_bbox


def test_radius_bbox_is_nonzero_and_contains_center() -> None:
    query = {
        "geometry": {
            "type": "radius",
            "lat": 18.0119,
            "lon": -66.2396,
            "radius_m": 2000,
        }
    }
    west, south, east, north = query_bbox(query)
    assert west < -66.2396 < east
    assert south < 18.0119 < north


def test_geojson_bbox_uses_all_coordinates() -> None:
    query = {
        "geometry": {
            "type": "geojson",
            "geojson": {
                "type": "Polygon",
                "coordinates": [[
                    [-66.2, 18.0],
                    [-66.0, 18.0],
                    [-66.0, 18.2],
                    [-66.2, 18.2],
                    [-66.2, 18.0],
                ]],
            },
        }
    }
    assert query_bbox(query) == (-66.2, 18.0, -66.0, 18.2)


def test_ssurgo_specs_are_bounded_to_two_source_manifestations() -> None:
    provider = {
        "wfs_endpoint": "https://sdmdataaccess.sc.egov.usda.gov/Spatial/SDMWGS84Geographic.wfs",
    }
    query = {
        "geometry": {
            "type": "bbox",
            "west": -66.1,
            "south": 18.2,
            "east": -65.9,
            "north": 18.4,
        }
    }
    rows = build_request_specs("SSURGO_SOILS", provider, query)
    assert [row["request_role"] for row in rows] == ["SurveyAreaPoly", "MapunitPoly"]
    assert all(row["identity_state"] == "SOURCE_MANIFESTATION" for row in rows)
    assert all("BBOX=" in row["url"] for row in rows)


def test_3dhp_metadata_is_discovery_not_source_identity() -> None:
    provider = {
        "feature_service": "https://3dhp.usgs.gov/arcgis/rest/services/usgs_3dhp_all/FeatureServer",
    }
    query = {
        "geometry": {
            "type": "bbox",
            "west": -66.1,
            "south": 18.2,
            "east": -65.9,
            "north": 18.4,
        }
    }
    rows = build_request_specs("USGS_3DHP_NHD", provider, query)
    assert len(rows) == 1
    assert rows[0]["identity_state"] == "DISCOVERY_FOR_LAYER_DENOMINATOR"
    assert rows[0]["url"].endswith("?f=json")


def test_fema_wms_capabilities_remains_resolver_only() -> None:
    provider = {
        "wms_capabilities": "https://hazards.fema.gov/gis/nfhl/services/public/NFHL/MapServer/WMSServer?request=GetCapabilities&service=WMS",
    }
    query = {
        "geometry": {
            "type": "point",
            "lat": 18.4,
            "lon": -66.0,
        }
    }
    rows = build_request_specs("FEMA_NFHL", provider, query)
    assert len(rows) == 1
    assert rows[0]["identity_state"] == "RESOLVER_ONLY"


def test_usace_ports_preserves_four_source_manifestations() -> None:
    provider = {
        "layers": [
            {"role": "ports", "url": "https://example.invalid/0"},
            {"role": "principal_ports", "url": "https://example.invalid/1"},
            {"role": "navigation_facilities", "url": "https://example.invalid/2"},
            {"role": "waterway_network_nodes", "url": "https://example.invalid/3"},
        ]
    }
    query = {
        "geometry": {
            "type": "bbox",
            "west": -66.2,
            "south": 18.1,
            "east": -65.8,
            "north": 18.5,
        }
    }
    rows = build_request_specs("USACE_PORTS_NAV", provider, query)
    assert len(rows) == 4
    assert {row["request_role"] for row in rows} == {
        "ports",
        "principal_ports",
        "navigation_facilities",
        "waterway_network_nodes",
    }
    assert all(row["identity_state"] == "SOURCE_MANIFESTATION" for row in rows)

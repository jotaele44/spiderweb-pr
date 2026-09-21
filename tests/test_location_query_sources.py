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
    assert all(row["identity_state"] == "RESOLVER_STAGE_SOURCE_MANIFESTATION" for row in rows)
    assert all("FILTER=" in row["url"] for row in rows)
    assert all("SRSNAME=EPSG%3A4326" in row["url"] for row in rows)
    assert all("OUTPUTFORMAT=GML2" in row["url"] for row in rows)
    assert all("MAXFEATURES=250000" in row["url"] for row in rows)
    assert all(row["wfs_max_features"] == 250000 for row in rows)
    assert all(row["truncation_policy"] == "FAIL_IF_RETURNED_COUNT_REACHES_REQUEST_LIMIT" for row in rows)


def test_3dhp_certified_six_layer_denominator_routes_aoi_queries() -> None:
    provider = {
        "status": "READY_SPECIALIZED",
        "feature_service": "https://hydro.nationalmap.gov/arcgis/rest/services/3DHP_all/FeatureServer",
        "layers": [
            {"id": 20, "role": "hydrolocation_sink_spring_waterbody_outlet"},
            {"id": 30, "role": "hydrolocation_headwater_terminus_divergence_confluence_catchment_outlet"},
            {"id": 40, "role": "hydrolocation_reach_code_external_connection"},
            {"id": 50, "role": "flowline"},
            {"id": 60, "role": "waterbody"},
            {"id": 80, "role": "catchment"},
        ],
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
    assert len(rows) == 6
    assert {row["request_role"] for row in rows} == {
        "hydrolocation_sink_spring_waterbody_outlet",
        "hydrolocation_headwater_terminus_divergence_confluence_catchment_outlet",
        "hydrolocation_reach_code_external_connection",
        "flowline",
        "waterbody",
        "catchment",
    }
    assert all(row["identity_state"] == "SOURCE_MANIFESTATION" for row in rows)
    assert all(row["protocol"] == "ARCGIS_FEATURE_LAYER" for row in rows)


def test_fema_nfhl_rest_metadata_remains_resolver_only() -> None:
    provider = {
        "map_service": "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer",
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
    assert rows[0]["identity_state"] == "DISCOVERY_FOR_LAYER_DENOMINATOR"
    assert rows[0]["request_role"] == "nfhl_map_service_denominator"
    assert rows[0]["protocol"] == "ARCGIS_METADATA"
    assert rows[0]["url"].endswith("?f=json")


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


def test_point_bbox_is_nonzero_for_envelope_query() -> None:
    west, south, east, north = query_bbox({
        "geometry": {"type": "point", "lat": 18.3, "lon": -66.0}
    })
    assert west < -66.0 < east
    assert south < 18.3 < north


def test_feature_collection_bbox_uses_all_features() -> None:
    bbox = query_bbox({
        "geometry": {
            "type": "geojson",
            "geojson": {
                "type": "FeatureCollection",
                "features": [
                    {"type": "Feature", "geometry": {"type": "Point", "coordinates": [-66.2, 18.1]}},
                    {"type": "Feature", "geometry": {"type": "Point", "coordinates": [-65.8, 18.5]}},
                ],
            },
        }
    })
    assert bbox == (-66.2, 18.1, -65.8, 18.5)


def test_arcgis_specs_require_object_id_denominator() -> None:
    provider = {
        "layer_url": "https://example.invalid/FeatureServer/0",
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
    rows = build_request_specs("USFWS_NWI", provider, query)
    assert len(rows) == 1
    row = rows[0]
    assert row["protocol"] == "ARCGIS_FEATURE_LAYER"
    assert row["pagination_policy"] == "OBJECT_ID_DENOMINATOR_THEN_BATCH"
    assert "returnIdsOnly=true" in row["url"]
    assert row["layer_url"] == provider["layer_url"]

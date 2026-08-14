import json

import pytest

from integration.crim_lookup import (
    CrimClient,
    CrimLookup,
    HttpResult,
    IdentityState,
    InvalidInputError,
    LookupMode,
    LookupState,
    PaginationError,
    SchemaDriftError,
    SourceResponseError,
    classify_tipo,
    graph_node_for_feature,
    normalize_identifier,
    validate_layer_metadata,
    validate_lon_lat,
)


def _result(payload, url="https://example.test/query", status=200, content_type="application/json"):
    return HttpResult(status, content_type, json.dumps(payload).encode(), url)


def test_identifier_escapes_quotes_and_preserves_zeroes():
    seen = {}

    def transport(url, params):
        seen.update(params)
        return _result({"features": []}, url)

    lookup = CrimLookup(CrimClient(transport=transport))
    result = lookup.identifier(LookupMode.NUM_CATASTRO, "0012'34", return_geometry=False)
    assert result.state == LookupState.VALID_ZERO_RESULT
    assert seen["where"] == "NUM_CATASTRO='0012''34'"
    assert normalize_identifier(" 001234 ") == "001234"


def test_exact_identifier_multiple_is_unresolved_not_first_match():
    features = [{"attributes": {"OBJECTID": 1}}, {"attributes": {"OBJECTID": 2}}]
    lookup = CrimLookup(CrimClient(transport=lambda u, p: _result({"features": features}, u)))
    result = lookup.identifier(LookupMode.GLOBALID, "{X}")
    assert result.match_count == 2
    assert result.state == LookupState.MULTIPLE_CANDIDATES
    assert result.identity_state == IdentityState.UNRESOLVED
    assert len(result.candidates) == 2


def test_arcgis_error_object_is_not_zero_result():
    lookup = CrimLookup(CrimClient(transport=lambda u, p: _result({"error": {"code": 400}}, u)))
    with pytest.raises(SourceResponseError):
        lookup.identifier(LookupMode.NUM_CATASTRO, "123")


def test_invalid_json_is_source_error_not_zero():
    client = CrimClient(
        transport=lambda u, p: HttpResult(200, "text/html", b"<html>oops</html>", u)
    )
    with pytest.raises(SourceResponseError):
        client.count()


def test_coordinate_validation_and_swap_warning():
    _, _, warnings = validate_lon_lat(18.2, -66.1)
    assert any("swapped" in x for x in warnings)
    with pytest.raises(InvalidInputError):
        validate_lon_lat(500, 18)


def test_point_retains_all_boundary_candidates():
    features = [
        {"attributes": {"OBJECTID": 10, "TIPO": "P"}},
        {"attributes": {"OBJECTID": 11, "TIPO": "P"}},
    ]
    lookup = CrimLookup(CrimClient(transport=lambda u, p: _result({"features": features}, u)))
    result = lookup.point(-66.05, 18.35)
    assert result.state == LookupState.MULTIPLE_CANDIDATES
    assert result.identity_state == IdentityState.CANDIDATE_NOT_IDENTITY
    assert [x["attributes"]["OBJECTID"] for x in result.candidates] == [10, 11]


def test_tipo_is_not_conflated_with_parcel():
    assert classify_tipo({"attributes": {"TIPO": "P"}}) == "PARCEL"
    assert classify_tipo({"attributes": {"TIPO": "V"}}) == "ROAD"
    assert classify_tipo({"attributes": {"TIPO": "A"}}) == "WATER"
    node = graph_node_for_feature(
        {"attributes": {"GLOBALID": "g", "TIPO": "V"}}, "a" * 64
    )
    assert node["node_type"] == "CRIM_SPATIAL_FEATURE"


def test_schema_contract_requires_core_fields_and_crs():
    meta = {
        "id": 0,
        "geometryType": "esriGeometryPolygon",
        "sourceSpatialReference": {"wkid": 32161},
        "fields": [
            {"name": x}
            for x in ["OBJECTID", "GLOBALID", "NUM_CATASTRO", "OLDPID", "TIPO", "CATEGORIA"]
        ],
    }
    validate_layer_metadata(meta)
    broken = dict(meta)
    broken["fields"] = [{"name": "OBJECTID"}]
    with pytest.raises(SchemaDriftError):
        validate_layer_metadata(broken)


def test_complete_query_arithmetic_closure_and_order():
    def transport(url, params):
        if params.get("returnCountOnly") == "true":
            return _result({"count": 3}, url)
        if params.get("returnIdsOnly") == "true":
            return _result({"objectIds": [9, 2, 7]}, url)
        ids = [int(x) for x in params["objectIds"].split(",")]
        return _result(
            {"features": [{"attributes": {"OBJECTID": x, "TIPO": "P"}} for x in reversed(ids)]},
            url,
        )

    result = CrimLookup(CrimClient(transport=transport)).complete_query(chunk_size=2)
    assert result.match_count == 3
    assert [f["attributes"]["OBJECTID"] for f in result.candidates] == [9, 2, 7]


def test_complete_query_detects_count_ids_race():
    def transport(url, params):
        if params.get("returnCountOnly") == "true":
            return _result({"count": 3}, url)
        if params.get("returnIdsOnly") == "true":
            return _result({"objectIds": [1, 2]}, url)
        raise AssertionError

    with pytest.raises(PaginationError, match="count/object-id mismatch"):
        CrimLookup(CrimClient(transport=transport)).complete_query()


def test_complete_query_detects_duplicate_manifestation():
    def transport(url, params):
        if params.get("returnCountOnly") == "true":
            return _result({"count": 2}, url)
        if params.get("returnIdsOnly") == "true":
            return _result({"objectIds": [1, 2]}, url)
        return _result(
            {"features": [{"attributes": {"OBJECTID": 1}}, {"attributes": {"OBJECTID": 1}}]},
            url,
        )

    with pytest.raises(PaginationError, match="duplicate OBJECTID"):
        CrimLookup(CrimClient(transport=transport)).complete_query()

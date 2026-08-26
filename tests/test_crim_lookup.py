import json
from pathlib import Path

import pytest

from integration.crim_lookup import (
    LAYER_URL,
    QUERY_URL,
    REQUIRED_FIELDS,
    CrimClient,
    CrimError,
    CrimLookup,
    HttpResult,
    IdentityState,
    InvalidInputError,
    LookupMode,
    LookupResult,
    LookupState,
    PaginationError,
    SchemaDriftError,
    SourceResponseError,
    SourceTransportError,
    classify_tipo,
    graph_node_for_feature,
    normalize_identifier,
    validate_layer_metadata,
    validate_lon_lat,
)


def _result(
    payload,
    url="https://example.test/query",
    status=200,
    content_type="application/json",
):
    return HttpResult(status, content_type, json.dumps(payload).encode(), url)


def _assert_schema_valid(payload):
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(Path("schemas/crim_lookup.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(payload)


def test_identifier_escapes_quotes_and_preserves_zeroes():
    seen = {}

    def transport(url, params):
        seen.update(params)
        return _result({"features": []}, url)

    lookup = CrimLookup(CrimClient(transport=transport))
    result = lookup.identifier(
        LookupMode.NUM_CATASTRO, "0012'34", return_geometry=False
    )
    assert result.state == LookupState.VALID_ZERO_RESULT
    assert seen["where"] == "NUM_CATASTRO='0012''34'"
    assert normalize_identifier(" 001234 ") == "001234"


def test_exact_identifier_multiple_is_unresolved_not_first_match():
    features = [{"attributes": {"OBJECTID": 1}}, {"attributes": {"OBJECTID": 2}}]
    lookup = CrimLookup(
        CrimClient(transport=lambda u, p: _result({"features": features}, u))
    )
    result = lookup.identifier(LookupMode.GLOBALID, "{X}")
    assert result.match_count == 2
    assert result.state == LookupState.MULTIPLE_CANDIDATES
    assert result.identity_state == IdentityState.UNRESOLVED
    assert len(result.candidates) == 2


def test_single_nonunique_identifier_is_provisional():
    feature = {"attributes": {"OBJECTID": 1, "GLOBALID": "{X}"}}
    lookup = CrimLookup(
        CrimClient(transport=lambda u, p: _result({"features": [feature]}, u))
    )
    result = lookup.identifier(LookupMode.GLOBALID, "{X}")
    assert result.state == LookupState.MATCH
    assert result.identity_state == IdentityState.PROVISIONAL


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"features": None},
        {"features": {}},
        {"features": "not-an-array"},
        {"features": ["not-an-object"]},
        {"features": [{}]},
        {"features": [{"attributes": None}]},
        {"features": [{"attributes": {"OBJECTID": True}}]},
        {"features": [{"attributes": {"OBJECTID": "1"}}]},
    ],
)
def test_identifier_rejects_missing_or_malformed_features(payload):
    lookup = CrimLookup(CrimClient(transport=lambda u, p: _result(payload, u)))
    with pytest.raises(SourceResponseError, match="feature"):
        lookup.identifier(LookupMode.NUM_CATASTRO, "123")


@pytest.mark.parametrize("mode", ["identifier", "point"])
def test_identifier_and_point_reject_truncated_results(mode):
    payload = {
        "features": [{"attributes": {"OBJECTID": 1}}],
        "exceededTransferLimit": True,
    }
    lookup = CrimLookup(CrimClient(transport=lambda u, p: _result(payload, u)))
    with pytest.raises(PaginationError, match="exceeded transfer limit"):
        if mode == "identifier":
            lookup.identifier(LookupMode.OBJECTID, 1)
        else:
            lookup.point(-66.05, 18.35)


def test_rejects_nonboolean_transfer_limit_flag():
    payload = {"features": [], "exceededTransferLimit": "false"}
    lookup = CrimLookup(CrimClient(transport=lambda u, p: _result(payload, u)))
    with pytest.raises(SourceResponseError, match="must be boolean"):
        lookup.point(-66.05, 18.35)


def test_arcgis_error_object_is_not_zero_result():
    lookup = CrimLookup(
        CrimClient(transport=lambda u, p: _result({"error": {"code": 400}}, u))
    )
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
    with pytest.raises(InvalidInputError):
        validate_lon_lat(False, 18)


def test_point_retains_all_boundary_candidates():
    features = [
        {"attributes": {"OBJECTID": 10, "TIPO": "P"}},
        {"attributes": {"OBJECTID": 11, "TIPO": "P"}},
    ]
    lookup = CrimLookup(
        CrimClient(transport=lambda u, p: _result({"features": features}, u))
    )
    result = lookup.point(-66.05, 18.35)
    assert result.state == LookupState.MULTIPLE_CANDIDATES
    assert result.identity_state == IdentityState.CANDIDATE_NOT_IDENTITY
    assert [x["attributes"]["OBJECTID"] for x in result.candidates] == [10, 11]


def test_tipo_is_not_conflated_with_parcel():
    assert classify_tipo({"attributes": {"TIPO": "P"}}) == "PARCEL"
    assert classify_tipo({"attributes": {"TIPO": "V"}}) == "ROAD"
    assert classify_tipo({"attributes": {"TIPO": "A"}}) == "WATER"
    assert classify_tipo({"attributes": {"TIPO": None}}) == "UNKNOWN"
    assert classify_tipo({"attributes": {"TIPO": 1}}) == "UNKNOWN"
    node = graph_node_for_feature(
        {"attributes": {"OBJECTID": 1, "GLOBALID": "g", "TIPO": "V"}},
        "a" * 64,
    )
    assert node["node_type"] == "CRIM_SPATIAL_FEATURE"


def test_graph_nodes_do_not_collapse_duplicate_globalids():
    first = graph_node_for_feature(
        {"attributes": {"OBJECTID": 1, "GLOBALID": "duplicate", "TIPO": "P"}},
        "a" * 64,
    )
    second = graph_node_for_feature(
        {"attributes": {"OBJECTID": 2, "GLOBALID": "duplicate", "TIPO": "P"}},
        "a" * 64,
    )
    assert first["node_id"] != second["node_id"]
    assert first["objectid_raw"] == 1
    assert second["objectid_raw"] == 2


def test_graph_nodes_are_bound_to_canonicalized_source_manifestation():
    feature = {"attributes": {"OBJECTID": 1, "GLOBALID": "same"}}
    first = graph_node_for_feature(feature, "a" * 64)
    second = graph_node_for_feature(feature, "b" * 64)
    uppercase = graph_node_for_feature(feature, "A" * 64)
    assert first["node_id"] != second["node_id"]
    assert first["node_id"] == uppercase["node_id"]
    assert uppercase["source_manifest_sha256"] == "a" * 64


def test_graph_node_requires_manifestation_identity_inputs():
    with pytest.raises(InvalidInputError, match="integer OBJECTID"):
        graph_node_for_feature({"attributes": {"GLOBALID": "g"}}, "a" * 64)
    with pytest.raises(InvalidInputError, match="manifest SHA-256"):
        graph_node_for_feature({"attributes": {"OBJECTID": 1}}, "not-a-sha")


def test_schema_contract_requires_core_fields_and_crs():
    meta = {
        "id": 0,
        "geometryType": "esriGeometryPolygon",
        "sourceSpatialReference": {"wkid": 32161},
        "fields": [
            {"name": x}
            for x in [
                "OBJECTID",
                "GLOBALID",
                "NUM_CATASTRO",
                "OLDPID",
                "TIPO",
                "CATEGORIA",
            ]
        ],
    }
    validate_layer_metadata(meta)
    broken = dict(meta)
    broken["fields"] = [{"name": "OBJECTID"}]
    with pytest.raises(SchemaDriftError):
        validate_layer_metadata(broken)

    duplicated = dict(meta)
    duplicated["fields"] = [*meta["fields"], {"name": "OBJECTID"}]
    with pytest.raises(SchemaDriftError, match="duplicate field names"):
        validate_layer_metadata(duplicated)

    wrong_id_type = dict(meta)
    wrong_id_type["id"] = 0.0
    with pytest.raises(SchemaDriftError, match="layer id"):
        validate_layer_metadata(wrong_id_type)

    wrong_crs_type = dict(meta)
    wrong_crs_type["sourceSpatialReference"] = {"wkid": 32161.0}
    with pytest.raises(SchemaDriftError, match="native CRS"):
        validate_layer_metadata(wrong_crs_type)


def test_bbox_wraps_invalid_coordinate_types():
    lookup = CrimLookup(CrimClient(transport=lambda u, p: _result({"features": []}, u)))
    with pytest.raises(InvalidInputError, match="must be numeric"):
        lookup.bbox("west", 18.0, -66.0, 18.5)
    with pytest.raises(InvalidInputError, match="must be numeric"):
        lookup.bbox(False, 18.0, -66.0, 18.5)


def test_complete_query_arithmetic_closure_and_order():
    def transport(url, params):
        if params.get("returnCountOnly") == "true":
            return _result({"count": 3}, url)
        if params.get("returnIdsOnly") == "true":
            return _result({"objectIds": [9, 2, 7]}, url)
        ids = [int(x) for x in params["objectIds"].split(",")]
        return _result(
            {
                "features": [
                    {"attributes": {"OBJECTID": x, "TIPO": "P"}} for x in reversed(ids)
                ]
            },
            url,
        )

    result = CrimLookup(CrimClient(transport=transport)).complete_query(chunk_size=2)
    assert result.match_count == 3
    assert [f["attributes"]["OBJECTID"] for f in result.candidates] == [9, 2, 7]


@pytest.mark.parametrize("chunk_size", [True, 0, 1001, 2.5])
def test_complete_query_rejects_invalid_chunk_sizes(chunk_size):
    with pytest.raises(InvalidInputError, match="chunk_size"):
        CrimLookup().complete_query(chunk_size=chunk_size)


@pytest.mark.parametrize("where", [None, "", "   "])
def test_complete_query_rejects_invalid_where(where):
    with pytest.raises(InvalidInputError, match="where"):
        CrimLookup().complete_query(where=where)


def test_complete_query_detects_count_ids_race():
    def transport(url, params):
        if params.get("returnCountOnly") == "true":
            return _result({"count": 3}, url)
        if params.get("returnIdsOnly") == "true":
            return _result({"objectIds": [1, 2]}, url)
        raise AssertionError

    with pytest.raises(PaginationError, match="count/object-id mismatch"):
        CrimLookup(CrimClient(transport=transport)).complete_query()


def test_complete_query_rejects_missing_object_ids_for_zero_count():
    def transport(url, params):
        if params.get("returnCountOnly") == "true":
            return _result({"count": 0}, url)
        if params.get("returnIdsOnly") == "true":
            return _result({}, url)
        raise AssertionError

    with pytest.raises(SourceResponseError, match="objectIds"):
        CrimLookup(CrimClient(transport=transport)).complete_query()


def test_complete_query_accepts_explicit_null_object_ids_for_zero_count():
    def transport(url, params):
        if params.get("returnCountOnly") == "true":
            return _result({"count": 0}, url)
        if params.get("returnIdsOnly") == "true":
            return _result({"objectIds": None}, url)
        raise AssertionError

    result = CrimLookup(CrimClient(transport=transport)).complete_query()
    assert result.state == LookupState.VALID_ZERO_RESULT
    assert result.match_count == 0


def test_complete_query_detects_duplicate_manifestation():
    def transport(url, params):
        if params.get("returnCountOnly") == "true":
            return _result({"count": 2}, url)
        if params.get("returnIdsOnly") == "true":
            return _result({"objectIds": [1, 2]}, url)
        return _result(
            {
                "features": [
                    {"attributes": {"OBJECTID": 1}},
                    {"attributes": {"OBJECTID": 1}},
                ]
            },
            url,
        )

    with pytest.raises(PaginationError, match="duplicate OBJECTID"):
        CrimLookup(CrimClient(transport=transport)).complete_query()


def test_crim_lookup_schema_is_valid_draft_2020_12():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(Path("schemas/crim_lookup.schema.json").read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    assert set(schema["properties"]["mode"]["enum"]) == {
        mode.value for mode in LookupMode
    }


def test_source_config_matches_adapter_contract():
    config = json.loads(Path("configs/crim_source.json").read_text())
    assert config["layer_url"] == LAYER_URL
    assert config["query_url"] == QUERY_URL
    assert set(config["required_fields"]) == REQUIRED_FIELDS


def test_cli_emits_schema_shaped_success(capsys):
    import scripts.crim_lookup as cli

    class StubLookup:
        def identifier(self, mode, value):
            return LookupResult(
                state=LookupState.VALID_ZERO_RESULT,
                mode=mode,
                match_count=0,
                identity_state=IdentityState.CANDIDATE_NOT_IDENTITY,
            )

    rc = cli.main(["id", "OBJECTID", "-1"], lookup=StubLookup())
    payload = json.loads(capsys.readouterr().out)
    _assert_schema_valid(payload)
    assert rc == 0
    assert payload["state"] == "VALID_ZERO_RESULT"
    assert payload["mode"] == "OBJECTID"
    assert payload["candidates"] == []


@pytest.mark.parametrize(
    ("error", "state"),
    [
        (InvalidInputError("bad input"), "INVALID_INPUT"),
        (SchemaDriftError("changed schema"), "SCHEMA_DRIFT"),
        (PaginationError("partial result"), "TRUNCATED"),
        (SourceResponseError("bad response"), "SOURCE_ERROR"),
        (SourceTransportError("offline"), "SOURCE_ERROR"),
        (CrimError("unclassified"), "UNRESOLVED"),
    ],
)
def test_cli_emits_schema_shaped_known_errors(error, state, capsys):
    import scripts.crim_lookup as cli

    class StubLookup:
        def identifier(self, mode, value):
            raise error

    rc = cli.main(["id", "OBJECTID", "1"], lookup=StubLookup())
    payload = json.loads(capsys.readouterr().out)
    _assert_schema_valid(payload)
    assert rc == 2
    assert payload["state"] == state
    assert payload["mode"] == "OBJECTID"
    assert payload["identity_state"] == "UNRESOLVED"
    assert payload["warnings"]


def test_cli_maps_invalid_numeric_coordinates_to_structured_error(capsys):
    import scripts.crim_lookup as cli

    rc = cli.main(["point", "west", "18.2"])
    payload = json.loads(capsys.readouterr().out)
    _assert_schema_valid(payload)
    assert rc == 2
    assert payload["state"] == "INVALID_INPUT"
    assert payload["mode"] == "POINT"

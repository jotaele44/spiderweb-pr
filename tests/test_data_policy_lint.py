from scripts.check_data_policy import policy_violations


def test_allows_documented_placeholders_and_provenance_artifacts() -> None:
    assert policy_violations(
        [
            "outputs/.gitkeep",
            "cache/.gitkeep",
            "tile_cache/.gitkeep",
            "data/reference_geo/nid_dams_manifest.json",
            "data/usgs_ofr_98_038/derived/usgs_ofr_98_038_metallic_occurrences_wgs84.geojson",
            "tests/fixtures/valid_airspace_export/observations.jsonl",
            "exports/samples/observations.jsonl",
        ]
    ) == []


def test_rejects_runtime_directories_and_sensitive_artifacts() -> None:
    violations = policy_violations(
        [
            "outputs/export.geojson",
            "cache/model.db",
            "tile_cache/tile.png",
            "data/captures/flight.jpg",
            "flight_database.sqlite",
            "reports/run.jsonl",
            "outputs.zip",
        ]
    )

    assert len(violations) == 7
    assert any("outputs/export.geojson" in violation for violation in violations)
    assert any("cache/model.db" in violation for violation in violations)
    assert any("tile_cache/tile.png" in violation for violation in violations)
    assert any("data/captures/flight.jpg" in violation for violation in violations)
    assert any("flight_database.sqlite" in violation for violation in violations)
    assert any("reports/run.jsonl" in violation for violation in violations)
    assert any("outputs.zip" in violation for violation in violations)


def test_rejects_paths_that_escape_the_repository() -> None:
    assert policy_violations(["../outside.json"]) == [
        "../outside.json: path must be repository-relative"
    ]

from __future__ import annotations

import json
from pathlib import Path

from server.ingestion.ingest_tiger_pr import LAYER_SPECS, STATE_FIPS_PR

REPO_ROOT = Path(__file__).parent.parent
MANIFEST = REPO_ROOT / "data" / "tiger" / "2025" / "manifest.json"

EXPECTED_COUNTS = {
    "municipios": 78,
    "tracts": 981,
    "places": 292,
    "barrios": 939,
    "puma": 24,
}

GEOID_LENGTHS = {
    "municipios": 5,
    "tracts": 11,
    "places": 7,
    "barrios": 10,
    "puma": 7,
}


def test_tracked_tiger_manifest_is_portable_and_complete():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    layers = {entry["layer"]: entry for entry in manifest["layers"]}

    assert set(EXPECTED_COUNTS) <= set(layers)
    for layer, expected_count in EXPECTED_COUNTS.items():
        entry = layers[layer]
        source = entry["source"]
        output = entry["output"]

        assert output["feature_count"] == expected_count
        assert output["crs"] == "EPSG:4326"
        assert not Path(output["path"]).is_absolute()
        assert output["path"] == f"{layer}.geojson"
        assert len(source["sha256"]) == 64
        assert len(output["sha256"]) == 64
        assert source["bytes"] > 0
        assert output["bytes"] > 0


def test_tiger_sources_are_constrained_to_puerto_rico_geoids():
    assert STATE_FIPS_PR == "72"
    assert LAYER_SPECS["municipios"]["state_filter"] == STATE_FIPS_PR

    for layer in ("tracts", "places", "barrios", "puma"):
        filename = LAYER_SPECS[layer]["tiger_filename"].format(year=2025)
        assert "_72_" in filename

    assert GEOID_LENGTHS == {
        "municipios": 5,
        "tracts": 11,
        "places": 7,
        "barrios": 10,
        "puma": 7,
    }

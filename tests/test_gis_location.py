"""Identify location context: boundary membership and PR Grid V2 cursor lookup."""

from __future__ import annotations

import pytest

from spiderweb.gis_location import containing_feature, grid_v2_cursor_lookup

SQUARE = {
    "type": "Feature",
    "geometry": {
        "type": "Polygon",
        "coordinates": [
            [[-66.2, 18.2], [-66.0, 18.2], [-66.0, 18.4], [-66.2, 18.4], [-66.2, 18.2]]
        ],
    },
    "properties": {"NAME": "Demo", "GEOID": 72999},
}


def test_containing_feature_reports_name_and_string_id():
    assert containing_feature([SQUARE], -66.1, 18.3) == {"name": "Demo", "id": "72999"}
    assert containing_feature([SQUARE], -65.5, 18.3) is None


def test_grid_lookup_is_never_presented_as_a_record_binding():
    result = grid_v2_cursor_lookup(-66.1057, 18.4655)
    assert result["binding"] == "CURSOR_LOOKUP_NOT_RECORD_BINDING"
    assert result["evidence_state"] == "COMPUTED"
    if result["status"] == "UNAVAILABLE":
        assert result["cell_ids"] == []


def test_grid_lookup_resolves_san_juan_and_rejects_points_off_the_grid():
    pytest.importorskip("pyproj")
    inside = grid_v2_cursor_lookup(-66.1057, 18.4655, level="L0")
    assert inside["status"] == "OK"
    assert inside["cell_ids"] and all(
        cell.startswith("PRG2:L0:") for cell in inside["cell_ids"]
    )
    outside = grid_v2_cursor_lookup(-60.0, 18.4)
    assert outside["status"] == "OUTSIDE" and outside["cell_ids"] == []

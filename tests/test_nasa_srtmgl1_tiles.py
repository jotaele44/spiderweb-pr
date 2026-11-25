"""SRTM tile naming, true extents and AOI selection."""

from __future__ import annotations

import pytest

from source_adapters.nasa_srtmgl1.registry import load_tiles
from source_adapters.nasa_srtmgl1.tiles import grid_extent, parse_tile_id, tile_id_for, tiles_for_bbox

PR_AOI = (-67.95, 17.85, -65.20, 18.55)


def test_parse_and_format_round_trip() -> None:
    assert parse_tile_id("N18W067") == (18, -67)
    assert parse_tile_id("S56W072") == (-56, -72)
    assert tile_id_for(18, -67) == "N18W067"
    assert tile_id_for(-1, 5) == "S01E005"
    for bad in ("N18W67", "X18W067", "n18w067", "N90W000"):
        with pytest.raises(ValueError):
            parse_tile_id(bad)


def test_grid_extent_is_half_a_sample_beyond_whole_degrees() -> None:
    assert grid_extent("N18W067") == (-67.000138889, 17.999861111, -65.999861111, 19.000138889)


def test_pr_aoi_selects_the_six_registered_tiles() -> None:
    ids = [t.tile_id for t in load_tiles()]
    assert tiles_for_bbox(PR_AOI, ids) == ("N17W066", "N17W067", "N17W068", "N18W066", "N18W067", "N18W068")


def test_box_ending_on_a_degree_line_does_not_take_the_neighbour() -> None:
    tiles = {t.tile_id: t for t in load_tiles()}
    box = (-66.5, 17.5, -66.4, 18.0)
    assert tiles_for_bbox(box, tiles) == ("N17W067",)
    # The CMR footprint of N18W067 starts at 17.99972 and would have selected it.
    assert tiles["N18W067"].cmr_footprint_wsen[1] < box[3]


def test_bad_bbox_is_refused() -> None:
    with pytest.raises(ValueError):
        tiles_for_bbox((-66.0, 18.0, -67.0, 19.0), ["N18W067"])

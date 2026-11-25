"""SRTMGL1N source numbers (User Guide V3, Table 2) and per-tile platform shares."""

from __future__ import annotations

import numpy as np
import pytest

from source_adapters.nasa_srtmgl1.composition import composition
from source_adapters.nasa_srtmgl1.num_codes import SRTM_ROOT, classify


@pytest.mark.parametrize(
    ("value", "category", "platform_class"),
    [
        (1, "water", None), (2, "water", None), (5, "water", None),
        (11, "srtm_interpolated", "spaceborne"), (25, "srtm_interpolated", "spaceborne"),
        (21, "gmted2010", "compiled"), (31, "nga_undisclosed", "compiled"),
        (51, "ned", "compiled"), (52, "ned", "compiled"), (53, "ned", "compiled"),
        (72, "cded", "compiled"),
        (101, "aster_gdem2", "spaceborne"), (200, "aster_gdem2", "spaceborne"),
        (201, "srtm_measured", "spaceborne"), (224, "srtm_measured", "spaceborne"),
        (0, "unmapped", None), (3, "unmapped", None), (7, "unmapped", None), (100, "unmapped", None), (225, "unmapped", None),
    ],
)
def test_table_two_codes(value: int, category: str, platform_class: str | None) -> None:
    source = classify(value)
    assert (source.category, source.platform_class) == (category, platform_class)


def test_srtm_codes_carry_the_shuttle_root() -> None:
    assert classify(202).acquisition_root == SRTM_ROOT
    assert classify(11).acquisition_root == SRTM_ROOT
    assert classify(150).acquisition_root == "aster:terra:gdem2"


def test_shares_are_over_land_samples_only() -> None:
    grid = np.array([[2, 2, 2, 2], [202, 203, 204, 107], [51, 21, 2, 225]], dtype=np.uint8)
    result = composition(grid)
    assert result["samples"] == 12
    assert result["water_samples"] == 5 and result["unmapped_samples"] == 1 and result["land_samples"] == 6
    assert result["category_counts"]["srtm_measured"] == 3
    assert result["land_share_percent"]["srtm_measured"] == pytest.approx(50.0)
    assert result["platform_share_percent"] == {
        "compiled": pytest.approx(100 * 2 / 6, abs=1e-4),
        "spaceborne_insar": pytest.approx(50.0),
        "spaceborne_optical_stereo": pytest.approx(100 / 6, abs=1e-4),
    }
    assert result["num_value_histogram"]["2"] == 5


def test_all_water_tile_has_no_shares() -> None:
    result = composition(np.full((3, 3), 2, dtype=np.uint8))
    assert result["land_samples"] == 0
    assert set(result["land_share_percent"].values()) == {None}

"""SRTMGL1N source numbers (SRTM User Guide V3, Table 2, "Fill Values of the .NUM files").

Each value says where a pixel's height came from. Values the table does not list
are reported as ``unmapped``; they are counted, never guessed.
"""

from __future__ import annotations

from dataclasses import dataclass

SRTM_ROOT = "srtm:sts-99:2000-02"


@dataclass(frozen=True)
class NumSource:
    category: str
    label: str
    platform_class: str | None
    acquisition_root: str | None


WATER = NumSource("water", "water-masked (NGA SRTM Water Body Database)", None, None)
UNMAPPED = NumSource("unmapped", "value not listed in Table 2", None, None)

_EXACT: dict[int, NumSource] = {
    1: NumSource("water", "water-masked SRTM void", None, None),
    2: NumSource("water", "water-masked SRTM non-void", None, None),
    5: NumSource("water", "GDEM elevation = 0 in SRTM void (ocean-masking correction)", None, None),
    11: NumSource("srtm_interpolated", "NGA-interpolated SRTM", "spaceborne", SRTM_ROOT),
    21: NumSource("gmted2010", "GMTED2010 oversampled from 7.5 arc-second postings", "compiled", "usgs:gmted2010"),
    25: NumSource("srtm_interpolated", "SRTM within GDEM (SRTM 3 arc-second oversampled)", "spaceborne", SRTM_ROOT),
    31: NumSource("nga_undisclosed", "NGA fill of SRTM via GDEM (undisclosed sources)", "compiled", "nga:undisclosed"),
    51: NumSource("ned", "USGS NED", "compiled", "usgs:ned"),
    52: NumSource("ned", "USGS NED via GDEM", "compiled", "usgs:ned"),
    53: NumSource("ned", "Alaska USGS NED via GDEM", "compiled", "usgs:ned"),
    72: NumSource("cded", "Canadian Digital Elevation Data via GDEM", "compiled", "nrcan:cded"),
}


def classify(value: int) -> NumSource:
    if value in _EXACT:
        return _EXACT[value]
    if 101 <= value <= 200:
        return NumSource("aster_gdem2", "ASTER GDEM2 (value - 100 = scene count)", "spaceborne", "aster:terra:gdem2")
    if 201 <= value <= 224:
        return NumSource("srtm_measured", "SRTM (value - 200 = swath count)", "spaceborne", SRTM_ROOT)
    return UNMAPPED


CATEGORIES = (
    "srtm_measured",
    "srtm_interpolated",
    "aster_gdem2",
    "ned",
    "gmted2010",
    "cded",
    "nga_undisclosed",
    "water",
    "unmapped",
)
LAND_CATEGORIES = tuple(c for c in CATEGORIES if c not in ("water", "unmapped"))

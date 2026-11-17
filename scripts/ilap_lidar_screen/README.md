# ILAP lidar change screen (island-wide, 2018 vs 2024)

Compares the two USGS 3DEP 1 m lidar surveys of Puerto Rico and lists every large
earth fill, then removes the ones with an ordinary explanation. It is a screening
tool: it ranks places to look at. It does not assert that any site contains
underground or non-public activity.

The rules were fixed before the first island-wide run and are in
[`CRITERIA.md`](CRITERIA.md), together with the amendments made after results were
seen (flagged there as post hoc).

## Steps

All scripts take a scratch working directory as the first argument and keep their
state under `<workdir>/island/`. Copy `ref/` to `<workdir>/island/ref/` first.

| Step | Script | Output |
|---|---|---|
| 1 | `fetch_tiles.py` | `tiles.json`: the 1 m DEM tile list from the TNM Access API |
| 2 | `screen_tiles.py <workdir> all` | per-tile patch list and change raster (resumable; finished tiles are skipped) |
| 3 | `aggregate.py` | merged, deduplicated patches; fills and cuts of 20,000 m3 or more with tests 1-3 |
| 4 | `flatness.py` | water-surface test and pixel boxes for step 6 |
| 5 | `classify.py` | `large_fills_classified.json`, `residuals.json` |
| 6 | `review_sheets.py` | one panel per residual: change map, 2024 hillshade, USGS imagery |
| - | `spot_check.py <workdir> <lat> <lon>` | both surveys' elevations around one point |

Needs `rasterio`, `numpy`, `scipy`, `matplotlib`, `Pillow` and `curl`. Behind a TLS
proxy, set `CURL_CA_BUNDLE`. Step 2 reads the tiles remotely and took about four
hours on two cores.

## Reference layers (`ref/`)

Snapshots taken 2026-11-17, used by the 500 m attribution tests.

- `echo_ref.json`: 334 EPA ECHO facilities in Puerto Rico with coordinates, from name
  searches (landfill, vertedero, relleno, cantera, quarry, aggregate, agregados,
  arenero) and SIC 4953, 1422, 1442, 1429, 3241, 3273 and NAICS 562212, 2123.
- `mrds_ref.json`: 712 USGS MRDS mineral sites in Puerto Rico.

The commands that built these two files were run ad hoc and were not kept, so there
is no builder script here.

## Result of the 2026-11-17 run

191 tiles from the tile list as it stood that day (479 items; `fetch_tiles.py`
returned 481 when re-run later the same day). 320 fills of 20,000 m3 or more,
52.5 million m3 in total.

| Class | Count |
|---|---|
| Balanced by cuts within 1 km | 160 |
| Landfill or registered waste/aggregate site within 500 m | 60 |
| Quarry or mine within 500 m | 27 |
| Water-level difference (amendment A1) | 17 |
| Data artifact (amendment A2) | 1 |
| Steep ground, unexplained (low confidence) | 13 |
| Unexplained after automatic tests | 42 |

The 55 in the last two rows were reviewed by eye. Fourteen (about 1.07 million m3)
had no identified source: nine engineered pads, four mounds and one canal-side strip.
The visual classes are judgments, not records; test 4 (documented project) was not
applied from documents.

## Known limits

- Sees only surface change of more than 1 m on patches of 500 m2 or more, on land
  above 0.5 m, between the two surveys.
- Blind where the 2018 survey has voids (one confirmed near 18.26608, -65.75274);
  the total void area has not been measured.
- Tile zones 19 and 20 overlap in the east. Duplicates are removed by centroid and
  volume, so a patch split differently by two tiles can be counted twice.
- Cannot tell imported fill by origin, and cannot see spoil placed in a landfill or
  quarry, spread thinner than 1 m, or moved by sea.

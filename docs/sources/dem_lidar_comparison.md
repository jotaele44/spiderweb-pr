# DEMs compared against 3DEP lidar

Every gridded DEM in the platform catalog
([`dem_sources_by_platform.md`](dem_sources_by_platform.md)) was compared against
USGS 3DEP 1 m bare-earth lidar at eight sites chosen to span Puerto Rico's terrain:
karst, high cordillera, rainforest, dry coast, dense city, the west coast,
east-central mountains and the north-east lowlands. The 2018 lidar is the reference;
the D24 lidar (flown 2023-2025) is compared against it as well.

- Script: `scripts/run_dem_vs_3dep_lidar.py` (reproducible; re-running skips finished sites).
- Sites and tiles: `data_sources/elevation/lidar_comparison_tiles.json`.
- Receipt: `evidence/dem_sources/lidar_comparison_2026-11-24/`: `comparison.json`,
  `tiles_provenance.json` (each lidar tile's sha256) and `datum_chain.json` (PROJ
  operations, epochs and the offset at each site centre).
- Lidar streamed: 4.40 GB in 18 tiles, each downloaded to a temporary file, hashed,
  used and deleted. No raster is committed.

## Method

- **Same sample positions.** The lidar's 1 m pixels are averaged onto each DEM's own
  grid: 1 arc-second cells centred on whole arc-seconds for SRTMGL1, NASADEM and COP30;
  cells with edges on whole arc-seconds for AW3D30 (pixel-is-area); the CUDEM tile
  lattice; the NCEI grids. A cell counts only if at least 90% of its lidar pixels are valid.
- **Same vertical datum.** The lidar is moved to each DEM's datum. Its tile metadata
  says NAVD88, USGS's programme-wide wording; NAVD88 is not defined in Puerto Rico, and
  the heights are treated as PRVD02 (tested below). The chain is explicit:
  - `Inverse of NAD83(2011) to PRVD02 height (2) (with axis order normalized for visualization)`
  - `Conversion from NAD83(2011) (geog3D) to NAD83(2011) (geocentric) + Inverse of ITRF2014 to NAD83(2011) (1) + Conversion from ITRF2014 (geocentric) to ITRF2014 (geog3D) (with axis order normalized for visualization)` at epoch 2018.79 (2018) or 2024.6 (D24)
  - ITRF2014 taken as WGS 84, then `WGS 84 to EGM96 height (1) (with axis order normalized for visualization)` or `WGS 84 to EGM2008 height (1) (with axis order normalized for visualization)`.

  PROJ's default NAD83(2011) to WGS 84 step is a null transform (stated accuracy 2 m);
  using it would have shifted every offset by about 1.9 m.
- **Differences** are DEM minus lidar. NMAD is 1.4826 times the median absolute
  deviation, a spread measure that ignores outliers.

## Results over all eight sites

| DEM | Samples | Median | Mean | NMAD | Std | RMSE | 95th pct abs | Within 5 m (%) |
|---|---|---|---|---|---|---|---|---|
| `nasa_srtmgl1_v003` SRTMGL1 (Shuttle C-band radar, 2000) | 542,832 | 3.63 | 4.53 | 4.48 | 5.87 | 7.41 | 15.36 | 58.9 |
| `nasa_nasadem_hgt_v001` NASADEM (Shuttle radar, reprocessed) | 542,832 | 1.88 | 2.80 | 4.35 | 5.96 | 6.59 | 13.93 | 66.7 |
| `copernicus_glo30_dem` COP30 (TanDEM-X X-band radar, 2011-15) | 542,832 | 4.39 | 6.46 | 5.58 | 6.30 | 9.03 | 18.59 | 53.2 |
| `jaxa_aw3d30` AW3D30 (ALOS optical stereo, 2006-11) | 539,334 | 4.16 | 5.92 | 5.25 | 6.61 | 8.88 | 18.79 | 54.6 |
| `ncei_puerto_rico_cudem_ninth_9525` CUDEM 1/9" (compiled, PRVD02) | 44,172,974 | -0.02 | 0.08 | 0.26 | 2.89 | 2.89 | 1.37 | 99.1 |
| `ncei_san_juan_19_prvd02_2015` NCEI San Juan 2015 1/9" (compiled, PRVD02) | 2,804,456 | -0.30 | -1.13 | 0.21 | 2.52 | 2.76 | 7.72 | 93.1 |
| `ncei_arecibo_2007` NCEI Arecibo 2007 1/3" (compiled, MHW) | 539,174 | 0.15 | 0.30 | 3.70 | 9.84 | 9.85 | 19.70 | 70.6 |
| `ncei_fajardo_2007` NCEI Fajardo 2007 1/3" (compiled, MHW) | 462,886 | 0.22 | 0.72 | 2.85 | 4.82 | 4.87 | 9.50 | 80.9 |
| `ncei_mayaguez_2006` NCEI Mayaguez 2006 1/3" (compiled, MHW) | 608,226 | 0.65 | 0.80 | 0.38 | 1.30 | 1.53 | 2.99 | 98.5 |
| `ncei_mayaguez_2007` NCEI Mayaguez 2007 1/3" (compiled, MHW) | 608,226 | -0.59 | -0.38 | 0.91 | 2.74 | 2.76 | 5.86 | 93.6 |
| `ncei_ponce_2007` NCEI Ponce 2007 1/3" (compiled, MHW) | 385,354 | 0.37 | 0.64 | 1.16 | 1.75 | 1.86 | 4.04 | 97.6 |
| `lidar_d24_minus_2018_1arcsec` 3DEP D24 lidar (2023-25) at 1" | 537,099 | -0.14 | -0.16 | 0.17 | 0.53 | 0.55 | 0.58 | 100.0 |

Positive values mean the DEM stands above bare earth. SRTMGL1, NASADEM, COP30 and
AW3D30 are surface models (radar or optical), so they include canopy and buildings;
the lidar is bare ground.

- **NASADEM is the closest spaceborne surface** (median +1.88 m), about half SRTMGL1's
  +3.63 m from the same 2000 flight. Their spreads are alike (NMAD 4.35 and 4.48 m).
- **COP30 is closest on flat ground and farthest on steep slopes**: +1.31 m under
  5 degrees, +12.83 m over 30 degrees. Steep slopes here are mostly forested, and
  X-band radar (TanDEM-X) scatters nearer the canopy top than C-band (SRTM); this is
  an inference from the pattern (T4), not measured canopy height.
- **Every spaceborne difference grows with slope**, in median and in spread.
- **CUDEM 1/9" matches the lidar to centimetres** (median -0.02 m, NMAD 0.07 m on flat
  ground), which suggests it is built partly from this lidar (see the datum test).
- **NCEI San Juan 2015 sits 0.30 m below the lidar** although both are PRVD02.
- **The two NCEI Mayagüez DEMs disagree with each other by 1.24 m** (+0.65 and
  -0.59 m) although both state Mean High Water.

No overlapping land cells: `ncei_puerto_rico_cudem_third_9524`. CUDEM 1/3" tiles exist only around the island's margins and offshore, where the 1/9" product does not reach.

### By lidar slope (median / NMAD, metres)

| DEM | 0-5 deg | 5-15 deg | 15-30 deg | 30-90 deg |
|---|---|---|---|---|
| `nasa_srtmgl1_v003` | 2.46 / 2.59 | 3.69 / 4.50 | 5.22 / 6.11 | 7.26 / 7.83 |
| `nasa_nasadem_hgt_v001` | 1.00 / 2.33 | 1.86 / 4.51 | 3.38 / 6.25 | 4.97 / 7.99 |
| `copernicus_glo30_dem` | 1.31 / 1.59 | 3.91 / 4.25 | 9.15 / 6.92 | 12.83 / 6.48 |
| `jaxa_aw3d30` | 2.08 / 2.60 | 3.84 / 4.70 | 7.54 / 7.22 | 10.71 / 8.02 |
| `ncei_puerto_rico_cudem_ninth_9525` | -0.01 / 0.07 | -0.02 / 0.17 | -0.03 / 0.46 | -0.04 / 0.84 |
| `lidar_d24_minus_2018_1arcsec` | -0.07 / 0.12 | -0.13 / 0.15 | -0.21 / 0.17 | -0.23 / 0.19 |

### By site (median / NMAD, metres)

| Site | Cover | `nasa_srtmgl1_v003` | `nasa_nasadem_hgt_v001` | `copernicus_glo30_dem` | `jaxa_aw3d30` | `ncei_puerto_rico_cudem_ninth_9525` | D24 - 2018 |
|---|---|---|---|---|---|---|---|
| North karst belt (Hatillo / Camuy) (x72y205) | karst forest and pasture | 3.32 / 2.65 | 0.96 / 2.51 | 1.55 / 1.90 | 1.06 / 2.21 | 0.00 / 0.09 | -0.03 / 0.10 |
| Central cordillera (Cerro de Punta) (x75y202) | steep montane forest | 6.26 / 6.57 | 3.31 / 6.67 | 9.32 / 8.02 | 8.45 / 7.98 | -0.01 / 0.67 | -0.15 / 0.17 |
| El Yunque (Sierra de Luquillo) (x84y203) | tropical rainforest | 6.00 / 6.92 | 5.75 / 6.77 | 11.93 / 7.22 | 6.92 / 7.76 | -0.00 / 0.38 | -0.29 / 0.21 |
| Dry south coast (Guánica) (x72y199) | dry forest and scrub | 4.12 / 2.74 | 1.12 / 2.46 | 2.70 / 2.27 | 4.08 / 3.14 | -0.03 / 0.11 | -0.13 / 0.07 |
| Urban San Juan (x17y205) | dense urban | 1.19 / 2.37 | 1.74 / 2.27 | 1.30 / 1.48 | 1.67 / 2.62 | -0.06 / 0.09 | -0.07 / 0.07 |
| West coast (Mayagüez) (x69y202) | urban edge, foothills | 3.43 / 3.51 | 2.10 / 3.50 | 2.87 / 3.60 | 4.78 / 3.82 | -0.02 / 0.15 | -0.17 / 0.12 |
| East-central (Cayey) (x80y201) | mountain agriculture and forest | 1.92 / 5.58 | 0.60 / 5.75 | 6.94 / 6.88 | 4.93 / 6.70 | -0.05 / 0.58 | -0.22 / 0.19 |
| North-east (Carolina), registered D24 tile (x81y203) | suburban and lowland | 3.16 / 3.90 | 1.78 / 4.23 | 4.00 / 5.23 | 3.20 / 4.28 | 0.00 / 0.21 | -0.09 / 0.18 |

## D24 lidar against the 2018 lidar

Both surveys are 1 m bare earth on the same datum, so no conversion is applied. At
1/9 arc-second (the CUDEM lattice, about 3.4 m), D24 minus 2018, in metres:

| Site | Cells | Median | NMAD | Median, slope under 5 deg | Median, slope over 30 deg | Beyond 1 m (%) |
|---|---|---|---|---|---|---|
| North karst belt (Hatillo / Camuy) | 4,757,268 | -0.02 | 0.10 | -0.01 | -0.14 | 1.6 |
| Central cordillera (Cerro de Punta) | 8,536,450 | -0.14 | 0.22 | -0.05 | -0.17 | 3.0 |
| El Yunque (Sierra de Luquillo) | 4,178,096 | -0.26 | 0.30 | -0.04 | -0.36 | 7.1 |
| Dry south coast (Guánica) | 3,400,498 | -0.13 | 0.08 | -0.11 | -0.17 | 0.4 |
| Urban San Juan | 2,567,172 | -0.07 | 0.07 | -0.07 | -0.09 | 1.3 |
| West coast (Mayagüez) | 5,425,350 | -0.15 | 0.14 | -0.12 | -0.30 | 2.4 |
| East-central (Cayey) | 6,388,086 | -0.19 | 0.22 | -0.07 | -0.28 | 5.0 |
| North-east (Carolina), registered D24 tile | 8,458,491 | -0.07 | 0.19 | 0.01 | -0.17 | 2.0 |

D24 reads lower than 2018 at every site: the median over all eight sites is -0.14 m
at 1 arc-second. The difference is smallest on flat ground (-0.07 m under 5 degrees)
and grows with slope (-0.23 m over 30 degrees). It is largest in the forested
interior (El Yunque, Cayey) and smallest in the karst (Hatillo).

A horizontal shift between the surveys would raise some slopes and lower others,
depending on which way they face, so it cannot give one sign on every slope. Two
explanations fit, and this comparison does not separate them (T4):

- a vertical offset between the two surveys' realizations of PRVD02, which would show
  on flat ground; the tiles' metadata does not name the geoid model used to process
  either survey;
- better ground detection under vegetation in D24, or debris and low regrowth that
  stayed in the 2018 ground class after Hurricane Maria; this would grow with slope
  and canopy.

## NCEI regional DEMs at the sites they cover

| Site | DEM | Vertical datum | Samples | Median | NMAD |
|---|---|---|---|---|---|
| North karst belt (Hatillo / Camuy) | `ncei_arecibo_2007` | Mean High Water | 539,174 | 0.15 | 3.70 |
| El Yunque (Sierra de Luquillo) | `ncei_fajardo_2007` | Mean High Water | 462,886 | 0.22 | 2.85 |
| Dry south coast (Guánica) | `ncei_ponce_2007` | Mean High Water | 385,354 | 0.37 | 1.16 |
| Urban San Juan | `ncei_san_juan_19_prvd02_2015` | Puerto Rico Vertical Datum of 2002 | 2,804,456 | -0.30 | 0.21 |
| West coast (Mayagüez) | `ncei_mayaguez_2006` | Mean High Water | 608,226 | 0.65 | 0.38 |
| West coast (Mayagüez) | `ncei_mayaguez_2007` | Mean High Water | 608,226 | -0.59 | 0.91 |

The 2006-2007 regional DEMs are on Mean High Water. No MHW to PRVD02 conversion is
registered, so their medians include the MHW offset as well as any bias.

## Is the lidar PRVD02 or NAVD88?

2018 lidar minus CUDEM 1/9" over low-slope cells (under 5 degrees). CUDEM is PRVD02
(NOAA metadata; its 1/3" tiles declare `NAD83 + PRVD02 height` in the file itself).

| Site | Samples | Median (m) | NMAD (m) |
|---|---|---|---|
| North karst belt (Hatillo / Camuy) | 2,654,677 | -0.004 | 0.058 |
| Central cordillera (Cerro de Punta) | 457,120 | 0.002 | 0.151 |
| El Yunque (Sierra de Luquillo) | 238,258 | -0.002 | 0.068 |
| Dry south coast (Guánica) | 1,374,335 | 0.024 | 0.056 |
| Urban San Juan | 2,462,323 | 0.062 | 0.079 |
| West coast (Mayagüez) | 2,649,247 | 0.021 | 0.071 |
| East-central (Cayey) | 685,421 | -0.015 | 0.149 |
| North-east (Carolina), registered D24 tile | 2,347,000 | -0.004 | 0.059 |

All eight medians are within 0.062 m of zero, so the heights behave as PRVD02. The
catalog keeps the stated NAVD88 and records the disagreement as registry conflict
`3dep_vertical_datum_label`.

This test is not independent. CUDEM's metadata names no source surveys (its lineage
points only to NCEI's DEM development reports), and its centimetre agreement suggests
it includes the 2018 lidar. If it does, the result shows that NOAA treats these
heights as PRVD02; it does not tie them to PRVD02 benchmarks. That tie (NGS published
PRVD02 heights against the lidar) was not made.

## Cerro de Punta summit

At the summit cell (18.172222, -66.591667) the 2018 lidar, averaged over the cell,
reads 1,330.55 m PRVD02: 1,331.77 m on EGM96 (offset +1.214 m) and 1,331.01 m on
EGM2008 (offset +0.456 m). At the same cell the DEMs read lower:

| DEM | Height | Lidar on its datum | DEM minus lidar |
|---|---|---|---|
| SRTMGL1 (EGM96) | 1,325.0 m | 1,331.77 m | -6.8 m |
| NASADEM (EGM96) | 1,323.0 m | 1,331.77 m | -8.8 m |
| COP30 (EGM2008) | 1,328.29 m | 1,331.01 m | -2.7 m |

The sign is the opposite of the island-wide bias (DEMs above bare earth), and the
datum offset is only about 1 m, so this is not a datum error. 30 m radar DEMs flatten
narrow peaks; the summit is the cell where that shows most.

## Caveats

- Surface models against bare earth: the DEM minus lidar difference is mostly canopy
  and buildings, not error in the ground.
- Epochs differ: 2000 (SRTM), 2006-2011 (AW3D30), 2011-2015 (COP30), 2018-2019 (lidar),
  2023-2025 (D24). The 2018 lidar was flown after Hurricane Maria stripped much of the
  canopy. That changes a bare-earth surface only through ground classification (see
  the D24 section), but the older surface models saw the canopy before the storm.
- Horizontal: the lidar is NAD83(2011) and the global DEMs WGS 84 / ITRF; the 1-2 m
  difference is under a tenth of a 30 m cell and is not corrected.
- Eight 10 km tiles (about 800 km2, less where a tile reaches the sea) sample about
  8,900 km2 of land. They were chosen for terrain variety, not at random, so the
  island-wide numbers weight each terrain by its tile, not by its area.
- The datum test is not independent of CUDEM's own inputs (see above).

## Open leads

- Which geoid model each survey's processing used (project-level metadata under
  `StagedProducts/Elevation/metadata/` on prd-tnm), to test the vertical explanation
  for D24 minus 2018.
- NGS PRVD02 benchmarks against the 2018 lidar: an independent datum tie.
- The 1.24 m disagreement between the two NCEI Mayagüez DEMs, both stated as MHW.
- The -0.30 m offset of NCEI San Juan 2015 against the lidar, both PRVD02.
- Coastal topobathy lidar DEMs (6211, 5154, 8571) have no fetcher, so they were not
  compared.

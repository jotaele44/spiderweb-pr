# DEMs compared against 3DEP lidar

Every gridded DEM in the platform catalog
([`dem_sources_by_platform.md`](dem_sources_by_platform.md)) was compared against
USGS 3DEP 1 m bare-earth lidar at eight sites chosen to span Puerto Rico's terrain:
karst, high cordillera, rainforest, dry coast, dense city, the west coast,
east-central mountains and the north-east lowlands. The 2018 lidar is the reference;
the D24 lidar (flown 2023-2025) is compared against it as well.

- Script: `scripts/run_dem_vs_3dep_lidar.py` (reproducible; `--force` re-runs finished sites).
- Sites and tiles: `data_sources/elevation/lidar_comparison_tiles.json`, including each
  part's stated geoid from `scripts/check_3dep_vertical_realization.py`.
- Receipts:
  - `evidence/dem_sources/lidar_comparison_2026-11-26/`: `comparison.json`,
    `tiles_provenance.json` (each lidar tile's sha256) and `datum_chain.json` (PROJ
    operations per survey, epochs, offsets at each site centre).
  - `evidence/dem_sources/3dep_vertical_realization_2026-11-26/`: `geoid_statements.json`
    (each survey's datum and geoid in its own metadata) and `checkpoints.json` (both
    surveys at USGS's D24 checkpoints).
- Lidar streamed: 4.40 GB in 18 tiles, each downloaded to a temporary file, hashed,
  used and deleted. No raster is committed.
- Run on 2026-11-26. It replaces the 2026-11-24 run, which moved the 2018 lidar off
  PRVD02 with GEOID18 instead of the GEOID12B the survey used.

## Method

- **Same sample positions.** The lidar's 1 m pixels are averaged onto each DEM's own
  grid: 1 arc-second cells centred on whole arc-seconds for SRTMGL1, NASADEM and COP30;
  cells with edges on whole arc-seconds for AW3D30 (pixel-is-area); the CUDEM tile
  lattice; the NCEI grids. A cell counts only if at least 90% of its lidar pixels are valid.
- **Same vertical datum.** Both surveys are on PRVD02, each reached through its own
  geoid model (see [Geoid realizations](#geoid-realizations-of-the-two-surveys)). The lidar
  is moved to each DEM's datum with an explicit chain:
  - PRVD02 to NAD83(2011) ellipsoidal height through the survey's geoid:
    2018 `Inverse of NAD83(2011) to PRVD02 height (1) (with axis order normalized for visualization)` (GEOID12B, EPSG:7646; EPSG has
    superseded it, so it is requested explicitly), D24 `Inverse of NAD83(2011) to PRVD02 height (2) (with axis order normalized for visualization)` (GEOID18, EPSG:9230);
  - `Conversion from NAD83(2011) (geog3D) to NAD83(2011) (geocentric) + Inverse of ITRF2014 to NAD83(2011) (1) + Conversion from ITRF2014 (geocentric) to ITRF2014 (geog3D) (with axis order normalized for visualization)` at epoch 2018.79 (2018) or 2024.6 (D24);
  - ITRF2014 taken as WGS 84, then `WGS 84 to EGM96 height (1) (with axis order normalized for visualization)` or `WGS 84 to EGM2008 height (1) (with axis order normalized for visualization)`.

  PROJ's default NAD83(2011) to WGS 84 step is a null transform (stated accuracy 2 m);
  using it would have shifted every offset by about 1.9 m.
- **Differences** are DEM minus lidar. NMAD is 1.4826 times the median absolute
  deviation, a spread measure that ignores outliers.

## Results over all eight sites

| DEM | Samples | Median | Mean | NMAD | Std | RMSE | 95th pct abs | Within 5 m (%) |
|---|---|---|---|---|---|---|---|---|
| `nasa_srtmgl1_v003` SRTMGL1 (Shuttle C-band radar, 2000) | 542,832 | 3.61 | 4.51 | 4.48 | 5.87 | 7.40 | 15.33 | 59.0 |
| `nasa_nasadem_hgt_v001` NASADEM (Shuttle radar, reprocessed) | 542,832 | 1.86 | 2.78 | 4.36 | 5.96 | 6.58 | 13.91 | 66.8 |
| `copernicus_glo30_dem` COP30 (TanDEM-X X-band radar, 2011-15) | 542,832 | 4.38 | 6.44 | 5.57 | 6.30 | 9.01 | 18.56 | 53.3 |
| `jaxa_aw3d30` AW3D30 (ALOS optical stereo, 2006-11) | 539,334 | 4.14 | 5.90 | 5.26 | 6.61 | 8.86 | 18.77 | 54.7 |
| `ncei_puerto_rico_cudem_ninth_9525` CUDEM 1/9" (compiled, PRVD02) | 44,172,974 | -0.02 | 0.08 | 0.26 | 2.89 | 2.89 | 1.37 | 99.1 |
| `ncei_san_juan_19_prvd02_2015` NCEI San Juan 2015 1/9" (compiled, PRVD02) | 2,804,456 | -0.30 | -1.13 | 0.21 | 2.52 | 2.76 | 7.72 | 93.1 |
| `ncei_arecibo_2007` NCEI Arecibo 2007 1/3" (compiled, MHW) | 539,174 | 0.15 | 0.30 | 3.70 | 9.84 | 9.85 | 19.70 | 70.6 |
| `ncei_fajardo_2007` NCEI Fajardo 2007 1/3" (compiled, MHW) | 462,886 | 0.22 | 0.72 | 2.85 | 4.82 | 4.87 | 9.50 | 80.9 |
| `ncei_mayaguez_2006` NCEI Mayaguez 2006 1/3" (compiled, MHW) | 608,226 | 0.65 | 0.80 | 0.38 | 1.30 | 1.53 | 2.99 | 98.5 |
| `ncei_mayaguez_2007` NCEI Mayaguez 2007 1/3" (compiled, MHW) | 608,226 | -0.59 | -0.38 | 0.91 | 2.74 | 2.76 | 5.86 | 93.6 |
| `ncei_ponce_2007` NCEI Ponce 2007 1/3" (compiled, MHW) | 385,354 | 0.37 | 0.64 | 1.16 | 1.75 | 1.86 | 4.04 | 97.6 |
| `lidar_d24_minus_2018_1arcsec` 3DEP D24 minus 2018 at 1", as published (both PRVD02) | 537,099 | -0.14 | -0.16 | 0.17 | 0.53 | 0.55 | 0.58 | 100.0 |
| `lidar_d24_minus_2018_same_geoid_1arcsec` 3DEP D24 minus 2018 at 1", on one geoid | 537,099 | -0.15 | -0.18 | 0.16 | 0.53 | 0.56 | 0.60 | 100.0 |

Positive values mean the DEM stands above bare earth. SRTMGL1, NASADEM, COP30 and
AW3D30 are surface models (radar or optical), so they include canopy and buildings;
the lidar is bare ground.

- **NASADEM is the closest spaceborne surface** (median +1.86 m), about half SRTMGL1's
  +3.61 m from the same 2000 flight. Their spreads are alike (NMAD 4.36 and 4.48 m).
- **COP30 is closest on flat ground and farthest on steep slopes**: +1.29 m under
  5 degrees, +12.80 m over 30 degrees. Steep slopes here are mostly forested, and
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
| `nasa_srtmgl1_v003` | 2.45 / 2.60 | 3.67 / 4.50 | 5.20 / 6.12 | 7.24 / 7.83 |
| `nasa_nasadem_hgt_v001` | 0.99 / 2.33 | 1.84 / 4.51 | 3.36 / 6.25 | 4.95 / 7.99 |
| `copernicus_glo30_dem` | 1.29 / 1.60 | 3.90 / 4.25 | 9.13 / 6.92 | 12.80 / 6.48 |
| `jaxa_aw3d30` | 2.06 / 2.61 | 3.83 / 4.71 | 7.51 / 7.22 | 10.69 / 8.03 |
| `ncei_puerto_rico_cudem_ninth_9525` | -0.01 / 0.07 | -0.02 / 0.17 | -0.03 / 0.46 | -0.04 / 0.84 |
| `lidar_d24_minus_2018_1arcsec` | -0.07 / 0.12 | -0.13 / 0.15 | -0.21 / 0.17 | -0.23 / 0.19 |
| `lidar_d24_minus_2018_same_geoid_1arcsec` | -0.08 / 0.10 | -0.15 / 0.14 | -0.23 / 0.17 | -0.26 / 0.19 |

### By site (median / NMAD, metres)

| Site | Cover | `nasa_srtmgl1_v003` | `nasa_nasadem_hgt_v001` | `copernicus_glo30_dem` | `jaxa_aw3d30` | `ncei_puerto_rico_cudem_ninth_9525` |
|---|---|---|---|---|---|---|
| North karst belt (Hatillo / Camuy) (x72y205) | karst forest and pasture | 3.32 / 2.65 | 0.95 / 2.51 | 1.54 / 1.90 | 1.05 / 2.21 | 0.00 / 0.09 |
| Central cordillera (Cerro de Punta) (x75y202) | steep montane forest | 6.24 / 6.57 | 3.28 / 6.67 | 9.30 / 8.02 | 8.42 / 7.99 | -0.01 / 0.67 |
| El Yunque (Sierra de Luquillo) (x84y203) | tropical rainforest | 5.97 / 6.94 | 5.71 / 6.77 | 11.90 / 7.23 | 6.89 / 7.77 | -0.00 / 0.38 |
| Dry south coast (Guánica) (x72y199) | dry forest and scrub | 4.12 / 2.75 | 1.12 / 2.46 | 2.70 / 2.28 | 4.08 / 3.14 | -0.03 / 0.11 |
| Urban San Juan (x17y205) | dense urban | 1.19 / 2.37 | 1.74 / 2.27 | 1.30 / 1.48 | 1.68 / 2.62 | -0.06 / 0.09 |
| West coast (Mayagüez) (x69y202) | urban edge, foothills | 3.44 / 3.51 | 2.11 / 3.50 | 2.88 / 3.61 | 4.80 / 3.82 | -0.02 / 0.15 |
| East-central (Cayey) (x80y201) | mountain agriculture and forest | 1.90 / 5.58 | 0.58 / 5.76 | 6.93 / 6.88 | 4.92 / 6.71 | -0.05 / 0.58 |
| North-east (Carolina), registered D24 tile (x81y203) | suburban and lowland | 3.10 / 3.90 | 1.72 / 4.24 | 3.94 / 5.24 | 3.14 / 4.29 | 0.00 / 0.21 |

## Geoid realizations of the two surveys

PRVD02 is a leveled datum. A lidar survey reaches it from GNSS ellipsoidal heights
through a hybrid geoid model, and the two surveys used different ones. Each survey's
own project-level metadata on USGS's prd-tnm bucket says so (T1, read 2026-11-26):

| Survey | Record | Datum statement | Geoid element | Geoid |
|---|---|---|---|---|
| 2018 | `PR_PRVI_A_2018` | vertical datum of PRVD02 (GEOID12B); altdatum "Puerto Rico Vertical Datum of 2002, Geoid 12B" | ldrgeoid "National Geodetic Survey (NGS) Geoid12B" | GEOID12B |
| 2018 | `PR_PRVI_D_2018` | vertical datum of PRVD02 (GEOID12B); altdatum "Puerto Rico Vertical Datum of 2002, Geoid 12B" | ldrgeoid "National Geodetic Survey (NGS) Geoid12B" | GEOID12B |
| 2018 | `PR_PRVI_E_2018` | vertical datum of PRVD02 (GEOID12B); altdatum "Puerto Rico Vertical Datum of 2002, Geoid 12B" | ldrgeoid "National Geodetic Survey (NGS) Geoid12B" | GEOID12B |
| 2018 | `PR_PRVI_F_2018` | vertical datum of PRVD02 (GEOID12B); altdatum "Puerto Rico Vertical Datum of 2002, Geoid 12B" | ldrgeoid "National Geodetic Survey (NGS) Geoid12B" | GEOID12B |
| 2018 | `PR_PRVI_H_2018` | vertical datum of PRVD02 (GEOID12B); altdatum "Puerto Rico Vertical Datum of 2002, Geoid 12B" | ldrgeoid "National Geodetic Survey (NGS) Geoid12B" | GEOID12B |
| D24 | `PR_PuertoRicoUSVI_1_D24` | VERT_CS "PRVD02 height - Geoid18 (Meters)" | | GEOID18 |
| D24 | `PR_PuertoRicoUSVI_2_D24` | VERT_CS "PRVD02 height - Geoid18 (Meters)" | | GEOID18 |
| D24 | `PR_PuertoRicoUSVI_3_D24` | VERT_CS "PRVD02 height - Geoid18 (Meters)" | | GEOID18 |
| D24 | `PR_PuertoRicoUSVI_4_D24` | VERT_CS "PRVD02 height - Geoid18 (Meters)" | | GEOID18 |
| D24 | `PR_PuertoRicoUSVI_5_D24` | VERT_CS "VIVD09 height - Geoid18 (Meters)" | | GEOID18 |
| D24 | `PR_PuertoRicoUSVI_6_D24` | VERT_CS "PRVD02 height - Geoid18 (Meters)" | | GEOID18 |

The D24 report of survey says the same: "The vertical datum was the Puerto Rico
Vertical Datum of 2002 (PRVD02), realized with the GEOID18 geoid model from the National
Geodetic Survey (NGS)." Part 5 covers the Virgin Islands (VIVD09); none of the eight
sites is there.

The NAVD88 wording comes from two places: USGS's ScienceBase abstract for every
tile ("referenced to the North American Vertical Datum of 1988"), and the 2018 ground
control report ("Final Vertical elevations are referenced to NAVD88 in meters using
Geoid model 2012B"). NAVD88 is not realized in Puerto Rico. The catalog records PRVD02
with the geoid, keeps the NAVD88 wording as stated, and holds the disagreement open
as registry conflict `3dep_vertical_datum_label`.

**Control.** Both surveys tie to published PRVD02 benchmarks at the centimetre level.
D24 held every CORS at its published NAD83(2011) epoch 2010.0 coordinates and closes
at NGS station COCO to -0.016 m in orthometric height. The 2018 VRS survey checked
23 NGS monuments, most within ±0.03 m. Control does not explain a uniform offset
between the surveys.

## D24 lidar against the 2018 lidar

D24 minus 2018 is reported two ways. **As published**, both surveys are PRVD02 heights
and are differenced directly. **On one geoid**, each survey is first returned to
NAD83(2011) ellipsoidal heights through its own geoid, so the difference is the change
of the surveyed surface. The two differ by GEOID18 - GEOID12B at each cell.

At 1/9 arc-second (the CUDEM lattice, about 3.4 m), in metres:

| Site | GEOID12B - GEOID18 (mean, range) | As published | As published, slope under 5 deg | One geoid | One geoid, under 5 deg | One geoid, over 30 deg | Beyond 1 m, one geoid (%) |
|---|---|---|---|---|---|---|---|
| North karst belt (Hatillo / Camuy) | +0.013 (-0.009 to +0.039) | -0.02 | -0.006 | -0.02 | -0.009 | -0.14 | 1.6 |
| Central cordillera (Cerro de Punta) | +0.025 (+0.001 to +0.042) | -0.14 | -0.052 | -0.16 | -0.082 | -0.20 | 3.0 |
| El Yunque (Sierra de Luquillo) | +0.043 (-0.037 to +0.092) | -0.26 | -0.039 | -0.28 | -0.077 | -0.39 | 7.7 |
| Dry south coast (Guánica) | +0.009 (-0.009 to +0.042) | -0.13 | -0.106 | -0.13 | -0.107 | -0.17 | 0.4 |
| Urban San Juan | -0.002 (-0.013 to +0.009) | -0.07 | -0.067 | -0.07 | -0.064 | -0.09 | 1.3 |
| West coast (Mayagüez) | -0.012 (-0.035 to +0.019) | -0.15 | -0.121 | -0.14 | -0.108 | -0.29 | 2.4 |
| East-central (Cayey) | +0.018 (-0.016 to +0.063) | -0.19 | -0.067 | -0.20 | -0.088 | -0.29 | 5.1 |
| North-east (Carolina), registered D24 tile | +0.059 (+0.002 to +0.100) | -0.07 | +0.009 | -0.12 | -0.065 | -0.23 | 2.1 |

Over all eight sites at 1 arc-second, D24 minus 2018 is -0.14 m as published and
-0.15 m on one geoid (median; NMAD 0.17 and 0.16 m).

- **The geoid change explains the pattern between sites.** For an unchanged surface the
  published difference would equal GEOID12B - GEOID18. Across the eight sites the
  flat-ground medians track it (r = 0.76). On one geoid their spread between sites
  falls from 0.045 to 0.031 m.
- **It does not explain the level.** On one geoid, D24 still reads 0.075 m below
  2018 on flat ground (mean of the site medians), and more on steep slopes.
- **Checkpoint test.** USGS's 91 D24 non-vegetated (NVA) checkpoints were surveyed
  in 2024 on PRVD02 through GEOID18. Sampling both DEMs at them (2018 moved to a
  GEOID18 basis):
  - D24 minus checkpoint: median -0.006 m, RMSE 0.049 m;
  - 2018 minus checkpoint: median +0.029 m (+0.008 m as published);
  - D24 minus 2018 at the checkpoints: median -0.034 m.

  So about 3 cm of the offset is a 2018 bias in open terrain. The
  checkpoints are D24's own QA points, so they test 2018 independently but D24 only
  against its own control. The 2018 spread there (std 0.36 m) includes ground that
  changed between 2018 and 2024.
- **The rest grows with slope and canopy.** It is largest in the forested interior and
  smallest in the karst. A horizontal shift would raise some slopes and lower others by
  aspect, so it cannot give one sign on every slope. Better ground detection under
  vegetation in D24, or debris and low regrowth that stayed in the 2018 ground class
  after Hurricane Maria, fits (T4); this comparison does not separate them.

Confidence:

| Finding | Basis | Confidence |
|---|---|---|
| 2018 used GEOID12B and D24 used GEOID18 | Both surveys' own metadata, every sub-project (T1) | High |
| The geoid change sets the site-to-site pattern of D24 - 2018 | r = 0.76 over 8 sites; spread 0.045 to 0.031 m | Moderate (8 sites) |
| About 3 cm of the level is a 2018 bias in open terrain | 91 D24 checkpoints (T1 survey heights) | Moderate (checkpoints are D24's own) |
| The slope-dependent rest is ground classification | Pattern only (T4) | Low |

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

The surveys' metadata settles it (PRVD02, see above). The heights also behave that
way: 2018 lidar minus CUDEM 1/9" over low-slope cells (under 5 degrees), with CUDEM on
PRVD02 (NOAA metadata; its 1/3" tiles declare `NAD83 + PRVD02 height` in the file itself).

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

All eight medians are within 0.062 m of zero.

This test is not independent. CUDEM's metadata names no source surveys (its lineage
points only to NCEI's DEM development reports), and its centimetre agreement suggests
it includes the 2018 lidar. If it does, the result shows that NOAA treats these
heights as PRVD02. The D24 checkpoints above are the independent tie for 2018.

## Cerro de Punta summit

At the summit cell (18.172222, -66.591667) the 2018 lidar, averaged over the cell,
reads 1,330.55 m PRVD02: 1,331.78 m on EGM96 (offset +1.231 m) and
1,331.02 m on EGM2008 (offset +0.473 m). At the same cell the DEMs read lower:

| DEM | Height | Lidar on its datum | DEM minus lidar |
|---|---|---|---|
| SRTMGL1 (EGM96) | 1,325.0 m | 1,331.78 m | -6.8 m |
| NASADEM (EGM96) | 1,323.0 m | 1,331.78 m | -8.8 m |
| COP30 (EGM2008) | 1,328.29 m | 1,331.02 m | -2.7 m |

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
- The CUDEM datum test is not independent of CUDEM's own inputs, and the D24
  checkpoints test D24 only against its own QA survey.

## Open leads

- NGS PRVD02 benchmarks against both lidar surveys: a tie independent of either survey.
- The 2016 Commonwealth lidar (`pr_commonwealth_lidar_2016`) is still recorded as NAVD88
  from the elevation inventory; its own metadata and geoid were not read. The 2018
  project folder holds a "PuertoRico_LiDAR_Differences_2016and2018" report.
- The 1.24 m disagreement between the two NCEI Mayagüez DEMs, both stated as MHW.
- The -0.30 m offset of NCEI San Juan 2015 against the lidar, both PRVD02.
- Coastal topobathy lidar DEMs (6211, 5154, 8571) have no fetcher, so they were not
  compared.

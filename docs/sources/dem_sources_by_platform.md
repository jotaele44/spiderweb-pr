# DEM sources by acquisition platform

Spiderweb registers elevation and bathymetry sources in many places. This page
breaks them down by the **platform that measured the heights**: from orbit, from
aircraft, from ships, or compiled from several of these. The platform decides what
surface a height describes, when it was measured, which vertical datum it uses, and
whether two sources can corroborate each other.

The catalog is `data_sources/elevation/dem_platform_catalog.yml`, checked against
`schemas/dem_platform_catalog.schema.json`. The code is `source_adapters/dem_platform/`.

```bash
python -m source_adapters.dem_platform.cli summary
python -m source_adapters.dem_platform.cli check --sources nasa_srtmgl1_v003,usgs_3dep_1m_pr_prvi_f_2018
```

## Why platform matters

| Platform | Surface it measures | Typical datum here | Example |
|---|---|---|---|
| Spaceborne radar interferometry | A radar scattering surface between canopy top and ground | EGM96 | SRTM (February 2000) |
| Spaceborne optical stereo | The first visible surface: canopy and roofs | not stated | AW3D30 (2006-2011) |
| Airborne lidar | Bare earth (classified DEM) or every return (point cloud) | NAVD88 | 3DEP 1 m (2018, 2024) |
| Shipborne multibeam sonar | Seafloor depth | MLLW | NOS BAG W00247 |
| Compiled | Whatever the constituents measured | PRVD02, MHW, MSL | NCEI CUDEM, GEBCO |

A 30 m radar surface from 2000 and a 1 m bare-earth lidar surface from 2018 differ
in surface, epoch and datum. Subtracting one from the other measures those
differences as much as any change on the ground.

## Every registration is accounted for

`registration_universe()` reads each file listed in `EXTRACTORS` in
`source_adapters/dem_platform/catalog.py`. Every registration it finds is either an
alias of one product or a classified non-product. `tests/test_dem_platform_catalog.py`
fails when a registration is unaccounted for or a catalog reference goes stale.

| Measure | Count |
|---|---|
| Registrations | 65 in 21 files |
| Aliases of products | 46 |
| Distinct products | 30 |
| Non-product registrations | 19 |
| Accounted for | 100.0% |

Several registrations name the same product. CUDEM 1/3 arc-second (m9524), for
example, appears in the NCEI YAML, the NCEI priority CSV and the marine dataset
registry; 3DEP 1 m PR_PRVI_F_2018 appears in five places. Each is one entry here.

The off-shore access-point registry (`registry/access_points/offshore.json`, 185
hydrographic records) already records the acquisition method per record in
`sensor_type` (183 of 185 set), so it is counted as one survey registry, not copied.
The land side has no such field filled: all ten inland records have
`sensor_type: null`, and `SensorType` (`gebco/marine_evidence.py`) has no member for
topographic lidar, radar interferometry or optical stereo. The catalog's
`sensor_type` uses that enum where a member fits and is null otherwise.

## Products by platform class

The basis column is the evidence tier for the platform: T1 is the provider's own
metadata, T2 is provider documentation or naming. A platform goes in only from such
a source; otherwise the entry would be `unverified`, which fails closed.

### Spaceborne (orbit or crewed spacecraft): 4

| Source | Name | Platform | Instrument (technique) | Surface | Vertical datum | Basis |
|---|---|---|---|---|---|---|
| `copernicus_glo30_dem` | Copernicus GLO-30 Digital Elevation Model | TanDEM-X | X-band SAR (Radar Interferometry) | radar scattering surface | undeclared | T1 |
| `jaxa_aw3d30` | ALOS World 3D 30 m (AW3D30) | ALOS | PRISM (Optical Stereo Photogrammetry) | first surface | undeclared | T1 |
| `nasa_nasadem_hgt_v001` | NASADEM Merged DEM Global 1 arc-second v001 | OV-105 | SRTM (Radar Interferometry) | radar scattering surface | EGM96 | T1 |
| `nasa_srtmgl1_v003` | NASA SRTM Global 1 arc-second v003 (SRTMGL1) | STS-99 | SRTM (Radar Interferometry) | radar scattering surface | EGM96 | T1 |

### Airborne (aircraft lidar): 9

| Source | Name | Platform | Instrument (technique) | Surface | Vertical datum | Basis |
|---|---|---|---|---|---|---|
| `noaa_ngs_topobathy_dem_2015_6211` | 2015 NOAA NGS Topobathy Lidar DEM: Puerto Rico | not named | LIDAR (Topobathymetric Lidar) | topobathymetric | undeclared | T2 |
| `noaa_ngs_topobathy_lidar_2019_9390` | 2019 NOAA NGS Topobathy Lidar: Puerto Rico | not named | LIDAR (Topobathymetric Lidar) | point cloud | undeclared | T2 |
| `pr_commonwealth_lidar_2016` | 2016 Commonwealth of Puerto Rico Project Lidar | not named | LIDAR (Lidar-Topo) | point cloud | NAVD88 | T2 |
| `usace_fema_topobathy_dem_2018_8571` | 2018 USACE FEMA Topobathy Lidar DEM: Puerto Rico | not named | LIDAR (Topobathymetric Lidar) | topobathymetric | undeclared | T2 |
| `usace_lidar_2004_pr` | 2004 USACE Lidar: Puerto Rico | not named | LIDAR (Lidar-Topo) | point cloud | undeclared | T2 |
| `usace_ncmp_topobathy_dem_2016_5154` | 2016 USACE NCMP Topobathy Lidar DEM: Puerto Rico | not named | LIDAR (Topobathymetric Lidar) | topobathymetric | PRVD02 | T2 |
| `usgs_3dep_1m_pr_prvi_f_2018` | USGS 3DEP 1 m DEM, PR_PRVI_F_2018 | not named | LIDAR (Lidar-Topo) | bare earth | NAVD88 | T1 |
| `usgs_3dep_1m_pr_puertoricousvi_d24` | USGS 3DEP 1 m DEM, PR_PuertoRicoUSVI_D24 | not named | LIDAR (Lidar-Topo) | bare earth | NAVD88 | T1 |
| `usgs_lidar_2018_hurricane_maria` | 2018 Hurricane Maria PR and USVI Lidar | not named | LIDAR (Lidar-Topo) | point cloud | NAVD88 | T2 |

### Shipborne (multibeam sonar): 4

| Source | Name | Platform | Instrument (technique) | Surface | Vertical datum | Basis |
|---|---|---|---|---|---|---|
| `nos_bag_h12935` | NOS hydrographic survey H12935 BAG | NOAA Ship NANCY FOSTER (R352) | MBES (Multibeam Echosounder) | bathymetric | MLLW | T1 |
| `nos_bag_w00247` | NOS hydrographic survey W00247 BAG (3 of 4) | NOAA Ship NANCY FOSTER (R352) | MBES (Multibeam Echosounder) | bathymetric | MLLW | T1 |
| `okeanos_ex1502l3_multibeam` | Okeanos Explorer EX1502L3 multibeam grid (50 m) | NOAA Ship OKEANOS EXPLORER (R337) | Kongsberg EM302 (Multibeam Echosounder) | bathymetric | undeclared | T1 |
| `okeanos_ex1811_multibeam` | Okeanos Explorer EX1811 multibeam XYZ (100 m) | NOAA Ship OKEANOS EXPLORER (R337) | MBES (Multibeam Echosounder) | bathymetric | undeclared | T2 |

### Compiled (assembled from several sources): 13

| Source | Name | Platform | Instrument (technique) | Surface | Vertical datum | Basis |
|---|---|---|---|---|---|---|
| `gebco_2023` | GEBCO_2023 Grid | not named | — | mixed | MSL (assumed) | T1 |
| `ncei_arecibo_2007` | NCEI Arecibo 1/3 arc-second DEM (2007) | not named | — | topobathymetric | MHW | T2 |
| `ncei_fajardo_2007` | NCEI Fajardo 1/3 arc-second DEM (2007) | not named | — | topobathymetric | MHW | T2 |
| `ncei_guayama_2007` | NCEI Guayama 1/3 arc-second DEM (2007) | not named | — | topobathymetric | MHW | T2 |
| `ncei_mayaguez_2006` | NCEI Mayaguez 1/3 arc-second DEM (2006) | not named | — | topobathymetric | MHW | T2 |
| `ncei_mayaguez_2007` | NCEI Mayaguez 1/3 arc-second DEM (2007) | not named | — | topobathymetric | MHW | T2 |
| `ncei_ponce_2007` | NCEI Ponce 1/3 arc-second DEM (2007) | not named | — | topobathymetric | MHW | T2 |
| `ncei_puerto_rico_cudem_ninth_9525` | NOAA NCEI CUDEM Puerto Rico 1/9 arc-second (m9525, 2022) | not named | — | topobathymetric | PRVD02 | T1 |
| `ncei_puerto_rico_cudem_third_9524` | NOAA NCEI CUDEM Puerto Rico 1/3 arc-second (m9524, 2022) | not named | — | topobathymetric | PRVD02 | T1 |
| `ncei_san_juan_19_prvd02_2015` | NCEI San Juan 1/9 arc-second DEM (2015) | not named | — | topobathymetric | PRVD02 | T2 |
| `ncei_st_croix_13_mhw_2014` | NCEI St Croix 1/3 arc-second DEM (2014) | not named | — | topobathymetric | MHW | T2 |
| `ncei_st_thomas_st_john_13_mhw_2014` | NCEI St Thomas and St John 1/3 arc-second DEM (2014) | not named | — | topobathymetric | MHW | T2 |
| `usgs_gls2000_dem` | USGS GLS2000 elevation data (Landsat terrain correction) | not named | — | mixed | undeclared | T1 |

## Non-product registrations

| File | Id | Classification | Reason |
|---|---|---|---|
| `data_sources/noaa/ncei_coastal_dems.yml` | `puerto_rico_2017` | planned not acquired | Planned PR-wide NCEI DEM; never published (NOAA_NCEI_DEM_GAP_001). |
| `configs/location_query_providers.json` | `USGS_3DEP_1M` | access service | Queries TNM 1 m DEM products; the products it returns are the usgs_3dep_1m_* entries. |
| `configs/remote_monitoring/providers.yaml` | `usgs_3dep_lidar` | provider capability | Remote-monitoring capability flag for 3DEP terrain; binds no product. |
| `configs/remote_monitoring/providers.yaml` | `usgs_reservoir_bathymetry` | provider capability | Remote-monitoring capability flag; binds no product. |
| `registry/access_points/offshore.json` | `sources` | survey registry | 185 hydrographic records with their own sensor_type (183 of 185 set); acquisition method is already recorded per record. |
| `spiderweb/access_points/products.py` | `USGS_TNM_ELEVATION_PRODUCTS` | access service | TNM products API client; returns usgs_3dep_1m_* products. |
| `pipeline/marine_lidar_sources.py` | `USInteragencyElevInventory` | inventory service | US Interagency Elevation Inventory map service (discovery only). |
| `pipeline/marine_sources.py` | `next-catalogs` | inventory service | NCEI multibeam and sounding catalogues (discovery only). |
| `pipeline/marine_sources.py` | `nos_hydro_dynamic` | inventory service | NOS BAG layer (discovery only). |
| `server/frontend/src/modules/SpatialIntelligence.tsx` | `terrarium` | display only | AWS Terrarium hillshade tiles composite SRTM, 3DEP, GMTED and ETOPO1 with per-tile datums; display only. |
| `server/frontend/src/spatial/runtime/CesiumRegionalRuntime.ts` | `createGooglePhotorealistic3DTileset` | display only | Google Photorealistic 3D Tiles: photogrammetric mesh, display only. |
| `spiderweb/access_points/acquisition.py` | `USIEI_TOPOGRAPHIC_LIDAR` | inventory service | Access-point discovery provider; the records it finds are registered in registry/access_points/*.json. |
| `spiderweb/access_points/acquisition.py` | `USIEI_TOPOBATHY_LIDAR` | inventory service | Access-point discovery provider; the records it finds are registered in registry/access_points/*.json. |
| `spiderweb/access_points/acquisition.py` | `USIEI_BATHYMETRIC_LIDAR` | inventory service | Access-point discovery provider; the records it finds are registered in registry/access_points/*.json. |
| `spiderweb/access_points/acquisition.py` | `USIEI_IFSAR` | inventory service | Access-point discovery provider; the records it finds are registered in registry/access_points/*.json. |
| `spiderweb/access_points/acquisition.py` | `USIEI_OTHER_BATHYMETRIC` | inventory service | Access-point discovery provider; the records it finds are registered in registry/access_points/*.json. |
| `spiderweb/access_points/acquisition.py` | `NCEI_MULTIBEAM_CATALOG` | inventory service | Access-point discovery provider; the records it finds are registered in registry/access_points/*.json. |
| `spiderweb/access_points/acquisition.py` | `NCEI_SOUNDING_CATALOG` | inventory service | Access-point discovery provider; the records it finds are registered in registry/access_points/*.json. |
| `spiderweb/access_points/acquisition.py` | `NOS_BAG_INVENTORY` | inventory service | Access-point discovery provider; the records it finds are registered in registry/access_points/*.json. |

## Registry conflicts

These disagreements between registries are recorded, not silently fixed. The test
checks that each observation still holds; when one is fixed, mark the conflict
`resolved`.

| Conflict | Description |
|---|---|
| `ncei_cudem_vertical_datum` | The NCEI YAML gives both CUDEM products PRVD02 (from provider metadata); the priority CSV gives source_dependent. |
| `ncei_cudem_horizontal_datum` | The NCEI YAML gives CUDEM NAD83 (EPSG:4269); the priority CSV gives WGS84. |
| `ncei_dataset_ids` | The YAML and CSV name 8 of their 9 shared products differently; only san_juan_19_prvd02_2015 matches. |
| `ncei_usvi_csv_only` | The St Croix and St Thomas/St John DEMs are in the CSV but not in the YAML manifest. |
| `cudem_m9525_tile_count` | The YAML says CUDEM m9525 has 25 tiles. TheHub's reader (thehub-pr docs/federation/DIGITAL_TWIN_V1.md) copied urllist9525.txt verbatim and found 26. |

## Merge policy and independence

`evaluate_platform_mix()` in `source_adapters/dem_platform/policy.py`:

- **Single source.** Passes when its platform is verified and its vertical datum is declared.
- **Several sources.** Pass only when they share one platform class, one surface
  model and one declared vertical datum, and none is compiled. Anything else gives
  `separate_layers_until_harmonization` with `review_required`.
- **Undeclared datum.** `undeclared` always needs review (COP30, AW3D30, the 2004 USACE lidar).

`shared_acquisition_roots()` decides whether two sources can corroborate each
other. Roots are canonical ids, not platform names: NASA's CMR records name the
same 2000 Shuttle flight `STS-99` (SRTMGL1) and `OV-105` (NASADEM), and both carry
the root `srtm:sts-99:2000-02`. GEBCO 2023 carries it too, because between 50 S and
60 N it uses SRTM15+ as its base. By default `measurement` and `fill` roots count;
`control` and `geolocation` do not.

## SRTMGL1 over Puerto Rico: measured composition

SRTMGL1 v003 fills radar voids from other sources, and SRTMGL1N records the source
of every sample (SRTM User Guide V3, Table 2). The six Puerto Rico tiles were read on
2026-11-23 (receipt: `evidence/dem_sources/srtmgl1_pr_2026-11-23/`). Over
9,906,422 land samples:

| Source | Samples | Share of land |
|---|---|---|
| SRTM radar, measured | 9,904,326 | 99.9788% |
| ASTER GDEM2 fill | 1,668 | 0.0168% |
| SRTM interpolated | 398 | 0.004% |
| NGA fill (undisclosed sources) | 29 | 0.0003% |
| USGS NED fill | 1 | less than 0.0001% |
| GMTED2010 or CDED fill | 0 | 0% |

| Tile | Land samples | SRTM measured | ASTER | SRTM interpolated | NED | NGA | Highest sample (m, EGM96) |
|---|---|---|---|---|---|---|---|
| `N17W066` | 35,574 | 35,574 | 0 | 0 | 0 | 0 | 490 |
| `N17W067` | 486,055 | 485,991 | 49 | 15 | 0 | 0 | 317 |
| `N17W068` | 112,035 | 112,033 | 0 | 2 | 0 | 0 | 299 |
| `N18W066` | 1,788,597 | 1,788,478 | 24 | 66 | 0 | 29 | 1,048 |
| `N18W067` | 6,158,010 | 6,156,249 | 1,461 | 299 | 1 | 0 | 1,328 |
| `N18W068` | 1,326,151 | 1,326,001 | 134 | 16 | 0 | 0 | 731 |

Edge rows and columns shared by neighbouring tiles are counted once per tile, as
published. There are no void samples. Over Puerto Rico, SRTMGL1 is effectively a
single-platform product.

### NUM codes (SRTM User Guide V3, Table 2)

| Value | Source | Category |
|---|---|---|
| 1, 2, 5 | Water-masked | water |
| 11 | NGA-interpolated SRTM | srtm_interpolated |
| 21 | GMTED2010 oversampled from 7.5 arc-seconds | gmted2010 |
| 25 | SRTM within GDEM | srtm_interpolated |
| 31 | NGA fill of SRTM via GDEM (undisclosed sources) | nga_undisclosed |
| 51, 52, 53 | USGS NED (direct, via GDEM, Alaska via GDEM) | ned |
| 72 | Canadian DEM via GDEM | cded |
| 101-200 | ASTER GDEM2, value minus 100 scenes | aster_gdem2 |
| 201-224 | SRTM, value minus 200 swaths | srtm_measured |
| anything else | not in the table | unmapped (counted, never guessed) |

## Landsat terrain correction: a geolocation dependency

Landsat Level-1 products are terrain-corrected with a DEM, so Landsat imagery
depends on elevation data too.

- **What the scenes say (T1).** Both 2024 Collection 2 L1TP scenes checked over
  Puerto Rico, `LC08_L1TP_005047_20241225_20250103_02_T1` and
  `LC09_L1TP_005048_20241217_20241217_02_T1`, record
  `DATA_SOURCE_ELEVATION = "GLS2000"`, `GROUND_CONTROL_POINTS_VERSION = 5`, and
  `GEOMETRIC_RMSE_MODEL` of 6.291 m and 4.918 m.
- **Two USGS wordings.** The Collection 1 description gives GLS2000 ground control
  points and lists SRTM, NED, CDED, DTED, GTOPO30 and GIMP as DEM sources, with the
  RAMP V2 DEM for L1GT scenes over Antarctica. The current Landsat Levels of
  Processing page says Collection 2 L1TP control points are re-baselined to the
  Sentinel-2 Global Reference Image, and lists ArcticDEM, NPI, CDEM, AK_NED, GIMP,
  SNF, NED, GMTED, NASADEM and RAMP V2. RAMP V2 covers Antarctica and is outside
  this area.
- **Not published.** Which constituent of GLS2000 covers Puerto Rico.
- **Size of the coupling.** Landsat OLI views at most 7.5 degrees off nadir, so a
  10-20 m DEM error moves a pixel 1.3-2.6 m. That is below the scenes' own model
  RMSE and well under a 30 m pixel.

The catalog records this as `usgs_gls2000_dem` with a `consumed_by` entry for the
`landsat_archive` provider in `configs/remote_monitoring/providers.yaml`, with
`dependency_kind: geolocation`. It is not an acquisition root, so it does not make
Landsat and SRTM dependent measurements.

## Not covered yet

- `SensorType` has no land members, and the inland access-point records have no
  `sensor_type`. Adding members means regenerating the hashed access-point registries.
- No EGM96 to PRVD02 or NAVD88 transformation is registered, so SRTM, NASADEM and
  the PRVD02 or NAVD88 products stay in separate layers.
- The vertical datums of COP30 and AW3D30 were not stated in the metadata checked.
- The platform used to orthorectify Sentinel-2 L1C is not recorded.

## Related

- `docs/source_adapters/nasa_srtmgl1.md`: SRTMGL1 adapter (LP DAAC).
- `docs/source_adapters/opentopography_globaldem.md`: OpenTopography adapter.
- `docs/sources/noaa_ncei_coastal_dems.md`: NOAA/NCEI coastal DEMs.

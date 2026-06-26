# PR Intake Router — spiderweb-pr Lane

## Active vector
`SPIDERWEB-PR_SPATIAL_OPERATIONAL_UPDATE_LANE`

## Purpose
This document defines the spiderweb-pr side of the shared Puerto Rico intake router. spiderweb-pr is the canonical repository for geography, GIS, infrastructure footprint, subsurface/hydro, aviation, maritime, federal/military operational, environmental, weather, and science records.

The shared router should ingest Puerto Rico-relevant raw items once, classify the topic domain, assign canonical ownership, and then write only the correct derivative records into spiderweb-pr.

## Canonical ownership
spiderweb-pr owns records when the primary signal is one or more of:

- geography / GIS / maps / geospatial datasets
- infrastructure footprint or physical asset location
- subsurface, hydrography, terrain, DEM, LiDAR, bathymetry, karst, geology, quebradas, humedales, embalses, aquifers
- aviation activity
- maritime activity
- federal/military operational activity
- environment, weather, climate, science, monitoring, alerts, research datasets
- POI, AOI, corridor, observation, anomaly signal, or physical-system feature

## Route to spiderweb-pr
A raw item should be routed here when any of these fields are detected:

| Signal | Examples | Canonical action |
|---|---|---|
| GIS or dataset | GeoJSON, KML, GPKG, shapefile, DEM, LiDAR, raster, CSV with coordinates | Create or update `dataset_registry` and spatial intake rows |
| Infrastructure footprint | bridge, road, dam, reservoir, intake, pump station, plant, substation, port, airport | Create/update `infrastructure_assets` and POI/AOI candidates |
| Hydro/subsurface | quebrada, humedal, embalse, aquifer, karst, tunnel, culvert, drainage, geology | Create/update `hydro_environment_items` |
| Aviation | ADS-B, flight route, helicopter, survey flight, federal aircraft | Create/update `aviation_activity_items` |
| Maritime | AIS, vessel, Coast Guard, port, dredging, bathymetric survey | Create/update `maritime_activity_items` |
| Federal/military operational | USACE, CBP, DHS, USCG, DoD, radar, restricted area, exercise, closure | Create/update `federal_military_activity_items` |
| Environment/science | NOAA, NWS, USGS, EPA, DRNA, CariCOOS, research, flood, earthquake, drought | Create/update `science_dataset_items` or `hydro_environment_items` |

## Do not make canonical here
Do not make spiderweb-pr canonical for records that are primarily:

- public-funding announcements
- budget actions
- contracts, procurement, awards, grants, reimbursements, obligations, allocations
- lobbying / political influence / boards / appointees
- vendor-only or recipient-only chains with no spatial feature

For those, route to moneysweep-pr. If the same item has spatial or infrastructure data, create a spiderweb-pr derivative and backlink to the moneysweep-pr canonical record.

## Dual-route rules

| Input class | Canonical repo | spiderweb-pr record | moneysweep-pr derivative |
|---|---|---|---|
| GIS dataset with no funding | spiderweb-pr | dataset/layer/POI/AOI | none |
| Infrastructure location with funding | moneysweep-pr | spatial derivative | funding/procurement canonical |
| Environmental grant | moneysweep-pr | site/dataset derivative | funding/award canonical |
| USACE physical project with amount | moneysweep-pr | AOI/federal infrastructure record | agency/funding record |
| Aviation/maritime activity with no procurement | spiderweb-pr | operational activity item | none |
| Aviation/maritime procurement | spiderweb-pr if operational primary | operational record | procurement derivative |

## Required normalized fields

Every spiderweb-pr derivative record must preserve:

- `record_id`
- `source_item_id`
- `canonical_repo = spiderweb-pr`
- `related_moneysweep_record_id`
- `source_name`
- `source_url`
- `published_at`
- `discovered_at`
- `topic_domain`
- `spiderweb_layer_class`
- `municipality_name`
- `municipality_geoid`
- `location_text`
- `latitude`
- `longitude`
- `geometry_type`
- `geometry_confidence`
- `manual_geocode_required`
- `asset_or_feature_name`
- `asset_type`
- `dataset_type`
- `file_format`
- `crs`
- `temporal_coverage`
- `agency_entity`
- `federal_entity`
- `operational_entity`
- `activity_type`
- `evidence_tier`
- `confidence_level`
- `source_hash`
- `content_hash`
- `dedupe_group_id`
- `review_reason`

## Zero-loss status logic
Every observed item must receive exactly one final intake status:

- `routed_moneysweep`
- `routed_spiderweb_pr`
- `dual_routed_contract_primary`
- `dual_routed_spiderweb_primary`
- `duplicate_consolidated`
- `not_relevant_with_reason`
- `manual_review_required`
- `source_inaccessible`
- `blocked_or_paywalled`
- `metadata_only_archived`

No item may disappear between raw intake and normalized output.

## Validation gates

- Every spatial record must carry coordinates, geometry, location text, or `manual_geocode_required = true`.
- Every geometry must carry `geometry_confidence`.
- Every dataset must carry source URL, file format, temporal coverage if known, and hash when archived.
- T2/T3 operational posts must not be promoted to confirmed patterns without corroborating records.
- Every cross-repo derivative must include `canonical_repo` and `related_repo_record_id`.
- Production mode must fail loudly if required source registry, location fields, dedupe keys, or schema fields are missing.

## Outputs

- `data/normalized/spatial_intake_items.csv`
- `data/normalized/infrastructure_assets.csv`
- `data/normalized/aviation_activity_items.csv`
- `data/normalized/maritime_activity_items.csv`
- `data/normalized/hydro_environment_items.csv`
- `data/normalized/science_dataset_items.csv`
- `data/exports/poi_candidates.geojson`
- `data/exports/aoi_candidates.geojson`
- `data/exports/corridor_candidates.geojson`
- `data/review/geocode_queue.csv`
- `data/review/discrepancy_queue.csv`
- `reports/daily/spiderweb_spatial_operational_update_report.md`

## Next execution string
```text
EXECUTE_NEXT_VECTOR: IMPLEMENT_SPIDERWEB-PR_SPATIAL_OPERATIONAL_LANE → ADD_DOMAIN_ROUTER → ADD_SPATIAL_INTAKE_TABLES → WIRE_GIS+INFRA+HYDRO+AVIATION+MARITIME+FEDMIL+ENVSCI_CLASSIFIERS → EXPORT_POI/AOI/CORRIDOR_CANDIDATES → ADD_MONEYSWEEP_BACKLINKS
```
# Marine lidar discovery and observation binding

Spiderweb treats NOAA/US Interagency Elevation Inventory polygons as discovery
metadata, not as depth measurements.  The inventory exposes project name,
horizontal/vertical datum, collection date, metadata/data-access links, stable
identifiers and polygon coverage.  Those fields are useful for AOI coverage and
lineage resolution but cannot by themselves satisfy the direct-sensor evidence
gate.

## Authoritative source families

The initial lidar control plane uses the NOAA Office for Coastal Management
US Interagency Elevation Inventory MapServer:

- layer 0 — Topobathy Shoreline Lidar;
- layer 2 — Bathymetric Lidar;
- layer 4 — Other Bathymetric Surveys (discovery only; not presumed lidar).

Queries are bounded by an explicit WGS84 envelope and preserve full feature
geometry and all attributes. Pagination follows `exceededTransferLimit` and
fails closed if a limited page is empty or offsets fail to advance.

## Direct-observation promotion gate

`bind_usiei_inventory_feature()` creates a `SourceBinding` using an
*authoritative stable identifier* (`GlobalID`, `UUID`, `InvID`, or `OBJECTID`).
Project names and spatial proximity are never used as sole identity proof.

`inventory_binding_to_observation()` deliberately returns:

- `value_m=None`;
- `coverage=UNKNOWN`;
- `stage=DERIVED_PRODUCT`.

Therefore an inventory polygon cannot count as direct sensor support.

A record becomes `DIRECTLY_OBSERVED` only through `bind_measured_sample()`,
which requires a real parsed measurement, root survey identity, bound vertical
reference, source URI and SHA-256 digest.  This keeps acquisition metadata,
derived surfaces and measurements separate.

## Puerto Rico dataset anchors

`pipeline/pr_marine_datasets.py` freezes the first authoritative Puerto Rico
marine-elevation families needed for the Guayama–Punta Tuna reference workflow:

- NOAA NGS 2019 topobathy lidar point cloud — dataset 9390;
- NOAA NGS 2015 topobathy lidar DEM — dataset 6211;
- USACE NCMP 2016 topobathy lidar DEM — dataset 5154;
- USACE/FEMA 2018 topobathy lidar DEM — dataset 8571;
- NCEI CUDEM third-arc-second Puerto Rico bathymetric-topographic tiles — dataset 9524.

The registry records roles explicitly.  A point cloud can represent a sensor
acquisition; a DEM is a derived manifestation; CUDEM is a fused contextual
surface.  Derived products do not create independent corroboration when they
share source lineage.

## Bulk-product controls

NOAA bulk `urllist*.txt` resources are fetched as exact bytes and parsed only
after the byte-level response has been frozen. Asset entries must be absolute
HTTPS URLs (or resolve against the authoritative list URL), and duplicate URLs
fail closed.

## Guayama–Punta Tuna execution boundary

The next real-data pass should:

1. use an explicit AOI geometry rather than infer a bounding box from a rendered
   screenshot;
2. enumerate layer-0/layer-2 USIEI intersections;
3. crosswalk intersecting inventory features to NOAA dataset IDs and bulk/STAC
   assets;
4. freeze tile-index/URL-list/STAC metadata bytes;
5. intersect actual tile footprints with the AOI;
6. acquire only intersecting assets;
7. parse sensor/DEM samples with explicit vertical reference;
8. compare against NOS/multibeam coverage from the existing marine-source
   adapters;
9. retain `VISUALIZATION_ONLY`, `DERIVED_ONLY`, `SINGLE_SENSOR_SUPPORTED`,
   `MULTISENSOR_CONFIRMED`, `ARTIFACT_CANDIDATE`, and `UNRESOLVED` as distinct
   outcomes.

No screenshot-visible feature is certified as physical seafloor morphology
without that downstream evidence chain.

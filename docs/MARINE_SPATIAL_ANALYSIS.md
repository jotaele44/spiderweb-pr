# Marine Spatial Analysis

Spiderweb treats the shoreline as a transition between spatial domains, not as
the end of analysis.  The marine workflow extends the existing GEBCO terrain
capability with source-agnostic evidence controls for hydrographic and remote
sensing observations.

## Scope

The first implementation lives in `gebco.marine_evidence` and the pipeline
adapter in `pipeline.marine_analysis`.  Existing `pipeline.terrain_hook`
semantics are unchanged.

Supported sensor/product classes include multibeam and single-beam echosounder,
hydrographic soundings, bathymetric/topobathymetric lidar, satellite-derived
bathymetry, side-scan sonar, backscatter, sub-bottom/seismic products, ROV/AUV
observations, coastal DEMs, nautical charts, derived bathymetric grids and
visualizations.

## Evidence model

A marine observation records:

- stable observation ID;
- sensor type and processing stage;
- acquisition/root survey identity;
- coverage state;
- horizontal and vertical reference identity;
- explicit depth sign convention;
- optional depth and uncertainty in metres;
- acquisition timestamp;
- parent lineage IDs;
- source URI and SHA-256 when frozen by an acquisition layer.

`None` means no depth value.  `0.0` remains a valid observation.

Processing stages are:

`RAW_OBSERVATION -> PROCESSED_OBSERVATION -> GRID -> DERIVED_PRODUCT -> VISUALIZATION`

A chart, grid, hillshade and visualization with the same acquisition root do
not constitute four independent confirmations.

## Vertical-reference gate

Direct numerical depth subtraction is allowed only when the two
`VerticalReference` values are fully bound and exactly compatible, or when the
caller supplies an explicit `DepthTransform` carrying an authority/binding.
Unknown or mismatched vertical references fail closed.

Spatial colocation, horizontal reprojection and grid alignment remain upstream
requirements.  Passing the vertical gate alone does not prove that two samples
represent the same location.

## Coverage states

- `DIRECTLY_OBSERVED`
- `INTERPOLATED`
- `EXTRAPOLATED`
- `REMOTE_DERIVED`
- `GENERALIZED`
- `NULL_EMPTY`
- `UNKNOWN`

Interpolation is never promoted to direct observation.

## Feature evidence states

- `MULTISENSOR_CONFIRMED` — at least two direct observations, two acquisition
  roots and two sensor types.
- `DIRECT_SENSOR_CONFIRMED` — direct sensor evidence exists but the strict
  multisensor independence gate is not met.
- `SINGLE_SENSOR_SUPPORTED` — direct support is bound to one acquisition root.
- `DERIVED_ONLY`
- `INTERPOLATED_ONLY`
- `VISUALIZATION_ONLY`
- `ARTIFACT_CANDIDATE`
- `NO_SENSOR_COVERAGE`
- `UNRESOLVED`

Artifact flags such as tile-seam, stitching, source-boundary, resampling or
hillshade-direction coincidence are preserved separately.  They can classify a
derived-only feature as an artifact candidate but do not erase independent
direct multisensor evidence.

## Geomorphology vocabulary

The initial ontology includes shelf, shelf break, slope, basin, trough, canyon,
channel, gully, ridge, mound, depression, escarpment, terrace, bank, shoal,
reef, hardbottom, sediment wave, slump, landslide, debris field, scour, dredged
channel, dredge spoil, excavation, linear/circular feature, anomalous morphology
and unresolved morphology.

`ANOMALOUS_MORPHOLOGY` is descriptive only.  It does not imply anthropogenic
origin.

## Pipeline usage

1. Acquire/freeze source products outside the analysis core.
2. Convert source records to `MarineObservation` without aggregating distinct
   observations.
3. Call `validate_observation_universe()` to enforce stable-ID uniqueness and
   lineage integrity.
4. Build a `MarineFeatureCandidate` from a bounded candidate set.
5. Call `assess_marine_feature()`.
6. For temporal change, spatially align samples first and then call
   `compare_temporal_observations()`; the vertical-reference gate and uncertainty
   propagation are applied before a delta is returned.

## Guayama–Punta Tuna reference case

The south-coast screenshot is a reference integration case, not a trusted
sensor layer.  The intended workflow is:

1. georegister the visualization from coastline/control points;
2. enumerate intersecting survey footprints;
3. freeze sensor/product lineage;
4. separate direct measurements from grids/interpolation/rendering;
5. test visible ridges, channels, depressions and lineaments against direct
   observations;
6. test tile/survey boundaries and illumination dependence;
7. promote only evidence states justified by independent acquisition roots.

No feature visible only in the rendered screenshot is certified as physical
seafloor morphology.

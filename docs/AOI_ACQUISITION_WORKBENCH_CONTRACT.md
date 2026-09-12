# AOI Acquisition Workbench Contract

Status: **OPEN / implementation contract**

This document freezes the user-facing and certification contract for the
Spiderweb-PR polygon-to-source-files workflow.

## Goal

A user may draw, import, or select an authoritative polygon AOI and request a
bounded acquisition plan. The frontend renders a frozen backend plan; the
frontend does not invent source identity, exact spatial classification, cache
identity, coverage, or certification state.

## State machine

```
NO_AOI
  -> AOI_EDITING
  -> AOI_VALIDATING
  -> AOI_VALID
  -> DISCOVERING
  -> PLAN_READY
  -> REVIEWED
  -> ACQUIRING
  -> VALIDATING
  -> COVERAGE_COMPUTING
  -> PASS | OPEN | FAIL | BLOCKED
```

Forbidden shortcuts:

- `AOI_VALID -> PASS`
- `DOWNLOAD_COMPLETE -> PASS`
- `FILES_PRESENT -> COVERAGE_COMPLETE`

## Geometry contract

The following objects remain separate:

- `RAW_IMPORT`
- `NORMALIZED_AOI`
- `PROCESSING_GEOMETRY`
- `SOURCE_FOOTPRINT`
- `AOI_INTERSECTION`
- `DISCOVERY_BBOX`

The polygon is authoritative. The bounding box is discovery-only.

Final source-footprint spatial states are:

- `FULLY_WITHIN`
- `PARTIAL`
- `TOUCH_ONLY`
- `OUTSIDE`
- `NULL_EMPTY`
- `UNRESOLVED`

Default acquisition policy:

- `FULLY_WITHIN`: include
- `PARTIAL`: include
- `TOUCH_ONLY`: exclude/review
- `OUTSIDE`: exclude
- `NULL_EMPTY`: block/review
- `UNRESOLVED`: block

## Frontend responsibilities

The frontend may:

- draw/edit/clear AOIs;
- import supported AOI files;
- select an existing map feature as AOI;
- select product/date/resolution/provider filters;
- request a dry run;
- render source footprints, intersections, discovery bbox, coverage masks,
  gaps, and unresolved geometries;
- render the complete candidate asset table;
- initiate an approved acquisition run;
- display transport, hashing, validation, coverage, and certification states;
- export backend-issued acquisition and coverage manifests.

The frontend must not:

- promote proximity/name/category to source identity;
- compute authoritative source inclusion when the backend plan exists;
- silently drop filtered, malformed, duplicate, null, or unresolved rows;
- treat a successful download as validation or certification;
- replace raw source bytes with clipped/derived outputs.

## Dry-run gate

A dry run is mandatory before fetch. The frozen plan must expose at least:

- source records examined;
- candidate assets;
- filtered/excluded assets;
- required assets;
- cache-valid assets;
- missing assets;
- unresolved assets;
- known estimated transfer bytes;
- provisional footprint coverage when available;
- valid-data coverage state (`UNKNOWN` until inspected when appropriate);
- arithmetic closure state;
- frozen plan identifier/hash.

Required arithmetic:

```
discovered = retained + excluded + unresolved
required = cache_valid + fetch_required + blocked_required
```

Any unexplained mismatch fails closed.

## Acquisition states

Per-asset states must preserve distinctions such as:

- `QUEUED`
- `CACHE_HIT`
- `DOWNLOADING`
- `DOWNLOADED`
- `HASHING`
- `VALIDATING`
- `PASS`
- `FAIL`
- `UNRESOLVED`

Global progress must display discovery, selection, acquisition, validation,
coverage, and certification independently.

## Coverage contract

`files downloaded` is never a proxy for usable coverage.

Coverage is computed backend-side from valid-data masks appropriate to the
requested product and task. The UI may display:

- AOI area;
- valid-data area;
- gap area;
- coverage percent;
- overlap/duplicate coverage diagnostics;
- unresolved residue.

`CERTIFIED` requires zero unresolved residue inside the bounded claim.

## Cache identity

A cache hit requires source-bound identity and validation. Filename equality,
normalized names, nearest source, or equal counts are insufficient.

The UI must be able to explain why an asset is reusable without presenting
filename equality as proof.

## Import contract

Target formats:

- GeoJSON
- KML/KMZ
- GeoPackage
- Shapefile ZIP

Imported bytes remain a distinct provenance artifact. CRS conversion and
geometry normalization are recorded, not hidden.

## Mobile contract

The iPhone interaction path must support:

- tap-to-add vertices;
- explicit Finish;
- Undo;
- edit handles with touch-sized hit areas;
- Dry Run and Fetch without hover/right-click assumptions;
- bottom-sheet or equivalent acquisition panel that does not make the map
  unusably narrow.

## Regression gates

At minimum test:

- valid polygon;
- self-intersection;
- empty polygon;
- polygon with hole;
- multipolygon;
- multipart import;
- unknown CRS;
- no source records;
- source/catalog failure;
- null source geometry;
- touch-only relation;
- duplicate URLs;
- same basename across distinct source identities;
- cache hash mismatch;
- interrupted transfer/resume;
- downloaded-but-invalid file;
- complete files with incomplete valid-data coverage;
- catalog mutation between dry run and execution;
- overlapping AOIs reusing a previously validated source;
- iPhone portrait/landscape edit flow.

## Certification boundary

This contract is **not certification**. The workflow remains OPEN until:

1. backend exact-polygon planning and source binding are wired;
2. the frontend consumes a frozen backend plan;
3. acquisition, hashing, validation, and coverage are wired;
4. desktop and iPhone regression gates pass;
5. arithmetic closes with zero unexplained residue inside the claim.

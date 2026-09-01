# Guayama–Punta Tuna marine reference run

## Purpose

This reference run moves Spiderweb from marine-source adapters into a bounded,
reproducible source-denominator execution for the south-coast sector between
Guayama and Punta Tuna.

The run intentionally uses **two different geometry objects**:

1. `DISCOVERY_CORRIDOR` — a broad analyst-defined source-enumeration envelope.
2. `REGISTERED_VISUALIZATION` — the exact screenshot footprint after control-point
   georegistration and independent review.

They are never interchangeable. A discovery envelope may enumerate candidate
sources, but it cannot certify a feature seen in the screenshot.

## Discovery corridor v0.1

`guayama_punta_tuna_discovery_v0_1`

- WGS84 bbox: `[-66.20, 17.50, -65.80, 18.05]`
- role: `DISCOVERY_CORRIDOR`
- certification: `false`
- purpose: source discovery only

The offshore extent is an analyst-defined search bound, not a reconstruction of
screenshot pixels. If the later registered visualization footprint extends beyond
this corridor, the denominator must be rerun against the larger certified AOI.

## Required source denominator

The canonical reference planner emits six bounded queries:

- NCEI multibeam catalog
- NCEI sounding catalog
- NOS hydrographic surveys with BAGs
- US Interagency Elevation Inventory topobathy shoreline lidar
- US Interagency Elevation Inventory bathymetric lidar
- US Interagency Elevation Inventory other bathymetric surveys

NOAA/NCEI's NOS hydrographic service also exposes a separate digital-sounding
layer. The current Spiderweb denominator retains the NCEI sounding catalog as a
separate discovery family and the BAG layer as a polygon/product family; future
expansion may add NOS layer 1 without treating it as an independent acquisition
when it aliases the same survey root.

## Execution

Dry-run the exact query denominator:

```bash
PYTHONPATH=. python scripts/run_guayama_marine_reference.py
```

Execute live acquisition on a network-enabled host:

```bash
PYTHONPATH=. python scripts/run_guayama_marine_reference.py --execute \
  --out evidence/marine/guayama_punta_tuna_v0_1
```

Every HTTP response is persisted as the exact returned bytes plus a sidecar
manifest containing request URL, HTTP status, retrieval UTC, response byte size,
SHA-256 and headers. Parsed JSON is not substituted for the raw response.

## Spatial classification

Envelope-level acquisition planning uses the controlled states:

- `FULLY_WITHIN`
- `PARTIAL`
- `TOUCH_ONLY`
- `OUTSIDE`
- `NULL_EMPTY`
- `UNRESOLVED`

Envelope intersection is a planning approximation only. Polygon-level geometry
must be used before certifying exact coverage boundaries.

## Certification gates

A screenshot-visible seafloor feature cannot be promoted from this run unless:

1. the screenshot has a separately frozen and certified georegistration;
2. source footprints intersect that registered footprint;
3. raw/processed product lineage is frozen to acquisition roots;
4. vertical references are bound or explicitly transformed;
5. direct observations are distinguished from interpolation, fused DEMs and
   visualizations;
6. source/tile seams and illumination artifacts are tested as negative controls;
7. the final evidence state is supported by the existing marine evidence model.

A successful source query is evidence of coverage/discovery only. It is not
evidence that any particular rendered ridge, channel, depression, lineament or
other morphology is physical.

# Remote-Sensing Monitoring — Architecture (Phase 0 backbone)

Status: **accepted (Phase 0)** · Package: `spiderweb.remote_monitoring`

## Why this exists

Static basemap interpretation cannot be reproduced, dated, or defended. This
subsystem replaces it with a versioned, reproducible remote-monitoring backbone
in which **every physical observation is traceable** to an acquisition, a
processing recipe, a geometry, and an explicit candidate-vs-confirmed decision.

The governing rule: a remote-sensing *detection is a candidate, never a
conclusion*. Promotion to a confirmed classified event is a separate, explicit
adjudication that requires corroboration a sensor alone cannot provide.

## Scope of Phase 0 (this package)

The **mandatory** pieces from the design brief, built stdlib-only so the base
test suite runs offline with no network or geospatial dependency:

- Candidate → confirmed lifecycle and adjudication state machine.
- Scene-level provenance and the five core data objects (schemas below).
- Confidence scoring model + classification bands.
- Physical-observation ↔ contract-record crosswalk with reconciliation states.
- Cadence-from-catalog and InSAR-pair compatibility helpers.
- `rm_*` GeoJSON export with `provenance_utils` lineage.

Out of scope here (later phases): live STAC pixel fetch, Sentinel-1 GRD
amplitude monitoring, coherence/InSAR processing, reservoir turbidity detectors,
a GPKG sink into `PRI.gpkg`, and alert-engine delivery. The optional
`discovery.py` seam (metadata-only, reusing the `imagery/` providers) is the
forward hook for the SAR/optical phases.

## The five corrections (encoded as code + tests)

1. **No hard-coded Sentinel-1 12-day cadence.** `catalog.observed_revisit_days`
   computes the cadence from actual acquisitions; there is no assumed-revisit
   constant. A valid InSAR pair must match relative orbit, mode, polarization,
   footprint, processing baseline, and a usable baseline
   (`catalog.insar_pair_compatibility` returns the explicit rejection reasons).
2. **Coherence loss is not a disturbance classification.** The
   detection-state → evidence-tier map (`schemas.DETECTION_STATE_INTERPRETATION`)
   keeps SAR-amplitude-only and coherence-loss-only as *candidates*; corroboration
   is required to climb tiers, and no combination auto-reaches a confirmed event.
3. **Planet NICFI is optional.** It sits behind a disabled capability flag in
   `configs/remote_monitoring/providers.yaml`
   (`enabled: false, status: entitlement_required, redistribution: unresolved`)
   and is never a baseline dependency.
4. **No lidar volume change without two compatible epochs.** A single 3DEP
   surface supports geomorphometry only; volumetric change requires two
   registered, datum-reconciled epochs and a level-of-detection threshold. The
   provider registry flags `volume_change_requires_two_epochs: true`.
5. **Satellite imagery does not measure dredged volume.** Imagery may indicate
   activity periods, plumes, or spoil-area change — not sediment mass, cubic
   meters, disposal quantity, or contract completion. Those need bathymetry,
   survey cross-sections, or disposal records.

Closing guardrail: `crosswalk.reconcile` returns `NO_SIGNAL_DETECTED` only when
observability was adequate, and attaches a disclaimer — it **never** means the
contracted work did not occur. Inadequate observability yields
`INSUFFICIENT_OBSERVABILITY` instead.

## Core data objects (JSON Schema, draft-07)

| Object | Schema file | Purpose |
| --- | --- | --- |
| `monitoring_aoi` | `schemas/monitoring_aoi.schema.json` | Versioned AOI polygon + objective |
| `source_scene` | `schemas/source_scene.schema.json` | Scene-level acquisition provenance |
| `remote_observation` | `schemas/remote_observation.schema.json` | One dated detection (candidate) |
| `adjudication_event` | `schemas/adjudication_event.schema.json` | Reversible candidate→confirmed decision |
| `physical_contract_crosswalk` | `schemas/physical_contract_crosswalk.schema.json` | Observation ↔ contract reconciliation |

All are auto-discovered by `integration.schema_validation.SchemaValidator` and
registered in `schemas/schema_index.json`.

## Confidence model

Seven additive components (max 100): sensor quality (15), registration
reliability (15), temporal persistence (15), independent corroboration (20),
terrain/hydro consistency (10), authoritative correlation (15), human
adjudication (10). Bands: Weak (0–29), Candidate (30–49), Supported (50–69),
Corroborated (70–84), High-confidence (85–100). The band names the **strength of
the surface-change signal only** — not the event class. Config:
`configs/remote_monitoring/confidence_model.yaml`.

## Pilot

`configs/remote_monitoring/aois.yaml` seeds two AOIs: **Carraízo reservoir**
(active Phase-0 pilot — a bounded reservoir with sedimentation/dredging use case)
and the **Cordillera Central landslide corridor** (seeded, inactive). Seed
polygons are approximate pending an authoritative `PRI.gpkg`-sourced boundary.

The defensible analytical product for Carraízo is *a dated physical-activity and
observability timeline compared against documented milestones and expenditures* —
not a claim that "money moved and the water did not," which would require the
physical timeline, bathymetry, and financial records to survive contradiction
review.

## Output layers

`exports.export_layers` writes `rm_monitoring_aois`, `rm_observations`,
`rm_change_candidates`, `rm_adjudications`, and `rm_contract_crosswalk` as
GeoJSON FeatureCollections. Each Feature carries `properties._meta`
(`provenance_utils.geojson_feature_meta`) and each run writes an
`rm_manifest.json` stamped with the canonical reproducibility block. These layer
names carry over to a future GPKG sink.

## Deferred inputs (before later phases)

PRI.gpkg layer/schema inventory; authoritative AOI boundaries; a
provider/licensing entitlement registry; local-vs-cloud execution model; and
selection of Carraízo vs. the Cordillera corridor as the first live validation
target.

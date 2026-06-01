# PR DEM Candidate QGIS Review Guide

This guide standardizes manual review of DEM terrain-screening candidates.

The purpose is to preserve observations, reduce review drift, and avoid unsupported conclusions. Candidate points are prioritization signals only.

## Required input layers

Load the following first:

```text
outputs/pr_dem_one_tile_pilot/pr_dem_one_tile_candidates.geojson
outputs/pr_dem_batch_arecibo_utuado/pr_dem_batch_candidates.geojson
```

Recommended context layers:

| Layer class | Purpose |
|---|---|
| DEM hillshade | Terrain context |
| Slope raster | Internal flatness / surrounding steepness check |
| Roads / TIGER edges | Access context |
| Hydro / water assets | Drainage and infrastructure context |
| Power / utility layers | Utility-adjacent context |
| Karst / geology | Karst-interface context |
| Recent imagery basemap | Visual confirmation |
| Historical imagery | Change detection |

## Candidate styling

Use graduated styling on:

```text
ILAP_SCORE
```

Suggested classes:

| Score range | Class | Meaning |
|---:|---|---|
| 0–30 | Background | Low priority |
| 31–50 | Review | Needs visual check |
| 51–70 | Candidate | Retain for context review |
| 71+ | High Priority | Review first |

Label field:

```text
candidate_id
```

## Review fields

Use the manual review template:

```text
templates/pr_dem_candidate_manual_review_template.csv
```

Validated schema:

```text
schemas/pr_dem_candidate_review.schema.json
```

### Core identity fields

| Field | Meaning |
|---|---|
| `candidate_id` | Stable candidate ID from the CSV/GeoJSON output |
| `source_tile` | DEM tile that generated the candidate |
| `batch_profile` | Regional batch profile, for example `arecibo_utuado` |
| `lon`, `lat` | Geographic coordinates when available |
| `x`, `y`, `crs` | Projected coordinates and CRS fallback |

### Terrain fields

| Field | Review use |
|---|---|
| `area_m2` | Reject implausibly tiny/huge patches unless justified |
| `mean_slope_deg` | Confirms internal flatness |
| `ring_mean_slope_deg` | Confirms contrast with surrounding terrain |
| `tpi_mean_m` | Helps distinguish local high/low terrain position |
| `terrain_visual_type` | Manual interpretation category |

### Context fields

| Field | Review use |
|---|---|
| `access_context` | Road, dead-end, service-track, or no visible access |
| `hydro_context` | Stream, reservoir, or drainage relation |
| `utility_context` | Powerline, substation, pipeline, tower-like, or none |
| `karst_context` | Karst zone, boundary, depression, or not related |
| `imagery_context` | Structure, clearing, vegetation, bare ground, or limited imagery |

### Decision fields

| Field | Allowed interpretation |
|---|---|
| `review_status` | Current review state |
| `review_decision` | Retain, escalate, reject, or insufficient evidence |
| `review_confidence` | Low / medium / high |
| `recommended_next_step` | Follow-up layer or review action |
| `review_notes` | Short observational notes only |
| `evidence_tier` | T1/T2/T3/T4 evidence classification |

## Review decision rules

| Condition | Recommended decision |
|---|---|
| Clear flat patch plus access/context overlap | `retain_candidate` |
| Strong terrain/context convergence | `escalate_high_priority` |
| Natural summit, ridge flat, or pasture feature | `reject_natural_feature` or `retain_low_priority` |
| Known road cut, quarry, or ordinary facility | `reject_known_ordinary_infrastructure` unless context warrants retention |
| Raster seam, void, interpolation issue, or edge artifact | `reject_data_artifact` |
| Obscured imagery or contradictory layers | `insufficient_evidence` or `needs_second_pass` |

## Evidence tier guidance

| Tier | Use here |
|---|---|
| T1 technical | DEM-derived candidate, GIS layer overlap, CRS-valid coordinate |
| T2 operational | Access road, utility corridor, water asset, or facility context layer |
| T3 eyewitness | Not normally used in this DEM workflow unless separately documented |
| T4 secondary | General web/source context, notes, or indirect references |

## QGIS workflow

1. Load candidate GeoJSON.
2. Confirm CRS and point placement.
3. Style by `ILAP_SCORE`.
4. Label by `candidate_id`.
5. Add DEM hillshade and slope context.
6. Add roads, hydro, utility, karst/geology layers.
7. Review highest-score points first.
8. Fill one row per reviewed candidate in the manual review CSV.
9. Use conservative decisions when imagery or layer context is ambiguous.
10. Export final reviewed CSV as a locked review artifact.

## Guardrail

Do not describe a candidate as confirmed infrastructure, hidden infrastructure, or subsurface activity based on DEM geometry alone. The output is a prioritization layer requiring cross-source validation.

# PR DEM QGIS Queue Style Guide

This guide styles the post-review decision queues created by:

```text
tools/pr_dem_review_decision_router.py
```

The queue outputs are review-management layers, not confirmed findings.

## Queue layers

Load these GeoJSON files from:

```text
outputs/pr_dem_review_queues/
```

| Queue file | Purpose |
|---|---|
| `queue_escalated.geojson` | Highest-priority retained/escalated review features |
| `queue_retained.geojson` | Retained features for normal follow-up |
| `queue_second_pass.geojson` | Features needing another review pass |
| `queue_insufficient_evidence.geojson` | Features with inadequate evidence |
| `queue_rejected.geojson` | Rejected natural/ordinary/artifact features |
| `queue_unreviewed.geojson` | Features without review rows |
| `queue_all_routed.geojson` | All routed features in one layer |

## Recommended layer order

| Order | Layer |
|---:|---|
| 1 | `queue_escalated.geojson` |
| 2 | `queue_retained.geojson` |
| 3 | `queue_second_pass.geojson` |
| 4 | `queue_insufficient_evidence.geojson` |
| 5 | `queue_unreviewed.geojson` |
| 6 | `queue_rejected.geojson` |
| 7 | DEM hillshade / slope / basemap context |

## Labeling

Label all queue layers with:

```text
candidate_id
```

For dense areas, use rule-based labels only for:

```text
decision_queue IN ('escalated', 'retained', 'second_pass')
```

## Attribute fields to inspect

| Field | Use |
|---|---|
| `decision_queue` | Final route bucket |
| `decision_queue_reason` | Why the feature entered the queue |
| `review_review_decision` | Manual review decision |
| `review_review_status` | Manual review status |
| `review_review_confidence` | Manual review confidence |
| `review_recommended_next_step` | Next follow-up action |
| `review_terrain_visual_type` | Visual terrain category |
| `review_access_context` | Access context |
| `review_hydro_context` | Hydro context |
| `review_utility_context` | Utility context |
| `review_karst_context` | Karst context |
| `review_imagery_context` | Imagery context |
| `ILAP_SCORE` | Original prioritization score |

## Suggested review order

1. `queue_escalated.geojson`
2. `queue_second_pass.geojson`
3. `queue_retained.geojson`
4. `queue_insufficient_evidence.geojson`
5. `queue_unreviewed.geojson`
6. `queue_rejected.geojson`

## Queue interpretation

| Queue | Interpretation |
|---|---|
| `escalated` | Strongest reviewed candidates; prioritize cross-layer follow-up |
| `retained` | Keep for continued analysis, but lower urgency |
| `second_pass` | Needs another human review or extra context layer |
| `insufficient_evidence` | Do not escalate until more evidence exists |
| `rejected` | Preserve as audit trail and false-positive training set |
| `unreviewed` | Missing review row; do not interpret |

## Guardrail

Decision queues are workflow-management categories. They do not confirm infrastructure, hidden infrastructure, or subsurface activity. All escalations require cross-source validation.

# Confidence Model

Every row carries a `confidence` object with a scalar `score` in `[0, 1]` plus
the `method` used to compute it. Components are optional sub-scores that
contributed to the final score.

## Shape

```json
"confidence": {
  "score": 0.78,
  "method": "ocr_consensus",
  "components": {
    "ocr_avg": 0.85,
    "geo_calib": 0.65
  }
}
```

| Field        | Type     | Required | Notes |
|--------------|----------|----------|-------|
| `score`      | number   | yes      | In `[0.0, 1.0]`. 1.0 = ground truth; 0.0 = no confidence. |
| `method`     | string   | yes      | Canonical method name (see below). |
| `components` | object   | no       | Per-component sub-scores; producer-defined keys. |

## Recommended `method` values

| Method                | Used when                                                       |
|-----------------------|-----------------------------------------------------------------|
| `ground_truth`        | Verified by an external authority (FAA filing, official log).   |
| `manifest_attested`   | Source produced a signed/hashed manifest; we trust the manifest. |
| `ocr_consensus`       | Multi-engine OCR agreement (Tesseract + PaddleOCR + EasyOCR).   |
| `rule_based`          | Deterministic rule fired (e.g. takeoff = ground_speed crossing threshold). |
| `track_aggregation`   | Score is derived from multiple observations aggregated into a track. |
| `model_prediction`    | ML model output (include version in `actor` of the relevant lineage step). |
| `human_review`        | Verified by a human reviewer (high confidence). |

Producers should stick to this list when possible. Custom method names are
allowed but should be namespaced (e.g. `custom.heuristic.v2`).

## Composition

When a row's score is derived from multiple components, each component should
appear in `components` with its own `[0, 1]` sub-score. The producer chooses
the aggregation function (min, mean, weighted mean); the contract does not
require a specific aggregation, but recommends documenting it in the actor's
public docs.

## Why this matters

- **Filtering.** Consumers can drop rows below a threshold (e.g. `score < 0.5`).
- **Triage.** Operations teams can route low-confidence rows to manual review
  queues without re-running upstream pipelines.
- **Federation arbitration.** When two producers disagree on the same subject,
  the consumer can prefer the higher-confidence claim, optionally weighted by
  `method` (e.g. `ground_truth` > `manifest_attested` > `model_prediction`).

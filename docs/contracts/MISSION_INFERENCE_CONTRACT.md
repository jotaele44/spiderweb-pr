# Mission Inference Contract

Schema ID: `mission_inference`  
JSON Schema dialect: Draft-07  
File: `schemas/mission_inference.schema.json`

---

## Purpose

A mission inference record captures the output of the Phase 3 multi-factor
scoring engine for a single flight. It records which mission type the pipeline
assigned to the flight, how confident it is in that assignment, and the
per-signal breakdown that explains the score.

Records conforming to this schema are written to the `mission_scores` table
by `Phase3Pipeline` and can be retrieved in structured form via
`Phase3Pipeline.explain(flight_id)`.

Required fields (`flight_id`, `mission_type`, `total_score`) uniquely
identify the scored flight and provide the minimum information needed for
downstream consumers (cluster assignments, Markov predictor, alert engine)
to act on the result.

`additionalProperties: true` — extra fields are permitted and ignored by
schema validation.

---

## Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `flight_id` | string | **yes** | Identifier of the flight that was scored. Must be non-empty. |
| `mission_type` | string | **yes** | The mission type label assigned by the scorer (e.g. `"Power Line Inspection"`). Must be non-empty. |
| `total_score` | number | **yes** | Composite weighted score in the range `[0.0, 1.0]`. Higher values indicate stronger evidence for the assigned mission type. |
| `confidence_level` | string enum\|null | no | Human-readable confidence tier derived from `total_score`. See [Confidence Level Values](#confidence-level-values). |
| `signal_scores` | string\|null | no | JSON-encoded object mapping each signal name to its individual score contribution (e.g. `{"altitude_profile": 0.82, "hover_behavior": 0.55}`). |
| `explanation` | string\|null | no | JSON-encoded list of human-readable strings describing the scoring rationale for the top mission type. |
| `scored_at` | string\|null | no | ISO 8601 timestamp of when this score was computed. |
| `markov_next_mission` | string\|null | no | Mission type predicted as most likely to follow this flight, as determined by the Markov chain predictor. |

---

## Confidence Level Values

The `confidence_level` field maps `total_score` ranges to a qualitative tier.
Exactly one of the following values must be used (or `null`):

| Value | Typical Score Range | Meaning |
|-------|---------------------|---------|
| `HIGH` | ≥ 0.70 | Strong evidence — multiple independent signals align with the assigned mission type. |
| `MEDIUM` | 0.40 – 0.69 | Moderate evidence — some signals are consistent but others are ambiguous. |
| `LOW` | < 0.40 | Weak evidence — signals are sparse or contradictory; assignment is tentative. |
| `null` | — | Confidence could not be determined or scoring was not completed. |

---

## Signal Names

The `signal_scores` field (when present) maps the following signal names to
per-signal scores. Each score is a float in `[0.0, 1.0]`.

| Signal | Weight | Description |
|--------|--------|-------------|
| `corridor_alignment` | 0.20 | Degree to which the flight track follows known mission corridors. |
| `infrastructure_proximity` | 0.18 | Proximity to critical infrastructure assets (power lines, pipelines, etc.). |
| `altitude_profile` | 0.15 | Match between observed altitude envelope and expected mission altitude. |
| `hover_behavior` | 0.12 | Presence and pattern of hover or loiter behavior. |
| `operator_identity` | 0.10 | Known operator classification for the callsign. |
| `repeat_frequency` | 0.08 | How often this flight route/pattern recurs historically. |
| `time_pattern` | 0.08 | Match between time-of-day and known operational windows. |
| `speed_profile` | 0.06 | Match between observed speed distribution and mission speed envelope. |
| `duration_profile` | 0.03 | Match between flight duration and expected mission duration. |

Weights sum to 1.0. Individual signal scores are computed by
`MultiFactorMissionScorer._score_against_profile()` and stored as a
JSON string in the `signal_scores` column.

---

## Minimal Valid Example

```json
{
  "flight_id": "FLT-2024-03-14-001",
  "mission_type": "Power Line Inspection",
  "total_score": 0.83,
  "confidence_level": "HIGH",
  "signal_scores": "{\"corridor_alignment\": 0.95, \"infrastructure_proximity\": 0.90, \"altitude_profile\": 0.78, \"hover_behavior\": 0.70, \"operator_identity\": 0.85, \"repeat_frequency\": 0.60, \"time_pattern\": 0.75, \"speed_profile\": 0.55, \"duration_profile\": 0.50}",
  "explanation": "[\"Strong corridor alignment with Route PR-22 power corridor\", \"Aircraft hovered 4 times near transmission towers\", \"Operator N5854Z has 12 prior power inspection flights\"]",
  "scored_at": "2024-03-14T15:00:00Z",
  "markov_next_mission": "Power Line Inspection"
}
```

---

## Programmatic Access

**Score explanation** — use `Phase3Pipeline.explain(flight_id)` to retrieve
a structured breakdown for a specific flight:

```python
from mission_inference import Phase3Pipeline

pipeline = Phase3Pipeline()
result = pipeline.explain("FLT-2024-03-14-001")
# Returns:
# {
#   "flight_id": "FLT-2024-03-14-001",
#   "top_mission": "Power Line Inspection",
#   "score": 0.83,
#   "signals": {
#     "corridor_alignment": 0.95,
#     "infrastructure_proximity": 0.90,
#     ...
#   }
# }
```

**Schema validation** — use `SchemaValidator` from `schema_validation.py`:

```python
from schema_validation import SchemaValidator
v = SchemaValidator()
result = v.validate(inference_dict, "mission_inference")
if not result["valid"]:
    print(result["errors"])
```

The schema is auto-loaded by `SchemaValidator._load_schemas()` from the
`schemas/` directory — no registration step required.

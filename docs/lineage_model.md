# Lineage Model

Every row in every stream carries a non-empty `lineage` array. Lineage is the
producer's attestation of *how this row came to be* — the chain of steps from
raw input to the row in the manifest.

## Shape

```json
"lineage": [
  {"step": "ingest",       "actor": "fr24_screenshot_inventory", "ts": "2024-03-15T08:05:00+00:00"},
  {"step": "ocr",          "actor": "ensemble_ocr@v1",            "ts": "2024-03-15T08:06:00+00:00"},
  {"step": "georeference", "actor": "geo_calibration@v1",         "ts": "2024-03-15T08:07:00+00:00"},
  {"step": "export",       "actor": "spiderweb-pr@0.1.0",         "ts": "2026-05-28T00:00:00+00:00"}
]
```

Each step is an object:

| Field    | Type   | Required | Notes |
|----------|--------|----------|-------|
| `step`   | string | yes      | Short canonical name: `ingest`, `dedup`, `ocr`, `georeference`, `cluster`, `score`, `export` |
| `actor`  | string | yes      | Identifier + version of the component that performed the step (`module@version`) |
| `ts`     | string | yes      | ISO-8601 timestamp with timezone for when the step ran |
| `inputs` | array  | no       | Optional list of upstream identifiers (file hashes, row ids) consumed by this step |

## Rules

1. **Non-empty.** A row with zero steps is rejected. Even a single-step lineage
   (`[{"step":"export", ...}]`) is acceptable for purely synthetic rows.
2. **Ordered oldest-first.** Consumers may rely on chronological order.
3. **Append-only.** Producers should never delete or rewrite earlier steps.
4. **Canonical steps preferred.** Stick to the names above when they fit; use
   namespaced custom names (e.g. `cluster.dbscan`) when they don't.

## Example: FR24 screenshot → corridor crossing event

```
ingest        fr24_screenshot_inventory@1.2   2024-03-15T08:05:00Z
ocr           ensemble_ocr@v1                  2024-03-15T08:06:00Z   (inputs: ["sha256:abc..."])
georeference  geo_calibration@v1               2024-03-15T08:07:00Z
cluster       corridor_graph@v2                2024-03-15T08:10:00Z
score         rule_based_confidence@v1         2024-03-15T08:11:00Z
export        spiderweb-pr@0.1.0               2026-05-28T00:00:00Z
```

## Why this matters

- **Auditability.** A consumer or auditor can ask "where did this row come
  from?" and get a deterministic answer.
- **Reprocessing.** When a step is fixed (e.g. OCR model upgrade), every row
  produced by the old actor can be located and reprocessed.
- **Federation trust.** Hubs receiving rows from multiple producers can weight
  by which actors appeared in lineage (e.g. trust georeferenced points more
  than dead-reckoned ones).

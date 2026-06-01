# PR DEM Review Lock Workflow

This guide validates manual QGIS review rows, merges review decisions into candidate GeoJSON, writes summary reports, and produces a checksum manifest.

This stage runs after candidate review rows have been filled using:

```text
templates/pr_dem_candidate_manual_review_template.csv
```

Validation schema:

```text
schemas/pr_dem_candidate_review.schema.json
```

Tool:

```text
tools/pr_dem_review_lock.py
```

## Inputs

| Input | Description |
|---|---|
| Candidate GeoJSON | Output from one-tile or batch DEM candidate generation |
| Review CSV | Manual review rows using the template |
| Review schema | JSON schema defining required fields and allowed values |

Example candidate GeoJSON paths:

```text
outputs/pr_dem_one_tile_pilot/pr_dem_one_tile_candidates.geojson
outputs/pr_dem_batch_arecibo_utuado/pr_dem_batch_candidates.geojson
```

## Outputs

Default output directory:

```text
outputs/pr_dem_review_lock/
```

Generated artifacts:

| File | Purpose |
|---|---|
| `validation_report.json` | PASS/FAIL validation status and counts |
| `validation_findings.csv` | Row-level validation warnings/failures |
| `invalid_review_rows.csv` | Invalid rows isolated for correction |
| `reviewed_candidates.geojson` | Candidate GeoJSON with `review_*` properties attached |
| `review_summary.json` | Machine-readable review summary |
| `review_summary.md` | Human-readable review summary |
| `locked_review_manifest.json` | SHA-256 manifest of inputs and locked outputs |

## Default behavior

If any review row is invalid, the tool stops before merging unless `--allow-invalid` is passed.

Invalid rows are always written to:

```text
outputs/pr_dem_review_lock/invalid_review_rows.csv
```

Use `--allow-invalid` only when you want to exclude invalid rows and merge only valid rows.

## Review field merge behavior

The tool preserves the original candidate geometry and candidate properties.

Review fields are added with a `review_` prefix. Example:

```text
review_review_status
review_review_decision
review_review_confidence
review_terrain_visual_type
review_access_context
review_hydro_context
review_utility_context
review_karst_context
review_imagery_context
```

Each candidate receives a merge status:

| Value | Meaning |
|---|---|
| `review_attached` | Matching review row was merged |
| `no_review_row` | Candidate had no matching review row |

## Lock manifest

The lock manifest records:

- input paths
- input file sizes
- input SHA-256 checksums
- output paths
- output file sizes
- output SHA-256 checksums
- validation status
- merge counts

This makes the reviewed candidate layer reproducible and auditable.

## Command block for later

Run after the review CSV has been filled:

```bash
python tools/pr_dem_review_lock.py \
  --candidate-geojson outputs/pr_dem_batch_arecibo_utuado/pr_dem_batch_candidates.geojson \
  --review-csv outputs/manual_review/pr_dem_candidate_review_completed.csv \
  --schema schemas/pr_dem_candidate_review.schema.json \
  --output-dir outputs/pr_dem_review_lock \
  --lock-dir outputs/pr_dem_review_lock/LOCKED
```

If you want to continue while excluding invalid rows:

```bash
python tools/pr_dem_review_lock.py \
  --candidate-geojson outputs/pr_dem_batch_arecibo_utuado/pr_dem_batch_candidates.geojson \
  --review-csv outputs/manual_review/pr_dem_candidate_review_completed.csv \
  --schema schemas/pr_dem_candidate_review.schema.json \
  --output-dir outputs/pr_dem_review_lock \
  --lock-dir outputs/pr_dem_review_lock/LOCKED \
  --allow-invalid
```

## Review lock gate

Do not treat a reviewed layer as locked unless:

1. `validation_report.json` has status `PASS`.
2. `reviewed_candidates.geojson` exists and is non-empty.
3. `review_summary.md` exists and is readable.
4. `locked_review_manifest.json` contains SHA-256 checksums for all final outputs.
5. The reviewed GeoJSON opens correctly in QGIS.

## Guardrail

A reviewed candidate remains a reviewed prioritization feature. Manual review can retain, reject, or escalate a candidate for further study, but it does not by itself confirm hidden infrastructure or subsurface activity.

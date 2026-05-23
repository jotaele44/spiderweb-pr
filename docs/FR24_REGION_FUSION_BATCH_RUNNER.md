# FR24 Region Fusion and Batch Runner

## Purpose

This layer connects region OCR outputs to structured parsing, fuses whole-image and region-derived fields, and adds a resumable batch runner for full-corpus OCR execution.

All outputs remain candidate records. This layer does not confirm aircraft events, anomalies, routes, infrastructure, or operational status.

## Region parsing

```bash
python fr24_region_parse.py \
  --input-jsonl data/_manifests/fr24_audit/fr24_region_ocr_results.jsonl \
  --output-csv data/_manifests/fr24_audit/fr24_region_parsed_events.csv \
  --review-csv data/_manifests/fr24_audit/fr24_region_review_queue.csv
```

Outputs:

| File | Purpose |
|---|---|
| `fr24_region_parsed_events.csv` | Structured region OCR candidates |
| `fr24_region_review_queue.csv` | Region OCR rows requiring review |

## OCR fusion

```bash
python fr24_ocr_fusion.py \
  --whole-image-csv data/_manifests/fr24_audit/fr24_ocr_parsed_events_probe_50.csv \
  --region-csv data/_manifests/fr24_audit/fr24_region_parsed_events.csv \
  --output-csv data/_manifests/fr24_audit/fr24_fused_event_candidates.csv \
  --review-csv data/_manifests/fr24_audit/fr24_fused_review_queue.csv
```

Fusion preserves both source values:

- `<field>_wi`
- `<field>_region`

Conflicts are not overwritten. They are routed to:

```text
fusion_conflict_review
```

## Batch runner

Whole-image mode:

```bash
python fr24_batch_run.py \
  --batch-plan data/_manifests/fr24_audit/fr24_full_corpus_batch_plan.csv \
  --batch-id fr24_batch_0001 \
  --mode whole-image \
  --limit 25
```

Region mode:

```bash
python fr24_batch_run.py \
  --batch-plan data/_manifests/fr24_audit/fr24_full_corpus_batch_plan.csv \
  --batch-id fr24_batch_0001 \
  --mode region \
  --limit 25
```

Outputs:

| File | Purpose |
|---|---|
| `batches/fr24_batch_0001_whole-image_ocr.jsonl` | Batch OCR JSONL |
| `batches/fr24_batch_0001_region_ocr.jsonl` | Region OCR JSONL |
| `batches/fr24_batch_0001_whole-image_status.json` | Whole-image status |
| `batches/fr24_batch_0001_region_status.json` | Region status |
| `fr24_batch_run_ledger.csv` | Resumable run ledger |
| `fr24_batch_error_queue.csv` | Non-fatal batch failures |

## Batch status

```bash
python fr24_batch_status.py \
  --ledger data/_manifests/fr24_audit/fr24_batch_run_ledger.csv
```

## Review queue

```bash
python fr24_review_queue_builder.py \
  --fused-csv data/_manifests/fr24_audit/fr24_fused_event_candidates.csv \
  --output-csv data/_manifests/fr24_audit/fr24_fused_review_queue_ranked.csv
```

## Conservative policy

Disallowed automatic labels:

- `confirmed`
- `confirmed_aircraft_event`
- `confirmed_anomaly`
- `confirmed_route`

Allowed review-gated labels:

- `region_parsed_candidate`
- `region_manual_review_required`
- `region_low_text_review`
- `fused_candidate`
- `fusion_conflict_review`
- `region_only_review`
- `manual_review_required`
- `planned_candidate`
- `not_confirmed`

## Known limitations

- OCR accuracy depends on local Tesseract and Pillow/HEIC availability.
- Region fractions are fixed approximations and may need UI-layout profiles.
- Fusion does not yet promote a single canonical field value; it preserves source fields side-by-side.
- Cross-batch deduplication should be added before downstream intelligence products.

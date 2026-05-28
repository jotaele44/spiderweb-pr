# PR Intake Derivative Handoff (Contract-Sweeper → spiderweb-pr)

The PR intake router federates Puerto Rico raw-intake items across the pair
**Contract-Sweeper** (`primary_repo`) and **spiderweb-pr** (`paired_repo`). Items in
spatial / GIS / infrastructure / aviation / maritime / environment / science domains are
emitted to the spiderweb-pr lane. This document is the contract for that lane: what the
producer writes, where it lands, and how spiderweb-pr consumes it.

## Producer (Contract-Sweeper)

`scripts/route_pr_intake.py` (a.k.a. `run_pr_intake_router.py`) classifies raw items via
`shared/pr_intake_router.py` and writes, among other outputs:

- `spiderweb_pr_derivatives.csv` — one row per item routed to (or dual-routed with a
  derivative in) spiderweb-pr.

See `Contract-Sweeper/docs/pr_intake_router_execution.md` for how to run it.

## Transport: dropzone

The consumer reads a configurable dropzone directory. Default:

```text
spiderweb-pr/data/intake/pr_intake/spiderweb_pr_derivatives.csv
```

Contract-Sweeper (or an operator) copies the router's
`data/exports/pr_intake_router/spiderweb_pr_derivatives.csv` into that dropzone. This
mirrors the existing "place raw items at `data/intake/pr_news/...`" convention on the
producer side and keeps the two repo layouts decoupled. (Alternative: point the importer
`--input-dir` directly at the producer's export dir.)

## On-disk CSV shape (IMPORTANT)

The producer's `csv.DictWriter` writes the row dict through `flatten_for_csv` +
`write_csv` (`scripts/route_pr_intake.py`). Consequences the importer must honor:

- **Every value is a string.** SQL/JSON nulls are written as **empty strings**.
- **`domains` and `output_tables` are JSON-encoded array strings**, e.g. `["subsurface_hydro"]`.
- **Column order is alphabetized.** Read by header name, never by position.

Columns (alphabetized): `canonical_repo, confidence_level, content_hash, dedupe_group_id,
discovered_at, domains, evidence_tier, final_status, output_tables, published_at,
record_id, related_repo_record_id, source_hash, source_item_id, source_name, source_url,
summary_own_words, target_repo, title`.

Required (per `schemas/pr_intake_derivative.schema.json`): `record_id`, `source_item_id`,
`target_repo` (= `spiderweb-pr`), `final_status`, `domains`, `title`, `source_url`. These
must be **present** columns; the consumer does not add constraints the producer doesn't
enforce. In particular `title` and `source_url` **may be empty strings** — the router does
not guarantee their content — so a routed item with an empty title is imported as a record,
not bounced to review.

`record_id` is `SW-PRINTAKE-<12 hex>`. `final_status` is one of `routed_spiderweb_pr`,
`dual_routed_spiderweb_primary`, or `dual_routed_contract_primary` (spiderweb-pr as the
derivative repo).

## Consumer (spiderweb-pr)

`readiness/pr_intake_import.py` → `PRIntakeImport(input_dir, output_dir).run()`:

1. Reads `spiderweb_pr_derivatives.csv` from the dropzone.
2. Validates each row against `schemas/pr_intake_derivative.schema.json` (Draft-07,
   `jsonschema>=4.17`), then `json.loads` the `domains` / `output_tables` arrays.
3. Routes invalid rows to `pr_intake_review_queue.csv` and continues — **zero-loss**:
   `records_valid + parse_errors == records_loaded`.
4. Emits a normalized intel-record layer:
   - `pr_intake_records.json` — all imported records (provenance preserved).
   - `pr_intake_records.geojson` — features only for records carrying coordinates (see below).
   - `pr_intake_import_manifest.json` — counts + zero-loss flag, conforming to the
     `spiderweb_intake_manifest.schema.json` shape.

## Known limitation: no coordinates in the derivative

The router enforces that a spatial raw item carries a location (`_validate_result`'s spatial
gate), but `_build_derivative` does **not** propagate `latitude`/`longitude`/`geometry`/
`municipality` into the derivative payload. So imported records are **non-spatial by
default** and `pr_intake_records.geojson` is typically an empty FeatureCollection.

The importer is forward-compatible: if a row carries optional `latitude`/`longitude`
columns it is emitted as a GeoJSON point. **Recommended follow-up (producer side):** add the
validated location fields to `_build_derivative` so spiderweb-pr can place these records on a
map without re-fetching the source.

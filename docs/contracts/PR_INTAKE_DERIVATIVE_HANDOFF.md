# PR Intake Derivative Handoff (Contract-Sweeper → spiderweb-pr)

The PR intake router federates Puerto Rico raw-intake items across the pair
**Contract-Sweeper** (`primary_repo`) and **spiderweb-pr** (`paired_repo`). Items in the
spatial / GIS / infrastructure / aviation / maritime / environment / science domains are
emitted to the spiderweb-pr lane. This document is the **producer-boundary contract** (the
on-disk CSV); the canonical spec for how spiderweb-pr normalizes it is
[`docs/pr_intake_router_spiderweb_lane.md`](../pr_intake_router_spiderweb_lane.md).

## Producer (Contract-Sweeper)

`scripts/route_pr_intake.py` (a.k.a. `run_pr_intake_router.py`) classifies raw items via
`shared/pr_intake_router.py` and writes `spiderweb_pr_derivatives.csv` — one row per item
routed to (or dual-routed with a derivative in) spiderweb-pr.

## Transport: dropzone

The consumer reads a configurable dropzone, default
`spiderweb-pr/data/intake/pr_intake/spiderweb_pr_derivatives.csv`; Contract-Sweeper (or an
operator) copies the router's `data/exports/pr_intake_router/spiderweb_pr_derivatives.csv`
there. (Alternative: point the builder `--input` at the producer's export dir directly.)

## On-disk CSV shape (the input contract)

The producer's `csv.DictWriter` (`flatten_for_csv` + `write_csv`) means:
- every value is a string; SQL/JSON nulls are written as **empty strings**;
- `domains` and `output_tables` are **JSON-encoded array strings**;
- column order is **alphabetized** — read by header name.

Validated by `schemas/pr_intake_derivative.schema.json`. Required: `record_id`,
`source_item_id`, `target_repo` (= `spiderweb-pr`), `final_status`, `domains`, `title`,
`source_url` (presence; `title`/`source_url` may be empty — the producer does not guarantee
content). `record_id` is `SW-PRINTAKE-<12 hex>`.

## Consumer (spiderweb-pr)

`readiness/spiderweb_spatial_lane.py` → `build_spiderweb_spatial_lane(input_dir, out_dir=None)`
(CLI: `scripts/build_spiderweb_spatial_lane.py`; registered as the `spiderweb_spatial_lane`
layer in `federation/hub/layer_registry.py`). It validates each row against the input schema,
normalizes it to the **34 fields** of the lane spec (validated by
`schemas/spiderweb_spatial_lane_record.schema.json`), and routes it by primary domain into the
spec's tables under `data/normalized/`, with candidate geojsons under `data/exports/`, review
queues under `data/review/`, a daily report, and `spiderweb_spatial_lane_report.json`. It is
**zero-loss**: every input row lands in exactly one normalized table or the discrepancy queue.

## Known limitation: thin derivative (producer enrichment held)

`shared/pr_intake_router.py:_build_derivative` does **not** yet carry
geometry / location / asset / dataset / agency fields. So those normalized fields are emitted
empty, every coordinate-less record is marked `manual_geocode_required = true` and listed in
`data/review/geocode_queue.csv`, and the candidate geojsons stay empty. Routing, the
Contract-Sweeper backlink (`related_contract_sweeper_record_id`), `topic_domain`,
`spiderweb_layer_class`, tier, and provenance populate now.

**Recommended follow-up (Contract-Sweeper, on hold):** enrich `_build_derivative` with the
validated `latitude`/`longitude`/`location_text`/`municipality_name`/`asset_type`/
`dataset_type`/`file_format`/`agency_entity` fields so the lane can place records on a map and
populate the full normalized record without consumer changes.

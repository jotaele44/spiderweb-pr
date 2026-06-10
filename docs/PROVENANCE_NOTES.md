# Provenance Notes

Some artifacts in this repo retain **FlightRadar24 (FR24)** provenance strings even though
the FR24 screenshot-processing pipeline itself migrated to
[`skywatcher-pr`](https://github.com/jotaele44/skywatcher-pr). They are kept as historical
/ synthetic test material, **not** live operational feeds.

## Where FR24 provenance remains
- **`exports/samples/*.jsonl`** — the federation export sample package
  (`airspace_events`, `observations`, `tracks`, `sources` + `manifest.sample.json`).
  Every record carries a `lineage` array referencing `fr24_screenshot_inventory`,
  `ensemble_ocr`, `geo_calibration`, etc., and `source_id` values prefixed `src_fr24_*`.
- **`docs/RLSM_OPERATIONAL_ONTOLOGY_V0_1.md`** — architectural/ontology context that
  references FR24 OCR normalization. Historical design doc, not executable.

## Status: synthetic, not a live feed
- Every fixture record is `"is_synthetic": true`; `manifest.sample.json` is `mode=test`.
- The repo's `federation.json` is `production_status: NON_PRODUCTION_DIAGNOSTIC`.
- These fixtures exercise the **producer export contract**; they are not FR24-derived
  operational data.

## Do NOT edit the fixtures to "scrub" FR24 strings
Record `id` fields are **content-addressed** (deterministic hashes of record content), and
`manifest.sample.json` pins each stream's `sha256`. Editing any field (including lineage
actor names or `source_id`) changes the record hash and the manifest digest, cascading
into test/validation failures. Preserve hash stability — keep the historical provenance as
written and rely on this note plus the `synthetic`/`NON_PRODUCTION` flags for context.

To regenerate fixtures with non-FR24 provenance, rebuild them from a current source through
`scripts/federation_export.py` rather than hand-editing — the ids will recompute coherently.

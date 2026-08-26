# FR24 Screenshot Processing → Skywatcher (migration note)

As of 2026-07-20, **all FlightRadar24 screenshot-processing capability lives in
`skywatcher-pr`**. SpiderWeb no longer ingests screenshots, runs OCR, or owns the
screenshot flight database.

## What changed here
- Removed the FR24 screenshot pipeline (former `run_all.py` phases 0-1,
  `pipeline/flight_analyzer.py`, `pipeline/hardened_pipeline.py`, and the
  `scripts/ocr_*.py` runners). See `SPIDERWEB_REMOVAL_LEDGER.md`.
- SpiderWeb now runs **downstream phases 2-4 only** (GIS, mission, operational).

## How flight data enters SpiderWeb now
Via the retained, schema-validated bridge — the only FR24 integration boundary
SpiderWeb keeps:

```bash
# Skywatcher produces a hub-canonical package:
#   (in skywatcher-pr)  python run_all.py --export-spiderweb DIR
# SpiderWeb consumes it:
python run_all.py --ingest-skywatcher DIR
```

`--ingest-skywatcher` validates every record in `DIR/bridge_records.jsonl`
against `schemas/spiderweb_bridge.schema.json` and routes valid records into
`flights` / `track_points` for downstream correlation. Invalid records and any
record carrying a terminal-accept label (e.g. `confirmed`) are rejected.

See `docs/ADR_SKYWATCHER_SPIDERWEB_INTEGRATION.md` (skywatcher-pr) and
`integration/skywatcher_bridge.py`.

# FR24 Executable Retirement Ledger

Status: **PASS** for the bounded Spiderweb executable-removal scope.

## Removed active code

| Path | Disposition |
|---|---|
| `pipeline/flight_analyzer.py` | Removed. It owned screenshot OCR, approximate map projection, and the screenshot/flight database builder. |
| `pipeline/hardened_pipeline.py` | Removed. It orchestrated OCR through an already-absent `pipeline.ensemble_ocr` dependency. |
| `scripts/ocr_checkpoint.py` | Removed. Screenshot batch runner. |
| `scripts/ocr_full.py` | Removed. Screenshot batch runner. |
| `scripts/ocr_parallel.py` | Removed. Screenshot batch runner. |
| `run_all.py` phases 0-1 and screenshot/RLSM/home-base flags | Removed. Several flags targeted modules that no longer existed. |
| `run_all.py --export-json` | Removed. Its standalone flight dashboard was retired in the earlier boundary migration. |
| `server/backend/main.py` `images` request field | Removed and forbidden at validation time. |
| `integration/skywatcher_bridge.py` | Removed. It consumed a producer-specific package before TheHub had admitted an equivalent canonical stream. |
| `schemas/spiderweb_bridge.schema.json` | Removed with the premature direct consumer; it was not a Hub canonical-stream contract. |
| `tests/test_ingest_skywatcher.py` | Removed with the implementation it exercised. The boundary suite now asserts that the direct consumer stays absent. |

The deleted implementations remain recoverable from Git history. No source data,
runtime database, or generated artifact is deleted by this change.

## Retained deliberately

| Path | Reason |
|---|---|
| `pipeline/geo_anchors.py` | Evidence-bounded homography fitting is generic spatial logic. It does not read screenshots, detect aircraft icons, or fall back to approximate Puerto Rico bounds. |
| `pipeline/hardening_layer.py` | Shared temporal/provenance validation used by retained adapters. |
| `pipeline/{aircraft_intelligence,gis_intelligence,mission_inference,operational_intelligence}.py` | Downstream analysis over an already validated database; no screenshot ingestion. |
| `integration/{ilap_airspace_bridge,aasb_airspace_bridge}.py` | Spiderweb-owned spatial export adaptations and release gates. |
| historical schemas and synthetic contract fixtures | Inert compatibility/evidence material; their separate contract retirement requires schema-index and fixture adjudication. |

## Cross-repository consumer decision

The proposed `integration/skywatcher_bridge.py` and
`schemas/spiderweb_bridge.schema.json` are not included. Skywatcher's
`bridge_records.jsonl` package is producer-specific and is not one of TheHub's
admitted canonical streams. The thin consumer remains **BLOCKED** until all
gates in `ADR_SKYWATCHER_SPIDERWEB_INTEGRATION.md` pass.

The merged migration note, removal ledger, and static zero-hit receipt that
described the direct bridge were superseded by this ledger and the executable
regression gates below. They are removed so historical prose cannot be mistaken
for a currently supported integration contract.

## Regression gates

```bash
python -m pytest tests/test_fr24_boundary.py tests/test_geo_anchors.py tests/test_maintenance.py -q
python run_all.py --phase 1        # must fail argument validation
python run_all.py --images 1       # must fail argument validation
python run_all.py --db missing.db  # must fail without creating missing.db
```

The full repository test, lint, lock, install, and release gates remain required
before merge; this ledger is not a substitute for exact-head certification.

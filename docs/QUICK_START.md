# Quick Start (T5-48)

A 1-page on-ramp for operators new to the spiderweb-pr pipeline. For deeper docs see [`RELEASE_READINESS.md`](RELEASE_READINESS.md), [`GIS_EXPORT_GUIDE.md`](GIS_EXPORT_GUIDE.md), [`SPIDERWEB_LANGUAGE_BRIDGE.md`](SPIDERWEB_LANGUAGE_BRIDGE.md), [`SCHEMA_AND_EXPORT_CONTRACTS.md`](SCHEMA_AND_EXPORT_CONTRACTS.md), [`ROI_TASK_LEDGER.md`](ROI_TASK_LEDGER.md), and [`NEXT_100_TASKS.md`](NEXT_100_TASKS.md).

## What this repo produces

A Puerto Rico Airspace Intelligence System (PRIIS) that turns FR24 flight screenshots + supporting reference data into:

- **PR Intel exports** — flight events, aircraft profiles, track points, screenshot evidence, mission inferences, anomaly index, GIS overlays. Lives under `<output-dir>/`.
- **Spiderweb overlay** — POI / ILAP / corridor / AASB-edge candidates fused into a single GeoJSON layer with MBIL classifications + evidence tiers. Lives at `<output-dir>/spiderweb_overlay_candidates.geojson`.
- **Release report** — single PASS/FAIL umbrella aggregating syntax + tests + validate + 2 exports + EarthGPT self-test. Lives at `<release-output-dir>/release_report.json`.

> The RLSM screenshot pipeline that previously appeared here migrated to skywatcher-pr — see below.

## Five commands an operator runs most days

```
# 1. Run the full release gate against your DB
python3 run_all.py --db ~/flight_database.db --release-check --release-output-dir /tmp/release

# 2. Check the result without re-running
python3 -c "import json; print(json.load(open('/tmp/release/release_report.json'))['overall_status'])"

# 3. Run the test suite locally (skip GEBCO tests — they need a separate dataset)
python3 -m pytest tests/ -q --ignore=tests/test_io.py --ignore=tests/test_terrain.py

# 4. Spiderweb intake — fuse all candidate layers into the overlay
python3 run_all.py --db ~/flight_database.db --export-spiderweb /tmp/spiderweb

# 5. PR Intel adapter — write the 8 PR Intel artifacts + GeoJSON exports
python3 run_all.py --db ~/flight_database.db --export-pr-intel /tmp/pr_intel
```

## RLSM screenshot pipeline — migrated

The OCR + unlabeled-vision RLSM passes (`fr24.rlsm_*`) **migrated to
[skywatcher-pr](https://github.com/jotaele44/skywatcher-pr)** in 2026-06 (PRs
#110/#111) and no longer live in this repo. Run that pipeline from skywatcher-pr.

## Where things live

| You want… | Look here |
|---|---|
| The release-gate runbook | [`RELEASE_READINESS.md`](RELEASE_READINESS.md) |
| QGIS / Google Earth import instructions | [`GIS_EXPORT_GUIDE.md`](GIS_EXPORT_GUIDE.md) |
| MBIL / evidence-tier / Spiderweb vocabulary | [`SPIDERWEB_LANGUAGE_BRIDGE.md`](SPIDERWEB_LANGUAGE_BRIDGE.md) |
| Per-artifact schema + provenance contract | [`SCHEMA_AND_EXPORT_CONTRACTS.md`](SCHEMA_AND_EXPORT_CONTRACTS.md) |
| Status of every release-readiness task | [`ROI_TASK_LEDGER.md`](ROI_TASK_LEDGER.md) |
| What's still outstanding | [`NEXT_100_TASKS.md`](NEXT_100_TASKS.md) |
| RLSM screenshot pipeline + runbook (migrated) | [skywatcher-pr](https://github.com/jotaele44/skywatcher-pr) |
| FAA registry ingestion | [`FAA_REGISTRY_PIPELINE.md`](FAA_REGISTRY_PIPELINE.md) |

## Three things that trip up new operators

1. **`data/*` is gitignored.** The large screenshot baseline + SQLite DBs live on disk only; check `.gitignore` if you're confused about what's tracked. (The former `data/rlsm/` schema + handoff migrated to skywatcher-pr.)
2. **Strict / demo / normal modes:** `--strict-production` raises on missing inputs; `--demo` labels manifests `mode: "demo"` and prefixes banners; default is `normal`. See [D2 in the plan](#) for details.
3. **MBIL alone cannot escalate to T1/T2.** A candidate with high `mbil_class` but no hydro / utility / corridor_id corroboration stays at T4 by design (T3-27 guardrail). See [`SPIDERWEB_LANGUAGE_BRIDGE.md`](SPIDERWEB_LANGUAGE_BRIDGE.md).

## When something fails

- `release_report.json["overall_status"] == "FAIL"` → look at `failure_reasons` first, then `<stage>.status` per section.
- Schema validation errors → read `<output-dir>/schema_validation.review_queue.csv` (enriched 9-column format: `routed_at`, `record_id`, `source_file`, `schema_name`, `field`, `error_type`, `error_message`, `record_json`, `suggested_fix`).
- Anything else → reproduce locally with the 5 commands above and bisect.

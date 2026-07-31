# Repo Boundary — spiderweb-pr

spiderweb-pr is the **spatial / operational PRODUCER** node of the PRII federation. This
document fixes what the repo owns and what it deliberately does not, so the boundary
doesn't drift back into split authority with the hub.

## This repo owns
- The spatial/operational **analysis pipeline** (`pipeline/`), GIS correlation,
  mission inference, anomaly detection, and the integration/export surfaces
  (`integration/`, `schemas/`). This includes spiderweb's **own** ILAP/AASB airspace
  bridges (`integration/{ilap,aasb}_airspace_bridge.py`), which are the producer flavor
  driving phase-2 / `release_check` export. They are a per-repo adaptation that shares an
  ancestor with — but is **not** interchangeable with — skywatcher-pr's airspace copies;
  the ownership split is recorded in `docs/DUPLICATION_REGISTER.md`.
- The **federation producer**: `federation/export_writer.py` + `federation/envelope.py`
  emit a validated evidence envelope; `scripts/federation_export.py` projects it to the
  Hub's canonical `{entities, sources, relationships}` (geometry carried on entities).
  Validated by `scripts/validate_export.py`; declared in `federation.json`.

## Retired airspace surface (2026-07-29)
The FR24/RLSM **ingestion** subsystem migrated to skywatcher-pr in 2026-06, but
remnants stayed behind and kept this repo looking like an airspace product. They
are now retired to `docs/legacy/`:

| Retired | Was |
|---|---|
| `server_ingestion/{registration_alerts,reconcile_registrations}.py` | aircraft registration watchlist + FR24 CSV reconcile |
| `scripts/parse_adsb_archive.py` | ADS-B archive → `events` + `track_points` |
| `ingest_data.ingest_fr24_csv` / `ingest_track_points` | read `outputs/fr24_selected_export.csv`, a file **no code here produced** |
| `migrations.ensure_{events_aircraft_columns,alerts_registration_column,track_points_table}` | aircraft-detail columns, ADS-B track table |
| `GET /events/{flight_id}/track` + `/events` aircraft columns | per-point flight track playback |
| `pipeline/rlsm_ontology_gate.py`, `scripts/rlsm_unlabeled.py`, `configs/rlsm_operational_ontology.yaml`, `schemas/rlsm_*.json` | RLSM route-line-segment mining (skywatcher owns RLSM) |
| `dashboard/` (whole viewer) + `scripts/{export_static_dashboard,gen_snapshot}.py` | Aircraft Catalog / Flight Log / **FR24 Review Queue** tabs |

`/events` survives as a **generic** spatial/operational event stream (contract,
imagery, report, outage, permit, field). It no longer carries aircraft fields.

**The old FR24 handoff was broken on both ends** and is not being rebuilt here:
skywatcher's documented adapter (`fr24/spiderweb_adapter.py` →
`fr24_spiderweb_intake_candidates.jsonl`) had no consumer in this repo, while the
live path read a CSV nothing here produced — a bespoke connector of exactly the
kind `docs/ADR_SKYWATCHER_SPIDERWEB_INTEGRATION.md` rejects. Any future intake
must follow that ADR's canonical-package route, after its four preconditions.

`maintenance/adapters/local.py::check_migration_remnants` now covers the
dashboard, `server/ingestion/`, `scripts/*adsb*` and the RLSM schemas/configs, so
this drift fails a maintenance audit instead of accumulating silently.

## This repo does NOT own
- **Federation orchestration** (producer discovery, conformance validation, cross-domain
  aggregation) — that is the parent hub, [`thehub-pr`](https://github.com/jotaele44/thehub-pr).
- **Cross-producer correlation** — owned by `thehub-pr` (aggregate graph) and the
  downstream **PRIIS** consumer (lead scoring). spiderweb emits its package and stops there.

Any future federation/consumer code added here must be a thin client of the canonical
control plane, not a second copy of it.

## Retired in-repo query-hub (2026-06-10)
spiderweb previously ran a local query-hub that ingested other producers' packages and
correlated them itself — a duplication of `thehub-pr` + PRIIS. It is **retired to
`docs/legacy/`** (non-executable design history), making this repo producer-only.

The four retired correlation strategies (now owned upstream): **temporal**,
**normalized-entity**, **spatial-haversine**, **external-id**.

Moved under `docs/legacy/`:
- `docs/legacy/federation/hub/**` (query, index, package_loader, normalize, layer_registry, adapters/moneysweep)
- `docs/legacy/readiness/{spiderweb_spatial_lane,moneysweep_package_gate}.py`
- `docs/legacy/scripts/{build_spiderweb_spatial_lane,ingest_moneysweep_package,federation_conformance_check,assess_moneysweep_package}.py`
- `docs/legacy/tests/**` (7 consumer tests + `test_federation_hardening_hub_xid.py`)

The `.github/workflows/intake-normalize.yml` workflow was deleted. **Cross-repo
consequence:** that workflow fired when moneysweep-pr's `intake-delivery` workflow
pushed `data/intake/pr_intake/spiderweb_pr_derivatives.csv`, normalizing it via the
spatial-lane builder. With it gone, delivered derivatives are **no longer auto-normalized
here, with no signal back to the sender.** This is a deliberate behavioral change of the
producer-only pivot, but it touches a sibling repo — see the precondition reminder.

### Retired consumer-flow docs/schema (resolved)
The docs/schema that described the retired consumer flow were relocated or annotated:
- `docs/legacy/contracts/PR_INTAKE_DERIVATIVE_HANDOFF.md` (relocated)
- `docs/legacy/contracts/CONTRACT_FINANCE_CONNECTIVITY_HEALTH.md` (relocated)
- `docs/legacy/schemas/spiderweb_spatial_lane_record.schema.json` (relocated; schema count 41, still ≥11)
- `docs/CONTRACT_FINANCE_PRODUCTION_FUSION_RECIPE.md` (deprecation banner + legacy paths)
- `data/intake/pr_intake/README.md` (deprecation banner)

## Co-resident standalone subsystems (kept by decision)
`earthgpt/` (satellite anomaly), `gebco/` (bathymetry), and `llm/` (UAP RAG) are
independent projects co-resident in this repo. They are **not** part of the federation
producer path (zero federation imports) but are retained here by decision (they are wired
into CI: `earthgpt` selftest gate, dedicated `test-gebco` job, `llm` subprocess from the
FastAPI server). Relocating them is a separate, out-of-scope effort.

## Cross-repo resolutions
1. **Resolved** — the four cross-producer correlation strategies (temporal /
   normalized-entity / spatial-haversine / external-id) were **re-homed into thehub-pr**
   (`src/hub/correlate.py` + the `hub correlate` step; merged thehub-pr #10). The central
   aggregator now owns cross-producer correlation, where it sees all producers; PRIIS's
   record↔infrastructure linking is unchanged. An earlier read confirmed neither the hub
   nor PRIIS covered these before, so this closed a real gap rather than a duplication.
2. **Resolved** — the moneysweep-pr → spiderweb delivery sender was retired
   (moneysweep-pr #250: removed the cross-repo delivery step + `deliver_derivatives.py`).
   The normalizer itself is preserved at `docs/legacy/scripts/build_spiderweb_spatial_lane.py`
   should the spatial lane ever be re-homed.

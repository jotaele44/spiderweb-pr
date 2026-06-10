# Repo Boundary — spiderweb-pr

spiderweb-pr is the **spatial / operational PRODUCER** node of the PRII federation. This
document fixes what the repo owns and what it deliberately does not, so the boundary
doesn't drift back into split authority with the hub.

## This repo owns
- The spatial/operational **flight-analysis pipeline** (`pipeline/`), GIS correlation,
  mission inference, anomaly detection, and the integration/export surfaces
  (`integration/`, `schemas/`).
- The **federation producer**: `federation/export_writer.py` + `federation/envelope.py`
  emit a validated evidence envelope; `scripts/federation_export.py` projects it to the
  Hub's canonical `{entities, sources, relationships}` (geometry carried on entities).
  Validated by `scripts/validate_export.py`; declared in `federation.json`.

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
- `docs/legacy/federation/hub/**` (query, index, package_loader, normalize, layer_registry, adapters/contract_sweeper)
- `docs/legacy/readiness/{spiderweb_spatial_lane,contract_sweeper_package_gate}.py`
- `docs/legacy/scripts/{build_spiderweb_spatial_lane,ingest_contract_sweeper_package,federation_conformance_check,assess_contract_sweeper_package}.py`
- `docs/legacy/tests/**` (7 consumer tests + `test_federation_hardening_hub_xid.py`)

The `.github/workflows/intake-normalize.yml` workflow was deleted. **Cross-repo
consequence:** that workflow fired when Contract-Sweeper's `intake-delivery` workflow
pushed `data/intake/pr_intake/spiderweb_pr_derivatives.csv`, normalizing it via the
spatial-lane builder. With it gone, delivered derivatives are **no longer auto-normalized
here, with no signal back to the sender.** This is a deliberate behavioral change of the
producer-only pivot, but it touches a sibling repo — see the precondition reminder.

### Known stale references (follow-up, non-blocking)
These docs/schema still describe the retired consumer flow and reference the moved scripts
by their old `scripts/` paths. They do not affect CI; relocate or annotate them in a
follow-up:
- `docs/contracts/PR_INTAKE_DERIVATIVE_HANDOFF.md`
- `docs/CONTRACT_FINANCE_PRODUCTION_FUSION_RECIPE.md`
- `docs/contracts/CONTRACT_FINANCE_CONNECTIVITY_HEALTH.md`
- `data/intake/pr_intake/README.md`
- `schemas/spiderweb_spatial_lane_record.schema.json` (left in place; still counted by `make validate-schemas`)

## Co-resident standalone subsystems (kept by decision)
`earthgpt/` (satellite anomaly), `gebco/` (bathymetry), and `llm/` (UAP RAG) are
independent projects co-resident in this repo. They are **not** part of the federation
producer path (zero federation imports) but are retained here by decision (they are wired
into CI: `earthgpt` selftest gate, dedicated `test-gebco` job, `llm` subprocess from the
FastAPI server). Relocating them is a separate, out-of-scope effort.

## Precondition reminders (cross-repo — confirm before merge)
1. Retiring the in-repo correlators assumes `thehub-pr` + PRIIS cover the four strategies
   (or intentionally drop them). Confirm upstream coverage before relying on this boundary
   in production.
2. The deleted `intake-normalize.yml` severed the Contract-Sweeper → spiderweb intake-
   delivery contract (`spiderweb_pr_derivatives.csv`). Either retire the sender side in
   Contract-Sweeper, or re-home the normalization (it now lives at
   `docs/legacy/scripts/build_spiderweb_spatial_lane.py`) wherever the spatial lane should
   be owned. Until then, delivered derivatives are silently un-normalized.

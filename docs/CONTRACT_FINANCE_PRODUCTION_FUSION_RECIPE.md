# Contract-Finance Production Fusion Recipe

> **⚠️ Deprecated (2026-06): retired consumer flow.** spiderweb-pr is now a
> producer-only federation node. The consumer/query-hub steps this runbook
> describes (`ingest_moneysweep_package`, `assess_moneysweep_package`,
> `federation_conformance_check`, and the query-hub) were retired — the scripts
> named below now live under `docs/legacy/scripts/` and the hub under
> `docs/legacy/federation/hub/`. Cross-producer correlation moved to thehub-pr.
> Kept as historical reference; see `docs/REPO_BOUNDARY.md`.

This runbook describes the production handoff from moneysweep-pr into
SpiderWeb PR.

The intended boundary is file-based:

```text
moneysweep-pr export package -> SpiderWeb package gate -> adapter outputs -> manifest-gated scoring layer -> calibration -> optional fusion -> dashboard
```

SpiderWeb must not import moneysweep-pr code. moneysweep-pr remains the
independent producer. SpiderWeb consumes validated package artifacts from disk.

## Required moneysweep-pr package files

A production handoff package must contain:

```text
manifest.json
artifact_manifest.json
entities.jsonl
sources.jsonl
funding_awards.jsonl
transactions.jsonl
relationships.jsonl
```

`artifact_manifest.json` is required for production auditability even though the
adapter can technically parse the five JSONL streams without it.

## Step 0 — Generate package in moneysweep-pr

From the moneysweep-pr repo, prepare uploaded masters if needed:

```bash
python scripts/prepare_uploaded_masters.py \
  --contracts-master /path/to/pr_contracts_master_v2.csv \
  --awards-master /path/to/pr_all_awards_master.csv \
  --lda-summary /path/to/lda_canonical_client_summary_all.csv \
  --output-dir data/staging/processed_uploaded_masters
```

Then generate the v1.1 package:

```bash
python scripts/run_export.py \
  --processed-dir data/staging/processed_uploaded_masters \
  --output-dir exports/moneysweep_uploaded_masters_v1_1 \
  --mode production
```

Then write the shared artifact manifest:

```bash
python scripts/write_artifact_manifest.py \
  --package-dir exports/moneysweep_uploaded_masters_v1_1 \
  --source-file /path/to/pr_contracts_master_v2.csv \
  --source-file /path/to/pr_all_awards_master.csv \
  --source-file /path/to/lda_canonical_client_summary_all.csv
```

Copy the resulting package directory into SpiderWeb, for example:

```text
data/incoming/moneysweep/latest/
```

## Step 1 — Run SpiderWeb consumer-boundary package gate

```bash
python scripts/assess_moneysweep_package.py \
  --package data/incoming/moneysweep/latest \
  --out outputs/contract_finance/moneysweep_package_gate_report.json
```

Expected statuses:

| Status | Meaning | Production posture |
|---|---|---|
| `READY` | No blockers or warnings | Full production pass allowed |
| `DEGRADED` | No blockers, but one or more warnings | Allowed with documented limitation |
| `NOT_READY` | One or more blockers | Stop pipeline |

For the first uploaded-master production pass, `DEGRADED` is acceptable when the
only warning is low point-geometry coverage. The layer is then municipality/entity
density intelligence, not point-confirmed spatial evidence.

## Step 2 — Convert moneysweep-pr package into SpiderWeb artifacts

```bash
python scripts/ingest_moneysweep_package.py \
  --package data/incoming/moneysweep/latest \
  --out outputs/contract_finance \
  --mode production
```

Expected outputs:

```text
outputs/contract_finance/contract_awards.geojson
outputs/contract_finance/financial_flows.geojson
outputs/contract_finance/municipality_funding_density.csv
outputs/contract_finance/entity_graph.graphml
outputs/contract_finance/contract_finance_ingest_report.json
```

## Step 3 — Build the scored Contract-Finance layer

Production builds must pass the moneysweep-pr artifact manifest gate before
scoring starts. The layer builder refuses unsafe manifests before writing the
scored overlay.

```bash
python scripts/build_contract_finance_layer.py \
  --input outputs/contract_finance \
  --out outputs/contract_finance \
  --artifact-manifest data/incoming/moneysweep/latest/artifact_manifest.json
```

Expected outputs:

```text
outputs/contract_finance/contract_finance_scored_overlay.geojson
outputs/contract_finance/contract_finance_layer_report.json
```

The layer report includes an `artifact_manifest_gate` block when the manifest
argument is supplied. Required posture is `artifact_manifest_gate.status=READY`.

## Step 4 — Calibrate the Contract-Finance layer

```bash
python scripts/calibrate_contract_finance_layer.py \
  --input outputs/contract_finance
```

Expected output:

```text
outputs/contract_finance/contract_finance_calibration_report.json
```

Calibration must be reviewed before fusion. Key checks:

| Check | Action |
|---|---|
| low point geometry | keep municipality/entity-density posture |
| low municipality coverage | stop or rerun with better geography |
| low lineage coverage | stop production fusion |
| extreme amount skew | inspect top records before score fusion |

## Step 5 — Optional fusion with airspace / ILAP overlay

Fusion requires an existing SpiderWeb overlay:

```text
outputs/spiderweb_overlay_candidates.geojson
```

Run:

```bash
python scripts/fuse_contract_finance_scores.py \
  --airspace-overlay outputs/spiderweb_overlay_candidates.geojson \
  --contract-finance-overlay outputs/contract_finance/contract_finance_scored_overlay.geojson \
  --out outputs/contract_finance
```

Expected outputs:

```text
outputs/contract_finance/spiderweb_fused_contract_finance_overlay.geojson
outputs/contract_finance/contract_finance_fusion_report.json
```

Fusion is conservative. It boosts existing airspace/ILAP candidates only when
there is a point-proximity match or municipality-key match. It does not create
new ILAP candidates by itself.

## Step 6 — Dashboard visibility

The dashboard automatically attempts to load:

```text
../outputs/contract_finance_layer_report.json
../outputs/contract_finance_scored_overlay.geojson
```

If these files are present beside the standard dashboard outputs, the optional
Contract-Finance panel appears. Missing files degrade gracefully.

For the current output layout, copy or symlink from `outputs/contract_finance/` to
`outputs/` if serving the existing dashboard without changing paths:

```bash
cp outputs/contract_finance/contract_finance_layer_report.json outputs/
cp outputs/contract_finance/contract_finance_scored_overlay.geojson outputs/
```

## Production readiness checklist

| Gate | Required posture |
|---|---|
| moneysweep-pr package validates in production mode | Required |
| `artifact_manifest.json` present | Required |
| package gate status | `READY` or documented `DEGRADED` |
| artifact manifest gate | `READY` before scoring |
| scored overlay generated | Required |
| calibration report generated | Required |
| fusion report generated | Required only when overlay exists |
| dashboard files present | Required only for analyst UI |

## Evidence posture

If point geometry coverage is low or zero, use the following language:

```text
Contract-Finance layer is production-ready for municipality/entity-density scoring, not point-confirmed spatial scoring.
```

Do not describe municipality-only matches as site-confirmed or coordinate-confirmed.

# PR DEM Regional Expansion Controller

This workflow scores configured PR DEM regional batch profiles after review queues and follow-up packets exist.

Tool:

```text
tools/pr_dem_regional_expansion_controller.py
```

Default inputs:

```text
configs/pr_dem_batch_profiles.json
outputs/pr_dem_review_queues/queue_summary.json
outputs/pr_dem_follow_up_packets/follow_up_index.json
```

Default output directory:

```text
outputs/pr_dem_expansion_controller/
```

## Purpose

The controller is a decision-support stage. It does not run DEM processing. It ranks which configured regional profile should be considered next.

## Outputs

| Output | Purpose |
|---|---|
| `expansion_priority_matrix.csv` | Spreadsheet-friendly profile ranking |
| `expansion_priority_matrix.json` | Machine-readable ranking and input signals |
| `expansion_recommendation.md` | Human-readable recommendation |
| `updated_batch_profiles.proposed.json` | Proposed profile-status update file |
| `expansion_controller_manifest.json` | Input/output checksum manifest |

## Scoring inputs

The controller reads signals from:

| Source | Signal examples |
|---|---|
| Queue summary | escalated, retained, second-pass, insufficient-evidence, rejected, unreviewed counts |
| Packet index | packet count, queue counts, decisions, recommended next steps, context terms |
| Profile config | current profile status, priority, purpose, notes, bbox |

## Recommendation values

| Value | Meaning |
|---|---|
| `run_next` | Strongest next expansion candidate |
| `ready_after_review` | Plausible next batch after human matrix review |
| `hold_for_more_signal` | Keep queued but do not run yet |
| `defer` | Insufficient reviewed signal |
| `do_not_run` | Completed/rejected profile |

## Proposed profile statuses

| Proposed status | Meaning |
|---|---|
| `ready_next` | Recommended next profile |
| `queued_profile` | Still queued for later use |
| `deferred` | Hold until stronger reviewed signal exists |
| `completed` | Marked completed by `--completed-profile` |

The proposed JSON does **not** automatically replace:

```text
configs/pr_dem_batch_profiles.json
```

Review it manually before applying.

## Command block for later

Default run:

```bash
python tools/pr_dem_regional_expansion_controller.py \
  --profiles configs/pr_dem_batch_profiles.json \
  --queue-summary outputs/pr_dem_review_queues/queue_summary.json \
  --packet-index outputs/pr_dem_follow_up_packets/follow_up_index.json \
  --output-dir outputs/pr_dem_expansion_controller
```

Run while marking the current pilot profile as completed:

```bash
python tools/pr_dem_regional_expansion_controller.py \
  --profiles configs/pr_dem_batch_profiles.json \
  --queue-summary outputs/pr_dem_review_queues/queue_summary.json \
  --packet-index outputs/pr_dem_follow_up_packets/follow_up_index.json \
  --output-dir outputs/pr_dem_expansion_controller \
  --completed-profile arecibo_utuado
```

Inspect recommendation:

```bash
cat outputs/pr_dem_expansion_controller/expansion_recommendation.md
```

Inspect proposed profile updates:

```bash
cat outputs/pr_dem_expansion_controller/updated_batch_profiles.proposed.json
```

## Expansion controller gate

Do not use the controller result to start a new batch unless:

1. `queue_summary.json` exists from the decision router.
2. `follow_up_index.json` exists from packet generation.
3. `expansion_priority_matrix.csv` exists and is non-empty.
4. `expansion_recommendation.md` is reviewed manually.
5. The top profile's bbox and purpose are still appropriate.

## Guardrail

The controller ranks configured batch profiles for planning. It does not validate the underlying terrain candidates, does not perform GIS processing, and does not replace human review.

# PR DEM / ILAP Terrain Screening — End-to-End Process

This document keeps the full process in order so terminal commands can be run later in one controlled sequence.

## Phase 0 — Guardrails

Do not treat any candidate count, coordinate, score, queue, packet, or class as valid until the pipeline produces real local output files and the score-sum / review-lock / queue-routing gates pass.

The processing order is:

```text
Integrity audit
→ one-tile pilot
→ output existence check
→ score-sum check
→ top-row visual review
→ Arecibo/Utuado batch dry run
→ Arecibo/Utuado batch run
→ batch score-sum check
→ QGIS candidate review
→ manual review CSV completion
→ review CSV validation + lock
→ decision queue routing
→ QGIS queue review
→ follow-up packet generation
```

## Phase 1 — Local folder integrity audit

Goal: confirm `PR_Geodata/` is structurally safe before raster/vector processing.

Script:

```text
tools/pr_geodata_integrity_audit.py
```

Main output:

```text
outputs/pr_geodata_audit/PR_GEODATA_INTEGRITY_GO_NO_GO.md
```

Gate:

| Status | Action |
|---|---|
| `GO` | Continue |
| `CONDITIONAL_GO` | Continue only after warnings are understood |
| `NO_GO` | Stop and fix FAIL findings |

## Phase 2 — One-tile pilot

Goal: process exactly one DEM GeoTIFF and confirm the method produces real local files.

Script:

```text
tools/pr_dem_one_tile_pilot.py
```

Outputs:

```text
outputs/pr_dem_one_tile_pilot/pr_dem_one_tile_candidates.csv
outputs/pr_dem_one_tile_pilot/pr_dem_one_tile_candidates.geojson
outputs/pr_dem_one_tile_pilot/pr_dem_one_tile_manifest.json
```

The one-tile pilot is intentionally bounded. It reads one DEM tile, downsamples it, extracts flat terrain patches with steeper surrounding terrain, and writes component-score columns.

## Phase 3 — Score-sum sanity check

Goal: verify additive score integrity.

Script:

```text
tools/verify_ilap_score_sum.py
```

Required equation:

```text
ILAP_SCORE = score_flat_patch + score_edge_contrast + score_high_local_position
```

Main output:

```text
outputs/pr_dem_one_tile_pilot/score_sum_check.json
```

Gate:

| Result | Action |
|---|---|
| `PASS` | Continue |
| `FAIL` | Stop; scoring columns are inconsistent |

## Phase 4 — Top-row review

Goal: inspect the first candidate rows before scaling up.

Review fields:

| Field | Use |
|---|---|
| `candidate_id` | Stable candidate reference |
| `lon`, `lat` | QGIS point placement |
| `area_m2` | Size plausibility |
| `mean_slope_deg` | Internal flatness |
| `ring_mean_slope_deg` | Surrounding slope contrast |
| `ILAP_SCORE` | Prioritization only |
| `review_class` | Review bucket |

Gate:

Top candidates must make geographic sense in QGIS. If coordinates are null, use `x`, `y`, and `crs` instead of lon/lat.

## Phase 5 — Arecibo/Utuado batch dry run

Goal: select intersecting DEM tiles without processing them.

Script:

```text
tools/pr_dem_batch_runner.py
```

Default profile:

```text
arecibo_utuado
```

The profile is a broad operational bounding box, not a legal municipal boundary.

Dry-run output:

```text
outputs/pr_dem_batch_arecibo_utuado/selected_tiles.csv
outputs/pr_dem_batch_arecibo_utuado/batch_manifest.json
```

Gate:

Open `selected_tiles.csv` and confirm the selected tile count is reasonable before running the batch.

## Phase 6 — Arecibo/Utuado batch run

Goal: run the one-tile pilot across the selected batch and merge outputs.

Batch outputs:

```text
outputs/pr_dem_batch_arecibo_utuado/pr_dem_batch_candidates.csv
outputs/pr_dem_batch_arecibo_utuado/pr_dem_batch_candidates.geojson
outputs/pr_dem_batch_arecibo_utuado/batch_score_sum_check.json
outputs/pr_dem_batch_arecibo_utuado/batch_manifest.json
```

Gate:

The batch score-sum report must pass.

## Phase 7 — QGIS candidate review

Load these files:

```text
outputs/pr_dem_one_tile_pilot/pr_dem_one_tile_candidates.geojson
outputs/pr_dem_batch_arecibo_utuado/pr_dem_batch_candidates.geojson
```

Recommended QGIS symbolization:

| Layer | Styling |
|---|---|
| Candidate points | Graduated by `ILAP_SCORE` |
| Candidate labels | `candidate_id` |
| DEM hillshade | Background terrain context |
| Roads | Overlay for access context |
| Hydro / water assets | Overlay for infrastructure context |
| Karst / geology | Overlay for geomorphic context |

Manual review template:

```text
templates/pr_dem_candidate_manual_review_template.csv
```

QGIS review guide:

```text
docs/PR_DEM_QGIS_REVIEW_GUIDE.md
```

## Phase 8 — Review CSV validation and locked artifact output

Goal: validate manual review rows, merge review metadata into GeoJSON, and produce auditable locked artifacts.

Script:

```text
tools/pr_dem_review_lock.py
```

Outputs:

```text
outputs/pr_dem_review_lock/validation_report.json
outputs/pr_dem_review_lock/validation_findings.csv
outputs/pr_dem_review_lock/invalid_review_rows.csv
outputs/pr_dem_review_lock/reviewed_candidates.geojson
outputs/pr_dem_review_lock/review_summary.json
outputs/pr_dem_review_lock/review_summary.md
outputs/pr_dem_review_lock/locked_review_manifest.json
```

Gate:

| Condition | Required result |
|---|---|
| Review CSV validation | `PASS` |
| Reviewed GeoJSON | Exists and opens in QGIS |
| Lock manifest | Contains SHA-256 checksums |
| Review summary | Exists and is readable |

## Phase 9 — Decision queue routing

Goal: split reviewed candidates into management queues for follow-up.

Script:

```text
tools/pr_dem_review_decision_router.py
```

Outputs:

```text
outputs/pr_dem_review_queues/queue_escalated.geojson
outputs/pr_dem_review_queues/queue_retained.geojson
outputs/pr_dem_review_queues/queue_second_pass.geojson
outputs/pr_dem_review_queues/queue_insufficient_evidence.geojson
outputs/pr_dem_review_queues/queue_rejected.geojson
outputs/pr_dem_review_queues/queue_unreviewed.geojson
outputs/pr_dem_review_queues/queue_all_routed.geojson
outputs/pr_dem_review_queues/queue_summary.json
outputs/pr_dem_review_queues/queue_summary.md
outputs/pr_dem_review_queues/queue_manifest.json
```

QGIS queue guide:

```text
docs/PR_DEM_QGIS_QUEUE_STYLE_GUIDE.md
```

Gate:

Open queue layers in QGIS and confirm queue counts in `queue_summary.md` are plausible.

## Phase 10 — Follow-up packet generation

Goal: generate per-candidate follow-up packets for escalated and retained candidates.

Script:

```text
tools/pr_dem_follow_up_packet_generator.py
```

Context checklist:

```text
configs/pr_dem_follow_up_context_layers.json
```

Default inputs:

```text
outputs/pr_dem_review_queues/queue_escalated.geojson
outputs/pr_dem_review_queues/queue_retained.geojson
```

Outputs:

```text
outputs/pr_dem_follow_up_packets/briefs/*.md
outputs/pr_dem_follow_up_packets/follow_up_index.csv
outputs/pr_dem_follow_up_packets/follow_up_index.json
outputs/pr_dem_follow_up_packets/follow_up_packet_summary.md
outputs/pr_dem_follow_up_packets/follow_up_manifest.json
```

Gate:

| Condition | Required result |
|---|---|
| Packet index | Exists and is non-empty |
| Packet summary | Exists and is readable |
| Manifest | Contains input/output SHA-256 checksums |
| Briefs | At least one exists if selected queues contain candidates |
| Packet count | Matches expected escalated + retained count |

## Full terminal command block for later

Run this only when ready to execute locally:

```bash
pip install rasterio numpy scipy fiona pyogrio

python tools/pr_geodata_integrity_audit.py \
  --geodata-root "~/Documents/Data/PR_Geodata" \
  --repo-root "."

cat outputs/pr_geodata_audit/PR_GEODATA_INTEGRITY_GO_NO_GO.md

DEM_TILE=$(find ~/Documents/Data/PR_Geodata/01_DEM_1m_LiDAR -type f \( -iname "*.tif" -o -iname "*.tiff" \) | head -n 1)
echo "$DEM_TILE"

python tools/pr_dem_one_tile_pilot.py \
  --dem-tile "$DEM_TILE" \
  --output-dir outputs/pr_dem_one_tile_pilot \
  --target-resolution-m 5

test -s outputs/pr_dem_one_tile_pilot/pr_dem_one_tile_candidates.csv && echo "CSV exists"
test -s outputs/pr_dem_one_tile_pilot/pr_dem_one_tile_candidates.geojson && echo "GeoJSON exists"
test -s outputs/pr_dem_one_tile_pilot/pr_dem_one_tile_manifest.json && echo "Manifest exists"

python tools/verify_ilap_score_sum.py \
  --csv outputs/pr_dem_one_tile_pilot/pr_dem_one_tile_candidates.csv \
  --output-json outputs/pr_dem_one_tile_pilot/score_sum_check.json

python - <<'PY'
import csv
p = 'outputs/pr_dem_one_tile_pilot/pr_dem_one_tile_candidates.csv'
with open(p, newline='', encoding='utf-8') as f:
    rows = list(csv.DictReader(f))
print('rows:', len(rows))
for r in rows[:10]:
    print(r['candidate_id'], r['ILAP_SCORE'], r['review_class'], r['lon'], r['lat'], r['area_m2'])
PY

python tools/pr_dem_batch_runner.py \
  --geodata-root "~/Documents/Data/PR_Geodata" \
  --repo-root "." \
  --profile arecibo_utuado \
  --output-dir outputs/pr_dem_batch_arecibo_utuado \
  --dry-run

cat outputs/pr_dem_batch_arecibo_utuado/selected_tiles.csv

python tools/pr_dem_batch_runner.py \
  --geodata-root "~/Documents/Data/PR_Geodata" \
  --repo-root "." \
  --profile arecibo_utuado \
  --output-dir outputs/pr_dem_batch_arecibo_utuado \
  --resume

cat outputs/pr_dem_batch_arecibo_utuado/batch_score_sum_check.json

python tools/pr_dem_review_lock.py \
  --candidate-geojson outputs/pr_dem_batch_arecibo_utuado/pr_dem_batch_candidates.geojson \
  --review-csv outputs/manual_review/pr_dem_candidate_review_completed.csv \
  --schema schemas/pr_dem_candidate_review.schema.json \
  --output-dir outputs/pr_dem_review_lock \
  --lock-dir outputs/pr_dem_review_lock/LOCKED

python tools/pr_dem_review_decision_router.py \
  --reviewed-geojson outputs/pr_dem_review_lock/reviewed_candidates.geojson \
  --output-dir outputs/pr_dem_review_queues

cat outputs/pr_dem_review_queues/queue_summary.md

python tools/pr_dem_follow_up_packet_generator.py \
  --queue-dir outputs/pr_dem_review_queues \
  --context-config configs/pr_dem_follow_up_context_layers.json \
  --output-dir outputs/pr_dem_follow_up_packets

cat outputs/pr_dem_follow_up_packets/follow_up_packet_summary.md
```

## Expansion rule

Only expand after the one-tile, Arecibo/Utuado batch, review-lock, queue-routing, and follow-up packet gates pass. The next expansion should be a named region batch, not full islandwide native-resolution processing.

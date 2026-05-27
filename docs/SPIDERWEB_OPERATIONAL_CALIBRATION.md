# Spiderweb Operational Calibration

## Purpose

This document describes the calibration workflow for the Spiderweb airspace overlay
pipeline. Calibration validates that `readiness/spiderweb_intake.py` scoring heuristics produce
sensible tier/MBIL/hydro/utility/terrain distributions when run against a real
operational database (≥15,000 screenshots).

**What is frozen while waiting for the real DB:**
- `integration/pr_intel_adapter.py`, `integration/schema_validation.py`, `integration/geo_calibration.py` — PRII modules, read-only
- `integration/ilap_airspace_bridge.py`, `integration/aasb_airspace_bridge.py` — producer boundary, read-only
- Raw FR24 image ingest path — frozen until fresh screenshot corpus is available

**What is active:**
- `readiness/spiderweb_intake.py` — scoring constants and heuristics
- `readiness/calibrate_scoring.py` — calibration driver and baseline comparison
- `run_all.py` — CLI surface (`--export-spiderweb`, `--spiderweb-intake`, `--calibrate-scoring`)

---

## Command Sequence

```bash
# 1. Export Spiderweb bridge files from a populated DB
python run_all.py --db /path/to/operational.db --export-spiderweb /path/to/sw_out

# 2. Run the Spiderweb intake (normalize + score + gap audit)
python run_all.py --spiderweb-intake /path/to/sw_out

# 3. Run the calibration driver (compare distributions to baseline ranges)
python run_all.py --calibrate-scoring /path/to/sw_out

# 4. Inspect the calibration report
python3 -c "
import json
r = json.load(open('/path/to/sw_out/calibration_report.json'))
print('status:', r['status'])
print('mode:  ', r['baseline_mode'])
print('count: ', r['candidate_count'])
for f in r['calibration_flags']:
    print(' FLAG:', f)
"
```

---

## Fixture vs Operational Mode

The calibration driver uses `candidate_count` to determine mode:

| Mode | Condition | T4/T1T2 checks | Status on flags |
|------|-----------|---------------|----------------|
| `fixture` | `candidate_count < 50` | suppressed | `WARN` |
| `operational` | `candidate_count >= 50` | active | `FAIL` |

The fixture DB (3 flights, 15 track points, 6 candidates) always produces `WARN` because
tier-skew checks (`pct_T4`, `pct_T1_or_T2`) are meaningless on <50 candidates.

A real operational DB (≥1,000 candidates) runs in `operational` mode — `FAIL` means a
scoring constant must be adjusted before merging.

---

## `calibration_report.json` Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `generated_at` | ISO timestamp | UTC time of report generation |
| `export_dir` | string | Path to the `--spiderweb-intake` output directory |
| `baseline_mode` | `"fixture"` \| `"operational"` | Determined by `candidate_count` |
| `status` | `"PASS"` \| `"WARN"` \| `"FAIL"` | Overall merge gate signal |
| `missing_inputs` | list of strings | Absent input files (overlay or gap audit) |
| `candidate_count` | int | Features in `spiderweb_overlay_candidates.geojson` |
| `tier_distribution` | `{T1, T2, T3, T4}` | Count per evidence tier |
| `mbil_distribution` | `{MBIL-0 … MBIL-3}` | Count per MBIL class |
| `signal_rates` | `{hydro_yes_pct, utility_yes_pct}` | Fraction of candidates with signal |
| `terrain_distribution` | `{urban, coastal, inland}` | Count per terrain context |
| `dedup_rate` | float 0–1 | Fraction of candidates removed by dedup |
| `calibration_flags` | list of flag objects | Metrics outside expected baseline ranges |

Each `calibration_flag` has:

```json
{
  "metric": "pct_mbil_0",
  "value": 0.22,
  "expected_max": 0.15,
  "action": "expand MUNICIPAL_CENTROIDS"
}
```

Flags are sorted alphabetically by `metric` for deterministic diffs.

---

## Calibration Flag Reference

| Metric | Operational range | If outside range: action |
|--------|------------------|--------------------------|
| `pct_T4` | 0.20 – 0.70 | Investigate tier thresholds |
| `pct_T1_or_T2` | 0.05 – 0.50 | If >0.50: check for tier inflation |
| `pct_mbil_0` | 0.00 – 0.15 | Expand `MUNICIPAL_CENTROIDS` in `readiness/spiderweb_intake.py` |
| `pct_hydro_yes` | 0.05 – 0.40 | Expand `HYDRO_LOCATIONS` |
| `pct_utility_yes` | 0.10 – 0.60 | Expand `UTILITY_CORRIDOR_WAYPOINTS` |
| `pct_urban_terrain` | 0.10 – 0.50 | Add urban bounding boxes to `_score_terrain` |
| `dedup_rate` | 0.00 – 0.30 | Tighten `DEDUP_THRESH_DEG` |

---

## Merge Gate

| Gate | Required |
|------|---------|
| `tests/test_spiderweb_intake.py` | 34 passing |
| Full test suite | no regressions |
| Fixture calibration status | `WARN` (not `FAIL`) |
| Operational synthetic all-T4 (50 candidates) | `FAIL` |
| CLI missing-dir | exits nonzero |
| CLI no-overlay-in-dir | exits nonzero with intake hint |
| PRII diff (`integration/pr_intel_adapter.py` etc.) | empty |
| Tracked `.db` / `.geojson` artifacts | none |

When running against the real operational DB, the merge gate additionally requires:
- `status = "PASS"` (zero calibration flags), **OR**
- all flagged metrics resolved by patching scoring constants in `readiness/spiderweb_intake.py`
  with no PRII diff introduced.

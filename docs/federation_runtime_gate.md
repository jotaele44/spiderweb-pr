# Federation runtime acceptance gate — spiderweb-pr

Runtime execution of the `07_SPIDERWEB` acceptance gate. The federation split-control audit
(`FEDERATION_7_PROGRAM_CURRENT_STATE_AUDIT_v1`) was a static GitHub-connector pass
(`runtime_executed = NO`); this records the native gate run performed locally on **2026-07-02**.

## Commands and results

| Step | Result |
|------|--------|
| `py_compile` sweep (repo `*.py`, excluding `.git`/`.claude`/`docs/legacy`) | OK |
| `pytest tests/ -q --ignore=tests/test_io.py --ignore=tests/test_terrain.py` | **884 passed / 34 skipped** (CI-representative) |
| `scripts/validate_export.py --package exports/samples --mode test` | OK |
| `release_check.py --db … --skip-tests --demo` | **overall PASS** (7/7 selftest) |

The spiderweb-owned suite and the export/release checks are green.

## Remaining blocker — production promotion

`ready_for_hub_live_execution` stays **false**. Only the synthetic sample package
(`exports/samples`) exists; `scripts/validate_export.py` rejects `is_synthetic: true` rows in
`--mode production`. Production promotion requires real (non-synthetic) spatial/operational
evidence-envelope rows from the retained producer pipeline, then a `--mode production` export.
No synthetic data was promoted to production to satisfy the gate. (Ref: P1-SPIDERWEB-NON-SYNTHETIC-ROWS.)

## Cross-repo handoff finding (no-cross-edit boundary)

`tests/test_spiderweb_spatial_lane.py::test_round_trip_zero_loss_across_the_seam` `pytest.skip`s in
normal spiderweb CI (it requires a co-located `moneysweep-pr`). When both repos are checked out
together, it surfaces a producer→consumer **filename drift**:

- `moneysweep-pr/run_pr_intake_router.py` writes `moneysweep_derivatives.csv`
  (`routing_summary.spiderweb_pr_derivative_count = 2`), but
- `readiness/spiderweb_spatial_lane.py` (`INPUT_FILENAME = "spiderweb_pr_derivatives.csv"`) reads
  `spiderweb_pr_derivatives.csv`, raising `SpiderwebSpatialLaneError: missing required input`.

This is a handoff-boundary issue that needs `moneysweep-pr` coordination to reconcile the derivatives
filename; per the federation no-cross-edit rule it is **not** patched unilaterally from this repo.

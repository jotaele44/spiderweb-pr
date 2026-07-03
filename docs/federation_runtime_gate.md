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

## Production promotion — real package built 2026-07-03; flip held

The real-rows blocker is resolved: `scripts/build_real_spatial_streams.py` projects committed
real data (the georeferenced `SITE_RI_20260522_001` site record and
`configs/airport_registry.yaml`) into 10 observations + 2 sources with `is_synthetic: false`
and deterministic ids. `build_export_package.py --source-dir exports/real --mode production`
plus `validate_export.py --mode production` pass (exit 0), and the parent hub validated the
production canonical projection (`hub validate-package` → VALID; `hub validate-federation`
classifies spiderweb-pr as `declared_not_live` with `package_valid=true`).

`ready_for_hub_live_execution` stays **false** by operator decision: the first real production
package is small (1 structure sighting + 9 airport reference locations) and the flip is held
for operator review. No synthetic data was promoted to production.
(Ref: P1-SPIDERWEB-NON-SYNTHETIC-ROWS — real-rows half closed.)

## Cross-repo handoff — seam closed 2026-07-03

The June-2026 retirement of moneysweep's `spiderweb_pr_derivatives.csv` writer (which left
`readiness/spiderweb_spatial_lane.py` input-starved) was reversed on the moneysweep side: the
router writes the stream again, schema-conformant with `schemas/pr_intake_derivative.schema.json`.
`tests/test_spiderweb_spatial_lane.py::test_round_trip_zero_loss_across_the_seam` now **passes**
against a co-located moneysweep-pr (zero-loss, empty discrepancy queue); it still `pytest.skip`s
in spiderweb-only CI.

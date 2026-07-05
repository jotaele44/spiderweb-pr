# Release Readiness

Operator runbook for the **release gate** — the single umbrella check that determines whether a build is shippable. The gate is implemented by [`release_check.py`](../release_check.py) and exposed three ways:

```
make release-check                                          # canonical
python release_check.py --db DB --output-dir DIR [--skip-tests]
python run_all.py --db DB --release-check [--release-output-dir DIR]
```

All three call `ReleaseCheck(db_path, output_dir, mode).run()`, which writes [`release_report.json`](../schemas/schema_index.json) (the schema index entry documents the structure).

---

## Stages and pass criteria

The gate runs six stages. Five gate the overall verdict; one (`earthgpt_selftest`) is intentionally non-gating.

| Stage | Pass when | Fail mode |
|---|---|---|
| `syntax_check` | Every `*.py` in `integration/`, `readiness/`, `pipeline/`, `earthgpt/`, `llm/`, `federation/` + root compiles cleanly. **Compile-only** — never imports, so optional-dep guards (`paddleocr`, `easyocr`, etc.) don't trip it (Open Risk #1). | One or more files fail `py_compile`. The report lists each file and its error. |
| `core_tests` | `pytest tests/ -q --ignore=test_io --ignore=test_terrain` exits 0 (or 5 — no tests collected). | Any test fails. Subset is the same as the `make test` target (D7 keeps GEBCO io/terrain tests out — they run in their own CI job). |
| `validate` | `SchemaValidator().run_db_validation()` runs without `_error`. Invalid records are routed to `review_queue.csv` but do **not** fail the stage — they're expected and counted. | DB missing (in normal mode → SKIPPED; in strict → SystemExit 2), or the validator raises. |
| `export_pr_intel` | `PRIntelAdapter.export_all()` returns `overall_status == "PASS"` (all 6 PR Intel gates green: schema_validation, coordinate_coverage, ocr_confidence_gate, evidence_chain_coverage, export_completeness, temporal_integrity). | Any sub-gate FAIL, or the adapter raises. |
| `export_spiderweb` | Both `ILAPAirspaceBridge.export_all()` and `AASBAirspaceBridge.export_all()` complete without raising; the manifest is written. | Either bridge raises. |
| `earthgpt_selftest` | `from earthgpt.selftest import run_selftest` succeeds and returns `passed == total`. | **WARNING (non-gating)** if import fails or any gate fails. EarthGPT is optional per ARCHITECTURE.md — its degradation never blocks the release. (Open Risk #4.) |

`overall_status = "PASS"` iff every **gating** stage is `PASS` (or `SKIPPED`). `failure_reasons` lists `<stage>:FAIL` for each gating stage that hard-failed.

---

## Modes

Resolved by [`run_modes.resolve_mode(args)`](../run_modes.py):

| Mode | When to use | Behavior |
|---|---|---|
| `normal` (default) | Local development, smoke tests | Missing DB → stages return `SKIPPED` softly; gate still produces JSON. |
| `--demo` | Demo runs against fixture data | Outputs are stamped `"mode": "demo"`; manifests carry `demo_warning`. Stages run as in normal. |
| `--strict-production` | CI / pre-deploy gate | Missing or empty production DB → structured JSON error to stderr + `SystemExit(2)`. **Mutually exclusive** with `--demo` (strict wins if both passed). |

In all modes the `reproducibility` block on every manifest records the resolved `mode`.

---

## Output: `release_report.json`

```
{
  "metadata": <reproducibility_metadata 8-key block>,
  "syntax_check":     {"status": "PASS|FAIL", "files_checked": N, "failures": [...]},
  "core_tests":       {"status": "PASS|FAIL|SKIPPED", "returncode": N, "passed": N, "failed": N, "skipped": N, "error": N, "summary": "..."},
  "validate":         {"status": "PASS|FAIL|SKIPPED", "schema_invalid": N, "review_queue": path, "tables": {schema: invalid_count}},
  "export_pr_intel":  {"status": ..., "integration_report": path, "gates": {gate: status}, "files": [...]},
  "export_spiderweb": {"status": ..., "manifest": path, "files": [...]},
  "earthgpt_selftest":{"status": "PASS|WARNING", "passed": N, "total": N, "gates": {name: bool}},
  "overall_status":   "PASS|FAIL",
  "failure_reasons":  ["<stage>:FAIL", ...]
}
```

See [`SCHEMA_AND_EXPORT_CONTRACTS.md`](SCHEMA_AND_EXPORT_CONTRACTS.md) for the canonical schema entry.

---

## Common failure modes

| Symptom | Probable cause | Fix |
|---|---|---|
| ~~`core_tests: FAIL` with `test_exports_reproducible` failing on `rlsm_ingest_manifest.csv`~~ | The RLSM export/coverage pipeline migrated to [skywatcher-pr](https://github.com/jotaele44/skywatcher-pr) (2026-06, PRs #110/#111); this failure mode no longer applies here. | — |
| `validate: FAIL` with `_error: "no such table: ..."` | Wrong DB path or pipeline not yet run. | Confirm `--db` points at the populated DB; run `python run_all.py --db DB --status` first. |
| `export_pr_intel: FAIL` with `evidence_chain_coverage < 0.50` | < 50% of screenshots linked to a flight (FK weakness). | Re-run the phase-0 ingest (`python run_all.py --image-dir <dir> --db DB`) so screenshots link to flights. (The standalone FR24 inventory/event-export flags migrated to [skywatcher-pr](https://github.com/jotaele44/skywatcher-pr).) |
| `export_spiderweb: FAIL` with `sqlite3.OperationalError: database is locked` | Concurrent writer on the same SQLite. | Single-writer discipline; the RLSM lock fix landed in commit `5e3832...` (timeout=30 on rlsm_unlabeled/extractors/ocr). |
| `earthgpt_selftest: WARNING` | EarthGPT module unavailable or a sub-gate failed. | Non-blocking. Investigate if EarthGPT is required for your release. |

---

## Verification matrix

After any release-relevant change:

```
python -m py_compile *.py
python -m pytest tests/ -q --ignore=tests/test_io.py --ignore=tests/test_terrain.py
python run_all.py --db ~/flight_database.db --status
python run_all.py --db ~/flight_database.db --validate
python run_all.py --db ~/flight_database.db --export-pr-intel /tmp/pr_intel_smoke
python run_all.py --db ~/flight_database.db --export-spiderweb /tmp/spiderweb_smoke
python run_all.py --db ~/flight_database.db --release-check --release-output-dir /tmp/release_smoke
python -c "import json; r=json.load(open('/tmp/release_smoke/release_report.json')); print(r['overall_status'])"
python run_all.py --db ~/flight_database.db --release-check --demo --release-output-dir /tmp/release_demo
python run_all.py --db ~/flight_database.db --release-check --strict-production --release-output-dir /tmp/release_strict
make release-check
```

Each command's expected outcome: `PASS` overall, or a structured failure that maps to one of the rows above.

---

## Cross-references

- [`SCHEMA_AND_EXPORT_CONTRACTS.md`](SCHEMA_AND_EXPORT_CONTRACTS.md) — what each output contains.
- [`SPIDERWEB_LANGUAGE_BRIDGE.md`](SPIDERWEB_LANGUAGE_BRIDGE.md) — canonical terminology.
- [`NEXT_100_TASKS.md`](NEXT_100_TASKS.md) — backlog (including a JSON Schema for `release_report.json` itself, currently unspecified).
- [`ROI_TASK_LEDGER.md`](ROI_TASK_LEDGER.md) — running task scorecard.

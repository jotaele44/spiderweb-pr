# Validation Gates

`scripts/validate_export.py` enforces the federation export contract. It is
**fail-closed**: every required gate must pass, in the requested mode, or the
package is rejected.

## Invocation

```bash
python scripts/validate_export.py --package <dir> --mode {test,production}
```

Writes `validation_report.json` next to the package. Exit codes:

| Code | Meaning                                                       |
|------|---------------------------------------------------------------|
| `0`  | Package is valid for the requested mode.                      |
| `2`  | Package failed one or more validation gates.                  |
| `3`  | Package layout is broken (e.g. missing manifest).             |
| `4`  | Invalid CLI args / missing `jsonschema` dependency.           |

## Gate matrix

| Gate                                                  | test | production |
|-------------------------------------------------------|:----:|:----------:|
| Manifest file exists                                  |  ✓   |     ✓      |
| Manifest validates against `spiderweb_airspace_export`|  ✓   |     ✓      |
| Manifest `package_id` matches recomputed sha256       |  ✓   |     ✓      |
| Manifest declares exactly the four required streams   |  ✓   |     ✓      |
| Each declared file exists                             |  ✓   |     ✓      |
| Each file's `sha256` matches the manifest             |  ✓   |     ✓      |
| Each file's `record_count` matches actual row count   |  ✓   |     ✓      |
| Every row validates against its stream schema         |  ✓   |     ✓      |
| Every row has non-empty `source_id`                   |  ✓   |     ✓      |
| Every row has non-empty `lineage[]`                   |  ✓   |     ✓      |
| Every row has `confidence{score, method}`             |  ✓   |     ✓      |
| Every row has a tz-aware ISO-8601 timestamp           |  ✓   |     ✓      |
| Every row geometry is in valid lat/lon range          |  ✓   |     ✓      |
| Every row `id` matches recomputed deterministic id    |  ✓   |     ✓      |
| Rows with `is_synthetic: true` are rejected           |  ✗   |     ✓      |

## Example failures

**Missing manifest:**
```
BROKEN: /tmp/pkg
  - manifest not found at /tmp/pkg/manifest.json
exit 3
```

**Stream sha256 tampered:**
```
FAILED: /tmp/pkg (mode=test)
  - observations.jsonl: sha256 mismatch declared=ab12... actual=cd34...
exit 2
```

**Synthetic row in production:**
```
FAILED: /tmp/pkg (mode=production)
  - airspace_events.jsonl row 0 (58490aa1...): synthetic row not allowed in production mode
exit 2
```

**Naive timestamp:**
```
FAILED: /tmp/pkg (mode=test)
  - observations.jsonl row 2 (...): missing or non-tz-aware observed_at
exit 2
```

## Programmatic use

`scripts/validate_export.py` exposes `validate_package(package_dir, mode)`
returning a dict (the same content as `validation_report.json`). The
`smoke_export.py` script uses this directly; consumers and CI can do the same
without spawning a subprocess.

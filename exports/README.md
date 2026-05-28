# exports/

Producer staging area for federation export packages.

This directory is **not** the live FR24 → SQLite → exports pipeline (that
remains under `outputs/`, `integration/`, and the existing `--export-spiderweb`
CLI). It is the staging area for the federation contract defined in
[`docs/export_contract.md`](../docs/export_contract.md).

## Layout

```
exports/
├── README.md       (this file)
├── .gitkeep        (preserves the dir in git)
└── samples/        (committed: canonical sample package for docs/tests/CI)
    ├── manifest.sample.json
    ├── airspace_events.sample.jsonl
    ├── observations.sample.jsonl
    ├── tracks.sample.jsonl
    └── sources.sample.jsonl
```

Producer output goes into per-build subdirectories under `exports/` (e.g.
`exports/2026-05-28T00-00-00Z/`). Those subdirectories are gitignored — only
`README.md`, `.gitkeep`, and `samples/` are tracked.

## Build a package

```bash
python scripts/build_export_package.py --out exports/my-package
```

The builder reads `exports/samples/` by default. Override with
`--source-dir <dir>` once a real producer feeds it.

## Validate a package

```bash
python scripts/validate_export.py --package exports/my-package --mode test
python scripts/validate_export.py --package exports/my-package --mode production
```

See [`docs/validation_gates.md`](../docs/validation_gates.md) for the full gate
matrix.

## Round-trip smoke test

```bash
python scripts/smoke_export.py
```

Builds from `exports/samples/` into a tempdir and validates in test mode.
Should print `OK` and exit 0.

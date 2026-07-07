# Census Partnership PR Source Adapter

On-demand downloader for the U.S. Census Bureau Puerto Rico Partnership Shapefile Batch Download page.

## Policy

This adapter follows `docs/source_adapters/census_partnership_pr.md`:

- Do not commit raw Census ZIP files.
- Do not commit extracted shapefile trees.
- Track small manifests and coverage ledgers.
- Promote only normalized analysis-ready GIS outputs.

## Dry run

```bash
python -m scripts.source_adapters.census_partnership_pr.fetch --dry-run
```

Dry run writes:

```text
manifests/census_partnership_pr/source_manifest.csv
manifests/census_partnership_pr/municipio_universe.csv
manifests/census_partnership_pr/planned_batches.csv
```

## Download selected municipios

```bash
python -m scripts.source_adapters.census_partnership_pr.fetch --municipios 72001,72003,72005
```

Runtime ZIPs are written under:

```text
data/raw/census_partnership_pr/
```

Manifests are written under:

```text
manifests/census_partnership_pr/
```

## Normalize a promoted ZIP

Requires GDAL/OGR locally:

```bash
python -m scripts.source_adapters.census_partnership_pr.normalize \
  data/raw/census_partnership_pr/pr72_72001_72003_72005.zip \
  outputs/promoted/census_partnership_pr/pr72_72001_72003_72005.gpkg
```

## Review gate

Before promotion, verify:

1. The expected municipio universe was parsed.
2. Every downloaded ZIP has a SHA256 hash.
3. Coverage ledger reports expected, selected, acquired, failed, hold, unresolved, and coverage percentage.
4. Raw/extracted Census payloads remain outside git-tracked paths.

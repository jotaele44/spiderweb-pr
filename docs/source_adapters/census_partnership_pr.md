# Census Partnership PR Source Adapter Policy

## Objective

Use the U.S. Census Bureau Puerto Rico Partnership Shapefile Batch Download page as an on-demand source adapter, not as a committed raw data dump.

## Decision

Adopt a hybrid on-demand cache model:

- Store small metadata and provenance records.
- Store validated derived GeoPackage outputs only when they are analysis-ready.
- Do not store raw ZIP downloads.
- Do not store extracted shapefile bundles.

## Repository-tracked artifacts

| Artifact | Policy | Purpose |
| --- | --- | --- |
| Adapter documentation | Track | Acquisition rules |
| Municipio universe CSV | Track when small/static | Expected-universe accounting |
| Source manifest | Track | URL, form action, parameters, timestamp |
| Download ledger | Track | Batch status and coverage |
| SHA256 manifest | Track | Payload identity and dedupe |
| Coverage ledger | Track | 0-to-100 accounting |
| Derived GeoPackage | Track only when promoted | Stable GIS output |

## Repository-excluded artifacts

| Artifact | Policy | Reason |
| --- | --- | --- |
| Raw Census ZIPs | Exclude | Regenerable source payloads |
| Extracted shapefiles | Exclude | Intermediate runtime files |
| Temporary batch folders | Exclude | Runtime cache only |
| Partial failed downloads | Exclude | Not analysis-ready |

## Required provenance fields

Adapter runs should emit:

- `source_url`
- `form_action`
- `request_method`
- `request_params`
- `batch_id`
- `requested_municipios`
- `download_timestamp_utc`
- `http_status`
- `content_type`
- `filename`
- `sha256`
- `bytes`
- `extract_status`
- `normalized_output_path`
- `review_status`

## Promotion rule

Promote an output only when:

1. The expected municipio universe is declared.
2. The requested subset is logged.
3. Each payload has a SHA256 hash.
4. Raw ZIPs and extracted shapefiles remain outside git-tracked paths.
5. The derived output is normalized into GeoPackage or another approved stable GIS artifact.
6. The coverage ledger reports expected, acquired, failed, skipped, unresolved, and coverage percentage.

## Path convention

Local-only runtime paths:

```text
data/raw/census_partnership_pr/
data/extracted/census_partnership_pr/
cache/census_partnership_pr/
```

Tracked paths:

```text
docs/source_adapters/census_partnership_pr.md
manifests/census_partnership_pr/source_manifest.csv
manifests/census_partnership_pr/sha256_manifest.csv
manifests/census_partnership_pr/coverage_ledger.csv
```

## Integrity checks

- Enforce the five-municipio batch limit.
- Re-parse the municipio checkbox universe before large runs.
- Reject HTML error pages returned in place of ZIP files.
- Deduplicate by SHA256 before extraction.
- Treat changed form actions or changed municipio counts as review-blocking events.

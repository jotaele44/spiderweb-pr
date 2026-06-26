# Artifact Manifest Standard

This document defines the shared artifact manifest expected at the
moneysweep-pr -> SpiderWeb handoff boundary.

The manifest is written by moneysweep-pr and consumed by SpiderWeb operators
for auditability, reproducibility, and run-to-run comparison. It is not a
replacement for `manifest.json`; it is the file-level evidence ledger for the
package.

## Filename

```text
artifact_manifest.json
```

## Schema version

```json
{
  "schema_version": "artifact_manifest.v1"
}
```

SpiderWeb production handoff should reject unknown major versions once automated
manifest enforcement is added.

## Required top-level fields

| Field | Type | Required | Description |
|---|---|---:|---|
| `schema_version` | string | yes | Must be `artifact_manifest.v1` for this standard. |
| `generated_at` | string | yes | ISO-8601 timestamp from producer runtime. |
| `producer` | string | yes | Expected: `moneysweep-pr`. |
| `export_contract_version` | string | yes | Expected moneysweep-pr export version, currently `1.1.0`. |
| `package_dir` | string | yes | Producer-side package path at manifest creation time. |
| `artifact_count` | integer | yes | Number of artifact records. |
| `source_count` | integer | yes | Number of source-file records. |
| `artifacts` | array | yes | Package output files with hashes/counts. |
| `sources` | array | yes | Original input files with hashes/counts. |

## Artifact record

Each item in `artifacts` should use:

| Field | Type | Required | Description |
|---|---|---:|---|
| `path` | string | yes | Package-relative path when possible. |
| `sha256` | string | yes | SHA-256 hash of file bytes. |
| `bytes` | integer | yes | File size in bytes. |
| `record_count` | integer or null | yes | JSONL row count, CSV data-row count, or null when not row-based. |

Minimum expected artifact paths for a moneysweep-pr package:

```text
manifest.json
entities.jsonl
sources.jsonl
funding_awards.jsonl
transactions.jsonl
relationships.jsonl
```

Recommended additional artifact paths:

```text
artifact_manifest.json
uploaded_master_mapping_report.json
export_streams_report.json
```

## Source record

Each item in `sources` uses the same record shape as artifacts:

| Field | Type | Required | Description |
|---|---|---:|---|
| `path` | string | yes | Source basename or relative path. |
| `sha256` | string | yes | SHA-256 hash of source file bytes. |
| `bytes` | integer | yes | Source file size in bytes. |
| `record_count` | integer or null | yes | CSV data-row count or null. |

For uploaded-master runs, expected source records are:

```text
pr_contracts_master_v2*.csv
pr_all_awards_master*.csv
lda_canonical_client_summary_all.csv
```

## Example

```json
{
  "schema_version": "artifact_manifest.v1",
  "generated_at": "2026-05-28T23:00:00+00:00",
  "producer": "moneysweep-pr",
  "export_contract_version": "1.1.0",
  "package_dir": "exports/moneysweep_uploaded_masters_v1_1",
  "artifact_count": 6,
  "source_count": 3,
  "artifacts": [
    {
      "path": "funding_awards.jsonl",
      "sha256": "...",
      "bytes": 123456,
      "record_count": 281337
    }
  ],
  "sources": [
    {
      "path": "pr_all_awards_master.csv",
      "sha256": "...",
      "bytes": 1234567,
      "record_count": 281337
    }
  ]
}
```

## SpiderWeb consumer rules

| Rule | Posture |
|---|---|
| Missing `artifact_manifest.json` | Block production handoff once manifest enforcement is automated. |
| Unknown `schema_version` major | Block. |
| `producer != moneysweep-pr` | Block for Contract-Finance path. |
| `export_contract_version != 1.1.0` | Block until adapter compatibility is updated. |
| Missing required stream artifacts | Block. |
| SHA mismatch after transfer | Block. |
| `record_count` mismatch vs package stream read | Block. |
| Missing source fingerprints | Degraded for test, block for production. |

## Relationship to package gate

The artifact manifest answers:

```text
Did SpiderWeb receive the exact files moneysweep-pr claims to have produced?
```

The package gate answers:

```text
Are the package contents safe and complete enough to ingest in production mode?
```

Both are needed for evidence-grade production handoff.

## Current implementation posture

moneysweep-pr can now write `artifact_manifest.json` with:

```bash
python scripts/write_artifact_manifest.py \
  --package-dir exports/moneysweep_uploaded_masters_v1_1 \
  --source-file /path/to/pr_contracts_master_v2.csv \
  --source-file /path/to/pr_all_awards_master.csv \
  --source-file /path/to/lda_canonical_client_summary_all.csv
```

SpiderWeb currently documents this as a required production artifact. Automated
manifest enforcement should be added as a future readiness gate before broader
multi-package automation.

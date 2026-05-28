# Federation Export Contract

This document defines the **federation producer contract** that `spiderweb-pr`
exposes to downstream federation hubs and other consumers. It is intentionally
narrow: a stable schema + manifest + validator skeleton, sitting alongside the
existing FR24-flavored pipeline contracts, with zero changes to that pipeline.

## Scope

A "federation export package" is a directory on disk containing:

```
<package>/
├── manifest.json               (required, validated against spiderweb_airspace_export)
├── airspace_events.jsonl       (one event per line)
├── observations.jsonl          (one observation per line)
├── tracks.jsonl                (one track per line)
└── sources.jsonl               (one source-registry entry per line)
```

A consumer is expected to read `manifest.json` first, then iterate the four
JSONL streams. Streams are sorted/grouped by the producer; consumers must not
assume any particular row ordering beyond what the manifest declares.

## Modes

A package is built in exactly one of two modes:

| Mode         | Synthetic rows | Use                                              |
|--------------|----------------|--------------------------------------------------|
| `test`       | allowed        | CI, samples, integration testing                 |
| `production` | rejected       | Live federation publish; consumers trust these   |

The producer stamps `mode` in the manifest. The validator (`scripts/validate_export.py`)
re-enforces it: in `--mode production` any row with `is_synthetic: true` fails the package.

## Streams

| Stream         | File                    | Schema                  | Required timestamp |
|----------------|-------------------------|-------------------------|--------------------|
| events         | `airspace_events.jsonl` | `spiderweb_event`       | `event_time`       |
| observations   | `observations.jsonl`    | `spiderweb_observation` | `observed_at`      |
| tracks         | `tracks.jsonl`          | `spiderweb_track`       | `observed_at`      |
| sources        | `sources.jsonl`         | `spiderweb_source`      | `first_seen_at`    |

See [`airspace_schema.md`](./airspace_schema.md) for the field-by-field reference.

## Required row metadata

Every row in every stream must carry:

- `id` — deterministic; see [Deterministic IDs](#deterministic-ids).
- `source_id` — references a row in `sources.jsonl`.
- `lineage` — non-empty array; see [`lineage_model.md`](./lineage_model.md).
- `confidence` — object with `score` and `method`; see [`confidence_model.md`](./confidence_model.md).
- A stream-appropriate timestamp (`event_time` / `observed_at` / `first_seen_at`).

## Deterministic IDs

The row `id` is computed by the producer and re-checked by the validator:

```python
def compute_row_id(row: dict) -> str:
    payload = {k: v for k, v in row.items() if k != "id"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
```

The manifest's `package_id` is computed the same way over the manifest body
(excluding `package_id` itself). This guarantees:

- A given input set always produces the same package — no time-based, no random IDs.
- Consumers can deduplicate across re-publishes by ID.
- Any mutation of a row payload changes its ID, making tampering observable.

## Manifest

The manifest is required and validated against `schemas/spiderweb_airspace_export.schema.json`.
Required fields:

```
package_id       sha256 of manifest body sans package_id (deterministic)
producer_id      e.g. "spiderweb-pr"
producer_version e.g. "0.1.0"
schema_version   MAJOR.MINOR — bump MAJOR for breaking changes
generated_at     ISO-8601 with timezone (UTC recommended)
mode             "test" | "production"
time_range       {start, end} — covers all rows across all streams
files            array of {filename, stream, record_count, sha256, schema_id}
```

`notes` is optional.

## Versioning

`schema_version` follows MAJOR.MINOR semantics:

- **MINOR** bumps: backward-compatible (added optional field, new event_type, etc.).
- **MAJOR** bumps: breaking changes (removed/renamed field, changed semantics).
  A consumer pinned to `schema_version=1.x` may reject `2.0` packages.

## Producer responsibilities

1. Compute deterministic row IDs.
2. Compute correct sha256 for each emitted JSONL file.
3. Compute deterministic `package_id` for the manifest.
4. Stamp `mode` accurately — `production` only when no synthetic rows are emitted
   and all upstream readiness gates have passed (see [`federation_readiness.md`](./federation_readiness.md)).
5. Run `scripts/validate_export.py --mode <mode>` before publish.

## Consumer responsibilities

1. Validate the package against this contract (`scripts/validate_export.py`)
   before treating it as authoritative.
2. Reject `mode=test` packages unless explicitly opted-in for testing.
3. Use `source_id` and `lineage` to attribute claims; never strip provenance.

## See also

- [`airspace_schema.md`](./airspace_schema.md) — field-by-field stream reference
- [`lineage_model.md`](./lineage_model.md) — lineage chain shape
- [`confidence_model.md`](./confidence_model.md) — confidence scoring
- [`validation_gates.md`](./validation_gates.md) — validator gate matrix
- [`federation_readiness.md`](./federation_readiness.md) — promotion checklist

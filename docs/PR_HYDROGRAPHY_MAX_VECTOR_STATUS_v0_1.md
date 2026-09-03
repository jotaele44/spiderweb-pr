# PR Hydrography MAX_VECTOR Status v0.1

## Current state

The control plane implementation is present on draft PR #267 and remains unmerged.

Validated code head: `870b4ccfe4d90ad0a0f1df781bd30035a999bbb6`.

Dedicated workflow run `31641238822` completed the offline regression job successfully.

## Passed implementation gates

- immutable content-addressed source snapshots
- source-universe separation
- request and schema fingerprints
- source-specific TIGER/NHD/NID/Inland Bathymetry certifier contracts
- artifact-role schema registry
- candidate-set union of discovery and explicit higher-grade evidence
- proximity-only non-promotion
- equal-top-evidence tie preservation
- analysis-only geometry repair
- strict CSV boolean handling and matching-only mojibake normalization
- remote change taxonomy
- temporal source-state model
- change-ledger contract
- crash/restart immutability tests
- logical replay equivalence tests
- persistent-snapshot disaster-recovery inventory
- fail-closed longitudinal reservoir spine builder
- alert-only scheduled freshness probe
- operator commands for pull, refresh, certify, resolve, build-spine, audit, reproduce, and historical byte binding

## Real-data gates still open

The following gates cannot be promoted from code/fixture evidence alone:

1. Historical local byte migration from the certified `PR_RESERVOIR_DATA` corpus into persistent Spiderweb snapshot storage.
2. Exact reconstruction of the 2026-08-11 snapshot set from those bytes.
3. True fresh full acquisition and byte/schema/denominator comparison against that reconstructed set.
4. Adjudication of all 32 NID-to-impoundment review rows using independent authoritative evidence.
5. Byte-level recovery of the primary 2004 36-row reservoir source and exact 2004-to-current crosswalk.
6. Exhaustion of the small-hydro/non-NID impoundment gap universe.
7. Full domain disaster-recovery replay from fresh clone plus persistent snapshot store.
8. Final v1 zero-gate certification.

## Preservation rule

No historical canonical byte is superseded merely because a fresh source is available. New bytes must enter as a child snapshot and every byte, schema, denominator, entity, and relationship change must be classified before promotion.

## Merge rule

Keep PR #267 in draft state. Do not auto-merge. Mark ready only after the final v1 certification observes zero unclassified source changes, zero unaccounted bytes, zero schema-role violations, zero proximity-only identities, zero hidden ties, zero unexplained denominator drift, zero canonical overwrites, and zero unbound parent snapshots.

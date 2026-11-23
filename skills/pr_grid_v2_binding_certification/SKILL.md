---
name: pr-grid-v2-binding-certification
description: Fail-closed certification workflow for Spiderweb PR Grid V2 exact EPSG:6566 point, polygon and line bindings, source snapshots and federation rollout.
---

# PR Grid V2 Binding Certification

Use this skill for Spiderweb V2 record-to-cell binding materialization,
schema upgrades, certification receipts, or cross-repository migration.
Spiderweb remains the sole geometry and binding authority. Do not
recompute authoritative membership in a consumer.

## Never mutate the frozen RC1

- Grid ID: `PR_GRID_GEOGRAPHIC_V2`
- Grid version: `2.0.0-rc1`
- Grid manifest SHA256:
  `8902af188ad449955119016f5747fe2393c582d9ed552fb03bcaecd9ab510aa4`
- RC1 binding schema SHA256:
  `dabc461e47134b3b150be9aeb23b3d0097563493b33b3187538255e06b16a022`
- vNext binding schema:
  `pr-grid-v2-binding/2.0.0-rc1`
- vNext schema SHA256:
  `e3dbd844bd8c35451e112af6a8d39461b1490454e2f41e191133d8115980f2c8`

## Inputs and evidence

1. Inspect input preamble, encoding, row counts, field types, source IDs, duplicate
   IDs, geometry types, CRS, precision evidence and transformation lineage.
2. Do not accept `EXACT` as positional proof just because the input says so.
3. Require a distinct frozen source snapshot and sidecar source manifest;
   independently hash bytes and verify input/snapshot byte identity and row
   cardinality. No silent transform or source repair.
4. A byte match is never proof of an authoritative source, original coordinates,
   geometry accuracy, record identity or historic continuity. The initial
   snapshot contract must say `authority_evidence_state=UNVERIFIED`.
5. Preserve raw source strings, names, record IDs and original source data.
   Do not strip/normalize identifiers and assert canonical identity.
6. Keep source/raw SHA, canonical GeoJSON geometry SHA, version and
   consumer pins separate. Hash equality applies only to comparable bytes.

## Spatial logic

- Projected input must be exactly EPSG:6566, finite XY, valid/nonempty, EXACT.
- Point boundary results: INTERIOR 1, EDGE_SHARED 2, CORNER_SHARED 4,
  OUTSIDE 0 plus explicit outcome.
- Polygon: exact intersection strictly positive area; touch-only 0 rows.
  Preserve polygon holes; confirm clipped area = sum cell-intersection areas.
- Line: exact positive clipped length per component/segment/cell. Do not
  discard traversal order or shared-grid-edge multiplicity.
- Length conservation must distinguish clipped source traversal, spatial
  support after dissolving retraced segments, and duplicated cell-edge
  assignments. These values are not interchangeable.
- Preserve complete per-record outcomes including OUTSIDE and TOUCH_ONLY;
  the sum of record binding counts equals output row count.
- Reject invalid geometry, wrong/missing CRS, non-EXACT source position,
  duplicate composite raw record IDs, malformed JSON/duplicate keys,
  unexpected geometry members or schema/pin drift.
- Candidate bbox/discovery is never identity proof or intersection proof.
- No consumer-side proximity-only placement or fake Cell_IDs.

## Execution

1. Read and execute root `TERMINAL_READY.txt`, including platform-specific
   instructions and manifest/snapshot creation.
2. Execute `tests/test_grid_v2_bindings.py`,
   `tests/test_grid_v2_bindings_vnext.py` and the full Spiderweb test suite.
3. Verify frozen RC1 manifest and schema hashes and the pinned new schema.
4. Run CLI `scripts/materialize_pr_grid_v2_exact_geometry_bindings_vnext.py`
   with `--source-manifest`, `--input`, `--level`,
   `--bindings-out`, `--receipt-out`.
5. Run the separate read-only audit CLI `scripts/audit_pr_grid_v2_binding_artifacts.py` and require its `Audit_State=PASS` (still `AUDIT_ONLY`).
6. Check input/snapshot and output SHA256, byte sizes, counts, complete
   `Record_Outcomes`, positive-area and positive-length invariants,
   and zero row counts for OUTSIDE/TOUCH_ONLY.
7. Only interpret completed green CI for the exact HEAD under review as
   execution evidence. Earlier runs are superseded.
8. Keep release `PROVISIONAL` until scope, authority evidence,
   geometry tests, source classification and CI reach certification.
9. Keep live six-repo consumer CI `OPEN` until it actually executes.
   Consumer pins must remain unchanged until Spiderweb certifies vNext.
10. Never merge a draft PR or activate domain source migration based only
   on local validation and passing fixture tests.

## Required outcome

Report a bounded table with `PASS`, `FAIL`, `OPEN`, `BLOCKED`,
`PROVISIONAL`, `AUDIT_ONLY` or `UNRESOLVED` for each gate.
Record the exact branch and HEAD commit, frozen artifact/hash identities,
test counts, skipped tests, CI run URL, and unresolved source-authority
and cross-repository gaps. Include root `TERMINAL_READY.txt` in each build.

## Audit separation

The independent-process artifact verifier uses the same authoritative Spiderweb
geometry engine for deterministic replay and therefore cannot certify a
second, genuinely independent geometry implementation. It validates the
emitted record set, schema, Cell_ID ranges and source/receipt hashes, and
rejects hostile output tampering. Always label that success AUDIT_ONLY.

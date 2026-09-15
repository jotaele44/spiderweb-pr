# Post-merge GIS hardening v2

Base reviewed: `3193a50994cbe4f4fe79b8b4e90ef400da4d088e`.
This is a bounded extension of PR #347, not a new data acquisition, publication,
geometry certification, or change to federation ownership.

## Changes

1. `validate_manifestation_dag` now checks derivation transitions in addition
   to graph structure. SIMPLIFIED and DELIVERY_MINIMIZED descendants cannot
   become FULL or CANONICALIZED_FULL, including through intermediate labels.
   MVT descendants remain MVT. A native source remains a parentless root.
   Structural success still does not certify source claims or geographic identity.

2. The benchmark preflight and runner now require a SHA-bound `lineage_lock`.
   This is an actual consumer gate, not only a unit test of the DAG function.
   Existing benchmark configs intentionally leave that lock unresolved.
   No production registry or existing municipios publication path is rewired.
   General persistence/publication integration remains a separate migration.

3. Browser measurements capture initial and every pan checkpoint, including
   actual camera and canvas dimensions, unique rendered IDs and fragment counts.
   Missing/duplicate trials, omitted/reordered checkpoints, invalid IDs,
   camera divergence, unexpected emptiness, unknown source IDs and per-checkpoint
   set differences fail the gate. Optional independently declared visible-ID
   expectations detect both arms omitting the same required synthetic feature.
   Camera equality uses an explicit 1e-7 numeric tolerance; this is not a
   simplification tolerance or a spatial identity test.

4. The runner consumes the rendered-parity receipt before emitting
   MEASURED_NOT_PUBLISHED. Failure returns FAIL_VIEWPORT_PARITY and cannot
   authorize a delivery winner. Source-wide tile ID parity and operator-visible
   checkpoint parity remain separate from geometric equivalence.

5. Both delivery arms read the same per-run read-only source copy, hash-bound
   to the original supplied artifact. This is local reuse, not reacquisition.

## Lineage lock

Add to the benchmark spec:

```json
{"lineage_lock":{"path":"/preserved/lineage.json","sha256":"<64 lowercase hex characters>"}}
```

The lock schema is `spiderweb.geometry-lineage-lock.v1` with exactly `schema`,
`nodes` and `artifact_bindings` at the top level. Nodes use the existing
GeometryManifestation fields; origin and representation enums are validated.
Each binding has `geometry_manifestation_id`, `artifact_sha256` and
`source_snapshot_id`. The selected binding must match the benchmark spec.
Duplicate JSON keys, node IDs and artifact bindings are rejected. No MVT node
can supply a canonical GeoJSON input. A lock is a frozen statement of lineage,
not independent confirmation of an authority's claims.

Legacy dataclass construction remains supported. Unknown historical lineage is
not invented, and such records do not pass strict admission. This remains a
single-parent model; multi-input derivations require a separate schema extension.

## Validation performed in this pass

96 unique tests passed, with zero failures/skips in the final local run:
39 preserved tests plus 57 added tests. Python runtime: 3.13.5.
The source tree is a hash-bound partial tree, not a full repository checkout.
No claim is made for the full repository suite or Python 3.11/3.12 matrices.

Six tests execute the production embedded measurement JavaScript in real
Chromium with an explicitly stubbed MapLibre protocol loaded in memory. They
exercise initial/pan capture, tile-fragment ID deduplication, camera mismatch,
invalid IDs, unexpected empty checkpoints and error cleanup. They do NOT test
MapLibre rendering, MVT decoding, Martin or HTTP delivery.

Two further tests exercise the Python runner using stubbed engines, verifying
that viewport mismatches block its success state and that both arms use the
same staged source. Stubbed numbers are not browser-performance measurements.

The attempted localhost browser navigation returned
`ERR_BLOCKED_BY_ADMINISTRATOR`. Full-checkout retrieval hit a DNS failure.
The environment did not provide the locked Martin/MapLibre assets or the MVT
Python decoder. The real-engine smoke therefore emitted a BLOCKED receipt.
No browser policy was disabled and no hosted Actions rerun was requested.
The user's Actions billing exception does not convert these results to PASS.

## Repeat the bounded tests

```sh
PYTHONPATH=. pytest -q \
  tests/test_geometry_manifestation_lineage.py \
  tests/test_gis_evidence_tools.py \
  tests/test_gis_lineage_residue.py \
  tests/test_gis_postmerge_hardening.py \
  tests/test_gis_browser_protocol.py
```

Browser protocol tests explicitly skip when their local dependencies are absent;
a skipped run is not equivalent to the no-skip local result reported above.

## Actual engine smoke, still pending

`synthetic_smoke.py` generates three explicitly synthetic polygon features,
a bound lineage lock and independent expected visible IDs for two viewports
with two pan checkpoints each. The real run requires supplied local assets:

```sh
python -m tools.gis_evidence.synthetic_smoke \
  --out /new-run/synthetic-smoke \
  --martin-path /locked/martin --martin-sha256 HASH --martin-version VERSION \
  --maplibre-path /locked/maplibre-gl.js --maplibre-sha256 HASH \
  --maplibre-version VERSION
```

Use a new output directory. Missing assets fail preflight without fetching
anything. The run uses five AB/BA repetitions and global tile ID checks plus
30 paired rendered checkpoints. The expected oracle itself has not yet been
validated against real engines here. Successful synthetic engine execution
would validate this path only, not tracts, barrios, NWI, COUSUB or an iPhone.

No administrative/wetland simplification thresholds, VDatum values, density-grid
choice, source acquisition, or layer-delivery promotion is part of this change.
MVT remains noncanonical and GeoJSON rollback remains mandatory.

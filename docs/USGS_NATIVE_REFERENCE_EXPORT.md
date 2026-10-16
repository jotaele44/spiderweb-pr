# USGS documentary reference export

`federation/usgs_native_reference.py` owns the source-native USGS adapter.
`scripts/export_usgs_native.py` uses the existing canonical package writer in
`scripts/federation_export.py`. The adapter reads checksum-verified inputs
supplied by the Hub; it does not acquire mutable sources.

The frozen regression scope is three NSHM2025 source assets: 51 points, six
MultiPolygons and 35 MultiLineStrings. Export conservation is 3 sources and 92
snapshot observations. Entire native features and collection metadata including
CRS remain in attributes. Source primary keys are typed and scoped to the asset
and raw payload hash. No names or coordinate proximity establish identity.

This is a **test-mode documentary reference package**. `observed_at` describes
source retrieval, never a geological event. Confidence 0 means domain confidence
is unassessed; the separate checksum proof describes byte integrity. The export
contains no canonical locations, representative points, new event claims,
geometry transformations or jurisdiction assignments. It is excluded from live
aggregation. PR coverage, native geometry interpretation, usage, lineage,
consumer fitness and scientific semantics remain OPEN. Production mode fails
before writing anything. Existing producer production exports are unchanged.

From this repository root, with the normal `prii-export-utils` dependency:

```sh
python -m pytest -q tests/test_usgs_native_reference.py tests/test_federation_export.py
python scripts/export_usgs_native.py --input-manifest tests/fixtures/usgs_native/input.json --source-root . --out /absolute/path/new-empty-package
```

For the real Hub staging input use its `data/usgs/producer_inputs/spiderweb-native.v1.json`
as `--input-manifest` and its repository root as `--source-root`. The produced
package includes `TERMINAL_READY.txt`. Validate with the Hub's canonical package
validator and the independent USGS export validator on its companion PR branch. Schema PASS
is explicitly separate from scientific or production readiness.

Regression gates include duplicate IDs and primary keys, missing/foreign source
identity, typed integer/string keys, checksum disagreement, path escape,
expanded-size limits, duplicate JSON fields, non-finite values, count drift,
naive timestamps, production refusal and deterministic replay. A nonempty output
directory fails closed so previous packages cannot be partially overwritten.

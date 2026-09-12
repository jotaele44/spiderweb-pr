# Frozen GIS evidence tools (draft v1)

These tools separate implementation/test success from empirical certification.
They do not acquire Census data, select simplification tolerances, publish MVT,
or change the existing municipios canary/publication configuration.

## Base and scope

Prepared against Spiderweb commit `d4bfb233a032a4c2bb1331c21bc56b2d48bfbba0`.
The original `spiderweb/spatial/archipelago.py` was verified against Git blob
`4958d9cac96672fa7a2ab06329abcc7cadc9d657` before modification.

Existing positional construction of GeometryManifestation is preserved by
appended optional defaults. Serialized forms gain fields and still require
downstream integration review. Strict lineage validation is opt-in through
`validate_manifestation_dag`; existing records are not silently assigned parents
or admitted as certified geometry. The validator handles a single declared
parent per record, not general multi-parent lineage. Its `PASS_STRUCTURAL_ONLY`
receipt never certifies canonical feature identity.

## COUSUB

Run from the repository root with an already-preserved archive:

```sh
python -m tools.gis_evidence.cousub \
  --archive /preserved/source/tiger/tl_2025_72_cousub.zip \
  --out /new-evidence-run/cousub.json
```

The locked source is 3,934,254 bytes and SHA256
`6930acc0987823109e570a04507c48991a4e446802648054d3661b104aab989c`.
The parser checks the ZIP and all members, inspects the DBF schema and preserves
raw padded GEOID/LSADC strings and field bytes. It rejects duplicate IDs before
forming sets. The 827/75/37 subclass matrix is an expectation, not an observation.
Unexpected real counts must remain conflicting evidence, not be repaired to fit.

Only after recovered rows pass may a separately versioned TIGERweb table be
compared using `--comparison-csv` and `--comparison-sha256`. That CSV must have an
explicit GEOID,LSADC header. Preserve the original TIGERweb response and parsing
mapping separately. This tool does not fetch or freeze the TIGERweb response.
No claim of 939-versus-939 equality exists until both row sets are observed.

## Martin/MapLibre benchmark

```sh
python -m tools.gis_evidence.delivery_benchmark \
  --spec configs/gis_benchmarks/tracts.json --out /new-evidence-run/tracts
```

Repeat independently with barrios.json and wetlands_nwi_prvi.json. Use a new
output directory for every run; earlier trials/receipts are never overwritten.
The runner needs an existing frozen GeoJSON, local Martin executable, local
MapLibre JS, exact SHA256/version locks, Playwright with Chromium, and the
`mapbox-vector-tile` Python dependency (the existing canary uses 2.2.0).
The configs intentionally leave runtime locks unresolved. NWI additionally needs
a real stable-ID field, exact filtered-layer count, source hash, and lineage.
Do not invent these fields or assign IDs from row order. Use the SAME filtered
NWI geometry/properties in both delivery arms; do not compare unfiltered raw
wetlands against filtered MVT.

The runner generalizes the existing canary's tile-coverage identity approach,
not its entire fault-injection matrix. The existing municipios canary is retained.
ID reconstruction covers the declared identity zoom and source-bbox tile cover.
It preserves all five set differences and records repeated tile fragments.
It does not prove geometry equality, visibility at every zoom, or canonical
identity. Duplicate IDs in the source fail before set operations.

Measurements use at least five paired AB/BA repetitions, fresh browser contexts,
a warm Martin process after the identity scan, and loopback delivery only.
HTTP redirects and browser requests off loopback are blocked. The source data
are never downloaded by this tool. Identical input/order is deterministic;
wall-clock timings are observations and are not expected to be bit-identical.

`time_to_data_idle_ms` means source-addition to MapLibre data-idle, not app TTI.
`peak_main_thread_js_heap_bytes` excludes worker/GPU/total renderer memory.
HTTP fixture counters include tile requests made by workers. RAF intervals are
recorded as observations, not a certified rendering-performance score. A page
returning an empty expected viewport or an error does not get a winning score.
The runner does not automatically promote delivery: measured results still need
review against a predeclared operator performance/failure budget and relevant
failure-isolation controls. GeoJSON rollback is mandatory; MVT is noncanonical.

## Full versus simplified geometry

```sh
python -m tools.gis_evidence.simplification \
  --full /preserved/full.geojson --full-sha256 FULL_HASH \
  --simplified /preserved/simplified.geojson --simplified-sha256 CHILD_HASH \
  --stable-id GEOID --source-crs EPSG:4326 --operation-crs EPSG:6566 \
  --probe-offset-m 1 --out /new-evidence-run/errors.json
```

The CRS in this example is not a universal choice. Independently establish its
suitability for the actual onshore/offshore layer and preserve the transformation.
No geometry repair, Z/M stripping, or spatial-identity promotion is implicit.
The caller supplies real FULL and SIMPLIFIED manifestations; the tool does not
create a simplified replacement or choose an acceptable tolerance.

Metrics include discrete/densified Hausdorff, symmetric difference, area deltas,
vertex counts, validity, and per-feature ID set differences. Discrete Hausdorff
is an approximation, not a rigorous continuous maximum. Validity alone is not
proof that shared-boundary topology was preserved. Boundary probes are bounded
samples; all containing/touching IDs are retained. Passing a sample never proves
universal PIP equivalence. Both ADMIN_BOUNDARY_STRICT and WETLAND_DISPLAY
thresholds remain unset until real measurements and operational requirements
support a decision.

## Validation and current empirical state

```sh
PYTHONPATH=. pytest -q \
  tests/test_geometry_manifestation_lineage.py \
  tests/test_gis_lineage_residue.py \
  tests/test_gis_evidence_tools.py
```

The local execution passed 39 unique positive/negative tests with no skips.
Geometry tests require Shapely 2.x, pyproj and NumPy; a minimal environment may
skip optional geometry tests, which is NOT full spatial-test certification.
The embedded benchmark JavaScript passed `node --check`.

Empirical status as of the draft: the exact COUSUB archive was not recovered;
no TIGERweb comparison response was acquired; tracts, barrios and NWI each
stopped at input/runtime preflight. There are no real browser timing results,
no real-layer simplification-error receipts, and no selected tolerances.
The full repository suite and real Martin/MapLibre integration were not executed
in the local partial source tree. This draft must not be represented as a
certified geospatial release or a completed three-layer benchmark.

# Geospatial Visualization Engine

`viz_engine/` renders reproducible, source-bound views of already-wired geospatial
data: a top-down map, a vertical cross-section along a transect, and a bounded 3D
scene. Every output ships with a machine-readable receipt. **A rendered picture is
never evidence of a connection.**

## Status

`DESIGN-IMPLEMENTED / FIXTURE-CERTIFIED / NOT ACTIVATED`. The engine is exercised
only against the synthetic snapshot in `tests/fixtures/viz/pilot_snapshot/`
(invented data; it says nothing about real Puerto Rico hydrology). No real
snapshot adapter exists yet, nothing is wired into the desktop app or API, and no
production path calls it. Real-data wiring (NHD flowlines, 3DEP/GEBCO DEM, the
AguaYLuz and ILAP adapters) is a later change; the NHD/NID acquisition gates in
`docs/PR_HYDROGRAPHY_MAX_VECTOR_STATUS_v0_1.md` are still open.

## Ownership

- Spiderweb-PR owns the renderer, its contracts and the presentation layer.
- AguaYLuz keeps hydrologic analysis and measurements; it is consumed through a
  read-only snapshot, never copied into a second hydrologic database.
- The engine never writes to a snapshot. Rendering is covered by a test that the
  input bytes are unchanged afterwards.

## Pipeline

```text
snapshot dir (snapshot.json + layers/*.json, every layer pinned by sha256)
  -> load_snapshot        refuses changed bytes (SnapshotIntegrityError)
  -> validate_snapshot    reference frames, identities, network, connections, wells
  -> render xy | section | 3d
  -> receipt              <artifact>.receipt.json next to the artifact
```

CLI:

```bash
python -m viz_engine render --view xy|section|3d --snapshot DIR --config scene.json --out OUT
python -m viz_engine verify --artifact OUT/x.svg --receipt OUT/x.svg.receipt.json
```

`render` exits 0 on `PASS` and 3 on `FAIL` (the artifact is still written, but
watermarked `VALIDATION FAILED - NOT FOR PUBLICATION`).

## Views

| View | Output | Controls (`schemas/viz_scene_v1.schema.json`) |
|---|---|---|
| `xy` | SVG: Horn hillshade, waterbody, flow network, wells, connections | `extent`, `layers`, `date`, `width` |
| `section` | SVG: DEM profile along a transect, wells to depth, water level, connections | `transect`, `vertical_exaggeration`, `buffer_m`, `samples`, `date` |
| `3d` | glTF 2.0 (self-contained): terrain mesh, well lines, connections | `vertical_exaggeration`, `date`; capped at 250,000 DEM cells |

`date` selects one measurement date in every view: features (wells and connections alike) whose
`observation_date` differs are left out; features with no date are always shown.

The section refuses (rather than clamps) a vertical exaggeration that would exceed
1,600 px. Well depths are read as feet below land surface, positive down, and
converted to metres (x0.3048); any other depth reference fails validation.

## Evidence classes and the drawing rule

Every feature carries `properties.evidence` in `observed | inferred | modeled |
unknown`; a missing or unrecognised value is treated as `unknown`.

| Class | Connection drawn as | Requires |
|---|---|---|
| `observed` | solid | `observation_ref` |
| `modeled` | long dash | `model_id` |
| `inferred` | dotted, labelled hypothesis | nothing (it is not evidence) |
| `unknown` | **never drawn as a link** | n/a |

A connection claiming `observed` or `modeled` without that backing fails
validation (`UNSUPPORTED_CONNECTION`); one whose endpoints are not snapshot
features fails (`CONNECTION_ENDPOINT_MISSING`).

## Validation gates

Any `error` issue makes the receipt `FAIL` and `publication_ready` false;
`export_publication()` then raises `PublicationBlocked`. It also re-checks the files on disk
against the validated render (artifact sha256 and receipt hash), so a later render into the same
output directory cannot be exported under an earlier run's `PASS`.

| Code | Trips when |
|---|---|
| `CRS_MISMATCH` / `DATUM_MISMATCH` / `UNIT_MISMATCH` | a layer's CRS, vertical datum or vertical unit differs from the snapshot's; nothing is silently reprojected |
| `UNSUPPORTED_VERTICAL_UNIT` | the snapshot's vertical unit is not metres; the renderers compute in metres and never convert elevations, so a consistently declared feet-based snapshot is refused rather than rendered wrongly |
| `DUPLICATE_FEATURE_ID` | one feature id appears more than once across layers |
| `MERGED_ID_WITHOUT_ADJUDICATION` | `merged_from` is set without `identity_adjudication` (proximity never merges identities: `CANDIDATE_NOT_IDENTITY`) |
| `REVERSED_FLOW` | a segment digitised downstream rises more than 1 m against the DEM |
| `DISCONNECTED_SEGMENT` | a segment is not in the main network and is not `network_role: isolated_declared` |
| `MISSING_RASTER_COVERAGE` / `NO_RASTER` | the map extent, transect or a well falls outside the DEM or on nodata, or there is no DEM (a 3D run without a DEM still writes an empty glTF scene and a `FAIL` receipt) |
| `UNSUPPORTED_CONNECTION` / `CONNECTION_ENDPOINT_MISSING` | see above |
| `DEPTH_REFERENCE_UNSUPPORTED` | a well's depth reference is not `below_land_surface` |

A layer file whose bytes no longer match the manifest is rejected before any
rendering (`SnapshotIntegrityError`).

## Receipt (`schemas/viz_receipt_v1.schema.json`)

Records: input snapshot id/version and manifest hash; every layer's id, kind,
sha256 and source; CRS, vertical datum, units and extent; each drawn feature id with
its evidence class and observation date; processing steps; renderer name, version,
Python version and repo commit; the full validation result; and the output file's
sha256. `render_id` hashes the render *inputs* (snapshot + view + config +
software) and is embedded in the artifact, so there is no circularity with the
output hash. Output is byte-reproducible: SVG and glTF are written by stdlib code
with fixed number formatting and no timestamps, and tests render twice and compare
bytes.

## Contracts and fixtures

- `schemas/viz_snapshot_v1.schema.json`, `viz_scene_v1.schema.json`,
  `viz_receipt_v1.schema.json`. These are engine-local; they are not release-pipeline
  artifacts and are deliberately not listed in `schemas/schema_index.json`.
- `tests/fixtures/viz/build_pilot_fixture.py` regenerates the synthetic snapshot and
  scene configs.
- Tests: `tests/test_viz_engine.py`, `tests/test_viz_engine_negative.py`
  (`make test-viz`).

## Not built yet

PNG/GeoTIFF/GeoJSON/3D Tiles export, temporal wet/dry comparison, hydrostratigraphic
layers and volumes, real-data snapshot adapters, and the interactive MapLibre/Cesium
front end (the existing `server/frontend/src/spatial/runtime/` runtimes are the
intended consumers of the same scene and receipt JSON). Promoting any of this as a
shared federation contract needs a `federation-spatial-impact/1.0` report and hub
coordination (`thehub-pr` owns correlation authority).

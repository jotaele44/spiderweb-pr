# GIS viewer API (`/gis/*`) and map viewer tools

The `/gis/*` API is the backend for the viewer functions in the Spatial
Intelligence map. These are the functions a public GIS viewer offers, such as
the Junta de Planificación viewer at `gis.jp.pr.gov`: a layer catalog,
identify, search, area-of-interest query, export, saved views and print. It
works over the layers this backend already serves at `/geo/{layer}.geojson`.
It adds no new data sources.

Spiderweb owns the federation spatial contracts, so it authors the three
contracts below. The other PRII producers (moneysweep-pr, aguayluz-pr,
skywatcher-pr, ovnis-pr) mirror them byte for byte, along with the
producer-agnostic router (`server/backend/gis_api.py`) and the stdlib-only
geometry module (`spiderweb/gis_query.py`).

## Contracts

| Schema | Contract | Used by |
|---|---|---|
| `schemas/gis_layer_catalog_v1.schema.json` | `gis-layer-catalog/1.0` | `GET /gis/catalog` |
| `schemas/gis_query_v1.schema.json` | `gis-query/1.0` | `POST /gis/query`, `POST /gis/export` (request) |
| `schemas/gis_scenario_result_v1.schema.json` | `gis-scenario-result/1.0` | `POST /gis/scenario` in producers that hold a dependency network (not spiderweb) |

The AOI geometry vocabulary (`point`, `radius`, `bbox`, `polygon`/`geojson`)
is copied from `schemas/location_query.schema.json`, so both APIs read the
same JSON. The two APIs have different jobs:
[LOCATION_QUERY](LOCATION_QUERY.md) plans *acquisition* of source data for an
AOI, while `gis-query` reads *features the producer already holds*.

Scenario results are always `evidence_state: HYPOTHESIS` and `persisted:
false`. They never enter canonical exports or federation streams.

## Catalog derivation

`GET /gis/catalog` is built by `spiderweb/gis_catalog.py` from three
registries. None of them is replaced:

1. `configs/layer_catalog.yaml` supplies the folder tree, labels, registry
   status and visibility class (V1/V2/V3 → `access_default`).
2. `configs/spatial_layer_bindings.yaml` supplies the rendering binding
   (format → `source.kind`).
3. `configs/gis_layer_interaction.yaml` supplies the identify, search and
   query fields, plus optional classification and temporal fields.

Every layer in `layer_catalog.yaml` appears in the catalog. Layers that have
no interaction entry show every property on identify and are not
searchable. `min_zoom`/`max_zoom` stay `null` until zoom thresholds are
measured against rendered output, the same rule `spatial_layer_bindings.yaml`
applies to camera heights. `data_available` is computed at request time.

## Endpoints

| Endpoint | What it does |
|---|---|
| `GET /gis/catalog` | Returns the `gis-layer-catalog/1.0` document. |
| `GET /gis/identify?lon&lat&tol_m=25&layers=a,b&limit=10` | Returns features within `tol_m` of the point, nearest first, showing only the layer's `identify_fields`. It also returns location context: the municipio and barrio that contain the point (when TIGER layers are ingested), and the PR Grid V2 cell under the cursor. |
| `GET /gis/search?q&layers&limit` | Ranks matches on each layer's `search_fields`: exact, then prefix, then word prefix, then substring. Matching ignores case and accents. It also parses typed coordinates (decimal degrees in either order, or DMS with hemisphere letters). |
| `POST /gis/query` | Runs a `gis-query/1.0` AOI query and returns per-layer `matched_count`, `returned_count`, `excluded_count` and `truncated`, plus a summary of classification-field value counts. The result has `evidence_state: COMPUTED`. |
| `POST /gis/export` | Takes the same body plus `format: geojson\|csv` and returns the AOI selection as a download. Only `PUBLIC` layers can be exported: `RESTRICTED` and `OBSERVE_ONLY` layers return 403, though they can still be viewed, identified and queried. |

Integrity rules carried by every response:

- **Missing geometry is counted, never guessed.** Features without usable
  geometry, or without a parseable time when a `time_range` is given, are
  counted in `excluded_count`. They are never dropped silently.
- **A missing artifact is not an error.** A layer with no backing artifact
  on this deployment returns `matched_count: 0` with `error: "no backing
  artifact on this deployment"`, not a 500.
- **The grid lookup is not a binding.** The PR Grid V2 identify lookup is
  marked `binding: CURSOR_LOOKUP_NOT_RECORD_BINDING`, because a click is not
  a `VERIFIED_SOURCE_COORDINATE`. Record-cell bindings still go only through
  `spiderweb/grid_v2_source_coordinates.py`. The lookup needs `pyproj`; when
  `pyproj` is missing it reports `status: UNAVAILABLE`.
- **Matches are not identities.** Identify, search and query report spatial
  relations, not identities.

## Map viewer tools (Spatial Intelligence, MapLibre runtime)

| Tool | Where |
|---|---|
| Search (places, features, coordinates) → fly/fit to result | `server/frontend/src/modules/GisViewerControls.tsx` |
| Home extent, previous/next extent, Shift-drag zoom to box, scale bar, cursor coordinates | `GisViewerControls.tsx`, `src/spatial/gis/extentHistory.ts` |
| Per-layer opacity | `GisViewerControls.tsx`, `src/spatial/gis/opacity.ts` |
| Save view to URL hash and named bookmarks | `src/spatial/gis/mapState.ts` |
| Print to PNG (with scale bar, north, extent and attribution) plus a JSON sidecar recording extent, zoom, layers and time | `src/spatial/gis/printMap.ts` |
| Identify, with Google Maps / Street View hand-off | `src/modules/SpatialToolsPanel.tsx`, `src/spatial/gis/externalLinks.ts` |
| Polygon query with GeoJSON/CSV export | `SpatialToolsPanel.tsx`, `src/spatial/gis/gisApi.ts` |
| Area measurement (spherical-excess ring area) | `SpatialToolsPanel.tsx`, `src/spatial/gis/measure.ts` |

Identify and polygon query run against exactly the catalog layers switched on
in the layer control. These tools are not available in the Cesium 3D mode,
the same as the existing measure, buffer and nearest tools.

## Tests

- `tests/test_gis_query.py` covers geometry, time, search and CSV primitives.
- `tests/test_gis_catalog.py` covers registry joins and validates the
  schemas.
- `tests/test_gis_location.py` covers boundary membership and the grid
  lookup.
- `tests/test_gis_api.py` runs the endpoints against the committed
  natural-features gazetteer.
- `server/frontend/src/spatial/gis/gis.test.ts` and
  `src/modules/SpatialToolsPanel.gis.test.tsx` cover the frontend.

Change impact is recorded in
`reports/federation_spatial_impact_gis_viewer_v1.json`.

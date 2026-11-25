# FAWS cartographic foundation — laboratory candidate
Operation: faws-v0.1.0/spiderweb/01-05
Baseline: 139bbc67f7c266c963d74872724e1fa36d0ee6dc
Governance proposal: TheHub PR 453, 6ebb83677864cf284f2d93157c4c6458f46073f5.
Reference consumer: Skywatcher PR 383.

Existing SpatialRuntime abstracts camera/lifecycle only; MapLibre-specific layers
remain in SpatialIntelligence. regionalScene uses a raster basemap; raster
features cannot be styled individually. Existing vector-tile overlays are the
migration path. Cesium camera scale equivalence is approximate. Existing
maplibre_layer_runtime_v1 schema, GIS map state and opacity helpers remain intact.

The opt-in resolver handles priority, opacity, visibility, and per-property
resolution trace. Stack order is explicit; callers must enforce trusted
precedence and mandatory attribution outside this surface. Neutral is an empty
patch preserving existing defaults, not a qualified visual reference. Priority
zero suppresses display even when visible is requested. No rendering, geometry,
source, analytical, or governance mutations occur in the resolver. Known layer
IDs must come from the trusted runtime catalog. No new engine or registry.

Gates 01/02 partial source audit; 03 neutral identity candidate; 04/05 narrow
typed contract and resolver candidate; 06 tests authored, execution unverified.
Missing: serialized schema, complete renderer capability matrix, vector
basemap, live catalog binding, renderer adapters, independent text/density
controls, viewport tolerance tests, source/provenance enforcement, persistence,
visual regressions and downstream integration. No production wiring or
certification. FAWS full qualification and durable execution remain withheld.

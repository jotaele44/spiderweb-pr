# FAWS renderer capability matrix — source audit only
Baseline: 176912c852d1ae7afc48e8f6482c60b8f064b258. TheHub PR 453; Spiderweb PR 481.
Canonical catalog: schemas/gis_layer_catalog_v1.schema.json, GET /gis/catalog.
The labels-only configs/layer_catalog.yaml is not proof of availability.
Use authorized catalog entries with active status and verified runtime availability;
do not override access_default, precision_max_zoom, attribution, geometry or source.
The serialized preset schema covers the existing three-property laboratory subset.
Runtime parsing/schema validation and catalog enforcement remain separate gates.

| Surface | MapLibre | Cesium |
|---|---|---|
| Neutral view | Existing raster style | Photorealistic tiles or grid |
| Camera lifecycle | Existing | Existing |
| Exact scale parity | Unverified | Approximate zoom conversion |
| Individual overlay visibility | Existing renderer-specific controls | Shared adapter not demonstrated |
| Overlay opacity | Existing helper | Shared adapter not demonstrated |
| Per-feature raster styling | Unsupported | Unsupported for baked imagery |
| Vector overlays | Existing municipio path; deployment availability unverified | Not demonstrated through shared interface |
| Priority and label composition | Laboratory intent only | Laboratory intent only |
| Geometry invariance | Intent-only tests | Live regression pending |

Canonical IDs observed in catalog: municipios, barrios, places, tracts, airports,
gazetteer_pr_domestic_names, water_reservoir, nid_dams, power_line, flights.
These are catalog identities, not assertions of live availability or public access.
Do not alias multiple datasets solely on their display names. Resolve remaining
roads, buildings, waterways, coastlines, elevation and aviation layers against
actual source bindings before profile activation.
No runtime adapter, live availability test, or qualification claimed.

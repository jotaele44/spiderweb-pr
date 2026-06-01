# GIS Export Guide

How to consume the pipeline's GeoJSON outputs in QGIS, Google Earth, and other GIS tools.

All spatial outputs use **EPSG:4326** (WGS-84 lat/lon). The `crs` member is declared inline in every FeatureCollection.

---

## What ships

The pipeline emits these GeoJSON artifacts (per [`SCHEMA_AND_EXPORT_CONTRACTS.md`](SCHEMA_AND_EXPORT_CONTRACTS.md)):

| File | Geometry | Schema | Contents |
|---|---|---|---|
| `gis_airspace_features.geojson` | `Point` | `gis_feature` | Airport nodes (origin + destination per flight, deduped) |
| `route_lines.geojson` | `LineString` | `gis_feature` | Origin→destination route lines per flight |
| `spiderweb_overlay_candidates.geojson` | `Point` | `spiderweb_observation` | Normalized POI / ILAP / corridor / AASB-edge candidates |
| `airspace_poi_candidates.geojson` | `Point` | `spiderweb_observation` | Raw POI candidates from the producer |
| `airspace_ilap_candidates.geojson` | `Point` / `LineString` | `ilap_corridor_candidate` | ILAP track candidates |
| `airspace_corridor_candidates.geojson` | `LineString` | `ilap_corridor_candidate` | Corridor candidates |

All carry per-feature **provenance** (`screenshot_id`, `sha256`, `source_path`) plus type-specific properties — see the relevant schema for the full list.

---

## QGIS

### Importing

1. **Drag-and-drop** the `.geojson` file from Finder/Explorer onto the QGIS map canvas.
2. QGIS auto-detects EPSG:4326 from the inline `crs` member — verify in the Layers panel (right-click → Properties → Source → CRS).
3. If the file is large (the full `screenshot_evidence` mirror can be ~50 MB), set rendering to "Render Layer Without Caching" the first time to avoid the cache-build pause.

### Symbology hints

- **Airport nodes** (`gis_airspace_features.geojson`): style by `properties.type` (currently always `"airport"`). Suggest a black-outlined yellow circle, 4 mm. Label by `properties.name`.
- **Route lines** (`route_lines.geojson`): style line width by `properties.duration_min` (longer flights = thicker). Categorize by `properties.callsign` for operator-color coding.
- **Spiderweb candidates** (`spiderweb_overlay_candidates.geojson`): categorize by `properties.evidence_tier` (T1 red, T2 orange, T3 yellow, T4 grey). Filter by `properties.mbil_class` to inspect built-up areas.
- **ILAP candidates**: style by `properties.overall_confidence` (graduated, 0–1).

### Joining with provenance

Every feature has `properties.screenshot_id` and `properties.source_path`. To audit a feature back to its source screenshot:

1. Open the feature's Attribute Table.
2. Copy `source_path` (e.g. `data/FR24_baseline/2025-08/2025-08-16T04-04-50_ec16e576.png`).
3. The path is relative to the repo root.

---

## Google Earth Pro

Google Earth doesn't read GeoJSON natively — it consumes KML/KMZ.

### Quick conversion (per file)

```
# Requires GDAL 2.4+ (Homebrew: brew install gdal)
ogr2ogr -f KML route_lines.kml outputs/route_lines.geojson
ogr2ogr -f KML gis_airspace_features.kml outputs/gis_airspace_features.geojson
```

Then **File → Open** the `.kml` in Google Earth Pro.

### Notes

- KML loses some GeoJSON properties (Google Earth's KML reader only displays a subset by default). Right-click the layer → Properties → Description to add a custom `<description>` template if you need all fields visible.
- Use Google Earth's Time Slider with `properties.takeoff_time` (when KML-converted with `--lco DateField=takeoff_time`) to animate a flight history.

### KML export — not yet implemented in-pipeline

The pipeline does **not** currently emit `.kml` directly. Two paths if you want this:

1. **Quick path (no new dependency):** the `ogr2ogr` one-liner above.
2. **Native KML export (deferred to [`NEXT_100_TASKS.md`](NEXT_100_TASKS.md), task 49):** add a thin `_export_kml` step in `integration/pr_intel_adapter.py` using `simplekml` (optional dep, `pip install simplekml`).

---

## Other tools

- **Mapbox Studio / MapLibre GL**: GeoJSON loads directly via the API. Use the `crs` member to confirm projection; set `cluster: true` on the airport-nodes source for clean zoom-out display.
- **Folium (Python notebook)**: `folium.GeoJson(path)` — set `style_function` to color by `properties.evidence_tier`. Use `tooltip=folium.GeoJsonTooltip(['name', 'callsign', 'evidence_tier'])` for inspect-on-hover.
- **kepler.gl**: drag-drop works; the auto-config defaults to a heatmap visualization. Manually switch to "GeoJSON" layer type for route lines.

---

## Validation

After importing into any GIS tool, sanity-check:

- **CRS** is EPSG:4326 (the loaded layer should show coordinates around `lon ≈ -67..-65`, `lat ≈ 17.5..18.6` for PR airspace).
- **Feature count** matches `source_manifest.json` → the relevant artifact's `geo_summary.feature_count`.
- **Bbox** matches `source_manifest.json` → `geo_summary.bbox` (the FeatureCollection extent is computed by `provenance_utils.feature_collection_summary()`).

If any of these drifts, the upstream pipeline likely emitted a stale artifact — re-run `--export-pr-intel` or `--export-spiderweb`.

---

## Cross-references

- [`SCHEMA_AND_EXPORT_CONTRACTS.md`](SCHEMA_AND_EXPORT_CONTRACTS.md) — per-artifact schema.
- [`SPIDERWEB_LANGUAGE_BRIDGE.md`](SPIDERWEB_LANGUAGE_BRIDGE.md) — canonical vocabulary for property values.
- [`RELEASE_READINESS.md`](RELEASE_READINESS.md) — gate that ensures these files are produced.

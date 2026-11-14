import type * as maplibregl from "maplibre-gl";
import type { EriDataset } from "./eriApi";
import { eriFootprintsUrl, eriTileUrlTemplate } from "./eriApi";

/**
 * MapLibre plumbing for the NOAA ERI imagery layer. Kept free of React so the
 * main map and the swipe-comparison map share one implementation.
 */

export const ERI_IMAGERY_ID = "eri-imagery";
export const ERI_FOOTPRINTS_ID = "eri-footprints";
export const ERI_FOOTPRINT_LAYERS = {
  fill: `${ERI_FOOTPRINTS_ID}-fill`,
  line: `${ERI_FOOTPRINTS_ID}-line`,
  selected: `${ERI_FOOTPRINTS_ID}-selected`,
} as const;

// Layer types that belong underneath imagery: the base map and its hillshade.
const BASE_LAYER_TYPES = new Set(["background", "raster", "hillshade"]);

/**
 * Id of the first overlay layer, so imagery is inserted above the base map but
 * below every vector overlay regardless of the order they were toggled in.
 */
export function firstOverlayLayerId(map: maplibregl.Map): string | undefined {
  const layers = map.getStyle()?.layers ?? [];
  return layers.find((layer) => !BASE_LAYER_TYPES.has(layer.type) && layer.id !== ERI_IMAGERY_ID)?.id;
}

export function removeEriImagery(map: maplibregl.Map): void {
  if (!map.getStyle()) return;
  if (map.getLayer(ERI_IMAGERY_ID)) map.removeLayer(ERI_IMAGERY_ID);
  if (map.getSource(ERI_IMAGERY_ID)) map.removeSource(ERI_IMAGERY_ID);
}

export function addEriImagery(
  map: maplibregl.Map,
  dataset: EriDataset,
  opacity: number,
  attribution: string,
): void {
  removeEriImagery(map);
  map.addSource(ERI_IMAGERY_ID, {
    type: "raster",
    tiles: [eriTileUrlTemplate(dataset.id)],
    tileSize: 256,
    // Below minzoom the backend refuses the tile (too many source images per
    // tile), so MapLibre must not ask; bounds stops requests off the flight.
    minzoom: dataset.min_zoom,
    maxzoom: dataset.max_zoom,
    bounds: dataset.bbox,
    attribution,
  });
  map.addLayer(
    {
      id: ERI_IMAGERY_ID,
      type: "raster",
      source: ERI_IMAGERY_ID,
      paint: { "raster-opacity": opacity, "raster-fade-duration": 150 },
    },
    firstOverlayLayerId(map),
  );
}

export function setEriImageryOpacity(map: maplibregl.Map, opacity: number): void {
  if (map.getLayer(ERI_IMAGERY_ID)) map.setPaintProperty(ERI_IMAGERY_ID, "raster-opacity", opacity);
}

export function removeEriFootprints(map: maplibregl.Map): void {
  if (!map.getStyle()) return;
  Object.values(ERI_FOOTPRINT_LAYERS).forEach((id) => {
    if (map.getLayer(id)) map.removeLayer(id);
  });
  if (map.getSource(ERI_FOOTPRINTS_ID)) map.removeSource(ERI_FOOTPRINTS_ID);
}

export function addEriFootprints(map: maplibregl.Map, dataset: EriDataset): void {
  removeEriFootprints(map);
  map.addSource(ERI_FOOTPRINTS_ID, { type: "geojson", data: eriFootprintsUrl(dataset.id) });
  // Invisible fill: the click target for "identify this image".
  map.addLayer({
    id: ERI_FOOTPRINT_LAYERS.fill,
    type: "fill",
    source: ERI_FOOTPRINTS_ID,
    paint: { "fill-color": "#ffd166", "fill-opacity": 0 },
  });
  map.addLayer({
    id: ERI_FOOTPRINT_LAYERS.line,
    type: "line",
    source: ERI_FOOTPRINTS_ID,
    paint: {
      "line-color": "#ffd166",
      // Coverage outline when zoomed out; recede once the pixels are visible.
      "line-opacity": ["interpolate", ["linear"], ["zoom"], 8, 0.9, dataset.min_zoom, 0.6, 17, 0.25],
      "line-width": ["interpolate", ["linear"], ["zoom"], 8, 0.4, 14, 1],
    },
  });
  map.addLayer({
    id: ERI_FOOTPRINT_LAYERS.selected,
    type: "line",
    source: ERI_FOOTPRINTS_ID,
    filter: ["==", ["get", "name"], ""],
    paint: { "line-color": "#ff5d73", "line-width": 2.5 },
  });
}

export function setSelectedFootprint(map: maplibregl.Map, name: string | null): void {
  if (map.getLayer(ERI_FOOTPRINT_LAYERS.selected)) {
    map.setFilter(ERI_FOOTPRINT_LAYERS.selected, ["==", ["get", "name"], name ?? ""]);
  }
}

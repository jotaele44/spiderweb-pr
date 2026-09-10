import * as maplibregl from "maplibre-gl";
import type { SpatialRuntime } from "./SpatialRuntime";
import {
  UnsupportedSpatialCapabilityError,
  assertFiniteWgs84Coordinate,
  type CircleRenderStyle,
  type PolygonRenderStyle,
  type SpatialAdapters,
  type SpatialLayerHandle,
  type SpatialMarkerHandle,
  type SpatialMarkerSpec,
  type VectorTilePolygonLayerSpec,
  type GeoJsonPolygonLayerSpec,
  type GeoJsonCircleLayerSpec,
} from "./SpatialAdapters";

function waitForStyle(map: maplibregl.Map): Promise<void> {
  if (map.isStyleLoaded()) return Promise.resolve();
  return new Promise((resolve) => {
    const onStyle = () => {
      if (!map.isStyleLoaded()) return;
      map.off("styledata", onStyle);
      resolve();
    };
    map.on("styledata", onStyle);
  });
}

function polygonLayerIds(id: string): [string, string] {
  return [`${id}-fill`, `${id}-line`];
}

function addPolygonPaint(
  map: maplibregl.Map,
  id: string,
  sourceId: string,
  style: PolygonRenderStyle,
  sourceLayer?: string,
): void {
  const [fillId, lineId] = polygonLayerIds(id);
  const common = sourceLayer ? { source: sourceId, "source-layer": sourceLayer } : { source: sourceId };
  map.addLayer({
    id: fillId,
    type: "fill",
    ...common,
    paint: { "fill-color": style.fillColor, "fill-opacity": style.fillOpacity },
  });
  map.addLayer({
    id: lineId,
    type: "line",
    ...common,
    layout: { "line-join": "round", "line-cap": "round" },
    paint: {
      "line-color": style.lineColor,
      "line-width": style.lineWidth ?? 0.8,
      "line-opacity": style.lineOpacity ?? 0.6,
    },
  });
}

function removePolygonPaint(map: maplibregl.Map, id: string): void {
  const [fillId, lineId] = polygonLayerIds(id);
  if (map.getLayer(lineId)) map.removeLayer(lineId);
  if (map.getLayer(fillId)) map.removeLayer(fillId);
}

function addCirclePaint(
  map: maplibregl.Map,
  id: string,
  sourceId: string,
  style: CircleRenderStyle,
): void {
  map.addLayer({
    id: `${id}-circle`,
    type: "circle",
    source: sourceId,
    paint: {
      "circle-radius": style.radius,
      "circle-color": style.color,
      "circle-opacity": style.opacity ?? 0.75,
      "circle-stroke-color": style.strokeColor ?? "#0b1220",
      "circle-stroke-width": style.strokeWidth ?? 0.5,
    },
  });
}

function removeCirclePaint(map: maplibregl.Map, id: string): void {
  const layerId = `${id}-circle`;
  if (map.getLayer(layerId)) map.removeLayer(layerId);
}

function removable(
  map: maplibregl.Map,
  sourceId: string,
  removePaint: () => void,
  removeError?: () => void,
): SpatialLayerHandle {
  let removed = false;
  return {
    remove() {
      if (removed) return;
      removed = true;
      removeError?.();
      if (!map.isStyleLoaded()) return;
      removePaint();
      if (map.getSource(sourceId)) map.removeSource(sourceId);
    },
  };
}

export function createMapLibreSpatialAdapters(
  map: maplibregl.Map,
  runtime: SpatialRuntime,
): SpatialAdapters {
  const layer = {
    capabilities: {
      geoJsonPolygon: true,
      geoJsonCircle: true,
      vectorTilePolygon: true,
    },
    async addGeoJsonPolygonLayer(spec: GeoJsonPolygonLayerSpec): Promise<SpatialLayerHandle> {
      await waitForStyle(map);
      const sourceId = spec.id;
      if (map.getSource(sourceId)) throw new Error(`spatial source already exists: ${sourceId}`);
      map.addSource(sourceId, { type: "geojson", data: spec.data });
      addPolygonPaint(map, spec.id, sourceId, spec.style);
      return removable(map, sourceId, () => removePolygonPaint(map, spec.id));
    },
    async addGeoJsonCircleLayer(spec: GeoJsonCircleLayerSpec): Promise<SpatialLayerHandle> {
      await waitForStyle(map);
      const sourceId = spec.id;
      if (map.getSource(sourceId)) throw new Error(`spatial source already exists: ${sourceId}`);
      map.addSource(sourceId, { type: "geojson", data: spec.data });
      addCirclePaint(map, spec.id, sourceId, spec.style);
      return removable(map, sourceId, () => removeCirclePaint(map, spec.id));
    },
    async addVectorTilePolygonLayer(spec: VectorTilePolygonLayerSpec): Promise<SpatialLayerHandle> {
      await waitForStyle(map);
      const sourceId = spec.id;
      if (map.getSource(sourceId)) throw new Error(`spatial source already exists: ${sourceId}`);
      const onError = (event: maplibregl.ErrorEvent) => {
        if ("sourceId" in event && event.sourceId === sourceId) spec.onError?.();
      };
      map.on("error", onError);
      map.addSource(sourceId, {
        type: "vector",
        tiles: spec.tiles,
        minzoom: spec.minZoom,
        maxzoom: spec.maxZoom,
      });
      addPolygonPaint(map, spec.id, sourceId, spec.style, spec.sourceLayer);
      return removable(
        map,
        sourceId,
        () => removePolygonPaint(map, spec.id),
        () => map.off("error", onError),
      );
    },
  };

  const marker = {
    supported: true,
    addMarker(spec: SpatialMarkerSpec): SpatialMarkerHandle {
      assertFiniteWgs84Coordinate(spec.coordinate);
      if (!Number.isFinite(spec.sizePx) || spec.sizePx <= 0) throw new Error("marker size must be positive");
      const el = document.createElement("button");
      el.type = "button";
      el.className = "map-marker";
      const tone = spec.tone === "alert" ? "var(--alert)" : spec.tone === "warning" ? "var(--warn)" : "var(--t1)";
      Object.assign(el.style, {
        width: `${spec.sizePx}px`,
        height: `${spec.sizePx}px`,
        borderRadius: "999px",
        border: "2px solid var(--surface-2)",
        background: tone,
        boxShadow: "0 0 0 1px var(--ink)",
      });
      el.title = spec.label;
      el.setAttribute("aria-label", spec.label);
      el.onclick = spec.onActivate;
      const instance = new maplibregl.Marker({ element: el }).setLngLat(spec.coordinate).addTo(map);
      return { remove: () => instance.remove() };
    },
  };

  const camera = {
    supported: true,
    setView: runtime.setView.bind(runtime),
    getView: runtime.getView.bind(runtime),
    resize: runtime.resize.bind(runtime),
  };

  return {
    renderer: "maplibre",
    capabilities: {
      geoJsonPolygon: true,
      geoJsonCircle: true,
      vectorTilePolygon: true,
      investigationMarker: true,
      camera: true,
      popup: false,
      featureSelection: false,
    },
    layer,
    marker,
    camera,
  };
}

export function unsupportedMapLibreCapability(capability: "popup" | "featureSelection"): never {
  throw new UnsupportedSpatialCapabilityError("maplibre", capability);
}

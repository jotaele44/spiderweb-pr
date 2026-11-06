/**
 * Per-layer opacity for catalog layers. Multiplies each style layer's
 * original opacity (captured on first use) by a factor in [0, 1], so a layer
 * drawn at 0.08 fill opacity keeps its relative look at factor 1.
 */
import type * as maplibregl from "maplibre-gl";

const OPACITY_PROPERTY: Record<string, string> = {
  fill: "fill-opacity",
  line: "line-opacity",
  circle: "circle-opacity",
  symbol: "icon-opacity",
  heatmap: "heatmap-opacity",
  raster: "raster-opacity",
  "fill-extrusion": "fill-extrusion-opacity",
};

type PaintProperty = Parameters<maplibregl.Map["getPaintProperty"]>[1];

const baseOpacity = new WeakMap<maplibregl.Map, Map<string, unknown>>();

export function opacityProperty(layerType: string): string | null {
  return OPACITY_PROPERTY[layerType] ?? null;
}

export function scaledOpacity(base: unknown, factor: number): unknown {
  const clamped = Math.min(1, Math.max(0, factor));
  if (typeof base === "number") return base * clamped;
  if (base === undefined || base === null) return clamped;
  // Data-driven base expression: scale it rather than replace it.
  return ["*", base, clamped];
}

/** Apply `factor` to every style layer drawing from `sourceId`; returns how many were changed. */
export function setSourceOpacity(map: maplibregl.Map, sourceId: string, factor: number): number {
  const style = map.getStyle();
  let cache = baseOpacity.get(map);
  if (!cache) {
    cache = new Map();
    baseOpacity.set(map, cache);
  }
  let changed = 0;
  for (const layer of style.layers ?? []) {
    if (!("source" in layer) || layer.source !== sourceId) continue;
    const property = opacityProperty(layer.type) as PaintProperty | null;
    if (!property) continue;
    if (!cache.has(layer.id)) cache.set(layer.id, map.getPaintProperty(layer.id, property));
    map.setPaintProperty(
      layer.id,
      property,
      scaledOpacity(cache.get(layer.id), factor) as Parameters<maplibregl.Map["setPaintProperty"]>[2],
    );
    changed += 1;
  }
  return changed;
}

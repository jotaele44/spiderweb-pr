import { MapLibreRuntime } from "./MapLibreRuntime";
import type { SpatialRuntime } from "./SpatialRuntime";

export type SpatialRuntimeMode = "maplibre" | "cesium";

export function createSpatialRuntime(mode: "maplibre"): MapLibreRuntime;
export function createSpatialRuntime(mode: SpatialRuntimeMode): SpatialRuntime {
  switch (mode) {
    case "maplibre":
      return new MapLibreRuntime();
    case "cesium":
      // Cesium is loaded eagerly here only for the (unused in practice) sync
      // overload path — real callers should use createCesiumRuntime() below,
      // which is what actually keeps Cesium out of the initial bundle.
      throw new Error("use createCesiumRuntime() for the lazy-loaded Cesium path");
  }
}

/**
 * Lazy-loaded Cesium path — Cesium (and vite-plugin-cesium's static assets)
 * are not pulled into the initial bundle. Only imported once a caller
 * actually asks for 3D mode.
 */
export async function createCesiumRuntime(): Promise<SpatialRuntime> {
  const { CesiumRegionalRuntime } = await import("./CesiumRegionalRuntime");
  return new CesiumRegionalRuntime();
}

import { MapLibreRuntime } from "./MapLibreRuntime";
import type { SpatialRuntime } from "./SpatialRuntime";

export type SpatialRuntimeMode = "maplibre" | "cesium";

// The only 2D runtime; the only real call site (useSpatialRuntime) always
// passes "maplibre" literally. Cesium boots separately via the lazy
// createCesiumRuntime() below, which is what actually keeps Cesium out of
// the initial bundle — this function has no mode argument or Cesium branch
// to avoid a misleading runtime throw for a value it can never receive.
export function createSpatialRuntime(): MapLibreRuntime {
  return new MapLibreRuntime();
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

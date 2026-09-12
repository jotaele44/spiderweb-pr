import type { SpatialRuntimeMode } from "../runtime/RuntimeFactory";

export const SPATIAL_MODE_STORAGE_KEY = "priis_spatial_mode";

export function readSpatialMode(storage?: Pick<Storage, "getItem">): SpatialRuntimeMode {
  try {
    const target = storage ?? globalThis.localStorage;
    return target.getItem(SPATIAL_MODE_STORAGE_KEY) === "cesium" ? "cesium" : "maplibre";
  } catch {
    return "maplibre";
  }
}

export function writeSpatialMode(
  mode: SpatialRuntimeMode,
  storage?: Pick<Storage, "setItem">,
): boolean {
  try {
    const target = storage ?? globalThis.localStorage;
    target.setItem(SPATIAL_MODE_STORAGE_KEY, mode);
    return true;
  } catch {
    return false;
  }
}

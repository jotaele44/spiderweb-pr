import { MapLibreRuntime } from "./MapLibreRuntime";
import type { SpatialRuntime } from "./SpatialRuntime";

export type SpatialRuntimeMode = "maplibre";

export function createSpatialRuntime(mode: "maplibre"): MapLibreRuntime;
export function createSpatialRuntime(mode: SpatialRuntimeMode): SpatialRuntime {
  switch (mode) {
    case "maplibre":
      return new MapLibreRuntime();
  }
}

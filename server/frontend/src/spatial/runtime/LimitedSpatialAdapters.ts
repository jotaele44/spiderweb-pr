import type { SpatialRuntime } from "./SpatialRuntime";
import {
  UnsupportedSpatialCapabilityError,
  type SpatialAdapters,
  type SpatialCapabilitySet,
  type SpatialRendererId,
} from "./SpatialAdapters";

const NO_OVERLAYS: SpatialCapabilitySet = {
  geoJsonPolygon: false,
  geoJsonCircle: false,
  vectorTilePolygon: false,
  investigationMarker: false,
  camera: true,
  popup: false,
  featureSelection: false,
};

/**
 * Explicit adapter for a renderer whose current bounded implementation only
 * supports camera lifecycle. This preserves the renderer's existing behavior
 * without returning null raw-map handles that silently erase capabilities.
 */
export function createCameraOnlySpatialAdapters(
  renderer: SpatialRendererId,
  runtime: SpatialRuntime,
): SpatialAdapters {
  const unsupported = (capability: keyof SpatialCapabilitySet): never => {
    throw new UnsupportedSpatialCapabilityError(renderer, capability);
  };

  return {
    renderer,
    capabilities: { ...NO_OVERLAYS },
    layer: {
      capabilities: {
        geoJsonPolygon: false,
        geoJsonCircle: false,
        vectorTilePolygon: false,
      },
      addGeoJsonPolygonLayer: async () => unsupported("geoJsonPolygon"),
      addGeoJsonCircleLayer: async () => unsupported("geoJsonCircle"),
      addVectorTilePolygonLayer: async () => unsupported("vectorTilePolygon"),
    },
    marker: {
      supported: false,
      addMarker: () => unsupported("investigationMarker"),
    },
    camera: {
      supported: true,
      setView: runtime.setView.bind(runtime),
      getView: runtime.getView.bind(runtime),
      resize: runtime.resize.bind(runtime),
    },
  };
}

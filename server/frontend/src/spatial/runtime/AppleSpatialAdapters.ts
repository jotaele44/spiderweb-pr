import type { AppleMapKitRuntime } from "./AppleMapKitRuntime";
import {
  UnsupportedSpatialCapabilityError,
  type GeoJsonCircleLayerSpec,
  type GeoJsonPolygonLayerSpec,
  type SpatialAdapters,
  type SpatialLayerHandle,
  type SpatialMarkerHandle,
  type SpatialMarkerSpec,
} from "./SpatialAdapters";

/**
 * The live MapKit JS bridge implements only semantic overlay operations. It
 * must not expose Apple tile URLs, raster bytes, caches, or internal provider
 * objects to domain code. Tests inject a credential-free fake bridge.
 */
export interface AppleOverlayBridge {
  addGeoJsonPolygonLayer(spec: GeoJsonPolygonLayerSpec): Promise<SpatialLayerHandle>;
  addGeoJsonCircleLayer(spec: GeoJsonCircleLayerSpec): Promise<SpatialLayerHandle>;
  addMarker(spec: SpatialMarkerSpec): SpatialMarkerHandle;
}

export function createAppleSpatialAdapters(
  runtime: AppleMapKitRuntime,
  overlayBridge: AppleOverlayBridge,
): SpatialAdapters {
  return {
    renderer: "apple-mapkit",
    capabilities: {
      geoJsonPolygon: true,
      geoJsonCircle: true,
      vectorTilePolygon: false,
      investigationMarker: true,
      camera: true,
      popup: false,
      featureSelection: false,
    },
    layer: {
      capabilities: {
        geoJsonPolygon: true,
        geoJsonCircle: true,
        vectorTilePolygon: false,
      },
      addGeoJsonPolygonLayer: (spec) => overlayBridge.addGeoJsonPolygonLayer(spec),
      addGeoJsonCircleLayer: (spec) => overlayBridge.addGeoJsonCircleLayer(spec),
      async addVectorTilePolygonLayer() {
        throw new UnsupportedSpatialCapabilityError("apple-mapkit", "vectorTilePolygon");
      },
    },
    marker: {
      supported: true,
      addMarker: (spec) => overlayBridge.addMarker(spec),
    },
    camera: {
      supported: true,
      setView(view, options) {
        // A canonical zoom→Apple camera-distance conversion is intentionally
        // not guessed here. The live bridge must supply a measured conversion
        // before this adapter is wired into useSpatialRuntime.
        void view;
        void options;
        throw new UnsupportedSpatialCapabilityError("apple-mapkit", "camera");
      },
      getView() {
        throw new UnsupportedSpatialCapabilityError("apple-mapkit", "camera");
      },
      resize() {
        // MapKit JS owns its host resize behavior; no provider pixel access is
        // exposed. Live parity still requires an observed resize regression.
      },
    },
  };
}

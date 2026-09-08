import {
  UnsupportedSpatialCapabilityError,
  type GeoJsonCircleLayerSpec,
  type GeoJsonPolygonLayerSpec,
  type SpatialAdapters,
  type SpatialCameraAdapter,
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

function unavailableCamera(): SpatialCameraAdapter {
  return {
    supported: false,
    setView() {
      throw new UnsupportedSpatialCapabilityError("apple-mapkit", "camera");
    },
    getView() {
      throw new UnsupportedSpatialCapabilityError("apple-mapkit", "camera");
    },
    resize() {
      throw new UnsupportedSpatialCapabilityError("apple-mapkit", "camera");
    },
  };
}

/**
 * `cameraBridge` is deliberately optional. Apple overlay parity can be tested
 * credential-free before camera parity, but the adapter advertises camera=false
 * until a measured zoom↔camera-distance bridge is supplied. This prevents a
 * deterministic approximation from being mislabeled as evidence of parity.
 */
export function createAppleSpatialAdapters(
  overlayBridge: AppleOverlayBridge,
  cameraBridge?: SpatialCameraAdapter,
): SpatialAdapters {
  const camera = cameraBridge ?? unavailableCamera();
  return {
    renderer: "apple-mapkit",
    capabilities: {
      geoJsonPolygon: true,
      geoJsonCircle: true,
      vectorTilePolygon: false,
      investigationMarker: true,
      camera: camera.supported,
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
    camera,
  };
}

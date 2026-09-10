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

export interface AppleOverlayCapabilities {
  geoJsonPolygon: boolean;
  geoJsonCircle: boolean;
  investigationMarker: boolean;
}

/**
 * The live MapKit JS bridge implements only semantic overlay operations. It
 * must not expose Apple tile URLs, raster bytes, caches, or internal provider
 * objects to domain code. Every supported capability is declared explicitly;
 * construction does not imply parity.
 */
export interface AppleOverlayBridge {
  readonly capabilities: AppleOverlayCapabilities;
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

export function createAppleSpatialAdapters(
  overlayBridge: AppleOverlayBridge,
  cameraBridge?: SpatialCameraAdapter,
): SpatialAdapters {
  const camera = cameraBridge ?? unavailableCamera();
  const supports = overlayBridge.capabilities;
  return {
    renderer: "apple-mapkit",
    capabilities: {
      geoJsonPolygon: supports.geoJsonPolygon,
      geoJsonCircle: supports.geoJsonCircle,
      vectorTilePolygon: false,
      investigationMarker: supports.investigationMarker,
      camera: camera.supported,
      popup: false,
      featureSelection: false,
    },
    layer: {
      capabilities: {
        geoJsonPolygon: supports.geoJsonPolygon,
        geoJsonCircle: supports.geoJsonCircle,
        vectorTilePolygon: false,
      },
      addGeoJsonPolygonLayer(spec) {
        if (!supports.geoJsonPolygon) {
          return Promise.reject(new UnsupportedSpatialCapabilityError("apple-mapkit", "geoJsonPolygon"));
        }
        return overlayBridge.addGeoJsonPolygonLayer(spec);
      },
      addGeoJsonCircleLayer(spec) {
        if (!supports.geoJsonCircle) {
          return Promise.reject(new UnsupportedSpatialCapabilityError("apple-mapkit", "geoJsonCircle"));
        }
        return overlayBridge.addGeoJsonCircleLayer(spec);
      },
      async addVectorTilePolygonLayer() {
        throw new UnsupportedSpatialCapabilityError("apple-mapkit", "vectorTilePolygon");
      },
    },
    marker: {
      supported: supports.investigationMarker,
      addMarker(spec) {
        if (!supports.investigationMarker) {
          throw new UnsupportedSpatialCapabilityError("apple-mapkit", "investigationMarker");
        }
        return overlayBridge.addMarker(spec);
      },
    },
    camera,
  };
}

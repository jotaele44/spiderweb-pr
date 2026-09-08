import { describe, expect, it, vi } from "vitest";
import type { GeoJSON } from "geojson";
import { createAppleSpatialAdapters, type AppleOverlayBridge } from "./AppleSpatialAdapters";
import { createCameraOnlySpatialAdapters } from "./LimitedSpatialAdapters";
import { assertFiniteWgs84Coordinate, UnsupportedSpatialCapabilityError, type SpatialCameraAdapter } from "./SpatialAdapters";
import type { SpatialRuntime } from "./SpatialRuntime";

function runtimeStub(): SpatialRuntime {
  return {
    initialize: vi.fn(async () => undefined),
    destroy: vi.fn(),
    setView: vi.fn(),
    getView: vi.fn(() => ({ center: [-66.1, 18.4], zoom: 9 })),
    resize: vi.fn(),
    onBasemapError: vi.fn(() => () => undefined),
  };
}

function appleBridgeStub(): AppleOverlayBridge {
  return {
    addGeoJsonPolygonLayer: vi.fn(async () => ({ remove: vi.fn() })),
    addGeoJsonCircleLayer: vi.fn(async () => ({ remove: vi.fn() })),
    addMarker: vi.fn(() => ({ remove: vi.fn() })),
  };
}

describe("renderer-neutral spatial capability gates", () => {
  it("accepts finite WGS84 edge coordinates and rejects invalid coordinates", () => {
    expect(() => assertFiniteWgs84Coordinate([-180, -90])).not.toThrow();
    expect(() => assertFiniteWgs84Coordinate([180, 90])).not.toThrow();
    expect(() => assertFiniteWgs84Coordinate([181, 0])).toThrow(/WGS84/);
    expect(() => assertFiniteWgs84Coordinate([0, 91])).toThrow(/WGS84/);
    expect(() => assertFiniteWgs84Coordinate([Number.NaN, 18])).toThrow(/finite/);
  });

  it("represents current Cesium overlay gaps explicitly rather than with null raw-map state", async () => {
    const adapters = createCameraOnlySpatialAdapters("cesium", runtimeStub());
    expect(adapters.capabilities).toEqual({
      geoJsonPolygon: false,
      geoJsonCircle: false,
      vectorTilePolygon: false,
      investigationMarker: false,
      camera: true,
      popup: false,
      featureSelection: false,
    });
    await expect(adapters.layer.addGeoJsonPolygonLayer({
      id: "x",
      data: { type: "FeatureCollection", features: [] },
      style: { fillOpacity: 0, fillColor: "#000", lineColor: "#000" },
    })).rejects.toBeInstanceOf(UnsupportedSpatialCapabilityError);
  });

  it("does not advertise Apple camera parity until a measured camera bridge is supplied", () => {
    const adapters = createAppleSpatialAdapters(appleBridgeStub());
    expect(adapters.capabilities.camera).toBe(false);
    expect(adapters.camera.supported).toBe(false);
    expect(() => adapters.camera.getView()).toThrow(UnsupportedSpatialCapabilityError);
  });

  it("advertises Apple camera only when an explicit bridge supplies it", () => {
    const camera: SpatialCameraAdapter = {
      supported: true,
      setView: vi.fn(),
      getView: vi.fn(() => ({ center: [-66.05, 18.45], zoom: 11 })),
      resize: vi.fn(),
    };
    const adapters = createAppleSpatialAdapters(appleBridgeStub(), camera);
    expect(adapters.capabilities.camera).toBe(true);
    expect(adapters.camera).toBe(camera);
  });

  it("passes canonical GeoJSON to the Apple semantic bridge without mutation", async () => {
    const data: GeoJSON = {
      type: "FeatureCollection",
      features: [{ type: "Feature", properties: { stable_id: "MUNI-001" }, geometry: null }],
    };
    const bridge = appleBridgeStub();
    const adapters = createAppleSpatialAdapters(bridge);
    const before = JSON.stringify(data);
    await adapters.layer.addGeoJsonPolygonLayer({
      id: "geo-municipios",
      data,
      style: { fillOpacity: 0.08, fillColor: "#4dc4d6", lineColor: "#4dc4d6", lineWidth: 0.8, lineOpacity: 0.6 },
    });
    expect(bridge.addGeoJsonPolygonLayer).toHaveBeenCalledOnce();
    expect((bridge.addGeoJsonPolygonLayer as ReturnType<typeof vi.fn>).mock.calls[0]?.[0].data).toBe(data);
    expect(JSON.stringify(data)).toBe(before);
  });
});

import { describe, expect, it, vi } from "vitest";
import type * as maplibregl from "maplibre-gl";
import type { GeoJSON } from "geojson";
import { createMapLibreSpatialAdapters } from "./MapLibreSpatialAdapters";
import type { SpatialRuntime } from "./SpatialRuntime";

function runtimeStub(): SpatialRuntime {
  return {
    initialize: vi.fn(async () => undefined),
    destroy: vi.fn(),
    setView: vi.fn(),
    getView: vi.fn(() => ({ center: [-66.4, 18.2], zoom: 9 })),
    resize: vi.fn(),
    onBasemapError: vi.fn(() => () => undefined),
  };
}

function mapStub() {
  const sources = new Map<string, unknown>();
  const layers = new Map<string, unknown>();
  const listeners = new Map<string, Set<(event: unknown) => void>>();
  const map = {
    isStyleLoaded: vi.fn(() => true),
    getSource: vi.fn((id: string) => sources.get(id)),
    addSource: vi.fn((id: string, source: unknown) => { sources.set(id, source); }),
    removeSource: vi.fn((id: string) => { sources.delete(id); }),
    getLayer: vi.fn((id: string) => layers.get(id)),
    addLayer: vi.fn((layer: { id: string }) => { layers.set(layer.id, layer); }),
    removeLayer: vi.fn((id: string) => { layers.delete(id); }),
    on: vi.fn((event: string, listener: (payload: unknown) => void) => {
      const set = listeners.get(event) ?? new Set();
      set.add(listener);
      listeners.set(event, set);
    }),
    off: vi.fn((event: string, listener: (payload: unknown) => void) => listeners.get(event)?.delete(listener)),
  };
  return {
    map: map as unknown as maplibregl.Map,
    sources,
    layers,
    emit(event: string, payload: unknown) {
      listeners.get(event)?.forEach((listener) => listener(payload));
    },
  };
}

const EMPTY_GEOJSON: GeoJSON = { type: "FeatureCollection", features: [] };

describe("MapLibre semantic adapters", () => {
  it("preserves source/layer identities and polygon paint semantics", async () => {
    const stub = mapStub();
    const adapters = createMapLibreSpatialAdapters(stub.map, runtimeStub());
    const handle = await adapters.layer.addGeoJsonPolygonLayer({
      id: "geo-municipios",
      data: EMPTY_GEOJSON,
      style: {
        fillColor: "#4dc4d6",
        fillOpacity: 0.08,
        lineColor: "#4dc4d6",
        lineWidth: 0.8,
        lineOpacity: 0.6,
      },
    });

    expect(stub.sources.get("geo-municipios")).toEqual({ type: "geojson", data: EMPTY_GEOJSON });
    expect(stub.layers.get("geo-municipios-fill")).toMatchObject({
      id: "geo-municipios-fill",
      type: "fill",
      source: "geo-municipios",
      paint: { "fill-color": "#4dc4d6", "fill-opacity": 0.08 },
    });
    expect(stub.layers.get("geo-municipios-line")).toMatchObject({
      id: "geo-municipios-line",
      type: "line",
      source: "geo-municipios",
      layout: { "line-join": "round", "line-cap": "round" },
      paint: { "line-color": "#4dc4d6", "line-width": 0.8, "line-opacity": 0.6 },
    });

    handle.remove();
    handle.remove();
    expect(stub.sources.has("geo-municipios")).toBe(false);
    expect(stub.layers.has("geo-municipios-fill")).toBe(false);
    expect(stub.layers.has("geo-municipios-line")).toBe(false);
  });

  it("preserves renderer-native point-circle styling", async () => {
    const stub = mapStub();
    const adapters = createMapLibreSpatialAdapters(stub.map, runtimeStub());
    await adapters.layer.addGeoJsonCircleLayer({
      id: "geo-gazetteer_pr_domestic_names",
      data: EMPTY_GEOJSON,
      style: { color: "#5eead4", radius: 2.5, opacity: 0.75, strokeColor: "#0b1220", strokeWidth: 0.5 },
    });
    expect(stub.layers.get("geo-gazetteer_pr_domestic_names-circle")).toMatchObject({
      type: "circle",
      source: "geo-gazetteer_pr_domestic_names",
      paint: {
        "circle-radius": 2.5,
        "circle-color": "#5eead4",
        "circle-opacity": 0.75,
        "circle-stroke-color": "#0b1220",
        "circle-stroke-width": 0.5,
      },
    });
  });

  it("scopes vector tile errors to the adapter source and removes the listener", async () => {
    const stub = mapStub();
    const onError = vi.fn();
    const adapters = createMapLibreSpatialAdapters(stub.map, runtimeStub());
    const handle = await adapters.layer.addVectorTilePolygonLayer({
      id: "mvt-municipios",
      tiles: ["/tiles/municipios/{z}/{x}/{y}.pbf"],
      sourceLayer: "municipios",
      minZoom: 0,
      maxZoom: 14,
      style: { fillColor: "#4dc4d6", fillOpacity: 0.08, lineColor: "#4dc4d6", lineWidth: 0.8, lineOpacity: 0.6 },
      onError,
    });

    stub.emit("error", { sourceId: "other-source" });
    expect(onError).not.toHaveBeenCalled();
    stub.emit("error", { sourceId: "mvt-municipios" });
    expect(onError).toHaveBeenCalledOnce();

    handle.remove();
    stub.emit("error", { sourceId: "mvt-municipios" });
    expect(onError).toHaveBeenCalledOnce();
  });
});

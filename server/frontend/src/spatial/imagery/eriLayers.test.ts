import { describe, expect, it } from "vitest";
import type * as maplibregl from "maplibre-gl";
import type { EriDataset } from "./eriApi";
import {
  ERI_FOOTPRINT_LAYERS,
  ERI_FOOTPRINTS_ID,
  ERI_IMAGERY_ID,
  addEriFootprints,
  addEriImagery,
  firstOverlayLayerId,
  removeEriFootprints,
  removeEriImagery,
  setEriImageryOpacity,
  setSelectedFootprint,
} from "./eriLayers";

const dataset: EriDataset = {
  id: "maria_20170924b",
  label: "Hurricane Maria",
  event: "2017_Hurricane_Maria",
  flight: "20170924b_RGB",
  kind: "post_event",
  acquired: "2017-09-24",
  bbox: [-66.78, 18.17, -65.57, 18.5],
  min_zoom: 14,
  max_zoom: 20,
  source_url: "https://noaa-eri-pds.s3.amazonaws.com/index.html#2017_Hurricane_Maria/20170924b_RGB/",
};

interface FakeLayer { id: string; type: string; source?: string; paint?: Record<string, unknown>; filter?: unknown }

/** Just enough of maplibregl.Map to observe layer order and source config. */
function fakeMap(initial: FakeLayer[]) {
  const layers = [...initial];
  const sources = new Map<string, Record<string, unknown>>();
  const map = {
    getStyle: () => ({ layers }),
    getLayer: (id: string) => layers.find((layer) => layer.id === id),
    getSource: (id: string) => sources.get(id),
    addSource: (id: string, source: Record<string, unknown>) => void sources.set(id, source),
    removeSource: (id: string) => void sources.delete(id),
    addLayer: (layer: FakeLayer, beforeId?: string) => {
      const at = beforeId ? layers.findIndex((entry) => entry.id === beforeId) : -1;
      if (at === -1) layers.push(layer);
      else layers.splice(at, 0, layer);
    },
    removeLayer: (id: string) => void layers.splice(layers.findIndex((layer) => layer.id === id), 1),
    setPaintProperty: (id: string, key: string, value: unknown) => {
      const layer = layers.find((entry) => entry.id === id);
      if (layer) layer.paint = { ...layer.paint, [key]: value };
    },
    setFilter: (id: string, filter: unknown) => {
      const layer = layers.find((entry) => entry.id === id);
      if (layer) layer.filter = filter;
    },
  };
  return { map: map as unknown as maplibregl.Map, layers, sources };
}

describe("ERI imagery layer", () => {
  it("is inserted above the base map and hillshade but below vector overlays", () => {
    const { map, layers, sources } = fakeMap([
      { id: "osm", type: "raster" },
      { id: "terrain-dem-hillshade", type: "hillshade" },
      { id: "geo-municipios-fill", type: "fill" },
      { id: "geo-municipios-line", type: "line" },
    ]);
    expect(firstOverlayLayerId(map)).toBe("geo-municipios-fill");
    addEriImagery(map, dataset, 0.7, "NOAA");
    expect(layers.map((layer) => layer.id)).toEqual([
      "osm",
      "terrain-dem-hillshade",
      ERI_IMAGERY_ID,
      "geo-municipios-fill",
      "geo-municipios-line",
    ]);
    expect(sources.get(ERI_IMAGERY_ID)).toMatchObject({
      type: "raster",
      tileSize: 256,
      minzoom: 14,
      maxzoom: 20,
      bounds: dataset.bbox,
      attribution: "NOAA",
    });
    expect(String((sources.get(ERI_IMAGERY_ID)?.tiles as string[])[0])).toContain(
      "/imagery/eri/maria_20170924b/tiles/{z}/{x}/{y}.png",
    );
    expect(layers[2].paint?.["raster-opacity"]).toBe(0.7);
  });

  it("goes on top when the map has no overlays", () => {
    const { map, layers } = fakeMap([{ id: "osm", type: "raster" }]);
    addEriImagery(map, dataset, 1, "NOAA");
    expect(layers.map((layer) => layer.id)).toEqual(["osm", ERI_IMAGERY_ID]);
  });

  it("replaces rather than duplicates on a second add, and removes cleanly", () => {
    const { map, layers, sources } = fakeMap([{ id: "osm", type: "raster" }]);
    addEriImagery(map, dataset, 1, "NOAA");
    addEriImagery(map, { ...dataset, id: "other_flight" }, 1, "NOAA");
    expect(layers.filter((layer) => layer.id === ERI_IMAGERY_ID)).toHaveLength(1);
    expect(String((sources.get(ERI_IMAGERY_ID)?.tiles as string[])[0])).toContain("other_flight");
    setEriImageryOpacity(map, 0.25);
    expect(layers[1].paint?.["raster-opacity"]).toBe(0.25);
    removeEriImagery(map);
    expect(layers.map((layer) => layer.id)).toEqual(["osm"]);
    expect(sources.has(ERI_IMAGERY_ID)).toBe(false);
  });
});

describe("ERI footprints", () => {
  it("adds outline, click-target and selection layers from the footprint GeoJSON", () => {
    const { map, layers, sources } = fakeMap([{ id: "osm", type: "raster" }]);
    addEriFootprints(map, dataset);
    expect(String(sources.get(ERI_FOOTPRINTS_ID)?.data)).toContain(
      "/imagery/eri/maria_20170924b/footprints.geojson",
    );
    expect(layers.slice(1).map((layer) => layer.id)).toEqual([
      ERI_FOOTPRINT_LAYERS.fill,
      ERI_FOOTPRINT_LAYERS.line,
      ERI_FOOTPRINT_LAYERS.selected,
    ]);
    setSelectedFootprint(map, "x.tif");
    expect(layers[layers.length - 1].filter).toEqual(["==", ["get", "name"], "x.tif"]);
    setSelectedFootprint(map, null);
    expect(layers[layers.length - 1].filter).toEqual(["==", ["get", "name"], ""]);
    removeEriFootprints(map);
    expect(layers.map((layer) => layer.id)).toEqual(["osm"]);
    expect(sources.has(ERI_FOOTPRINTS_ID)).toBe(false);
  });

  it("tolerates a map whose style is already gone", () => {
    const map = { getStyle: () => undefined } as unknown as maplibregl.Map;
    expect(() => {
      removeEriImagery(map);
      removeEriFootprints(map);
    }).not.toThrow();
  });
});

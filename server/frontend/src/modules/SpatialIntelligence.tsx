import { useEffect, useEffectEvent, useMemo, useRef, useState } from "react";
import type { Feature, GeoJSON, Point } from "geojson";
import * as maplibregl from "maplibre-gl";
import { point } from "@turf/helpers";
import { byId, fmtMoney } from "../lib/format";
import type { PriisData, Selection } from "../types/priis";
import { Pill } from "../components/Badges";
import { AnomalyCard } from "../components/AnomalyCard";
import {
  API_BASE,
  MUNICIPIOS_DELIVERY,
  martinTileJsonUrl,
  martinTileUrlTemplate,
} from "../config";
import { useSpatialRuntime } from "../spatial/runtime/useSpatialRuntime";
import { DEFAULT_REGIONAL_SCENE_CONFIG } from "../spatial/config/regionalScene";
import type { SpatialRuntimeMode } from "../spatial/runtime/RuntimeFactory";
import { useSpatialTools, SpatialToolsPanel } from "./SpatialToolsPanel";

type PolygonLayerKey = "municipios" | "tracts" | "places" | "barrios";
type PointLayerKey = "gazetteer_pr_domestic_names";
type MarkerLayerKey = "contracts" | "infrastructure" | "sensitive" | "anomaly";
type BackendLayerKey = PolygonLayerKey | PointLayerKey;
type LayerKey = MarkerLayerKey | BackendLayerKey;
export type LayerStatus = "idle" | "loading" | "source-ready" | "loaded" | "error";

interface PolygonLayerConfig {
  fillOpacity: number;
  lineColor: string;
  fillColor: string;
  defaultOn: boolean;
  label: string;
}

const POLYGON_LAYERS: Record<PolygonLayerKey, PolygonLayerConfig> = {
  municipios: { fillOpacity: 0.08, fillColor: "#4dc4d6", lineColor: "#4dc4d6", defaultOn: true, label: "Municipios" },
  tracts:     { fillOpacity: 0.04, fillColor: "#f4b740", lineColor: "#f4b740", defaultOn: false, label: "Census tracts" },
  places:     { fillOpacity: 0.05, fillColor: "#a07cff", lineColor: "#a07cff", defaultOn: false, label: "Places" },
  barrios:    { fillOpacity: 0.04, fillColor: "#6f7782", lineColor: "#6f7782", defaultOn: false, label: "Barrios" },
};

const POLYGON_LAYER_KEYS = Object.keys(POLYGON_LAYERS) as PolygonLayerKey[];

interface PointLayerConfig {
  color: string;
  radius: number;
  defaultOn: boolean;
  label: string;
}

// Rendered as a native GL circle layer, not maplibregl.Marker DOM elements
// (the pattern MarkerLayerKey/site markers below use): at ~2,000 features,
// one DOM node per point would be a real rendering-performance regression.
const POINT_LAYERS: Record<PointLayerKey, PointLayerConfig> = {
  gazetteer_pr_domestic_names: { color: "#5eead4", radius: 2.5, defaultOn: false, label: "Natural features" },
};

const POINT_LAYER_KEYS = Object.keys(POINT_LAYERS) as PointLayerKey[];
const BACKEND_LAYER_KEYS: BackendLayerKey[] = [...POLYGON_LAYER_KEYS, ...POINT_LAYER_KEYS];

const MARKER_LABELS: Record<MarkerLayerKey, string> = {
  contracts: "Contracts",
  infrastructure: "Infrastructure",
  sensitive: "Sensitive sites",
  anomaly: "Anomalies",
};

function isPolygonKey(key: LayerKey): key is PolygonLayerKey {
  return key in POLYGON_LAYERS;
}
function isPointKey(key: LayerKey): key is PointLayerKey {
  return key in POINT_LAYERS;
}
function isBackendKey(key: LayerKey): key is BackendLayerKey {
  return (BACKEND_LAYER_KEYS as string[]).includes(key);
}
function layerLabel(key: LayerKey): string {
  if (isPolygonKey(key)) return POLYGON_LAYERS[key].label;
  if (isPointKey(key)) return POINT_LAYERS[key].label;
  return MARKER_LABELS[key];
}

export function layerStatusText(enabled: boolean, status?: LayerStatus): string {
  if (!enabled) return "off";
  if (status === "loading") return "loading…";
  if (status === "source-ready") return "source ready";
  if (status === "loaded") return "rendered";
  if (status === "error") return "error";
  return "on";
}

function whenStyleReady(map: maplibregl.Map, fn: () => void) {
  if (map.isStyleLoaded()) { fn(); return; }
  const handler = () => {
    if (map.isStyleLoaded()) { map.off("styledata", handler); fn(); }
  };
  map.on("styledata", handler);
}

function addPolygonPaintLayers(
  map: maplibregl.Map,
  key: PolygonLayerKey,
  sourceId: string,
  sourceLayer?: string,
) {
  const cfg = POLYGON_LAYERS[key];
  const common = sourceLayer ? { source: sourceId, "source-layer": sourceLayer } : { source: sourceId };
  map.addLayer({
    id: `${sourceId}-fill`,
    type: "fill",
    ...common,
    paint: { "fill-color": cfg.fillColor, "fill-opacity": cfg.fillOpacity },
  });
  map.addLayer({
    id: `${sourceId}-line`,
    type: "line",
    ...common,
    layout: { "line-join": "round", "line-cap": "round" },
    paint: { "line-color": cfg.lineColor, "line-width": 0.8, "line-opacity": 0.6 },
  });
}

function removePolygonPaintLayers(map: maplibregl.Map, sourceId: string) {
  if (map.getLayer(`${sourceId}-line`)) map.removeLayer(`${sourceId}-line`);
  if (map.getLayer(`${sourceId}-fill`)) map.removeLayer(`${sourceId}-fill`);
}

function addCirclePaintLayer(map: maplibregl.Map, key: PointLayerKey, sourceId: string) {
  const cfg = POINT_LAYERS[key];
  map.addLayer({
    id: `${sourceId}-circle`,
    type: "circle",
    source: sourceId,
    paint: {
      "circle-radius": cfg.radius,
      "circle-color": cfg.color,
      "circle-opacity": 0.75,
      "circle-stroke-color": "#0b1220",
      "circle-stroke-width": 0.5,
    },
  });
}

function removeCirclePaintLayer(map: maplibregl.Map, sourceId: string) {
  if (map.getLayer(`${sourceId}-circle`)) map.removeLayer(`${sourceId}-circle`);
}

function useGeoJsonLayer(opts: {
  mapRef: React.MutableRefObject<maplibregl.Map | null>;
  ready: boolean;
  sourceId: string;
  url: string;
  isOn: boolean;
  addLayers: (map: maplibregl.Map, sourceId: string) => void;
  removeLayers: (map: maplibregl.Map) => void;
  onStatus: (status: LayerStatus) => void;
  /** Property to key feature-state by (e.g. "GEOID" for the density overlay). */
  promoteId?: string;
}) {
  const { mapRef, ready, sourceId, url, isOn, promoteId } = opts;
  const addLayers = useEffectEvent(opts.addLayers);
  const removeLayers = useEffectEvent(opts.removeLayers);
  const onStatus = useEffectEvent(opts.onStatus);

  useEffect(() => {
    const candidate = mapRef.current;
    if (candidate === null) return;
    const map: maplibregl.Map = candidate;

    function teardown() {
      removeLayers(map);
      if (map.getSource(sourceId)) map.removeSource(sourceId);
    }

    if (!isOn) {
      if (map.isStyleLoaded()) teardown();
      onStatus("idle");
      return;
    }

    const controller = new AbortController();
    let cancelled = false;

    async function load() {
      if (cancelled || map.getSource(sourceId)) return;
      onStatus("loading");
      try {
        const res = await fetch(url, { signal: controller.signal });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const geojson = (await res.json()) as GeoJSON;
        if (cancelled) return;
        // Backend/source retrieval succeeded. Do not call this rendered until
        // MapLibre's style is actually ready and the source/layers are attached.
        onStatus("source-ready");
        whenStyleReady(map, () => {
          if (cancelled || map.getSource(sourceId)) return;
          map.addSource(sourceId, { type: "geojson", data: geojson, ...(promoteId ? { promoteId } : {}) });
          addLayers(map, sourceId);
          onStatus("loaded");
        });
      } catch (err) {
        if (cancelled || (err instanceof DOMException && err.name === "AbortError")) return;
        onStatus("error");
      }
    }
    void load();

    return () => {
      cancelled = true;
      controller.abort();
      if (map.isStyleLoaded()) teardown();
    };
  }, [mapRef, ready, sourceId, url, isOn, promoteId]);
}

function useVectorTileLayer(opts: {
  mapRef: React.MutableRefObject<maplibregl.Map | null>;
  ready: boolean;
  sourceId: string;
  martinSourceId: string;
  sourceLayer: string;
  isOn: boolean;
  addLayers: (map: maplibregl.Map, sourceId: string, sourceLayer: string) => void;
  removeLayers: (map: maplibregl.Map) => void;
  onStatus: (status: LayerStatus) => void;
  /** Property to key feature-state by (e.g. "GEOID" for the density overlay). */
  promoteId?: string;
}) {
  const { mapRef, ready, sourceId, martinSourceId, sourceLayer, isOn, promoteId } = opts;
  const addLayers = useEffectEvent(opts.addLayers);
  const removeLayers = useEffectEvent(opts.removeLayers);
  const onStatus = useEffectEvent(opts.onStatus);

  useEffect(() => {
    const candidate = mapRef.current;
    if (candidate === null) return;
    const map: maplibregl.Map = candidate;

    function teardown() {
      removeLayers(map);
      if (map.getSource(sourceId)) map.removeSource(sourceId);
    }

    if (!isOn) {
      if (map.isStyleLoaded()) teardown();
      onStatus("idle");
      return;
    }

    const controller = new AbortController();
    let cancelled = false;
    const onMapError = (event: maplibregl.ErrorEvent) => {
      if ("sourceId" in event && event.sourceId === sourceId) onStatus("error");
    };
    map.on("error", onMapError);

    async function load() {
      if (cancelled || map.getSource(sourceId)) return;
      onStatus("loading");
      try {
        const res = await fetch(martinTileJsonUrl(martinSourceId), { signal: controller.signal });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const tilejson = (await res.json()) as {
          minzoom?: number;
          maxzoom?: number;
          tiles?: string[];
          vector_layers?: { id?: string }[];
        };
        if (!(tilejson.tiles ?? []).length) throw new Error("TileJSON has no tiles");
        if (tilejson.vector_layers?.length) {
          const advertised = new Set(tilejson.vector_layers.map((item) => item.id));
          if (!advertised.has(sourceLayer)) throw new Error(`missing source-layer ${sourceLayer}`);
        }
        if (cancelled) return;
        onStatus("source-ready");
        whenStyleReady(map, () => {
          if (cancelled || map.getSource(sourceId)) return;
          map.addSource(sourceId, {
            type: "vector",
            tiles: [martinTileUrlTemplate(martinSourceId)],
            minzoom: tilejson.minzoom ?? 0,
            maxzoom: tilejson.maxzoom ?? 14,
            ...(promoteId ? { promoteId: { [sourceLayer]: promoteId } } : {}),
          });
          addLayers(map, sourceId, sourceLayer);
          onStatus("loaded");
        });
      } catch (err) {
        if (cancelled || (err instanceof DOMException && err.name === "AbortError")) return;
        onStatus("error");
      }
    }
    void load();

    return () => {
      cancelled = true;
      controller.abort();
      map.off("error", onMapError);
      if (map.isStyleLoaded()) teardown();
    };
  }, [mapRef, ready, sourceId, martinSourceId, sourceLayer, isOn, promoteId]);
}

function usePolygonLayer(
  mapRef: React.MutableRefObject<maplibregl.Map | null>,
  ready: boolean,
  key: PolygonLayerKey,
  isOn: boolean,
  onStatus: (status: LayerStatus) => void,
  promoteId?: string,
) {
  const sourceId = `geo-${key}`;
  useGeoJsonLayer({
    mapRef,
    ready,
    sourceId,
    url: `${API_BASE}/geo/${key}.geojson`,
    isOn,
    onStatus,
    promoteId,
    addLayers: (map: maplibregl.Map, id: string) => addPolygonPaintLayers(map, key, id),
    removeLayers: (map: maplibregl.Map) => removePolygonPaintLayers(map, sourceId),
  });
}

function usePointLayer(
  mapRef: React.MutableRefObject<maplibregl.Map | null>,
  ready: boolean,
  key: PointLayerKey,
  isOn: boolean,
  onStatus: (status: LayerStatus) => void,
) {
  const sourceId = `geo-${key}`;
  useGeoJsonLayer({
    mapRef,
    ready,
    sourceId,
    url: `${API_BASE}/geo/${key}.geojson`,
    isOn,
    onStatus,
    addLayers: (map: maplibregl.Map, id: string) => addCirclePaintLayer(map, key, id),
    removeLayers: (map: maplibregl.Map) => removeCirclePaintLayer(map, sourceId),
  });
}

export function SpatialIntelligence({
  data,
  selection,
  setSelection,
  leftCollapsed = false,
  rightCollapsed = false,
}: {
  data: PriisData;
  selection: Selection | null;
  setSelection: (selection: Selection) => void;
  leftCollapsed?: boolean;
  rightCollapsed?: boolean;
}) {
  const [spatialMode, setSpatialMode] = useState<SpatialRuntimeMode>(
    () => (localStorage.getItem("priis_spatial_mode") === "cesium" ? "cesium" : "maplibre"),
  );
  const {
    hostRef,
    mapRef,
    runtimeRef,
    ready: mapReady,
    tilesFailed,
    setTilesFailed,
    activeMode,
    fallbackReason,
  } = useSpatialRuntime(DEFAULT_REGIONAL_SCENE_CONFIG, spatialMode);
  const markersRef = useRef<maplibregl.Marker[]>([]);
  const [layerStatus, setLayerStatus] = useState<Partial<Record<BackendLayerKey, LayerStatus>>>({});
  const [layerPanelCollapsed, setLayerPanelCollapsed] = useState(
    () => localStorage.getItem("spiderweb_layer_collapsed") === "true",
  );
  const [layers, setLayers] = useState<Record<LayerKey, boolean>>(() => ({
    contracts: true,
    infrastructure: true,
    sensitive: true,
    anomaly: true,
    ...(Object.fromEntries(
      POLYGON_LAYER_KEYS.map((k) => [k, POLYGON_LAYERS[k].defaultOn]),
    ) as Record<PolygonLayerKey, boolean>),
    ...(Object.fromEntries(
      POINT_LAYER_KEYS.map((k) => [k, POINT_LAYERS[k].defaultOn]),
    ) as Record<PointLayerKey, boolean>),
  }));

  const setStatus = (key: BackendLayerKey) => (status: LayerStatus) =>
    setLayerStatus((prev) => (prev[key] === status ? prev : { ...prev, [key]: status }));

  const municipiosViaMartin = MUNICIPIOS_DELIVERY === "martin";

  useVectorTileLayer({
    mapRef,
    ready: mapReady,
    sourceId: "mvt-municipios",
    martinSourceId: "municipios",
    sourceLayer: "municipios",
    isOn: layers.municipios && municipiosViaMartin,
    onStatus: setStatus("municipios"),
    promoteId: "GEOID",
    addLayers: (map, sourceId, sourceLayer) => addPolygonPaintLayers(map, "municipios", sourceId, sourceLayer),
    removeLayers: (map) => removePolygonPaintLayers(map, "mvt-municipios"),
  });
  usePolygonLayer(
    mapRef,
    mapReady,
    "municipios",
    layers.municipios && !municipiosViaMartin,
    setStatus("municipios"),
    "GEOID",
  );
  const municipiosSourceId = municipiosViaMartin ? "mvt-municipios" : "geo-municipios";
  usePolygonLayer(mapRef, mapReady, "tracts", layers.tracts, setStatus("tracts"));
  usePolygonLayer(mapRef, mapReady, "places", layers.places, setStatus("places"));
  usePolygonLayer(mapRef, mapReady, "barrios", layers.barrios, setStatus("barrios"));
  usePointLayer(
    mapRef,
    mapReady,
    "gazetteer_pr_domestic_names",
    layers.gazetteer_pr_domestic_names,
    setStatus("gazetteer_pr_domestic_names"),
  );

  // Map lifecycle (init/destroy/basemap-error) lives in useSpatialRuntime now;
  // this effect only handles the marker-specific part of unmount cleanup.
  useEffect(() => {
    return () => {
      markersRef.current.forEach((m) => m.remove());
      markersRef.current = [];
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];
    data.sites.forEach((site) => {
      const contractTotal = data.contracts
        .filter((c) => c.site === site.id)
        .reduce((sum, c) => sum + c.amount, 0);
      const anomaly = data.anomalies.find((a) => a.siteId === site.id);
      const visible =
        (layers.sensitive && (site.sensitive ?? false)) ||
        (layers.infrastructure && !!site.infrastructure_class) ||
        (layers.contracts && contractTotal > 0) ||
        (layers.anomaly && !!anomaly);
      if (!visible) return;
      const el = document.createElement("button");
      el.type = "button";
      el.className = "map-marker";
      const size = `${Math.max(14, Math.sqrt(contractTotal / 1_000_000) * 5)}px`;
      Object.assign(el.style, {
        width: size,
        height: size,
        borderRadius: "999px",
        border: "2px solid var(--surface-2)",
        background: anomaly ? "var(--alert)" : site.sensitive ? "var(--warn)" : "var(--t1)",
        boxShadow: "0 0 0 1px var(--ink)",
      });
      const markerLabel = `${site.name} · ${fmtMoney(contractTotal)} · ${anomaly?.id ?? "no anomaly"}`;
      el.title = markerLabel;
      el.setAttribute("aria-label", markerLabel);
      el.onclick = () =>
        setSelection({
          kind: anomaly && layers.anomaly ? "anomaly" : "site",
          id: anomaly && layers.anomaly ? anomaly.id : site.id,
        });
      const marker = new maplibregl.Marker({ element: el })
        .setLngLat([site.lng, site.lat])
        .addTo(map);
      markersRef.current.push(marker);
    });
  }, [data, layers, setSelection, mapRef]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime || selection?.kind !== "site") return;
    const site = byId(data.sites, selection.id);
    if (site) runtime.setView({ center: [site.lng, site.lat], zoom: 11 }, { animate: true, speed: 0.8 });
  }, [data.sites, selection, runtimeRef]);

  const spatialToolTargets = useMemo(() => ({
    Sites: () =>
      data.sites.map((site) =>
        point([site.lng, site.lat], { name: site.name, id: site.id }),
      ),
    "Natural features": () => {
      const map = mapRef.current;
      if (!map || !layers.gazetteer_pr_domestic_names) return [];
      return map.querySourceFeatures("geo-gazetteer_pr_domestic_names") as unknown as Feature<Point>[];
    },
  }), [data.sites, layers.gazetteer_pr_domestic_names, mapRef]);
  // Only attaches when the MapLibre (2D) runtime is active — mapRef stays
  // null in Cesium mode, so these tools simply don't render there yet.
  const spatialTools = useSpatialTools({ mapRef, mapReady, targets: spatialToolTargets });

  // Gazetteer-density choropleth: off by default, and only meaningful with
  // the municipios boundary layer itself on (there's nothing to shade
  // otherwise). Reuses the municipios source's GEOID promoteId above for
  // feature-state, the same technique as aguayluz-pr's drought/event-density
  // fills.
  const [densityOn, setDensityOn] = useState(false);
  const [densityByGeoid, setDensityByGeoid] = useState<Record<string, number> | null>(null);
  const toggleDensity = () => {
    setDensityOn((v) => {
      if (v) setDensityByGeoid(null);
      return !v;
    });
  };
  useEffect(() => {
    if (!densityOn) return;
    const controller = new AbortController();
    fetch(`${API_BASE}/geo/municipios/density?layer=gazetteer_pr_domestic_names`, { signal: controller.signal })
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
      .then((body: { by_geoid: Record<string, number> }) => setDensityByGeoid(body.by_geoid))
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setDensityByGeoid({});
      });
    return () => controller.abort();
  }, [densityOn]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const densityLayerId = "municipios-density-fill";
    function apply() {
      if (!map) return;
      if (!densityOn || !densityByGeoid || !map.getSource(municipiosSourceId)) {
        if (map.getLayer(densityLayerId)) map.removeLayer(densityLayerId);
        return;
      }
      const maxCount = Math.max(1, ...Object.values(densityByGeoid));
      for (const [geoid, count] of Object.entries(densityByGeoid)) {
        map.setFeatureState(
          { source: municipiosSourceId, id: geoid, ...(municipiosViaMartin ? { sourceLayer: "municipios" } : {}) },
          { density: count / maxCount },
        );
      }
      if (!map.getLayer(densityLayerId)) {
        map.addLayer({
          id: densityLayerId,
          type: "fill",
          source: municipiosSourceId,
          ...(municipiosViaMartin ? { "source-layer": "municipios" } : {}),
          paint: {
            "fill-color": [
              "interpolate", ["linear"], ["coalesce", ["feature-state", "density"], 0],
              0, "rgba(94, 234, 212, 0.05)",
              1, "rgba(94, 234, 212, 0.75)",
            ],
            "fill-opacity": 1,
          },
        });
      }
    }
    if (map.isStyleLoaded()) apply();
    else map.once("styledata", apply);
  }, [densityOn, densityByGeoid, mapReady, mapRef, municipiosSourceId, municipiosViaMartin]);

  useEffect(() => {
    localStorage.setItem("spiderweb_layer_collapsed", String(layerPanelCollapsed));
  }, [layerPanelCollapsed]);

  // Persist the requested 2D/3D mode. Note this is the *requested* mode
  // (spatialMode), not activeMode — if Cesium fails and useSpatialRuntime
  // falls back to MapLibre, we still remember "cesium" was requested so the
  // next visit retries it rather than silently sticking on the fallback.
  useEffect(() => {
    localStorage.setItem("priis_spatial_mode", spatialMode);
  }, [spatialMode]);

  // "L" toggles the layer panel. Ignore while typing in an input/textarea.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)) return;
      if (event.key === "l" || event.key === "L") {
        event.preventDefault();
        setLayerPanelCollapsed((value) => !value);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => runtimeRef.current?.resize(), 320);
    return () => window.clearTimeout(timer);
  }, [leftCollapsed, rightCollapsed, layerPanelCollapsed, runtimeRef]);

  const failedLayers = BACKEND_LAYER_KEYS.filter((k) => layers[k] && layerStatus[k] === "error");

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h1>Spatial Intelligence</h1>
          <span className="subtle">MapLibre layer control · contract, infrastructure, anomaly convergence</span>
        </div>
        <div className="row">
          <button
            className="act"
            data-on={!layerPanelCollapsed}
            aria-pressed={!layerPanelCollapsed}
            onClick={() => setLayerPanelCollapsed((value) => !value)}
            title="Toggle layer panel (L)"
          >
            {layerPanelCollapsed ? "Show layers" : "Hide layers"}
          </button>
          <button
            className="act"
            data-on={spatialMode === "cesium"}
            onClick={() => setSpatialMode((m) => (m === "cesium" ? "maplibre" : "cesium"))}
            title="Toggle 2D/3D scene"
          >
            {spatialMode === "cesium" ? "3D (regional preview)" : "2D"}
          </button>
          <Pill tone="info">{activeMode === "cesium" ? "Cesium (regional)" : "MapLibre GL JS"}</Pill>
        </div>
      </div>
      {fallbackReason && (
        <div className="map-note" role="status">
          <span>3D scene unavailable ({fallbackReason}) — showing 2D instead.</span>
        </div>
      )}
      <div
        className="map-shell"
        data-layer-collapsed={layerPanelCollapsed}
        style={{ gridTemplateColumns: layerPanelCollapsed ? "1fr 0px" : "1fr 280px" }}
      >
        <div className="map-col">
          <div ref={hostRef} className="map-host" />
          {activeMode === "maplibre" && failedLayers.length > 0 && (
            <div className="map-error" role="alert">
              <span>Layer data unavailable — backend offline: {failedLayers.map(layerLabel).join(", ")}</span>
            </div>
          )}
          {tilesFailed && (
            <div className="map-note" role="status">
              <span>Base map tiles unavailable (offline?)</span>
              <button className="linklike" onClick={() => setTilesFailed(false)} aria-label="Dismiss base map note">dismiss</button>
            </div>
          )}
        </div>
        <aside className="layer-panel">
          {activeMode === "maplibre" && (
            <>
              <SpatialToolsPanel {...spatialTools} />
              <div className="hr" />
            </>
          )}
          <h2>Layer control</h2>
          {(Object.entries(layers) as [LayerKey, boolean][]).map(([key, value]) => {
            const status = isBackendKey(key) && value ? layerStatus[key] : undefined;
            return (
              <button
                key={key}
                className="navbtn"
                data-active={value}
                data-status={status}
                aria-pressed={value}
                onClick={() => setLayers((cur) => ({ ...cur, [key]: !cur[key] }))}
              >
                <span>{layerLabel(key)}</span>
                <span>{layerStatusText(value, status)}</span>
              </button>
            );
          })}
          {activeMode === "maplibre" && layers.municipios && (
            <button
              className="navbtn"
              data-active={densityOn}
              aria-pressed={densityOn}
              onClick={toggleDensity}
              title="Shade municipios by natural-features (gazetteer) density"
            >
              <span>Gazetteer density</span>
              <span>{densityOn ? (densityByGeoid ? "on" : "loading…") : "off"}</span>
            </button>
          )}
          <div className="hr" />
          <h2>Top spatial anomalies</h2>
          <div className="col">
            {data.anomalies.map((anomaly) => (
              <AnomalyCard
                key={anomaly.id}
                anomaly={anomaly}
                heading={anomaly.id}
                body={byId(data.sites, anomaly.siteId)?.name}
                onClick={() => setSelection({ kind: "anomaly", id: anomaly.id })}
              />
            ))}
          </div>
        </aside>
      </div>
    </section>
  );
}

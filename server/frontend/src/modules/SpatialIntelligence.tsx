import { useEffect, useEffectEvent, useMemo, useRef, useState, type MutableRefObject } from "react";
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
import type {
  PolygonRenderStyle,
  CircleRenderStyle,
  SpatialAdapters,
  SpatialCapabilitySet,
  SpatialLayerHandle,
  SpatialMarkerHandle,
} from "../spatial/runtime/SpatialAdapters";
import { useSpatialTools, SpatialToolsPanel } from "./SpatialToolsPanel";

type PolygonLayerKey = "municipios" | "tracts" | "places" | "barrios";
type PointLayerKey = "gazetteer_pr_domestic_names";
type MarkerLayerKey = "contracts" | "infrastructure" | "sensitive" | "anomaly";
type BackendLayerKey = PolygonLayerKey | PointLayerKey;
type LayerKey = MarkerLayerKey | BackendLayerKey;
export type LayerStatus = "idle" | "loading" | "source-ready" | "loaded" | "unsupported" | "error";

interface DensityEnvelope {
  byGeoid: Record<string, number>;
  matchedCount: number;
  totalFeatures: number;
  unmatchedCount: number;
  scopeState: string;
}

export type DensityLoadState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; data: DensityEnvelope }
  | { status: "error"; message: string };

function objectValue(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("density response must be an object");
  }
  return value as Record<string, unknown>;
}

function nonNegativeInteger(value: unknown, field: string) {
  if (!Number.isInteger(value) || Number(value) < 0) throw new Error(`${field} must be a non-negative integer`);
  return Number(value);
}

export function parseDensityEnvelope(value: unknown): DensityEnvelope {
  const body = objectValue(value);
  const rawByGeoid = objectValue(body.by_geoid);
  const byGeoid: Record<string, number> = {};
  for (const [geoid, count] of Object.entries(rawByGeoid)) {
    byGeoid[geoid] = nonNegativeInteger(count, `by_geoid.${geoid}`);
  }
  const matchedCount = nonNegativeInteger(body.matched_count, "matched_count");
  const unmatchedCount = nonNegativeInteger(body.unmatched, "unmatched");
  const totalFeatures = nonNegativeInteger(body.total_features, "total_features");
  if (matchedCount !== Object.values(byGeoid).reduce((sum, count) => sum + count, 0)) {
    throw new Error("matched_count does not equal the by_geoid sum");
  }
  if (matchedCount + unmatchedCount !== totalFeatures) {
    throw new Error("density arithmetic does not close");
  }
  const scope = objectValue(body.scope);
  if (scope.identity_effect !== "NONE") throw new Error("density identity_effect must be NONE");
  return {
    byGeoid,
    matchedCount,
    totalFeatures,
    unmatchedCount,
    scopeState: typeof scope.state === "string" ? scope.state : "UNRESOLVED",
  };
}

export function densityStatusText(enabled: boolean, state: DensityLoadState) {
  if (!enabled) return "off";
  if (state.status === "loading" || state.status === "idle") return "loading...";
  if (state.status === "error") return "error";
  if (state.data.matchedCount > 0) return "rendered";
  if (state.data.totalFeatures > 0) return "unresolved";
  return "empty source";
}

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
  if (status === "unsupported") return "unsupported";
  if (status === "error") return "error";
  return "on";
}

function polygonStyle(key: PolygonLayerKey): PolygonRenderStyle {
  const cfg = POLYGON_LAYERS[key];
  return {
    fillOpacity: cfg.fillOpacity,
    fillColor: cfg.fillColor,
    lineColor: cfg.lineColor,
    lineWidth: 0.8,
    lineOpacity: 0.6,
  };
}

function circleStyle(key: PointLayerKey): CircleRenderStyle {
  const cfg = POINT_LAYERS[key];
  return {
    color: cfg.color,
    radius: cfg.radius,
    opacity: 0.75,
    strokeColor: "#0b1220",
    strokeWidth: 0.5,
  };
}

function useGeoJsonLayer(opts: {
  adaptersRef: MutableRefObject<SpatialAdapters | null>;
  capabilities: SpatialCapabilitySet | null;
  ready: boolean;
  id: string;
  url: string;
  isOn: boolean;
  kind: "polygon" | "circle";
  style: PolygonRenderStyle | CircleRenderStyle;
  onStatus: (status: LayerStatus) => void;
  promoteId?: string;
}) {
  const { adaptersRef, capabilities, ready, id, url, isOn, kind, style, promoteId } = opts;
  const onStatus = useEffectEvent(opts.onStatus);
  const styleRef = useRef(style);
  const styleSignature = JSON.stringify(style);

  useEffect(() => {
    styleRef.current = style;
  }, [style, styleSignature]);

  useEffect(() => {
    const adapters = adaptersRef.current;
    if (!ready || !adapters) return;
    if (!isOn) {
      onStatus("idle");
      return;
    }
    const supported = kind === "polygon" ? capabilities?.geoJsonPolygon : capabilities?.geoJsonCircle;
    if (supported === false) {
      onStatus("unsupported");
      return;
    }
    if (supported !== true) return;
    const layerAdapter = adapters.layer;

    const controller = new AbortController();
    let cancelled = false;
    let handle: SpatialLayerHandle | null = null;

    async function load() {
      onStatus("loading");
      try {
        const res = await fetch(url, { signal: controller.signal });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const geojson = (await res.json()) as GeoJSON;
        if (cancelled) return;
        onStatus("source-ready");
        const currentStyle = styleRef.current;
        const created = kind === "polygon"
          ? await layerAdapter.addGeoJsonPolygonLayer({ id, data: geojson, style: currentStyle as PolygonRenderStyle, promoteId })
          : await layerAdapter.addGeoJsonCircleLayer({ id, data: geojson, style: currentStyle as CircleRenderStyle });
        if (cancelled) {
          created.remove();
          return;
        }
        handle = created;
        onStatus("loaded");
      } catch (err) {
        if (cancelled || (err instanceof DOMException && err.name === "AbortError")) return;
        onStatus("error");
      }
    }
    void load();

    return () => {
      cancelled = true;
      controller.abort();
      handle?.remove();
    };
  }, [adaptersRef, capabilities, ready, id, url, isOn, kind, styleSignature, promoteId]);
}

function useVectorTileLayer(opts: {
  adaptersRef: MutableRefObject<SpatialAdapters | null>;
  capabilities: SpatialCapabilitySet | null;
  ready: boolean;
  id: string;
  martinSourceId: string;
  sourceLayer: string;
  isOn: boolean;
  style: PolygonRenderStyle;
  onStatus: (status: LayerStatus) => void;
  promoteId?: string;
}) {
  const { adaptersRef, capabilities, ready, id, martinSourceId, sourceLayer, isOn, style, promoteId } = opts;
  const onStatus = useEffectEvent(opts.onStatus);
  const styleRef = useRef(style);
  const styleSignature = JSON.stringify(style);

  useEffect(() => {
    styleRef.current = style;
  }, [style, styleSignature]);

  useEffect(() => {
    const adapters = adaptersRef.current;
    if (!ready || !adapters) return;
    if (!isOn) {
      onStatus("idle");
      return;
    }
    if (capabilities?.vectorTilePolygon === false) {
      onStatus("unsupported");
      return;
    }
    if (capabilities?.vectorTilePolygon !== true) return;
    const layerAdapter = adapters.layer;

    const controller = new AbortController();
    let cancelled = false;
    let handle: SpatialLayerHandle | null = null;

    async function load() {
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
        const created = await layerAdapter.addVectorTilePolygonLayer({
          id,
          tiles: [martinTileUrlTemplate(martinSourceId)],
          sourceLayer,
          minZoom: tilejson.minzoom ?? 0,
          maxZoom: tilejson.maxzoom ?? 14,
          style: styleRef.current,
          promoteId,
          onError: () => onStatus("error"),
        });
        if (cancelled) {
          created.remove();
          return;
        }
        handle = created;
        onStatus("loaded");
      } catch (err) {
        if (cancelled || (err instanceof DOMException && err.name === "AbortError")) return;
        onStatus("error");
      }
    }
    void load();

    return () => {
      cancelled = true;
      controller.abort();
      handle?.remove();
    };
  }, [adaptersRef, capabilities, ready, id, martinSourceId, sourceLayer, isOn, styleSignature, promoteId]);
}

function usePolygonLayer(
  adaptersRef: MutableRefObject<SpatialAdapters | null>,
  capabilities: SpatialCapabilitySet | null,
  ready: boolean,
  key: PolygonLayerKey,
  isOn: boolean,
  onStatus: (status: LayerStatus) => void,
  promoteId?: string,
) {
  useGeoJsonLayer({
    adaptersRef,
    capabilities,
    ready,
    id: `geo-${key}`,
    url: `${API_BASE}/geo/${key}.geojson`,
    isOn,
    kind: "polygon",
    style: polygonStyle(key),
    onStatus,
    promoteId,
  });
}

function usePointLayer(
  adaptersRef: MutableRefObject<SpatialAdapters | null>,
  capabilities: SpatialCapabilitySet | null,
  ready: boolean,
  key: PointLayerKey,
  isOn: boolean,
  onStatus: (status: LayerStatus) => void,
) {
  useGeoJsonLayer({
    adaptersRef,
    capabilities,
    ready,
    id: `geo-${key}`,
    url: `${API_BASE}/geo/${key}.geojson`,
    isOn,
    kind: "circle",
    style: circleStyle(key),
    onStatus,
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
    adaptersRef,
    capabilities,
    ready: mapReady,
    tilesFailed,
    setTilesFailed,
    activeMode,
    fallbackReason,
  } = useSpatialRuntime(DEFAULT_REGIONAL_SCENE_CONFIG, spatialMode);
  const markersRef = useRef<SpatialMarkerHandle[]>([]);
  const spatialToolActiveRef = useRef(false);
  const densityGeoidsRef = useRef<Set<string>>(new Set());
  const [layerStatus, setLayerStatus] = useState<Partial<Record<BackendLayerKey, LayerStatus>>>({});
  const [layerPanelCollapsed, setLayerPanelCollapsed] = useState(
    () => localStorage.getItem("spiderweb_layer_collapsed") === "true",
  );
  const [layers, setLayers] = useState<Record<LayerKey, boolean>>(() => ({
    contracts: true,
    infrastructure: true,
    sensitive: true,
    anomaly: true,
    ...(Object.fromEntries(POLYGON_LAYER_KEYS.map((key) => [key, POLYGON_LAYERS[key].defaultOn])) as Record<PolygonLayerKey, boolean>),
    ...(Object.fromEntries(POINT_LAYER_KEYS.map((key) => [key, POINT_LAYERS[key].defaultOn])) as Record<PointLayerKey, boolean>),
  }));

  const setStatus = (key: BackendLayerKey) => (status: LayerStatus) =>
    setLayerStatus((previous) => (previous[key] === status ? previous : { ...previous, [key]: status }));

  const municipiosViaMartin = MUNICIPIOS_DELIVERY === "martin" && capabilities?.vectorTilePolygon === true;

  useVectorTileLayer({
    adaptersRef,
    capabilities,
    ready: mapReady,
    id: "mvt-municipios",
    martinSourceId: "municipios",
    sourceLayer: "municipios",
    isOn: layers.municipios && municipiosViaMartin,
    style: polygonStyle("municipios"),
    onStatus: setStatus("municipios"),
    promoteId: "GEOID",
  });
  usePolygonLayer(adaptersRef, capabilities, mapReady, "municipios", layers.municipios && !municipiosViaMartin, setStatus("municipios"), "GEOID");
  const municipiosSourceId = municipiosViaMartin ? "mvt-municipios" : "geo-municipios";
  usePolygonLayer(adaptersRef, capabilities, mapReady, "tracts", layers.tracts, setStatus("tracts"));
  usePolygonLayer(adaptersRef, capabilities, mapReady, "places", layers.places, setStatus("places"));
  usePolygonLayer(adaptersRef, capabilities, mapReady, "barrios", layers.barrios, setStatus("barrios"));
  usePointLayer(adaptersRef, capabilities, mapReady, "gazetteer_pr_domestic_names", layers.gazetteer_pr_domestic_names, setStatus("gazetteer_pr_domestic_names"));

  useEffect(() => () => {
    markersRef.current.forEach((marker) => marker.remove());
    markersRef.current = [];
  }, []);

  useEffect(() => {
    const adapters = adaptersRef.current;
    if (!mapReady || !adapters) return;
    markersRef.current.forEach((marker) => marker.remove());
    markersRef.current = [];
    if (!adapters.marker.supported) return;

    data.sites.forEach((site) => {
      const contractTotal = data.contracts.filter((contract) => contract.site === site.id).reduce((sum, contract) => sum + contract.amount, 0);
      const anomaly = data.anomalies.find((item) => item.siteId === site.id);
      const visible =
        (layers.sensitive && (site.sensitive ?? false)) ||
        (layers.infrastructure && !!site.infrastructure_class) ||
        (layers.contracts && contractTotal > 0) ||
        (layers.anomaly && !!anomaly);
      if (!visible) return;

      const sizePx = Math.max(14, Math.sqrt(contractTotal / 1_000_000) * 5);
      const markerLabel = `${site.name} · ${fmtMoney(contractTotal)} · ${anomaly?.id ?? "no anomaly"}`;
      markersRef.current.push(adapters.marker.addMarker({
        coordinate: [site.lng, site.lat],
        label: markerLabel,
        sizePx,
        tone: anomaly ? "alert" : site.sensitive ? "warning" : "primary",
        onActivate: () => {
          if (spatialToolActiveRef.current) return;
          setSelection({
            kind: anomaly && layers.anomaly ? "anomaly" : "site",
            id: anomaly && layers.anomaly ? anomaly.id : site.id,
          });
        },
      }));
    });

    return () => {
      markersRef.current.forEach((marker) => marker.remove());
      markersRef.current = [];
    };
  }, [data, layers, setSelection, adaptersRef, capabilities, mapReady]);

  useEffect(() => {
    const camera = adaptersRef.current?.camera;
    if (!camera?.supported || selection?.kind !== "site") return;
    const site = byId(data.sites, selection.id);
    if (site) camera.setView({ center: [site.lng, site.lat], zoom: 11 }, { animate: true, speed: 0.8 });
  }, [data.sites, selection, adaptersRef, capabilities]);

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
  const spatialTools = useSpatialTools({ mapRef, mapReady, targets: spatialToolTargets, interactionLockRef: spatialToolActiveRef });

  const [densityOn, setDensityOn] = useState(false);
  const [densityState, setDensityState] = useState<DensityLoadState>({ status: "idle" });
  const [densityRequest, setDensityRequest] = useState(0);
  const densityByGeoid = densityState.status === "ready" ? densityState.data.byGeoid : null;
  const toggleDensity = () => {
    if (densityOn) {
      setDensityOn(false);
      setDensityState({ status: "idle" });
      return;
    }
    setDensityState({ status: "loading" });
    setDensityOn(true);
  };
  const retryDensity = () => {
    setDensityState({ status: "loading" });
    setDensityRequest((request) => request + 1);
  };
  useEffect(() => {
    if (!densityOn) return;
    const controller = new AbortController();
    async function loadDensity() {
      try {
        const response = await fetch(
          `${API_BASE}/geo/municipios/density?layer=gazetteer_pr_domestic_names`,
          { signal: controller.signal },
        );
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const rawBody = await response.json() as unknown;
        setDensityState({ status: "ready", data: parseDensityEnvelope(rawBody) });
      } catch (error: unknown) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setDensityState({ status: "error", message: error instanceof Error ? error.message : String(error) });
      }
    }
    void loadDensity();
    return () => controller.abort();
  }, [densityOn, densityRequest]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || activeMode !== "maplibre") return;
    const densityMap = map;
    const densityLayerId = "municipios-density-fill";
    const featureTarget = {
      source: municipiosSourceId,
      ...(municipiosViaMartin ? { sourceLayer: "municipios" } : {}),
    };
    function clearDensityState() {
      for (const geoid of densityGeoidsRef.current) {
        densityMap.removeFeatureState({ ...featureTarget, id: geoid }, "density");
      }
      densityGeoidsRef.current.clear();
    }
    function removeDensityLayer() {
      try {
        clearDensityState();
      } catch {
        // The source may be temporarily absent during renderer/style swaps.
      }
      if (densityMap.getLayer(densityLayerId)) densityMap.removeLayer(densityLayerId);
    }
    function apply() {
      if (!densityOn || !densityByGeoid || !densityMap.getSource(municipiosSourceId)) {
        removeDensityLayer();
        return;
      }
      try {
        clearDensityState();
      } catch {
        // Source data events will retry once the promoted source is available.
      }
      if (Object.keys(densityByGeoid).length === 0) {
        if (densityMap.getLayer(densityLayerId)) densityMap.removeLayer(densityLayerId);
        return;
      }
      const maxCount = Math.max(1, ...Object.values(densityByGeoid));
      for (const [geoid, count] of Object.entries(densityByGeoid)) {
        densityMap.setFeatureState(
          { source: municipiosSourceId, id: geoid, ...(municipiosViaMartin ? { sourceLayer: "municipios" } : {}) },
          { density: count / maxCount },
        );
        densityGeoidsRef.current.add(geoid);
      }
      if (!densityMap.getLayer(densityLayerId)) {
        densityMap.addLayer({
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
    const onSourceData = (event: maplibregl.MapSourceDataEvent) => {
      if (event.sourceId === municipiosSourceId && event.isSourceLoaded) apply();
    };
    if (map.isStyleLoaded()) apply();
    else map.once("styledata", apply);
    map.on("sourcedata", onSourceData);
    return () => {
      map.off("sourcedata", onSourceData);
    };
  }, [activeMode, densityOn, densityByGeoid, mapReady, mapRef, municipiosSourceId, municipiosViaMartin]);

  useEffect(() => {
    localStorage.setItem("spiderweb_layer_collapsed", String(layerPanelCollapsed));
  }, [layerPanelCollapsed]);

  useEffect(() => {
    localStorage.setItem("priis_spatial_mode", spatialMode);
  }, [spatialMode]);

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
    const timer = window.setTimeout(() => {
      const camera = adaptersRef.current?.camera;
      if (camera?.supported) camera.resize();
    }, 320);
    return () => window.clearTimeout(timer);
  }, [leftCollapsed, rightCollapsed, layerPanelCollapsed, adaptersRef, capabilities]);

  const failedLayers = BACKEND_LAYER_KEYS.filter((key) => layers[key] && layerStatus[key] === "error");
  const unsupportedLayers = BACKEND_LAYER_KEYS.filter((key) => layers[key] && layerStatus[key] === "unsupported");

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h1>Spatial Intelligence</h1>
          <span className="subtle">Renderer-neutral layer control · contract, infrastructure, anomaly convergence</span>
        </div>
        <div className="row">
          <button className="act" data-on={!layerPanelCollapsed} aria-pressed={!layerPanelCollapsed} onClick={() => setLayerPanelCollapsed((value) => !value)} title="Toggle layer panel (L)">
            {layerPanelCollapsed ? "Show layers" : "Hide layers"}
          </button>
          <button className="act" data-on={spatialMode === "cesium"} onClick={() => setSpatialMode((mode) => (mode === "cesium" ? "maplibre" : "cesium"))} title="Toggle 2D/3D scene">
            {spatialMode === "cesium" ? "3D (regional preview)" : "2D"}
          </button>
          <Pill tone="info">{activeMode === "cesium" ? "Cesium (regional)" : "MapLibre GL JS"}</Pill>
        </div>
      </div>
      {fallbackReason && <div className="map-note" role="status"><span>3D scene unavailable ({fallbackReason}) — showing 2D instead.</span></div>}
      <div className="map-shell" data-layer-collapsed={layerPanelCollapsed} style={{ gridTemplateColumns: layerPanelCollapsed ? "1fr 0px" : "1fr 280px" }}>
        <div className="map-col">
          <div ref={hostRef} className="map-host" />
          {failedLayers.length > 0 && <div className="map-error" role="alert"><span>Layer data unavailable — backend offline: {failedLayers.map(layerLabel).join(", ")}</span></div>}
          {unsupportedLayers.length > 0 && <div className="map-note" role="status"><span>Active renderer does not support: {unsupportedLayers.map(layerLabel).join(", ")}</span></div>}
          {tilesFailed && <div className="map-note" role="status"><span>Base map tiles unavailable (offline?)</span><button className="linklike" onClick={() => setTilesFailed(false)} aria-label="Dismiss base map note">dismiss</button></div>}
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
              <button key={key} className="navbtn" data-active={value} data-status={status} aria-pressed={value} onClick={() => setLayers((current) => ({ ...current, [key]: !current[key] }))}>
                <span>{layerLabel(key)}</span><span>{layerStatusText(value, status)}</span>
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
              <span>Gazetteer density</span><span>{densityStatusText(densityOn, densityState)}</span>
            </button>
          )}
          {activeMode === "maplibre" && layers.municipios && densityOn && densityState.status === "error" && (
            <div className="map-error" role="alert">
              <span>Density unavailable; no zero-feature inference was made. {densityState.message}</span>
              <button className="linklike" onClick={retryDensity}>retry</button>
            </div>
          )}
          {activeMode === "maplibre" && layers.municipios && densityOn && densityState.status === "ready" && (
            <div className="map-note" role="status">
              <span>{densityState.data.matchedCount} matched · {densityState.data.unmatchedCount} unresolved · {densityState.data.totalFeatures} total · identity effect NONE · {densityState.data.scopeState}</span>
            </div>
          )}
          <div className="hr" />
          <h2>Top spatial anomalies</h2>
          <div className="col">
            {data.anomalies.map((anomaly) => <AnomalyCard key={anomaly.id} anomaly={anomaly} heading={anomaly.id} body={byId(data.sites, anomaly.siteId)?.name} onClick={() => setSelection({ kind: "anomaly", id: anomaly.id })} />)}
          </div>
        </aside>
      </div>
    </section>
  );
}

import { useEffect, useEffectEvent, useRef, useState, type MutableRefObject } from "react";
import type { GeoJSON } from "geojson";
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

type PolygonLayerKey = "municipios" | "tracts" | "places" | "barrios";
type PointLayerKey = "gazetteer_pr_domestic_names";
type MarkerLayerKey = "contracts" | "infrastructure" | "sensitive" | "anomaly";
type BackendLayerKey = PolygonLayerKey | PointLayerKey;
type LayerKey = MarkerLayerKey | BackendLayerKey;
export type LayerStatus = "idle" | "loading" | "source-ready" | "loaded" | "unsupported" | "error";

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

// Kept as a renderer-native point layer rather than thousands of DOM markers.
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
}) {
  const { adaptersRef, capabilities, ready, id, url, isOn, kind, style } = opts;
  const onStatus = useEffectEvent(opts.onStatus);

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
        const created = kind === "polygon"
          ? await adapters.layer.addGeoJsonPolygonLayer({ id, data: geojson, style: style as PolygonRenderStyle })
          : await adapters.layer.addGeoJsonCircleLayer({ id, data: geojson, style: style as CircleRenderStyle });
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
  }, [adaptersRef, capabilities, ready, id, url, isOn, kind, style]);
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
}) {
  const { adaptersRef, capabilities, ready, id, martinSourceId, sourceLayer, isOn, style } = opts;
  const onStatus = useEffectEvent(opts.onStatus);

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
        const created = await adapters.layer.addVectorTilePolygonLayer({
          id,
          tiles: [martinTileUrlTemplate(martinSourceId)],
          sourceLayer,
          minZoom: tilejson.minzoom ?? 0,
          maxZoom: tilejson.maxzoom ?? 14,
          style,
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
  }, [adaptersRef, capabilities, ready, id, martinSourceId, sourceLayer, isOn, style]);
}

function usePolygonLayer(
  adaptersRef: MutableRefObject<SpatialAdapters | null>,
  capabilities: SpatialCapabilitySet | null,
  ready: boolean,
  key: PolygonLayerKey,
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
    kind: "polygon",
    style: polygonStyle(key),
    onStatus,
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
    adaptersRef,
    capabilities,
    ready: mapReady,
    tilesFailed,
    setTilesFailed,
    activeMode,
    fallbackReason,
  } = useSpatialRuntime(DEFAULT_REGIONAL_SCENE_CONFIG, spatialMode);
  const markersRef = useRef<SpatialMarkerHandle[]>([]);
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

  // Martin remains the preferred MapLibre delivery path. A renderer that does
  // not implement vector tiles falls back to the same canonical GeoJSON rather
  // than silently losing municipios.
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
  });
  usePolygonLayer(
    adaptersRef,
    capabilities,
    mapReady,
    "municipios",
    layers.municipios && !municipiosViaMartin,
    setStatus("municipios"),
  );
  usePolygonLayer(adaptersRef, capabilities, mapReady, "tracts", layers.tracts, setStatus("tracts"));
  usePolygonLayer(adaptersRef, capabilities, mapReady, "places", layers.places, setStatus("places"));
  usePolygonLayer(adaptersRef, capabilities, mapReady, "barrios", layers.barrios, setStatus("barrios"));
  usePointLayer(
    adaptersRef,
    capabilities,
    mapReady,
    "gazetteer_pr_domestic_names",
    layers.gazetteer_pr_domestic_names,
    setStatus("gazetteer_pr_domestic_names"),
  );

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
      const contractTotal = data.contracts
        .filter((contract) => contract.site === site.id)
        .reduce((sum, contract) => sum + contract.amount, 0);
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
        onActivate: () => setSelection({
          kind: anomaly && layers.anomaly ? "anomaly" : "site",
          id: anomaly && layers.anomaly ? anomaly.id : site.id,
        }),
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
            onClick={() => setSpatialMode((mode) => (mode === "cesium" ? "maplibre" : "cesium"))}
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
          {failedLayers.length > 0 && (
            <div className="map-error" role="alert">
              <span>Layer data unavailable — backend offline: {failedLayers.map(layerLabel).join(", ")}</span>
            </div>
          )}
          {unsupportedLayers.length > 0 && (
            <div className="map-note" role="status">
              <span>Active renderer does not support: {unsupportedLayers.map(layerLabel).join(", ")}</span>
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
                onClick={() => setLayers((current) => ({ ...current, [key]: !current[key] }))}
              >
                <span>{layerLabel(key)}</span>
                <span>{layerStatusText(value, status)}</span>
              </button>
            );
          })}
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

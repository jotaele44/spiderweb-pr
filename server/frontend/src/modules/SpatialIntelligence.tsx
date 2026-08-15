import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import { byId, fmtMoney } from "../lib/format";
import type { PriisData, Selection } from "../types/priis";
import { Pill } from "../components/Badges";
import { AnomalyCard } from "../components/AnomalyCard";
import {
  API_BASE,
  MUNICIPIOS_DELIVERY,
  TILE_ATTRIBUTION,
  TILE_URL,
  martinTileJsonUrl,
  martinTileUrlTemplate,
} from "../config";

const rasterStyle: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: [TILE_URL],
      tileSize: 256,
      attribution: TILE_ATTRIBUTION,
    },
  },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
};

type PolygonLayerKey = "municipios" | "tracts" | "places" | "barrios";
type MarkerLayerKey = "contracts" | "infrastructure" | "sensitive" | "anomaly";
type BackendLayerKey = PolygonLayerKey;
type LayerKey = MarkerLayerKey | BackendLayerKey;

type LayerStatus = "idle" | "loading" | "loaded" | "error";

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
const BACKEND_LAYER_KEYS: BackendLayerKey[] = [...POLYGON_LAYER_KEYS];

const MARKER_LABELS: Record<MarkerLayerKey, string> = {
  contracts: "Contracts",
  infrastructure: "Infrastructure",
  sensitive: "Sensitive sites",
  anomaly: "Anomalies",
};

function isPolygonKey(key: LayerKey): key is PolygonLayerKey {
  return key in POLYGON_LAYERS;
}
function isBackendKey(key: LayerKey): key is BackendLayerKey {
  return (BACKEND_LAYER_KEYS as string[]).includes(key);
}
function layerLabel(key: LayerKey): string {
  return isPolygonKey(key) ? POLYGON_LAYERS[key].label : MARKER_LABELS[key];
}

/** Run `fn` once the map style is loaded (immediately if already loaded). */
function whenStyleReady(map: maplibregl.Map, fn: () => void) {
  if (map.isStyleLoaded()) { fn(); return; }
  const handler = () => {
    if (map.isStyleLoaded()) { map.off("styledata", handler); fn(); }
  };
  map.on("styledata", handler);
}

/** Shared polygon paint layers for either GeoJSON or vector-tile sources. */
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

/**
 * Load a backend GeoJSON layer with explicit per-layer status. We fetch the
 * GeoJSON ourselves (rather than handing MapLibre a URL) so we can report
 * loading/error state to the caller — the source is only added on a successful
 * fetch.
 */
function useGeoJsonLayer(opts: {
  mapRef: React.MutableRefObject<maplibregl.Map | null>;
  ready: boolean;
  sourceId: string;
  url: string;
  isOn: boolean;
  addLayers: (map: maplibregl.Map, sourceId: string) => void;
  removeLayers: (map: maplibregl.Map) => void;
  onStatus: (status: LayerStatus) => void;
}) {
  const { mapRef, ready, sourceId, url, isOn } = opts;
  const addRef = useRef(opts.addLayers);
  const removeRef = useRef(opts.removeLayers);
  const statusRef = useRef(opts.onStatus);
  addRef.current = opts.addLayers;
  removeRef.current = opts.removeLayers;
  statusRef.current = opts.onStatus;

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    function teardown(m: maplibregl.Map) {
      removeRef.current(m);
      if (m.getSource(sourceId)) m.removeSource(sourceId);
    }

    if (!isOn) {
      if (map.isStyleLoaded()) teardown(map);
      statusRef.current("idle");
      return;
    }

    const controller = new AbortController();
    let cancelled = false;

    async function load() {
      if (cancelled || map.getSource(sourceId)) return;
      statusRef.current("loading");
      let geojson: GeoJSON.GeoJSON;
      try {
        const res = await fetch(url, { signal: controller.signal });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        geojson = (await res.json()) as GeoJSON.GeoJSON;
      } catch (err) {
        if (cancelled || (err instanceof DOMException && err.name === "AbortError")) return;
        statusRef.current("error");
        return;
      }
      if (cancelled) return;
      statusRef.current("loaded");
      whenStyleReady(map, () => {
        if (cancelled || map.getSource(sourceId)) return;
        map.addSource(sourceId, { type: "geojson", data: geojson });
        addRef.current(map, sourceId);
      });
    }
    void load();

    return () => {
      cancelled = true;
      controller.abort();
      if (map.isStyleLoaded()) teardown(map);
    };
  }, [mapRef, ready, sourceId, url, isOn]);
}

/**
 * Load one explicitly authorized Martin vector source. TileJSON is fetched first
 * as a fail-closed publication/shape check; MapLibre then receives the same-origin
 * MVT template directly so proxy-generated absolute TileJSON URLs cannot bypass
 * the `/tiles` ingress prefix.
 */
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
}) {
  const { mapRef, ready, sourceId, martinSourceId, sourceLayer, isOn } = opts;
  const addRef = useRef(opts.addLayers);
  const removeRef = useRef(opts.removeLayers);
  const statusRef = useRef(opts.onStatus);
  addRef.current = opts.addLayers;
  removeRef.current = opts.removeLayers;
  statusRef.current = opts.onStatus;

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    function teardown(m: maplibregl.Map) {
      removeRef.current(m);
      if (m.getSource(sourceId)) m.removeSource(sourceId);
    }

    if (!isOn) {
      if (map.isStyleLoaded()) teardown(map);
      statusRef.current("idle");
      return;
    }

    const controller = new AbortController();
    let cancelled = false;
    const onMapError = (event: { sourceId?: string }) => {
      if (event.sourceId === sourceId) statusRef.current("error");
    };
    map.on("error", onMapError);

    async function load() {
      if (cancelled || map.getSource(sourceId)) return;
      statusRef.current("loading");
      try {
        const res = await fetch(martinTileJsonUrl(martinSourceId), { signal: controller.signal });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const tilejson = (await res.json()) as {
          minzoom?: number;
          maxzoom?: number;
          vector_layers?: Array<{ id?: string }>;
        };
        const advertised = new Set((tilejson.vector_layers ?? []).map((item) => item.id));
        if (!advertised.has(sourceLayer)) throw new Error(`missing source-layer ${sourceLayer}`);
        if (cancelled) return;
        whenStyleReady(map, () => {
          if (cancelled || map.getSource(sourceId)) return;
          map.addSource(sourceId, {
            type: "vector",
            tiles: [martinTileUrlTemplate(martinSourceId)],
            minzoom: tilejson.minzoom ?? 0,
            maxzoom: tilejson.maxzoom ?? 14,
          });
          addRef.current(map, sourceId, sourceLayer);
          statusRef.current("loaded");
        });
      } catch (err) {
        if (cancelled || (err instanceof DOMException && err.name === "AbortError")) return;
        statusRef.current("error");
      }
    }
    void load();

    return () => {
      cancelled = true;
      controller.abort();
      map.off("error", onMapError);
      if (map.isStyleLoaded()) teardown(map);
    };
  }, [mapRef, ready, sourceId, martinSourceId, sourceLayer, isOn]);
}

/** Build the useGeoJsonLayer options for a TIGER polygon layer. */
function polygonLayerOpts(
  mapRef: React.MutableRefObject<maplibregl.Map | null>,
  ready: boolean,
  key: PolygonLayerKey,
  isOn: boolean,
  onStatus: (status: LayerStatus) => void,
) {
  const sourceId = `geo-${key}`;
  return {
    mapRef,
    ready,
    sourceId,
    url: `${API_BASE}/geo/${key}.geojson`,
    isOn,
    onStatus,
    addLayers: (map: maplibregl.Map, id: string) => addPolygonPaintLayers(map, key, id),
    removeLayers: (map: maplibregl.Map) => removePolygonPaintLayers(map, sourceId),
  };
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
  const hostRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);
  const [mapReady, setMapReady] = useState(false);
  const [layerStatus, setLayerStatus] = useState<Partial<Record<BackendLayerKey, LayerStatus>>>({});
  const [tilesFailed, setTilesFailed] = useState(false);
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
  }));

  const setStatus = (key: BackendLayerKey) => (status: LayerStatus) =>
    setLayerStatus((prev) => (prev[key] === status ? prev : { ...prev, [key]: status }));

  const municipiosViaMartin = MUNICIPIOS_DELIVERY === "martin";

  // Municipios is the only Martin canary. Both hooks remain mounted so changing
  // VITE_MUNICIPIOS_DELIVERY is a deterministic rollback rather than a code edit.
  useVectorTileLayer({
    mapRef,
    ready: mapReady,
    sourceId: "mvt-municipios",
    martinSourceId: "municipios",
    sourceLayer: "municipios",
    isOn: layers.municipios && municipiosViaMartin,
    onStatus: setStatus("municipios"),
    addLayers: (map, sourceId, sourceLayer) => addPolygonPaintLayers(map, "municipios", sourceId, sourceLayer),
    removeLayers: (map) => removePolygonPaintLayers(map, "mvt-municipios"),
  });
  useGeoJsonLayer(
    polygonLayerOpts(
      mapRef,
      mapReady,
      "municipios",
      layers.municipios && !municipiosViaMartin,
      setStatus("municipios"),
    ),
  );

  // Remaining admin layers stay on the established whole-GeoJSON path.
  useGeoJsonLayer(polygonLayerOpts(mapRef, mapReady, "tracts", layers.tracts, setStatus("tracts")));
  useGeoJsonLayer(polygonLayerOpts(mapRef, mapReady, "places", layers.places, setStatus("places")));
  useGeoJsonLayer(polygonLayerOpts(mapRef, mapReady, "barrios", layers.barrios, setStatus("barrios")));

  // Initialize map
  useEffect(() => {
    if (!hostRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: hostRef.current,
      style: rasterStyle,
      center: [-66.35, 18.22],
      zoom: 8.4,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-left");
    map.on("error", (e: { sourceId?: string }) => {
      if (e.sourceId === "osm") setTilesFailed(true);
    });
    mapRef.current = map;
    setMapReady(true);
    return () => {
      markersRef.current.forEach((m) => m.remove());
      markersRef.current = [];
      map.remove();
      mapRef.current = null;
      setMapReady(false);
    };
  }, []);

  // Site markers — rerender when data or layer toggles change
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
  }, [data, layers, setSelection]);

  // Fly to selection
  useEffect(() => {
    const map = mapRef.current;
    if (!map || selection?.kind !== "site") return;
    const site = byId(data.sites, selection.id);
    if (site) map.flyTo({ center: [site.lng, site.lat], zoom: 11, speed: 0.8 });
  }, [data.sites, selection]);

  // Persist the layer-panel collapse preference.
  useEffect(() => {
    localStorage.setItem("spiderweb_layer_collapsed", String(layerPanelCollapsed));
  }, [layerPanelCollapsed]);

  // "L" toggles the layer panel. Ignore while typing in an input/textarea.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)) {
        return;
      }
      if (event.key === "l" || event.key === "L") {
        event.preventDefault();
        setLayerPanelCollapsed((value) => !value);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Reflow MapLibre after any surrounding layout transition completes, so the
  // canvas matches its container instead of leaving blank gutters.
  useEffect(() => {
    const timer = window.setTimeout(() => mapRef.current?.resize(), 320);
    return () => window.clearTimeout(timer);
  }, [leftCollapsed, rightCollapsed, layerPanelCollapsed]);

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
          <Pill tone="info">MapLibre GL JS</Pill>
        </div>
      </div>
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
            const right = status === "loading" ? "loading…" : status === "error" ? "error" : value ? "on" : "off";
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
                <span>{right}</span>
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

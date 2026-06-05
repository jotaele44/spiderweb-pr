import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import { byId, fmtMoney } from "../data/mockData";
import type { PriisData, Selection } from "../types/priis";
import { AnomalyScore, Pill } from "../components/Badges";

const BASE = "http://localhost:8000";

const rasterStyle: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
};

type PolygonLayerKey = "municipios" | "tracts" | "places" | "barrios";
type LayerKey =
  | "contracts"
  | "infrastructure"
  | "sensitive"
  | "anomaly"
  | "flights"
  | PolygonLayerKey;

interface PolygonLayerConfig {
  fillOpacity: number;
  lineColor: string;
  fillColor: string;
  defaultOn: boolean;
  label: string;
}

const POLYGON_LAYERS: Record<PolygonLayerKey, PolygonLayerConfig> = {
  municipios: {
    fillOpacity: 0.08,
    fillColor: "#4dc4d6",
    lineColor: "#4dc4d6",
    defaultOn: true,
    label: "Municipios",
  },
  tracts: {
    fillOpacity: 0.04,
    fillColor: "#f4b740",
    lineColor: "#f4b740",
    defaultOn: false,
    label: "Census tracts",
  },
  places: {
    fillOpacity: 0.05,
    fillColor: "#a07cff",
    lineColor: "#a07cff",
    defaultOn: false,
    label: "Places",
  },
  barrios: {
    fillOpacity: 0.04,
    fillColor: "#6f7782",
    lineColor: "#6f7782",
    defaultOn: false,
    label: "Barrios",
  },
};

const POLYGON_LAYER_KEYS = Object.keys(POLYGON_LAYERS) as PolygonLayerKey[];

/**
 * Toggle a TIGER polygon source + (fill, line) layer pair on the MapLibre
 * instance. IDs follow the pattern `geo-${key}` / `geo-${key}-fill` /
 * `geo-${key}-line`. Removal order is line → fill → source (every layer
 * referencing the source must be gone before removeSource).
 */
function usePolygonLayer(
  mapRef: React.MutableRefObject<maplibregl.Map | null>,
  key: PolygonLayerKey,
  isOn: boolean,
) {
  const cfg = POLYGON_LAYERS[key];
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const SOURCE_ID = `geo-${key}`;
    const FILL_ID = `geo-${key}-fill`;
    const LINE_ID = `geo-${key}-line`;

    function removePolygon() {
      // Order matters: every layer must be gone before removeSource.
      if (map!.getLayer(LINE_ID)) map!.removeLayer(LINE_ID);
      if (map!.getLayer(FILL_ID)) map!.removeLayer(FILL_ID);
      if (map!.getSource(SOURCE_ID)) map!.removeSource(SOURCE_ID);
    }

    if (!isOn) {
      if (map.isStyleLoaded()) removePolygon();
      return;
    }

    function addPolygon() {
      if (map!.getSource(SOURCE_ID)) return;
      map!.addSource(SOURCE_ID, {
        type: "geojson",
        data: `${BASE}/geo/${key}.geojson`,
      });
      map!.addLayer({
        id: FILL_ID,
        type: "fill",
        source: SOURCE_ID,
        paint: {
          "fill-color": cfg.fillColor,
          "fill-opacity": cfg.fillOpacity,
        },
      });
      map!.addLayer({
        id: LINE_ID,
        type: "line",
        source: SOURCE_ID,
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": cfg.lineColor,
          "line-width": 0.8,
          "line-opacity": 0.6,
        },
      });
    }

    if (map.isStyleLoaded()) {
      addPolygon();
    } else {
      map.once("load", addPolygon);
    }

    return () => {
      if (mapRef.current?.isStyleLoaded()) removePolygon();
    };
  }, [isOn, key, cfg.fillColor, cfg.fillOpacity, cfg.lineColor, mapRef]);
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
  const [layerPanelCollapsed, setLayerPanelCollapsed] = useState(
    () => localStorage.getItem("priis_layer_collapsed") === "true",
  );
  const [layers, setLayers] = useState<Record<LayerKey, boolean>>(() => ({
    contracts: true,
    infrastructure: true,
    sensitive: true,
    anomaly: true,
    flights: false,
    ...(Object.fromEntries(
      POLYGON_LAYER_KEYS.map((k) => [k, POLYGON_LAYERS[k].defaultOn]),
    ) as Record<PolygonLayerKey, boolean>),
  }));

  // Polygon overlays — one hook per TIGER layer, all driven by POLYGON_LAYERS config.
  usePolygonLayer(mapRef, "municipios", layers.municipios);
  usePolygonLayer(mapRef, "tracts", layers.tracts);
  usePolygonLayer(mapRef, "places", layers.places);
  usePolygonLayer(mapRef, "barrios", layers.barrios);

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
    mapRef.current = map;
    return () => {
      markersRef.current.forEach((m) => m.remove());
      markersRef.current = [];
      map.remove();
      mapRef.current = null;
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
      el.title = `${site.name} · ${fmtMoney(contractTotal)} · ${anomaly?.id ?? "no anomaly"}`;
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

  // Flight GeoJSON layer — added/removed when toggle changes
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const SOURCE_ID = "flights-source";
    const LAYER_ID = "flights-layer";

    function removeFlight() {
      if (map!.getLayer(LAYER_ID)) map!.removeLayer(LAYER_ID);
      if (map!.getSource(SOURCE_ID)) map!.removeSource(SOURCE_ID);
    }

    if (!layers.flights) {
      if (map.isStyleLoaded()) removeFlight();
      return;
    }

    function addFlightLayer() {
      if (map!.getSource(SOURCE_ID)) return;
      map!.addSource(SOURCE_ID, {
        type: "geojson",
        data: `${BASE}/geo/flights.geojson`,
      });
      map!.addLayer({
        id: LAYER_ID,
        type: "line",
        source: SOURCE_ID,
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": "#4dc4d6",
          "line-width": 1.5,
          "line-opacity": 0.7,
        },
      });
    }

    if (map.isStyleLoaded()) {
      addFlightLayer();
    } else {
      void map.once("load", addFlightLayer);
    }

    return () => {
      if (mapRef.current?.isStyleLoaded()) removeFlight();
    };
  }, [layers.flights]);

  // Fly to selection
  useEffect(() => {
    const map = mapRef.current;
    if (!map || selection?.kind !== "site") return;
    const site = byId(data.sites, selection.id);
    if (site) map.flyTo({ center: [site.lng, site.lat], zoom: 11, speed: 0.8 });
  }, [data.sites, selection]);

  // Persist the layer-panel collapse preference.
  useEffect(() => {
    localStorage.setItem("priis_layer_collapsed", String(layerPanelCollapsed));
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
        <div ref={hostRef} className="map-host" />
        <aside className="layer-panel">
          <h3>Layer control</h3>
          {(Object.entries(layers) as [LayerKey, boolean][]).map(([key, value]) => (
            <button
              key={key}
              className="navbtn"
              data-active={value}
              onClick={() => setLayers((cur) => ({ ...cur, [key]: !cur[key] }))}
            >
              <span>{key}</span>
              <span>{value ? "on" : "off"}</span>
            </button>
          ))}
          <div className="hr" />
          <h3>Top spatial anomalies</h3>
          <div className="col">
            {data.anomalies.map((anomaly) => {
              const site = byId(data.sites, anomaly.siteId);
              return (
                <button
                  key={anomaly.id}
                  className="anom-card"
                  data-band={anomaly.band}
                  onClick={() => setSelection({ kind: "anomaly", id: anomaly.id })}
                >
                  <div className="row" style={{ justifyContent: "space-between" }}>
                    <b>{anomaly.id}</b>
                    <AnomalyScore score={anomaly.score} />
                  </div>
                  <p className="desc">{site?.name}</p>
                </button>
              );
            })}
          </div>
        </aside>
      </div>
    </section>
  );
}

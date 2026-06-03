import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import { byId, fmtMoney } from "../data/mockData";
import type { PriisData, Selection, SpatialFilter, SpatialFilterKind, TrackPoint } from "../types/priis";
import { AnomalyScore, Pill } from "../components/Badges";
import { toggleSpatialFilter } from "../lib/selectors";

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

type PolygonLayerKey =
  | "state"
  | "municipios"
  | "barrios"
  | "tracts"
  | "block_groups"
  | "places"
  | "zctas";
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
  state: {
    fillOpacity: 0.0,
    fillColor: "#ffffff",
    lineColor: "#ffffff",
    defaultOn: true,
    label: "PR outline",
  },
  municipios: {
    fillOpacity: 0.08,
    fillColor: "#4dc4d6",
    lineColor: "#4dc4d6",
    defaultOn: true,
    label: "Municipios",
  },
  barrios: {
    fillOpacity: 0.04,
    fillColor: "#6f7782",
    lineColor: "#6f7782",
    defaultOn: false,
    label: "Barrios",
  },
  tracts: {
    fillOpacity: 0.04,
    fillColor: "#f4b740",
    lineColor: "#f4b740",
    defaultOn: false,
    label: "Census tracts",
  },
  block_groups: {
    fillOpacity: 0.03,
    fillColor: "#e07a8c",
    lineColor: "#e07a8c",
    defaultOn: false,
    label: "Block groups",
  },
  places: {
    fillOpacity: 0.05,
    fillColor: "#a07cff",
    lineColor: "#a07cff",
    defaultOn: false,
    label: "Places",
  },
  zctas: {
    fillOpacity: 0.04,
    fillColor: "#7ec888",
    lineColor: "#7ec888",
    defaultOn: false,
    label: "ZCTAs",
  },
};

const POLYGON_LAYER_KEYS = Object.keys(POLYGON_LAYERS) as PolygonLayerKey[];

// Human-friendly labels for the operational overlays (non-polygon keys in
// the `layers` state). Polygon labels come from POLYGON_LAYERS[k].label.
const OPERATIONAL_LAYER_LABELS: Record<
  Exclude<LayerKey, PolygonLayerKey>,
  string
> = {
  contracts: "Contracts",
  infrastructure: "Infrastructure",
  sensitive: "Sensitive sites",
  anomaly: "Anomalies",
  flights: "Flights",
};

function labelFor(key: LayerKey): string {
  if (key in POLYGON_LAYERS) {
    return POLYGON_LAYERS[key as PolygonLayerKey].label;
  }
  return OPERATIONAL_LAYER_LABELS[key as Exclude<LayerKey, PolygonLayerKey>] ?? key;
}

export type PolygonClickHandler = (
  geoid: string,
  label: string,
  layerKind: PolygonLayerKey,
) => void;

/**
 * Toggle a TIGER polygon source + (fill, line) layer pair on the MapLibre
 * instance. IDs follow the pattern `geo-${key}` / `geo-${key}-fill` /
 * `geo-${key}-line`. Removal order is line → fill → source (every layer
 * referencing the source must be gone before removeSource).
 *
 * If `onClick` is provided, the fill layer becomes interactive: clicking a
 * polygon invokes the callback with its GEOID + NAME, and hovering changes
 * the cursor. The callback is read through a ref so passing a new function
 * each render doesn't tear down the layer.
 */
function usePolygonLayer(
  mapRef: React.MutableRefObject<maplibregl.Map | null>,
  key: PolygonLayerKey,
  isOn: boolean,
  onClick?: PolygonClickHandler,
) {
  const cfg = POLYGON_LAYERS[key];
  const onClickRef = useRef(onClick);
  useEffect(() => { onClickRef.current = onClick; }, [onClick]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const SOURCE_ID = `geo-${key}`;
    const FILL_ID = `geo-${key}-fill`;
    const LINE_ID = `geo-${key}-line`;

    // Handlers are declared at effect scope so cleanup can reference the
    // exact same function instances passed to map.on(...).
    const clickHandler = (
      e: maplibregl.MapMouseEvent & {
        features?: maplibregl.MapGeoJSONFeature[];
      },
    ) => {
      const feature = e.features?.[0];
      if (!feature) return;
      const props = feature.properties as {
        GEOID?: string;
        NAME?: string;
        NAMELSAD?: string;
      };
      if (!props.GEOID) return;
      onClickRef.current?.(
        props.GEOID,
        props.NAMELSAD ?? props.NAME ?? props.GEOID,
        key,
      );
    };
    const enterHandler = () => {
      if (map.getCanvas()) map.getCanvas().style.cursor = "pointer";
    };
    const leaveHandler = () => {
      if (map.getCanvas()) map.getCanvas().style.cursor = "";
    };

    function removePolygon() {
      map!.off("click", FILL_ID, clickHandler);
      map!.off("mouseenter", FILL_ID, enterHandler);
      map!.off("mouseleave", FILL_ID, leaveHandler);
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
      // Wire interactivity after layers exist.
      map!.on("click", FILL_ID, clickHandler);
      map!.on("mouseenter", FILL_ID, enterHandler);
      map!.on("mouseleave", FILL_ID, leaveHandler);
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
  spatialFilter,
  setSpatialFilter,
  flightTrack,
}: {
  data: PriisData;
  selection: Selection | null;
  setSelection: (selection: Selection) => void;
  spatialFilter: SpatialFilter | null;
  setSpatialFilter: (filter: SpatialFilter | null) => void;
  flightTrack: TrackPoint[] | null;
}) {
  // Click a polygon → set the cross-module filter. The pure
  // `toggleSpatialFilter` handles the "click same polygon to clear" rule.
  const handlePolygonClick: PolygonClickHandler = (geoid, label, layerKind) => {
    const kind = layerKind as SpatialFilterKind;
    setSpatialFilter(toggleSpatialFilter(spatialFilter, { kind, geoid, label }));
  };

  const hostRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);
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

  // Ephemeral flight track — when a flight event is selected, a polyline of
  // its ADS-B track is added to the map. Tears down on selection change.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const SOURCE_ID = "flight-track-source";
    const LAYER_ID = "flight-track-layer";

    function removeTrack() {
      if (map!.getLayer(LAYER_ID)) map!.removeLayer(LAYER_ID);
      if (map!.getSource(SOURCE_ID)) map!.removeSource(SOURCE_ID);
    }

    if (!flightTrack || flightTrack.length < 2) {
      if (map.isStyleLoaded()) removeTrack();
      return;
    }

    function addTrack() {
      removeTrack();
      map!.addSource(SOURCE_ID, {
        type: "geojson",
        data: {
          type: "Feature",
          properties: {},
          geometry: {
            type: "LineString",
            coordinates: flightTrack!.map((p) => [p.lng, p.lat]),
          },
        },
      });
      map!.addLayer({
        id: LAYER_ID,
        type: "line",
        source: SOURCE_ID,
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": "#f4b740",
          "line-width": 2.5,
          "line-opacity": 0.9,
        },
      });
    }

    if (map.isStyleLoaded()) {
      addTrack();
    } else {
      map.once("load", addTrack);
    }

    return () => {
      if (mapRef.current?.isStyleLoaded()) removeTrack();
    };
  }, [flightTrack]);

  // Polygon overlays — one hook per TIGER layer, all driven by POLYGON_LAYERS config.
  // PR outline is non-interactive (single feature, no useful filter to set).
  usePolygonLayer(mapRef, "state", layers.state);
  usePolygonLayer(mapRef, "municipios", layers.municipios, handlePolygonClick);
  usePolygonLayer(mapRef, "barrios", layers.barrios, handlePolygonClick);
  usePolygonLayer(mapRef, "tracts", layers.tracts, handlePolygonClick);
  usePolygonLayer(mapRef, "block_groups", layers.block_groups, handlePolygonClick);
  usePolygonLayer(mapRef, "places", layers.places, handlePolygonClick);
  usePolygonLayer(mapRef, "zctas", layers.zctas, handlePolygonClick);

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

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h1>Spatial Intelligence</h1>
          <span className="subtle">MapLibre layer control · contract, infrastructure, anomaly convergence</span>
        </div>
        <Pill tone="info">MapLibre GL JS</Pill>
      </div>
      <div className="map-shell">
        <div ref={hostRef} className="map-host" />
        <aside className="layer-panel">
          {spatialFilter && (
            <div className="card" style={{ marginBottom: 8, padding: 8 }}>
              <div className="subtle mono">SPATIAL FILTER</div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6 }}>
                <div>
                  <b>{spatialFilter.label}</b>
                  <div className="subtle mono" style={{ fontSize: "0.7rem" }}>
                    {spatialFilter.kind} · {spatialFilter.geoid}
                  </div>
                </div>
                <button className="act" onClick={() => setSpatialFilter(null)}>CLEAR</button>
              </div>
            </div>
          )}
          <h3>Layer control</h3>
          {(Object.entries(layers) as [LayerKey, boolean][]).map(([key, value]) => (
            <button
              key={key}
              className="navbtn"
              data-active={value}
              onClick={() => setLayers((cur) => ({ ...cur, [key]: !cur[key] }))}
            >
              <span>{labelFor(key)}</span>
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

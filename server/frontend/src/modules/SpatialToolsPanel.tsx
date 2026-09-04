import { useEffect, useEffectEvent, useState } from "react";
import * as maplibregl from "maplibre-gl";
import { point, featureCollection } from "@turf/helpers";
import type { Feature, FeatureCollection, Point } from "geojson";
import turfLength from "@turf/length";
import turfDistance from "@turf/distance";
import turfCircle from "@turf/circle";
import booleanPointInPolygon from "@turf/boolean-point-in-polygon";
import turfNearestPoint from "@turf/nearest-point";

export type ToolMode = "off" | "measure" | "buffer" | "nearest";

const MEASURE_SOURCE = "tool-measure-line";
const BUFFER_SOURCE = "tool-buffer-circle";
const NEAREST_SOURCE = "tool-nearest-highlight";
const BUFFER_RADII_KM = [1, 5, 10, 25];

function ensureLineSource(map: maplibregl.Map, id: string, color: string) {
  if (!map.getSource(id)) {
    map.addSource(id, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
    map.addLayer({
      id: `${id}-line`,
      type: "line",
      source: id,
      layout: { "line-join": "round", "line-cap": "round" },
      paint: { "line-color": color, "line-width": 2 },
    });
    map.addLayer({
      id: `${id}-points`,
      type: "circle",
      source: id,
      filter: ["==", ["geometry-type"], "Point"],
      paint: { "circle-radius": 4, "circle-color": color },
    });
  }
}

function ensureFillSource(map: maplibregl.Map, id: string, color: string) {
  if (!map.getSource(id)) {
    map.addSource(id, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
    map.addLayer({
      id: `${id}-fill`,
      type: "fill",
      source: id,
      paint: { "fill-color": color, "fill-opacity": 0.15 },
    });
    map.addLayer({
      id: `${id}-outline`,
      type: "line",
      source: id,
      paint: { "line-color": color, "line-width": 1.5 },
    });
  }
}

function setSourceData(map: maplibregl.Map, id: string, data: GeoJSON.FeatureCollection) {
  // eslint and tsc disagree on whether this narrowing is redundant; tsc
  // (the actual `tsc --noEmit` build) requires it — map.getSource()'s
  // declared return type is the generic Source interface, not GeoJSONSource.
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-type-assertion
  const source = map.getSource(id) as maplibregl.GeoJSONSource | undefined;
  void source?.setData(data);
}

/**
 * Shared interactive spatial-analysis panel: measure distance, buffer-radius
 * feature count, and nearest-feature lookup — the capability gap this
 * federation has versus QGIS/ArcGIS. Purely additive: only intercepts map
 * clicks while a mode is active, so it never touches existing click-to-select
 * behavior.
 */
export function useSpatialTools(opts: {
  mapRef: React.MutableRefObject<maplibregl.Map | null>;
  mapReady: boolean;
  targets: Record<string, () => Feature<Point>[]>;
}) {
  const { mapRef, mapReady, targets } = opts;
  const targetKeys = Object.keys(targets);
  const [mode, setMode] = useState<ToolMode>("off");
  const [targetKey, setTargetKey] = useState<string>(targetKeys[0] ?? "");
  const [measurePoints, setMeasurePoints] = useState<[number, number][]>([]);
  const [bufferCenter, setBufferCenter] = useState<[number, number] | null>(null);
  const [bufferRadiusKm, setBufferRadiusKm] = useState(5);
  const [bufferCount, setBufferCount] = useState<number | null>(null);
  const [nearestResult, setNearestResult] = useState<{ distanceKm: number; properties: Record<string, unknown> } | null>(null);

  // Ensure the three scratch sources/layers exist once the map is ready.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    function setup() {
      if (!map) return;
      ensureLineSource(map, MEASURE_SOURCE, "#facc15");
      ensureFillSource(map, BUFFER_SOURCE, "#38bdf8");
      ensureLineSource(map, NEAREST_SOURCE, "#f472b6");
    }
    if (map.isStyleLoaded()) setup();
    else map.once("styledata", setup);
  }, [mapRef, mapReady]);

  const clearAll = () => {
    setMeasurePoints([]);
    setBufferCenter(null);
    setBufferCount(null);
    setNearestResult(null);
    const map = mapRef.current;
    if (!map) return;
    setSourceData(map, MEASURE_SOURCE, featureCollection([]));
    setSourceData(map, BUFFER_SOURCE, featureCollection([]));
    setSourceData(map, NEAREST_SOURCE, featureCollection([]));
  };

  const setModeAndReset = (next: ToolMode) => {
    clearAll();
    setMode(next);
  };

  // Route map clicks to whichever tool is active. No-ops when off, so this
  // never competes with existing feature-click-to-select handlers.
  // useEffectEvent keeps this closure always reading the latest mode/
  // targetKey/bufferRadiusKm/targets without re-attaching the click listener
  // (and thus without needing ref-mirrors of that state) on every change.
  const onMapClick = useEffectEvent((map: maplibregl.Map, e: maplibregl.MapMouseEvent) => {
    if (mode === "off") return;
    const lngLat: [number, number] = [e.lngLat.lng, e.lngLat.lat];

    if (mode === "measure") {
      setMeasurePoints((prev) => {
        const next = [...prev, lngLat];
        if (next.length >= 2) {
          setSourceData(map, MEASURE_SOURCE, featureCollection([{ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: next } }]));
        }
        return next;
      });
      return;
    }

    if (mode === "buffer") {
      setBufferCenter(lngLat);
      const poly = turfCircle(point(lngLat), bufferRadiusKm, { steps: 64, units: "kilometers" });
      setSourceData(map, BUFFER_SOURCE, featureCollection([poly]));
      const getFeatures = targets[targetKey];
      const inside = getFeatures ? getFeatures().filter((f) => booleanPointInPolygon(f, poly)).length : 0;
      setBufferCount(inside);
      return;
    }

    if (mode === "nearest") {
      const getFeatures = targets[targetKey];
      const candidates = getFeatures ? getFeatures() : [];
      if (candidates.length === 0) {
        setNearestResult(null);
        return;
      }
      const origin = point(lngLat);
      const fc: FeatureCollection<Point> = featureCollection(candidates);
      const nearest = turfNearestPoint(origin, fc);
      const distanceKm = turfDistance(origin, nearest, { units: "kilometers" });
      const connector: Feature = {
        type: "Feature",
        properties: {},
        geometry: { type: "LineString", coordinates: [lngLat, nearest.geometry.coordinates] },
      };
      setSourceData(map, NEAREST_SOURCE, featureCollection([connector, nearest] as Feature[]));
      setNearestResult({ distanceKm, properties: nearest.properties ?? {} });
    }
  });

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const onClick = (e: maplibregl.MapMouseEvent) => onMapClick(map, e);
    map.on("click", onClick);
    return () => {
      map.off("click", onClick);
    };
  }, [mapRef, mapReady]);

  const measureLengthKm = measurePoints.length >= 2
    ? turfLength({ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: measurePoints } }, { units: "kilometers" })
    : 0;

  return {
    mode,
    setMode: setModeAndReset,
    targetKey,
    setTargetKey,
    targetKeys,
    measurePoints,
    measureLengthKm,
    bufferCenter,
    bufferRadiusKm,
    setBufferRadiusKm,
    bufferCount,
    nearestResult,
    clearAll,
  };
}

export function SpatialToolsPanel(state: ReturnType<typeof useSpatialTools>) {
  const { mode, setMode, targetKey, setTargetKey, targetKeys, measureLengthKm, measurePoints, bufferRadiusKm, setBufferRadiusKm, bufferCount, nearestResult, clearAll } = state;

  return (
    <div className="tools-panel">
      <h2>Spatial tools</h2>
      <div className="row">
        {(["off", "measure", "buffer", "nearest"] as ToolMode[]).map((m) => (
          <button
            key={m}
            className="navbtn"
            data-active={mode === m}
            aria-pressed={mode === m}
            onClick={() => setMode(m)}
          >
            {m === "off" ? "Off" : m[0].toUpperCase() + m.slice(1)}
          </button>
        ))}
      </div>
      {mode !== "off" && targetKeys.length > 0 && (
        <label className="tools-target">
          <span>Target layer</span>
          <select value={targetKey} onChange={(e) => setTargetKey(e.target.value)}>
            {targetKeys.map((k) => (
              <option key={k} value={k}>{k}</option>
            ))}
          </select>
        </label>
      )}
      {mode === "measure" && (
        <div className="tools-readout">
          <p>Click to add vertices; distance updates after the second point.</p>
          {measurePoints.length >= 2 && (
            <p>
              <strong>{measureLengthKm.toFixed(2)} km</strong> · {(measureLengthKm * 0.621371).toFixed(2)} mi
            </p>
          )}
        </div>
      )}
      {mode === "buffer" && (
        <div className="tools-readout">
          <p>Click to set the center. Radius:</p>
          <div className="row">
            {BUFFER_RADII_KM.map((r) => (
              <button
                key={r}
                className="navbtn"
                data-active={bufferRadiusKm === r}
                aria-pressed={bufferRadiusKm === r}
                onClick={() => setBufferRadiusKm(r)}
              >
                {r} km
              </button>
            ))}
          </div>
          {bufferCount !== null && (
            <p><strong>{bufferCount}</strong> feature{bufferCount === 1 ? "" : "s"} within {bufferRadiusKm} km</p>
          )}
        </div>
      )}
      {mode === "nearest" && (
        <div className="tools-readout">
          <p>Click to query the nearest feature.</p>
          {nearestResult && (
            <p><strong>{nearestResult.distanceKm.toFixed(2)} km</strong> away</p>
          )}
        </div>
      )}
      {mode !== "off" && (
        <button className="linklike" onClick={clearAll}>Clear</button>
      )}
    </div>
  );
}

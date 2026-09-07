import { useCallback, useEffect, useEffectEvent, useState } from "react";
import type { MutableRefObject } from "react";
import * as maplibregl from "maplibre-gl";
import { featureCollection, point } from "@turf/helpers";
import type { Feature, FeatureCollection, GeoJsonProperties, Point } from "geojson";
import turfLength from "@turf/length";
import turfDistance from "@turf/distance";
import turfCircle from "@turf/circle";
import booleanPointInPolygon from "@turf/boolean-point-in-polygon";
import turfNearestPoint from "@turf/nearest-point";

export type ToolMode = "off" | "measure" | "buffer" | "nearest";
type Position = [number, number];

interface QueryEvidence {
  candidateCount: number;
  excludedCount: number;
  identityEffect: "NONE";
  origin: Position;
  sourceError: string | null;
  state: "PASS" | "FAIL" | "CANDIDATE_NOT_IDENTITY" | "UNRESOLVED";
  targetKey: string;
}

type BufferResult = QueryEvidence & {
  count: number;
  radiusKm: number;
};

type NearestResult = QueryEvidence & {
  candidateLabel?: string;
  distanceKm?: number;
  properties?: GeoJsonProperties;
};

const MEASURE_SOURCE = "tool-measure-line";
const BUFFER_SOURCE = "tool-buffer-circle";
const NEAREST_SOURCE = "tool-nearest-highlight";
const BUFFER_RADII_KM = [1, 5, 10, 25];
const EMPTY_COLLECTION: FeatureCollection = { type: "FeatureCollection", features: [] };

function finitePosition(coordinates: unknown): coordinates is Position {
  return Array.isArray(coordinates)
    && coordinates.length >= 2
    && Number.isFinite(coordinates[0])
    && Number.isFinite(coordinates[1]);
}

export function pointCandidateSet(features: Feature[] = []) {
  const points: Feature<Point>[] = [];
  let excludedCount = 0;
  for (const candidate of features) {
    if (candidate.geometry?.type === "Point" && finitePosition(candidate.geometry.coordinates)) {
      points.push(candidate as Feature<Point>);
    } else {
      excludedCount += 1;
    }
  }
  return { features: points, excludedCount };
}

export function measureFeatureCollection(coordinates: Position[]): FeatureCollection {
  const validCoordinates = coordinates.filter(finitePosition);
  const features: Feature[] = validCoordinates.map((coordinate) => point(coordinate));
  if (validCoordinates.length >= 2) {
    features.unshift({
      type: "Feature",
      properties: {},
      geometry: { type: "LineString", coordinates: validCoordinates },
    });
  }
  return featureCollection(features);
}

export function bufferPointCandidates(origin: Position, radiusKm: number, candidates: Feature[] = []) {
  if (!finitePosition(origin) || !Number.isFinite(radiusKm) || radiusKm <= 0) return null;
  const candidateSet = pointCandidateSet(candidates);
  const polygon = turfCircle(point(origin), radiusKm, { steps: 64, units: "kilometers" });
  const matches = candidateSet.features.filter((candidate) => booleanPointInPolygon(candidate, polygon));
  return { polygon, matches, ...candidateSet };
}

export function nearestPointCandidate(origin: Position, candidates: Feature[] = []) {
  if (!finitePosition(origin)) return null;
  const candidateSet = pointCandidateSet(candidates);
  if (candidateSet.features.length === 0) {
    return { nearest: null, distanceKm: null, ...candidateSet };
  }
  const queryPoint = point(origin);
  const nearest = turfNearestPoint(queryPoint, featureCollection(candidateSet.features));
  return {
    nearest,
    distanceKm: turfDistance(queryPoint, nearest, { units: "kilometers" }),
    ...candidateSet,
  };
}

function ensureLineSource(map: maplibregl.Map, id: string, color: string) {
  if (!map.getSource(id)) {
    map.addSource(id, { type: "geojson", data: EMPTY_COLLECTION });
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
    map.addSource(id, { type: "geojson", data: EMPTY_COLLECTION });
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

function setSourceData(map: maplibregl.Map | null, id: string, data: FeatureCollection) {
  if (!map) return;
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-type-assertion
  const source = map.getSource(id) as maplibregl.GeoJSONSource | undefined;
  void source?.setData(data);
}

function readTarget(targets: Record<string, () => Feature[]>, targetKey: string) {
  try {
    const value = targets[targetKey]?.();
    return { candidates: Array.isArray(value) ? value : [], sourceError: null };
  } catch (error) {
    return { candidates: [], sourceError: error instanceof Error ? error.message : String(error) };
  }
}

function candidateLabel(properties: GeoJsonProperties) {
  if (!properties) return "unnamed candidate";
  for (const key of ["asset_id", "event_id", "alert_id", "id", "name"]) {
    const value = properties[key] as unknown;
    if (typeof value === "string" || typeof value === "number") return String(value);
  }
  return "unnamed candidate";
}

export function useSpatialTools(opts: {
  mapRef: MutableRefObject<maplibregl.Map | null>;
  mapReady: boolean;
  targets: Record<string, () => Feature[]>;
  interactionLockRef: MutableRefObject<boolean>;
}) {
  const { interactionLockRef, mapRef, mapReady, targets } = opts;
  const targetKeys = Object.keys(targets);
  const [mode, setMode] = useState<ToolMode>("off");
  const [targetKey, setTargetKey] = useState(targetKeys[0] ?? "");
  const [measurePoints, setMeasurePoints] = useState<Position[]>([]);
  const [bufferCenter, setBufferCenter] = useState<Position | null>(null);
  const [bufferRadiusKm, setBufferRadiusKm] = useState(5);
  const [bufferResult, setBufferResult] = useState<BufferResult | null>(null);
  const [nearestOrigin, setNearestOrigin] = useState<Position | null>(null);
  const [nearestResult, setNearestResult] = useState<NearestResult | null>(null);

  useEffect(() => {
    interactionLockRef.current = mode !== "off";
    return () => {
      interactionLockRef.current = false;
    };
  }, [interactionLockRef, mode]);

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
    setBufferResult(null);
    setNearestOrigin(null);
    setNearestResult(null);
    const map = mapRef.current;
    setSourceData(map, MEASURE_SOURCE, EMPTY_COLLECTION);
    setSourceData(map, BUFFER_SOURCE, EMPTY_COLLECTION);
    setSourceData(map, NEAREST_SOURCE, EMPTY_COLLECTION);
  };

  const setModeAndReset = (next: ToolMode) => {
    clearAll();
    setMode(next);
  };

  const runBuffer = useCallback((origin: Position, radiusKm: number, selectedTargetKey: string) => {
    const { candidates, sourceError } = readTarget(targets, selectedTargetKey);
    const analysis = bufferPointCandidates(origin, radiusKm, candidates);
    if (!analysis) return;
    setSourceData(mapRef.current, BUFFER_SOURCE, featureCollection([analysis.polygon]));
    setBufferResult({
      count: analysis.matches.length,
      candidateCount: analysis.features.length,
      excludedCount: analysis.excludedCount,
      identityEffect: "NONE",
      origin,
      radiusKm,
      sourceError,
      state: sourceError ? "FAIL" : "PASS",
      targetKey: selectedTargetKey,
    });
  }, [mapRef, targets]);

  const runNearest = useCallback((origin: Position, selectedTargetKey: string) => {
    const { candidates, sourceError } = readTarget(targets, selectedTargetKey);
    const analysis = nearestPointCandidate(origin, candidates);
    if (!analysis?.nearest) {
      setSourceData(mapRef.current, NEAREST_SOURCE, EMPTY_COLLECTION);
      setNearestResult({
        candidateCount: analysis?.features.length ?? 0,
        excludedCount: analysis?.excludedCount ?? 0,
        identityEffect: "NONE",
        origin,
        sourceError,
        state: sourceError ? "FAIL" : "UNRESOLVED",
        targetKey: selectedTargetKey,
      });
      return;
    }
    const connector: Feature = {
      type: "Feature",
      properties: {},
      geometry: { type: "LineString", coordinates: [origin, analysis.nearest.geometry.coordinates] },
    };
    setSourceData(mapRef.current, NEAREST_SOURCE, featureCollection([connector, analysis.nearest]));
    setNearestResult({
      candidateCount: analysis.features.length,
      candidateLabel: candidateLabel(analysis.nearest.properties),
      distanceKm: analysis.distanceKm,
      excludedCount: analysis.excludedCount,
      identityEffect: "NONE",
      origin,
      properties: analysis.nearest.properties,
      sourceError,
      state: sourceError ? "FAIL" : "CANDIDATE_NOT_IDENTITY",
      targetKey: selectedTargetKey,
    });
  }, [mapRef, targets]);

  const setTargetAndRecompute = (nextTargetKey: string) => {
    setTargetKey(nextTargetKey);
    if (mode === "buffer" && bufferCenter) runBuffer(bufferCenter, bufferRadiusKm, nextTargetKey);
    if (mode === "nearest" && nearestOrigin) runNearest(nearestOrigin, nextTargetKey);
  };

  const setRadiusAndRecompute = (nextRadiusKm: number) => {
    setBufferRadiusKm(nextRadiusKm);
    if (bufferCenter) runBuffer(bufferCenter, nextRadiusKm, targetKey);
  };

  const onMapClick = useEffectEvent((map: maplibregl.Map, event: maplibregl.MapMouseEvent) => {
    if (mode === "off") return;
    const lngLat: Position = [event.lngLat.lng, event.lngLat.lat];
    if (!finitePosition(lngLat)) return;

    if (mode === "measure") {
      setMeasurePoints((previous) => {
        const next = [...previous, lngLat];
        setSourceData(map, MEASURE_SOURCE, measureFeatureCollection(next));
        return next;
      });
      return;
    }
    if (mode === "buffer") {
      setBufferCenter(lngLat);
      runBuffer(lngLat, bufferRadiusKm, targetKey);
      return;
    }
    if (mode === "nearest") {
      setNearestOrigin(lngLat);
      runNearest(lngLat, targetKey);
    }
  });

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const onClick = (event: maplibregl.MapMouseEvent) => onMapClick(map, event);
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
    setTargetKey: setTargetAndRecompute,
    targetKeys,
    measurePoints,
    measureLengthKm,
    bufferRadiusKm,
    setBufferRadiusKm: setRadiusAndRecompute,
    bufferResult,
    nearestResult,
    clearAll,
  };
}

function EvidenceReadout({ result }: { result: QueryEvidence }) {
  return (
    <div className="tools-readout">
      <p>Target: <strong>{result.targetKey}</strong> · valid {result.candidateCount} · excluded malformed {result.excludedCount}</p>
      <p>Query: {result.origin.map((value) => value.toFixed(5)).join(", ")}</p>
      <p>Discovery only · identity effect <strong>{result.identityEffect}</strong> · state {result.state}</p>
      {result.sourceError && <p role="alert">Target error: {result.sourceError}</p>}
    </div>
  );
}

export function SpatialToolsPanel(state: ReturnType<typeof useSpatialTools>) {
  const { mode, setMode, targetKey, setTargetKey, targetKeys, measureLengthKm, measurePoints, bufferRadiusKm, setBufferRadiusKm, bufferResult, nearestResult, clearAll } = state;

  return (
    <div className="tools-panel">
      <h2>Spatial tools</h2>
      <div className="row">
        {(["off", "measure", "buffer", "nearest"] as ToolMode[]).map((candidateMode) => (
          <button
            key={candidateMode}
            className="navbtn"
            data-active={mode === candidateMode}
            aria-pressed={mode === candidateMode}
            onClick={() => setMode(candidateMode)}
          >
            {candidateMode === "off" ? "Off" : candidateMode[0].toUpperCase() + candidateMode.slice(1)}
          </button>
        ))}
      </div>
      {(["buffer", "nearest"] as ToolMode[]).includes(mode) && targetKeys.length > 0 && (
        <label className="tools-target">
          <span>Target layer</span>
          <select value={targetKey} onChange={(event) => setTargetKey(event.target.value)}>
            {targetKeys.map((key) => (
              <option key={key} value={key}>{key}</option>
            ))}
          </select>
        </label>
      )}
      {mode === "measure" && (
        <div className="tools-readout">
          <p>Click to add visible vertices; distance updates after the second point.</p>
          {measurePoints.length >= 2 && (
            <p><strong>{measureLengthKm.toFixed(2)} km</strong> · {(measureLengthKm * 0.621371).toFixed(2)} mi</p>
          )}
        </div>
      )}
      {mode === "buffer" && (
        <div className="tools-readout">
          <p>Click to set the center. Radius:</p>
          <div className="row">
            {BUFFER_RADII_KM.map((radiusKm) => (
              <button
                key={radiusKm}
                className="navbtn"
                data-active={bufferRadiusKm === radiusKm}
                aria-pressed={bufferRadiusKm === radiusKm}
                onClick={() => setBufferRadiusKm(radiusKm)}
              >
                {radiusKm} km
              </button>
            ))}
          </div>
          {bufferResult && <p><strong>{bufferResult.count}</strong> feature{bufferResult.count === 1 ? "" : "s"} within {bufferResult.radiusKm} km</p>}
          {bufferResult && <EvidenceReadout result={bufferResult} />}
        </div>
      )}
      {mode === "nearest" && (
        <div className="tools-readout">
          <p>Click to query the nearest feature.</p>
          {nearestResult?.distanceKm != null && <p><strong>{nearestResult.candidateLabel}</strong> · {nearestResult.distanceKm.toFixed(2)} km away</p>}
          {nearestResult?.state === "UNRESOLVED" && <p>No valid point candidate is available.</p>}
          {nearestResult && <EvidenceReadout result={nearestResult} />}
        </div>
      )}
      {mode !== "off" && (
        <button className="linklike" onClick={clearAll}>Clear</button>
      )}
    </div>
  );
}

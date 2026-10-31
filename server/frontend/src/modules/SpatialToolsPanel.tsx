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
import type { GisClient, IdentifyResponse, QueryResponse } from "../spatial/gis/gisApi";
import { drawPolygonCollection, formatArea, polygonFromVertices, ringAreaM2 } from "../spatial/gis/measure";
import { googleMapsPointUrl, googleStreetViewUrl } from "../spatial/gis/externalLinks";
import { downloadBlob } from "../spatial/gis/printMap";

export type ToolMode = "off" | "measure" | "area" | "buffer" | "nearest" | "identify" | "query";
const CLIENT_MODES: ToolMode[] = ["off", "measure", "area", "buffer", "nearest"];
const SERVER_MODES: ToolMode[] = ["identify", "query"];

/**
 * Backend-backed tools (identify, polygon query/export) — present only when the
 * host passes a GIS client. `activeLayers` returns the catalog layer ids the
 * user currently has switched on; queries run against exactly those.
 */
export interface SpatialToolsGisOptions {
  client: GisClient;
  activeLayers: () => string[];
  exportable: (layerId: string) => boolean;
}

type RemoteState<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; data: T }
  | { status: "error"; message: string };
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
const DRAW_SOURCE = "tool-draw-polygon";
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
  gis?: SpatialToolsGisOptions;
}) {
  const { gis, interactionLockRef, mapRef, mapReady, targets } = opts;
  const targetKeys = Object.keys(targets);
  const [mode, setMode] = useState<ToolMode>("off");
  const [targetKey, setTargetKey] = useState(targetKeys[0] ?? "");
  const [measurePoints, setMeasurePoints] = useState<Position[]>([]);
  const [bufferCenter, setBufferCenter] = useState<Position | null>(null);
  const [bufferRadiusKm, setBufferRadiusKm] = useState(5);
  const [bufferResult, setBufferResult] = useState<BufferResult | null>(null);
  const [nearestOrigin, setNearestOrigin] = useState<Position | null>(null);
  const [nearestResult, setNearestResult] = useState<NearestResult | null>(null);
  const [drawVertices, setDrawVertices] = useState<Position[]>([]);
  const [identifyState, setIdentifyState] = useState<RemoteState<IdentifyResponse>>({ status: "idle" });
  const [queryState, setQueryState] = useState<RemoteState<QueryResponse>>({ status: "idle" });
  const [exportError, setExportError] = useState<string | null>(null);

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
      ensureFillSource(map, DRAW_SOURCE, "#a3e635");
      if (!map.getLayer(`${DRAW_SOURCE}-points`)) {
        map.addLayer({
          id: `${DRAW_SOURCE}-points`,
          type: "circle",
          source: DRAW_SOURCE,
          filter: ["==", ["geometry-type"], "Point"],
          paint: { "circle-radius": 4, "circle-color": "#a3e635" },
        });
      }
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
    setDrawVertices([]);
    setIdentifyState({ status: "idle" });
    setQueryState({ status: "idle" });
    setExportError(null);
    const map = mapRef.current;
    setSourceData(map, MEASURE_SOURCE, EMPTY_COLLECTION);
    setSourceData(map, BUFFER_SOURCE, EMPTY_COLLECTION);
    setSourceData(map, NEAREST_SOURCE, EMPTY_COLLECTION);
    setSourceData(map, DRAW_SOURCE, EMPTY_COLLECTION);
  };

  const runIdentify = useCallback((lngLat: Position) => {
    if (!gis) return;
    setIdentifyState({ status: "loading" });
    gis.client
      .identify(lngLat[0], lngLat[1], gis.activeLayers())
      .then((data) => setIdentifyState({ status: "ready", data }))
      .catch((error: unknown) => setIdentifyState({ status: "error", message: error instanceof Error ? error.message : String(error) }));
  }, [gis]);

  const runPolygonQuery = () => {
    const polygon = polygonFromVertices(drawVertices);
    if (!gis || !polygon) return;
    const layers = gis.activeLayers();
    if (layers.length === 0) {
      setQueryState({ status: "error", message: "Switch on at least one catalog layer to query." });
      return;
    }
    setQueryState({ status: "loading" });
    setExportError(null);
    gis.client
      .queryPolygon(polygon, layers)
      .then((data) => setQueryState({ status: "ready", data }))
      .catch((error: unknown) => setQueryState({ status: "error", message: error instanceof Error ? error.message : String(error) }));
  };

  const exportPolygonQuery = (format: "geojson" | "csv") => {
    const polygon = polygonFromVertices(drawVertices);
    if (!gis || !polygon || queryState.status !== "ready") return;
    const layers = queryState.data.layers.map((layer) => layer.layer_id).filter((layerId) => gis.exportable(layerId));
    if (layers.length === 0) {
      setExportError("None of the queried layers is exportable (only PUBLIC layers are).");
      return;
    }
    setExportError(null);
    gis.client
      .exportPolygon(polygon, layers, format)
      .then((blob) => downloadBlob(blob, `gis-export.${format === "csv" ? "csv" : "geojson"}`))
      .catch((error: unknown) => setExportError(error instanceof Error ? error.message : String(error)));
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

    if (mode === "area" || mode === "query") {
      setDrawVertices((previous) => {
        const next = [...previous, lngLat];
        setSourceData(map, DRAW_SOURCE, drawPolygonCollection(next));
        return next;
      });
      if (mode === "query") setQueryState({ status: "idle" });
      return;
    }
    if (mode === "identify") {
      runIdentify(lngLat);
      return;
    }
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

  const drawAreaM2 = drawVertices.length >= 3 ? ringAreaM2(drawVertices) : 0;

  return {
    mode,
    setMode: setModeAndReset,
    gisEnabled: Boolean(gis),
    exportable: gis?.exportable ?? (() => false),
    drawVertices,
    drawAreaM2,
    identifyState,
    queryState,
    exportError,
    runPolygonQuery,
    exportPolygonQuery,
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

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean" || typeof value === "bigint") return value.toString();
  return "—";
}

/** Location-context values: boundary {name,id}, grid lookup {status,cell_ids}, or null. */
function locationText(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value !== "object") return formatValue(value);
  const record = value as Record<string, unknown>;
  if (Array.isArray(record.cell_ids)) {
    const cells = record.cell_ids as unknown[];
    return cells.length ? `${cells.map(String).join(", ")} (${formatValue(record.binding)})` : formatValue(record.status);
  }
  if ("name" in record) return `${formatValue(record.name)} (${formatValue(record.id)})`;
  return formatValue(value);
}

function IdentifyReadout({ state }: { state: RemoteState<IdentifyResponse> }) {
  if (state.status === "idle") return <p>Click the map to identify features in the active catalog layers.</p>;
  if (state.status === "loading") return <p>Identifying…</p>;
  if (state.status === "error") return <p role="alert">Identify failed: {state.message}</p>;
  const { point: clicked, hits, location } = state.data;
  return (
    <div className="tools-readout">
      <p>
        Point {clicked.lat.toFixed(6)}, {clicked.lon.toFixed(6)} ·{" "}
        <a href={googleMapsPointUrl(clicked.lon, clicked.lat)} target="_blank" rel="noreferrer noopener">Google Maps</a> ·{" "}
        <a href={googleStreetViewUrl(clicked.lon, clicked.lat)} target="_blank" rel="noreferrer noopener">Street View</a>
      </p>
      {Object.entries(location).map(([key, value]) => (
        <p key={key}>{key}: {locationText(value)}</p>
      ))}
      {hits.length === 0 && <p>No features within {state.data.tolerance_m} m.</p>}
      {hits.map((hit, index) => (
        <details key={`${hit.layer_id}-${hit.feature_id ?? index}`} open={index === 0}>
          <summary>{hit.layer_id} · {hit.feature_id ?? "unidentified"} · {hit.distance_m} m</summary>
          <dl>
            {Object.entries(hit.properties).map(([key, value]) => (
              <div key={key}><dt>{key}</dt><dd>{formatValue(value)}</dd></div>
            ))}
          </dl>
        </details>
      ))}
      <p>Spatial relation only · evidence {state.data.evidence_state} · identity effect NONE</p>
    </div>
  );
}

function QueryReadout({ state, exportable, onExport, exportError }: {
  state: RemoteState<QueryResponse>;
  exportable: (layerId: string) => boolean;
  onExport: (format: "geojson" | "csv") => void;
  exportError: string | null;
}) {
  if (state.status === "idle") return null;
  if (state.status === "loading") return <p>Querying…</p>;
  if (state.status === "error") return <p role="alert">Query failed: {state.message}</p>;
  const anyExportable = state.data.layers.some((layer) => exportable(layer.layer_id));
  return (
    <div className="tools-readout">
      <p><strong>{state.data.total_matched}</strong> feature{state.data.total_matched === 1 ? "" : "s"} in the polygon</p>
      {state.data.layers.map((layer) => (
        <p key={layer.layer_id}>
          {layer.layer_id}: {layer.matched_count}{layer.truncated ? ` (first ${layer.returned_count} returned)` : ""}
          {layer.excluded_count > 0 ? ` · ${layer.excluded_count} without usable geometry` : ""}
          {layer.error ? ` · ${layer.error}` : ""}
          {exportable(layer.layer_id) ? "" : " · not exportable"}
        </p>
      ))}
      <p>Evidence {state.data.evidence_state} · identity effect NONE</p>
      {anyExportable && (
        <div className="row">
          <button className="navbtn" onClick={() => onExport("geojson")}>Export GeoJSON</button>
          <button className="navbtn" onClick={() => onExport("csv")}>Export CSV</button>
        </div>
      )}
      {exportError && <p role="alert">Export failed: {exportError}</p>}
    </div>
  );
}

const MODE_LABEL: Record<ToolMode, string> = {
  off: "Off",
  measure: "Measure",
  area: "Area",
  buffer: "Buffer",
  nearest: "Nearest",
  identify: "Identify",
  query: "Polygon query",
};

export function SpatialToolsPanel(state: ReturnType<typeof useSpatialTools>) {
  const { mode, setMode, targetKey, setTargetKey, targetKeys, measureLengthKm, measurePoints, bufferRadiusKm, setBufferRadiusKm, bufferResult, nearestResult, clearAll, gisEnabled, exportable, drawVertices, drawAreaM2, identifyState, queryState, exportError, runPolygonQuery, exportPolygonQuery } = state;
  const modes = gisEnabled ? [...CLIENT_MODES, ...SERVER_MODES] : CLIENT_MODES;

  return (
    <div className="tools-panel">
      <h2>Spatial tools</h2>
      <div className="row">
        {modes.map((candidateMode) => (
          <button
            key={candidateMode}
            className="navbtn"
            data-active={mode === candidateMode}
            aria-pressed={mode === candidateMode}
            onClick={() => setMode(candidateMode)}
          >
            {MODE_LABEL[candidateMode]}
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
      {mode === "area" && (
        <div className="tools-readout">
          <p>Click to add polygon vertices; area updates after the third point.</p>
          {drawVertices.length >= 3 && <p><strong>{formatArea(drawAreaM2)}</strong></p>}
        </div>
      )}
      {mode === "identify" && <IdentifyReadout state={identifyState} />}
      {mode === "query" && (
        <div className="tools-readout">
          <p>Click to add polygon vertices, then run the query against the active catalog layers.</p>
          {drawVertices.length >= 3 && <p>{formatArea(drawAreaM2)}</p>}
          <button className="navbtn" disabled={drawVertices.length < 3 || queryState.status === "loading"} onClick={runPolygonQuery}>
            Run query
          </button>
          <QueryReadout state={queryState} exportable={exportable} onExport={exportPolygonQuery} exportError={exportError} />
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

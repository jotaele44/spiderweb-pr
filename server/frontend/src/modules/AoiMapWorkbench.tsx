import { useEffect, useEffectEvent, useRef, useState } from "react";
import type { MutableRefObject } from "react";
import * as maplibregl from "maplibre-gl";
import type { Feature, FeatureCollection } from "geojson";
import { API_BASE } from "../config";
import { AoiAcquisitionWorkbench } from "./AoiAcquisitionWorkbench";
import { assertPlanMatchesAoi, moveVertex, parseFrozenPlan, PlanRevisionGate, polygonParts, readGeometry } from "./aoiContract";
import type { AoiGeometry, AoiMode, FrozenAcquisitionPlan, Position } from "./aoiContract";

const SOURCE = "aoi-workbench-overlay";
const LAYERS = [`${SOURCE}-fill`, `${SOURCE}-line`, `${SOURCE}-point`];
const MAX_IMPORT_BYTES = 4 * 1024 * 1024;
const MAX_EDIT_HANDLES = 1000;

export function AoiMapWorkbench({ mapRef, mapReady, mode, setMode }: {
  mapRef: MutableRefObject<maplibregl.Map | null>; mapReady: boolean;
  mode: AoiMode; setMode: (mode: AoiMode) => void;
}) {
  const [geometry, setGeometry] = useState<AoiGeometry | null>(null);
  const [draft, setDraft] = useState<Position[]>([]);
  const [rawImport, setRawImport] = useState<string | null>(null);
  const [history, setHistory] = useState<AoiGeometry[]>([]);
  const [plan, setPlan] = useState<FrozenAcquisitionPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showBbox, setShowBbox] = useState(false);
  const [product, setProduct] = useState("");
  const [provider, setProvider] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [resolution, setResolution] = useState("");
  const [buffer, setBuffer] = useState("0");
  const fileRef = useRef<HTMLInputElement>(null);
  const revision = useRef(new PlanRevisionGate());
  const request = useRef<AbortController | null>(null);
  const focusedVertex = useRef<string | null>(null);

  const invalidate = () => {
    revision.current.invalidate(); request.current?.abort(); request.current = null;
    setPlan(null); setBusy(false); setError(null);
  };
  const replaceGeometry = (next: AoiGeometry) => {
    invalidate();
    if (geometry) setHistory((old) => [...old.slice(-49), geometry]);
    setGeometry(next);
  };
  const draw = () => {
    invalidate(); setGeometry(null); setDraft([]); setHistory([]); setRawImport(null); setMode("draw");
  };
  const clear = () => {
    invalidate(); setGeometry(null); setDraft([]); setHistory([]); setRawImport(null); setMode("idle");
    if (fileRef.current) fileRef.current.value = "";
  };
  const finish = () => {
    if (mode === "draw") {
      if (draft.length < 3) return;
      try { replaceGeometry(readGeometry({ type: "Polygon", coordinates: [[...draft, draft[0]]] })); }
      catch (err) { setError(err instanceof Error ? err.message : String(err)); return; }
      setDraft([]);
    }
    setMode("idle");
  };
  const undo = () => {
    invalidate();
    if (mode === "draw") setDraft((points) => points.slice(0, -1));
    else if (history.length) {
      setGeometry(history[history.length - 1]); setHistory((previous) => previous.slice(0, -1));
    }
  };

  const onMapClick = useEffectEvent((event: maplibregl.MapMouseEvent) => {
    if (mode !== "draw") return;
    if (draft.length >= 20000) { setError("Vertex limit reached"); return; }
    invalidate();
    setDraft((points) => [...points, [event.lngLat.lng, event.lngLat.lat]]);
  });
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const click = (event: maplibregl.MapMouseEvent) => onMapClick(event);
    map.on("click", click);
    return () => { map.off("click", click); };
  }, [mapRef, mapReady]);
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || mode === "idle") return;
    const wasEnabled = map.doubleClickZoom.isEnabled();
    const previousCursor = map.getCanvas().style.cursor;
    map.doubleClickZoom.disable(); map.getCanvas().style.cursor = "crosshair";
    return () => {
      if (wasEnabled) map.doubleClickZoom.enable();
      map.getCanvas().style.cursor = previousCursor;
    };
  }, [mapRef, mapReady, mode]);
  useEffect(() => () => { revision.current.invalidate(); request.current?.abort(); }, []);

  // Full server footprints are displayed. Neither viewport tiles nor this overlay
  // ever feed source selection back to the backend.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const features: Feature[] = [];
    if (geometry) features.push({ type: "Feature", geometry, properties: { kind: "AOI" } });
    if (draft.length >= 2) features.push({ type: "Feature", geometry: { type: "LineString", coordinates: draft }, properties: { kind: "AOI" } });
    for (const position of draft) features.push({ type: "Feature", geometry: { type: "Point", coordinates: position }, properties: { kind: "AOI" } });
    if (plan) {
      features.push({ type: "Feature", geometry: plan.processing_geometry, properties: { kind: "PROCESSING" } });
      for (const asset of plan.assets) {
        if (asset.source_footprint) features.push({ type: "Feature", geometry: asset.source_footprint,
          properties: { kind: "SOURCE", row_id: asset.row_id, decision: asset.disposition } });
      }
      if (showBbox) {
        const [w, s, e, n] = plan.discovery_bbox;
        features.push({ type: "Feature", geometry: { type: "Polygon", coordinates: [[[w,s],[e,s],[e,n],[w,n],[w,s]]] }, properties: { kind: "BBOX" } });
      }
    }
    const data: FeatureCollection = { type: "FeatureCollection", features };
    const paint = () => {
      if (!map.isStyleLoaded()) return;
      if (!map.getSource(SOURCE)) {
        map.addSource(SOURCE, { type: "geojson", data });
        map.addLayer({ id: LAYERS[0], type: "fill", source: SOURCE,
          filter: ["==", ["geometry-type"], "Polygon"], paint: { "fill-opacity": 0.09,
            "fill-color": ["match", ["get", "decision"], "UNRESOLVED", "#f59e0b", "EXCLUDED", "#64748b", "#38bdf8"] } });
        map.addLayer({ id: LAYERS[1], type: "line", source: SOURCE,
          paint: { "line-color": ["match", ["get", "kind"], "AOI", "#facc15", "BBOX", "#cbd5e1", "#38bdf8"], "line-width": 2 } });
        map.addLayer({ id: LAYERS[2], type: "circle", source: SOURCE,
          filter: ["==", ["geometry-type"], "Point"], paint: { "circle-radius": 5, "circle-color": "#facc15" } });
      } else {
        const source = map.getSource(SOURCE) as maplibregl.GeoJSONSource;
        void source.setData(data);
      }
    };
    paint(); map.on("style.load", paint);
    return () => { map.off("style.load", paint); };
  }, [mapRef, mapReady, geometry, draft, plan, showBbox]);
  useEffect(() => {
    const map = mapRef.current;
    return () => {
      if (!map?.getStyle()) return;
      for (const id of [...LAYERS].reverse()) if (map.getLayer(id)) map.removeLayer(id);
      if (map.getSource(SOURCE)) map.removeSource(SOURCE);
    };
  }, [mapRef, mapReady]);

  const onVertexMove = useEffectEvent((part: number, ring: number, vertex: number, value: Position) => {
    if (geometry) replaceGeometry(moveVertex(geometry, part, ring, vertex, value));
  });
  const handleCount = geometry ? polygonParts(geometry).reduce((sum, part) => sum + part.reduce((total, ring) => total + ring.length - 1, 0), 0) : 0;
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || mode !== "edit" || !geometry || handleCount > MAX_EDIT_HANDLES) return;
    const markers: maplibregl.Marker[] = [];
    let focusFrame: number | null = null;
    polygonParts(geometry).forEach((part, p) => part.forEach((ring, r) => ring.slice(0, -1).forEach((position, v) => {
      const id = `${p}:${r}:${v}`;
      const element = document.createElement("button");
      element.type = "button"; element.dataset.aoiVertex = id;
      element.setAttribute("aria-label", `Edit polygon ${p + 1}, ring ${r + 1}, vertex ${v + 1}; arrow keys move vertex`);
      Object.assign(element.style, { width: "44px", height: "44px", borderRadius: "50%", border: "2px solid #facc15", background: "#17212bcc", touchAction: "none", cursor: "move" });
      element.textContent = String(v + 1);
      const marker = new maplibregl.Marker({ element, draggable: true }).setLngLat(position).addTo(map);
      marker.on("dragstart", () => { focusedVertex.current = id; });
      marker.on("dragend", () => { const ll = marker.getLngLat(); onVertexMove(p, r, v, [ll.lng, ll.lat]); });
      element.addEventListener("keydown", (event) => {
        const direction: Record<string, [number, number]> = { ArrowLeft: [-1,0], ArrowRight: [1,0], ArrowUp: [0,-1], ArrowDown: [0,1] };
        const delta = direction[event.key];
        if (!delta) return;
        event.preventDefault(); event.stopPropagation(); focusedVertex.current = id;
        const pixel = map.project(marker.getLngLat()), step = event.shiftKey ? 10 : 1;
        const ll = map.unproject([pixel.x + delta[0] * step, pixel.y + delta[1] * step]);
        onVertexMove(p, r, v, [ll.lng, ll.lat]);
      });
      if (focusedVertex.current === id) focusFrame = requestAnimationFrame(() => element.focus());
      markers.push(marker);
    })));
    return () => { if (focusFrame !== null) cancelAnimationFrame(focusFrame); markers.forEach((marker) => marker.remove()); };
  }, [mapRef, mapReady, geometry, mode, handleCount]);

  const importGeoJson = async (file: File) => {
    invalidate(); const token = revision.current.invalidate();
    if (file.size > MAX_IMPORT_BYTES) { setError("Import exceeds 4 MiB; use a smaller AOI"); return; }
    if (!/\.(geojson|json)$/i.test(file.name)) { setError("This slice supports GeoJSON only. Other formats require backend conversion."); return; }
    try {
      const bytes = await file.arrayBuffer();
      const text = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(bytes);
      const parsed = readGeometry(JSON.parse(text.startsWith("\uFEFF") ? text.slice(1) : text) as unknown);
      if (!revision.current.current(token)) return;
      setRawImport(text); setGeometry(parsed); setDraft([]); setHistory([]); setMode("idle");
    } catch (err) { if (revision.current.current(token)) setError(err instanceof Error ? err.message : String(err)); }
  };
  const dryRun = async () => {
    if (!geometry || mode !== "idle") return;
    invalidate(); const token = revision.current.invalidate();
    if (!Number.isFinite(Number(buffer)) || Number(buffer) < 0 || (resolution !== "" && (!Number.isFinite(Number(resolution)) || Number(resolution) <= 0))) { setError("Invalid buffer or resolution"); return; }
    const controller = new AbortController(); request.current = controller; setBusy(true);
    try {
      const response = await fetch(`${API_BASE}/spatial/aoi/plan`, {
        method: "POST", signal: controller.signal, headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ aoi: geometry, raw_import_text: rawImport,
          input_kind: rawImport ? "IMPORTED_GEOJSON_WITH_EDIT_HISTORY" : "DRAWN",
          processing_buffer_m: Number(buffer), filters: {
            products: product ? [product] : [], providers: provider.trim() ? [provider.trim()] : [],
            date_from: dateFrom || null, date_to: dateTo || null,
            max_resolution_m: resolution ? Number(resolution) : null,
          } }),
      });
      const body: unknown = await response.json();
      if (!response.ok) throw new Error(`HTTP ${response.status}: ${JSON.stringify(body)}`);
      const frozen = parseFrozenPlan(body);
      assertPlanMatchesAoi(frozen, geometry);
      if (revision.current.current(token)) setPlan(frozen);
    } catch (err) {
      if (revision.current.current(token) && !(err instanceof DOMException && err.name === "AbortError")) setError(err instanceof Error ? err.message : String(err));
    } finally { if (revision.current.current(token)) setBusy(false); }
  };
  const exportPlan = () => {
    if (!plan) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(plan, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = `${plan.plan_id}.json`; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  };
  return <details className="tools-panel" open data-testid="aoi-map-workbench" style={{ maxHeight: "52dvh", overflowY: "auto", minWidth: 0 }}>
    <summary>AOI acquisition · {mode === "idle" ? (geometry ? "geometry pending/current plan below" : "no AOI") : mode}</summary>
    <div className="row" style={{ flexWrap: "wrap" }}>
      <button className="navbtn" type="button" onClick={draw} disabled={!mapReady}>Draw polygon</button>
      <button className="navbtn" type="button" onClick={() => { invalidate(); setMode("edit"); }} disabled={!geometry || !mapReady || handleCount > MAX_EDIT_HANDLES}>Edit vertices</button>
      <button className="navbtn" type="button" onClick={finish} disabled={mode === "idle" || (mode === "draw" && draft.length < 3)}>Finish</button>
      <button className="navbtn" type="button" onClick={undo} disabled={mode === "draw" ? !draft.length : !history.length}>Undo</button>
      <button className="navbtn" type="button" onClick={clear}>Clear AOI</button>
      <button className="navbtn" type="button" onClick={() => fileRef.current?.click()}>Import GeoJSON</button>
    </div>
    <input ref={fileRef} type="file" accept=".geojson,.json,application/geo+json,application/json" aria-label="Import AOI GeoJSON" hidden onChange={(event) => { const file = event.target.files?.[0]; if (file) void importGeoJson(file); event.target.value = ""; }} />
    <p>{mode === "draw" ? `Tap/click vertices (${draft.length}); use Finish, not double-tap.` : "Imported polygon parts and holes are preserved. Validation is performed by the backend."}</p>
    {handleCount > MAX_EDIT_HANDLES && <p role="alert">Imported AOI preserved; interactive editing is limited to {MAX_EDIT_HANDLES} vertices. No simplification was applied.</p>}
    <fieldset><legend>Plan scope</legend>
      <label>Product <select value={product} onChange={(event) => { invalidate(); setProduct(event.target.value); }}><option value="">All configured products</option><option value="bare_earth_dem">Bare-earth DEM</option><option value="point_cloud">Point cloud</option><option value="topobathy">Topobathy</option><option value="imagery">Imagery</option></select></label>
      <label>Provider ID <input value={provider} placeholder="All configured providers" onChange={(event) => { invalidate(); setProvider(event.target.value); }} /></label>
      <label>Acquired from <input type="date" value={dateFrom} onChange={(event) => { invalidate(); setDateFrom(event.target.value); }} /></label>
      <label>Acquired to <input type="date" value={dateTo} onChange={(event) => { invalidate(); setDateTo(event.target.value); }} /></label>
      <label>Maximum resolution (m) <input type="number" min="0.001" step="any" value={resolution} onChange={(event) => { invalidate(); setResolution(event.target.value); }} /></label>
      <label>Processing buffer (m) <input type="number" min="0" max="10000" value={buffer} onChange={(event) => { invalidate(); setBuffer(event.target.value); }} /></label>
      <label><input type="checkbox" checked={showBbox} onChange={(event) => setShowBbox(event.target.checked)} />Show backend discovery bbox (diagnostic only)</label>
    </fieldset>
    {error && <p role="alert" style={{ overflowWrap: "anywhere" }}>{error}</p>}
    <AoiAcquisitionWorkbench plan={plan} busy={busy} canDryRun={Boolean(geometry) && mode === "idle"} onDryRun={() => void dryRun()} onExportManifest={exportPlan} />
  </details>;
}

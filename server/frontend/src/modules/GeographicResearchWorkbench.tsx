import { useEffect, useState } from "react";
import { z } from "zod";
import type { MapMovementEvent } from "maplibre-gl";
import { API_BASE } from "../config";
import { fetchWithTimeout } from "../api/client";
import { useSpatialRuntime } from "../spatial/runtime/useSpatialRuntime";
import { DEFAULT_REGIONAL_SCENE_CONFIG } from "../spatial/config/regionalScene";
import type { CameraView } from "../spatial/runtime/SpatialRuntime";

const assetSchema = z.object({
  asset_id: z.string(), filename: z.string(), acquisition_status: z.string(),
  integrity_status: z.string(), expected_size_bytes: z.number().nullable(),
  licensing_status: z.string(), footprint: z.array(z.number()).length(4),
});
const optionSchema = z.object({
  dataset_version_id: z.string(), dataset_id: z.string(), source_id: z.string(),
  assets: z.array(assetSchema), valid_data_coverage: z.string(),
});
const contextSchema = z.object({
  context_id: z.string(), bbox: z.tuple([z.number(), z.number(), z.number(), z.number()]),
  catalog_scope: z.literal("PILOT_ONLY"), extent_within_pilot: z.boolean(),
  options: z.array(optionSchema), unresolved_asset_ids: z.array(z.string()),
  touch_only_asset_ids: z.array(z.string()),
});
type Context = z.infer<typeof contextSchema>;
type Camera = CameraView & { bearing: number; pitch: number };

function ComparisonPanel({ id, context, camera, onCamera }: {
  id: "A" | "B"; context: Context; camera: Camera | null; onCamera: (v: Camera) => void;
}) {
  const [version, setVersion] = useState("");
  const [assetId, setAssetId] = useState("");
  const { hostRef, mapRef, ready, graphicsUnavailableReason } = useSpatialRuntime(DEFAULT_REGIONAL_SCENE_CONFIG);
  const option = context.options.find((o) => o.dataset_version_id === version);
  const asset = option?.assets.find((a) => a.asset_id === assetId);
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const [w,s,e,n] = context.bbox;
    map.fitBounds([[w,s],[e,n]], { animate: false, padding: 20 });
  }, [ready, mapRef, context]);
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !camera) return;
    const c = map.getCenter();
    if (Math.abs(c.lng-camera.center[0]) < 1e-7 && Math.abs(c.lat-camera.center[1]) < 1e-7 &&
      Math.abs(map.getZoom()-camera.zoom) < 1e-7 && Math.abs(map.getBearing()-camera.bearing) < 1e-7 &&
      Math.abs(map.getPitch()-camera.pitch) < 1e-7) return;
    map.jumpTo(camera, { gsarSync: true });
  }, [ready, mapRef, camera]);
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const handler = (event: MapMovementEvent) => {
      if ((event as MapMovementEvent & { gsarSync?: boolean }).gsarSync) return;
      const c = map.getCenter();
      onCamera({ center: [c.lng,c.lat], zoom: map.getZoom(), bearing: map.getBearing(), pitch: map.getPitch() });
    };
    map.on("moveend", handler);
    return () => { map.off("moveend", handler); };
  }, [ready, mapRef, onCamera]);
  return <section aria-label={`Comparison panel ${id}`} style={{ minWidth: 0 }}>
    <h3>Panel {id}</h3>
    <label>Dataset version <select value={version} onChange={e => {setVersion(e.target.value); setAssetId("");}}>
      <option value="">Select dataset version</option>
      {context.options.map(o => <option key={o.dataset_version_id} value={o.dataset_version_id}>{o.dataset_version_id}</option>)}
    </select></label>
    <label>Native asset <select value={assetId} onChange={e => setAssetId(e.target.value)}>
      <option value="">Select native asset</option>
      {option?.assets.map(a => <option key={a.asset_id} value={a.asset_id}>{a.filename}</option>)}
    </select></label>
    <div ref={hostRef} style={{height: "320px", position: "relative"}} aria-label={`Reference basemap ${id}`} />
    {graphicsUnavailableReason && <p>{graphicsUnavailableReason}</p>}
    <p>Reference basemap only — selected raster evidence is not rendered.</p>
    {option && <p>{option.assets.length} intersecting files · valid-data coverage {option.valid_data_coverage}</p>}
    {asset && <dl><dt>Native file</dt><dd>{asset.filename}</dd><dt>Acquisition</dt><dd>{asset.acquisition_status}</dd><dt>Integrity</dt><dd>{asset.integrity_status}</dd><dt>Licensing</dt><dd>{asset.licensing_status}</dd><dt>Expected bytes</dt><dd>{asset.expected_size_bytes ?? "Unknown"}</dd></dl>}
  </section>;
}
export function GeographicResearchWorkbench() {
  const [bbox, setBbox] = useState("-66.05,18.3,-65.95,18.4");
  const [context, setContext] = useState<Context | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [sync, setSync] = useState(true);
  const [camera, setCamera] = useState<Camera | null>(null);
  async function resolve() {
    setBusy(true); setError(""); setContext(null); setCamera(null);
    try {
      const response = await fetchWithTimeout(`${API_BASE}/geo-sar/context?bbox=${encodeURIComponent(bbox)}`);
      if (!response.ok) throw new Error(`Context request failed: ${response.status}`);
      setContext(contextSchema.parse(await response.json()));
    } catch (err) { setError(String(err)); } finally { setBusy(false); }
  }
  return <section style={{padding: "1rem", overflow: "auto"}}>
    <h2>Geographic comparison — pilot</h2>
    <p>Read-only USGS 3DEP catalog. No downloads or analytical certification.</p>
    <form onSubmit={e => {e.preventDefault(); void resolve();}}>
      <label>Bounding box (west, south, east, north) <input value={bbox} onChange={e => setBbox(e.target.value)} /></label>
      <button disabled={busy}>Resolve extent</button>
    </form>
    <label><input type="checkbox" checked={sync} onChange={e => {setSync(e.target.checked); setCamera(null);}} /> Synchronize viewports</label>
    {error && <p role="alert">{error}</p>}
    {context && <>
      <p>{context.extent_within_pilot ? "Within pilot catalog extent" : "Outside or partly outside pilot catalog extent"} · {context.unresolved_asset_ids.length} unresolved footprints · {context.touch_only_asset_ids.length} boundary-only contacts.</p>
      <div key={context.context_id} style={{display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(min(100%, 300px),1fr))", gap:"1rem"}}>
        <ComparisonPanel id="A" context={context} camera={sync ? camera : null} onCamera={setCamera} />
        <ComparisonPanel id="B" context={context} camera={sync ? camera : null} onCamera={setCamera} />
      </div>
    </>}
  </section>;
}

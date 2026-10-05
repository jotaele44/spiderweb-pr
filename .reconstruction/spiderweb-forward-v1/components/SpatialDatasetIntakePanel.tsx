import { useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, Database, FileArchive, ShieldCheck } from "lucide-react";
import { FileDropzone } from "./FileDropzone";
import { Badge } from "./Badge";
import {
  buildAnalysisReceipt,
  buildSpatialDatasets,
  buildUploadManifest,
  closeDatasetArithmetic,
  preflightAnalysis,
  presetEligibility,
  type PresetId,
  type UploadFileInput,
} from "../helpers/spatialDatasetPipeline";
import styles from "./SpatialDatasetIntakePanel.module.css";

const PRESETS: PresetId[] = ["MANIFEST_AUDIT", "TOPOLOGY_REVIEW", "EXACT_ID_DIFF", "TERRAIN_CANDIDATES"];

export function SpatialDatasetIntakePanel() {
  const [uploads, setUploads] = useState<UploadFileInput[]>([]);
  const [status, setStatus] = useState("No uploads staged. Source identity is never inferred from filenames.");
  const [preset, setPreset] = useState<PresetId>("MANIFEST_AUDIT");
  const manifest = useMemo(() => buildUploadManifest(uploads), [uploads]);
  const datasets = useMemo(() => buildSpatialDatasets(manifest), [manifest]);
  const closure = useMemo(() => closeDatasetArithmetic(manifest, datasets), [manifest, datasets]);
  const preflight = useMemo(() => preflightAnalysis(preset, datasets), [preset, datasets]);
  const receipt = useMemo(() => datasets.length ? buildAnalysisReceipt(preset, datasets) : null, [preset, datasets]);

  const onFiles = async (files: File[]) => {
    setStatus(`Hashing ${files.length} source manifestation(s)…`);
    const rows: UploadFileInput[] = [];
    for (const file of files) {
      let sha256: string | undefined;
      if (globalThis.crypto?.subtle) {
        const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
        sha256 = [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, "0")).join("");
      }
      rows.push({ name: file.name, size: file.size, mime: file.type, relativePath: file.webkitRelativePath || undefined, sha256 });
    }
    setUploads(rows);
    setStatus(rows.every(row => row.sha256) ? `${rows.length} source manifestation(s) SHA-256 bound.` : `${rows.length} source manifestation(s) staged; one or more hashes unavailable.`);
  };

  return <section className={styles.panel} aria-label="Spatial dataset intake and preflight">
    <header className={styles.header}><div><span>MANIFEST → DATASET → PREFLIGHT → ANALYSIS → RECEIPT</span><h2>Dataset intake</h2><p>Files remain independent source manifestations unless a relation is authoritative. Shapefile sidecars group only by exact stem; archives and unsupported adapters fail closed.</p></div><Database size={22}/></header>
    <FileDropzone maxFiles={25} onFilesSelected={onFiles} title="Stage spatial source files" subtitle="GeoJSON, KML, CSV, Shapefile sidecars, KMZ/ZIP, GeoPackage and raster inputs are classified before analysis." />
    <div className={styles.status}>{status}</div>
    <div className={styles.presetRow}>{PRESETS.map(id => { const eligibility = presetEligibility(id, datasets); return <button type="button" key={id} data-active={preset===id} disabled={!eligibility.eligible && id!==preset} onClick={()=>setPreset(id)}><span>{id}</span><small>{eligibility.eligible ? "eligible" : eligibility.reason}</small></button> })}</div>
    <div className={styles.summary}>
      <Summary label="manifestations" value={manifest.length}/><Summary label="datasets" value={datasets.length}/><Summary label="ready" value={preflight.arithmetic.ready}/><Summary label="review" value={preflight.arithmetic.review}/><Summary label="blocked" value={preflight.arithmetic.blocked}/>
    </div>
    <div className={styles.gates}>
      <Badge variant={closure.closed ? "success" : "warning"}>{closure.closed ? "ARITHMETIC CLOSED" : "ARITHMETIC OPEN"}</Badge>
      <Badge variant={preflight.state === "PASS" ? "success" : "warning"}>PREFLIGHT {preflight.state}</Badge>
      {receipt && <code>{receipt.fingerprint}</code>}
    </div>
    {datasets.length > 0 && <div className={styles.datasets}>{datasets.map(dataset => <article key={dataset.datasetId}><div><strong>{dataset.datasetId}</strong><Badge variant={dataset.state === "READY" ? "success" : "warning"}>{dataset.state}</Badge></div><p>{dataset.format} · {dataset.role} · {dataset.capabilities.join(" / ") || "NO ANALYSIS CAPABILITY"}</p><code>{dataset.sourceIds.join(" | ")}</code>{dataset.issues.map(issue => <p key={`${dataset.datasetId}:${issue.code}`} className={styles.issue}><AlertTriangle size={13}/>{issue.code}: {issue.detail}</p>)}</article>)}</div>}
    {datasets.length > 0 && <footer className={styles.footer}>{preflight.state === "BLOCK" ? <><AlertTriangle size={16}/>Analysis is blocked until preflight residue closes.</> : <><CheckCircle2 size={16}/>Canonical analysis graph may execute as ANALYSIS_ONLY; RAW/NORMALIZED/CANONICAL planes remain distinct.</>}<span><ShieldCheck size={15}/>GeoPackage and unverified specialized adapters remain blocked.</span><span><FileArchive size={15}/>Archives are never auto-related to sibling files.</span></footer>}
  </section>;
}

function Summary({label,value}:{label:string;value:number}) { return <div><strong>{value}</strong><span>{label}</span></div>; }
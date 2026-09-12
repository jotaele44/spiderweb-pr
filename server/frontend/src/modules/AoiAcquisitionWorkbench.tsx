import { useMemo } from "react";

export type AoiWorkflowState =
  | "NO_AOI"
  | "AOI_EDITING"
  | "AOI_VALIDATING"
  | "AOI_VALID"
  | "DISCOVERING"
  | "PLAN_READY"
  | "REVIEWED"
  | "ACQUIRING"
  | "VALIDATING"
  | "COVERAGE_COMPUTING"
  | "PASS"
  | "OPEN"
  | "FAIL"
  | "BLOCKED";

export type SpatialRelation =
  | "FULLY_WITHIN"
  | "PARTIAL"
  | "TOUCH_ONLY"
  | "OUTSIDE"
  | "NULL_EMPTY"
  | "UNRESOLVED";

export type AssetState =
  | "QUEUED"
  | "CACHE_HIT"
  | "DOWNLOADING"
  | "DOWNLOADED"
  | "HASHING"
  | "VALIDATING"
  | "PASS"
  | "FAIL"
  | "UNRESOLVED";

export interface AoiDiagnostics {
  geometryType: "Polygon" | "MultiPolygon" | "UNRESOLVED";
  crs: string | null;
  vertexCount: number;
  areaKm2: number | null;
  valid: boolean;
  messages: string[];
}

export interface AcquisitionAssetRow {
  assetId: string;
  source: string;
  datasetId: string;
  product: string;
  acquisitionDate?: string | null;
  resolution?: string | null;
  relation: SpatialRelation;
  cacheState: string;
  sizeBytes?: number | null;
  sourceStatus: string;
  acquisitionState: AssetState;
  validationState: string;
  blockedReason?: string | null;
}

export interface AcquisitionPlanCounts {
  discovered: number;
  retained: number;
  excluded: number;
  unresolved: number;
  required: number;
  cacheValid: number;
  fetchRequired: number;
  blockedRequired: number;
}

export interface CoverageSummary {
  aoiAreaKm2: number;
  validAreaKm2: number;
  gapAreaKm2: number;
  percent: number;
  state: "UNKNOWN" | "PROVISIONAL" | "PASS" | "OPEN" | "FAIL";
}

export interface FrozenAcquisitionPlan {
  planId: string;
  planSha256: string;
  generatedAtUtc: string;
  state: AoiWorkflowState;
  diagnostics: AoiDiagnostics;
  counts: AcquisitionPlanCounts;
  estimatedDownloadBytesKnown: number;
  coverage?: CoverageSummary | null;
  assets: AcquisitionAssetRow[];
  unresolvedReasons: string[];
}

export interface AoiAcquisitionWorkbenchProps {
  plan: FrozenAcquisitionPlan | null;
  busy?: boolean;
  canDryRun?: boolean;
  onDraw?: () => void;
  onImport?: () => void;
  onEdit?: () => void;
  onClear?: () => void;
  onDryRun?: () => void;
  onFetch?: () => void;
  onExportManifest?: () => void;
}

export interface ArithmeticAudit {
  discoveredClosed: boolean;
  requiredClosed: boolean;
  pass: boolean;
}

export function auditPlanArithmetic(counts: AcquisitionPlanCounts): ArithmeticAudit {
  const discoveredClosed = counts.discovered === counts.retained + counts.excluded + counts.unresolved;
  const requiredClosed = counts.required === counts.cacheValid + counts.fetchRequired + counts.blockedRequired;
  return { discoveredClosed, requiredClosed, pass: discoveredClosed && requiredClosed };
}

function formatBytes(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B known";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(index >= 3 ? 2 : 1)} ${units[index]}`;
}

function StateLine({ label, value }: { label: string; value: string | number }) {
  return <p><span className="subtle">{label}</span> <strong>{value}</strong></p>;
}

export function AoiAcquisitionWorkbench({
  plan,
  busy = false,
  canDryRun = false,
  onDraw,
  onImport,
  onEdit,
  onClear,
  onDryRun,
  onFetch,
  onExportManifest,
}: AoiAcquisitionWorkbenchProps) {
  const arithmetic = useMemo(() => plan ? auditPlanArithmetic(plan.counts) : null, [plan]);
  const fetchBlocked = !plan
    || !arithmetic?.pass
    || plan.counts.blockedRequired > 0
    || plan.counts.unresolved > 0
    || !["PLAN_READY", "REVIEWED", "OPEN"].includes(plan.state);

  return (
    <section className="tools-panel" aria-label="AOI acquisition workbench">
      <h2>AOI acquisition</h2>
      <div className="row">
        <button className="navbtn" onClick={onDraw} disabled={busy}>Draw</button>
        <button className="navbtn" onClick={onImport} disabled={busy}>Import</button>
        <button className="navbtn" onClick={onEdit} disabled={busy || !plan}>Edit</button>
        <button className="navbtn" onClick={onClear} disabled={busy || !plan}>Clear</button>
      </div>

      {!plan && (
        <div className="tools-readout">
          <p>No frozen AOI plan loaded.</p>
          <p>Polygon is authoritative; any bbox is discovery-only.</p>
        </div>
      )}

      {plan && (
        <>
          <div className="tools-readout">
            <StateLine label="State" value={plan.state} />
            <StateLine label="Plan" value={plan.planId} />
            <StateLine label="Geometry" value={`${plan.diagnostics.geometryType} · ${plan.diagnostics.valid ? "VALID" : "INVALID"}`} />
            <StateLine label="CRS" value={plan.diagnostics.crs ?? "UNRESOLVED"} />
            <StateLine label="Vertices" value={plan.diagnostics.vertexCount} />
            {plan.diagnostics.areaKm2 !== null && <StateLine label="AOI area" value={`${plan.diagnostics.areaKm2.toFixed(3)} km²`} />}
            {plan.diagnostics.messages.map((message) => <p key={message} role={plan.diagnostics.valid ? undefined : "alert"}>{message}</p>)}
          </div>

          <div className="hr" />
          <div className="tools-readout">
            <StateLine label="Discovered" value={plan.counts.discovered} />
            <StateLine label="Retained" value={plan.counts.retained} />
            <StateLine label="Excluded" value={plan.counts.excluded} />
            <StateLine label="Unresolved" value={plan.counts.unresolved} />
            <StateLine label="Required" value={plan.counts.required} />
            <StateLine label="Cache valid" value={plan.counts.cacheValid} />
            <StateLine label="Fetch required" value={plan.counts.fetchRequired} />
            <StateLine label="Blocked required" value={plan.counts.blockedRequired} />
            <StateLine label="Transfer known" value={formatBytes(plan.estimatedDownloadBytesKnown)} />
            <p>Arithmetic: <strong>{arithmetic?.pass ? "PASS" : "FAIL"}</strong></p>
            {!arithmetic?.discoveredClosed && <p role="alert">Discovery arithmetic does not close.</p>}
            {!arithmetic?.requiredClosed && <p role="alert">Required-asset arithmetic does not close.</p>}
          </div>

          {plan.coverage && (
            <>
              <div className="hr" />
              <div className="tools-readout">
                <StateLine label="Coverage state" value={plan.coverage.state} />
                <StateLine label="Valid coverage" value={`${plan.coverage.percent.toFixed(2)}%`} />
                <StateLine label="Valid area" value={`${plan.coverage.validAreaKm2.toFixed(3)} km²`} />
                <StateLine label="Gap" value={`${plan.coverage.gapAreaKm2.toFixed(3)} km²`} />
                <p>Files present/downloaded are not treated as usable coverage.</p>
              </div>
            </>
          )}

          {plan.unresolvedReasons.length > 0 && (
            <div className="tools-readout" role="alert">
              <strong>Unresolved residue</strong>
              {plan.unresolvedReasons.map((reason) => <p key={reason}>{reason}</p>)}
            </div>
          )}

          <div className="hr" />
          <div className="row">
            <button className="act" onClick={onDryRun} disabled={busy || !canDryRun}>Dry run</button>
            <button className="act" onClick={onFetch} disabled={busy || fetchBlocked}>Fetch {plan.counts.fetchRequired}</button>
            <button className="act" onClick={onExportManifest} disabled={busy}>Export manifest</button>
          </div>

          <div className="tools-readout" style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>Asset</th><th>Source</th><th>Product</th><th>Spatial</th><th>Cache</th><th>Acquire</th><th>Validate</th>
                </tr>
              </thead>
              <tbody>
                {plan.assets.map((asset) => (
                  <tr key={`${asset.source}:${asset.datasetId}:${asset.assetId}`}>
                    <td>{asset.assetId}</td>
                    <td>{asset.source}</td>
                    <td>{asset.product}</td>
                    <td>{asset.relation}</td>
                    <td>{asset.cacheState}</td>
                    <td>{asset.acquisitionState}</td>
                    <td>{asset.validationState}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="subtle">Plan SHA-256: {plan.planSha256}</p>
        </>
      )}
    </section>
  );
}

import { useState } from "react";
import { auditPlanArithmetic } from "./aoiContract";
import type { FrozenAcquisitionPlan } from "./aoiContract";
export { auditPlanArithmetic } from "./aoiContract";
export type { FrozenAcquisitionPlan, AcquisitionPlanCounts } from "./aoiContract";

export function AoiAcquisitionWorkbench({ plan, busy, canDryRun, onDryRun, onExportManifest }: {
  plan: FrozenAcquisitionPlan | null; busy: boolean; canDryRun: boolean;
  onDryRun: () => void; onExportManifest: () => void;
}) {
  const [page, setPage] = useState(0);
  const pageCount = Math.max(1, Math.ceil((plan?.assets.length ?? 0) / 100));
  const current = Math.min(page, pageCount - 1);
  return <section aria-label="AOI acquisition workbench" style={{ minWidth: 0 }}>
    <h3>Acquisition plan</h3>
    <div className="row">
      <button className="act" type="button" onClick={onDryRun} disabled={busy || !canDryRun}>Dry run</button>
      <button className="act" type="button" disabled title="Acquisition worker and validated cache are not connected">Fetch disabled</button>
      <button className="act" type="button" onClick={onExportManifest} disabled={!plan || busy}>Export plan</button>
    </div>
    <p>Polygon authoritative. Bbox discovery-only. No source bytes are downloaded by Dry Run.</p>
    {busy && <p role="status">Validating geometry and planning against configured catalog snapshots…</p>}
    {!plan && !busy && <p>No current backend plan. Finish or import an AOI, then run Dry Run.</p>}
    {plan && <>
      <p role="status">Planning: <strong>{plan.planning_gate}</strong> · Workflow: {plan.state} · Certification: OPEN</p>
      <p>{plan.diagnostics.geometry_type} · {plan.diagnostics.vertex_count} vertices · {plan.diagnostics.area_km2.toFixed(4)} km² · {plan.diagnostics.crs}</p>
      <p>Discovered {plan.counts.discovered} = retained {plan.counts.retained} + excluded {plan.counts.excluded} + unresolved {plan.counts.unresolved}.</p>
      <p>Required {plan.counts.required} = validated cache {plan.counts.cache_valid} + transfer candidates {plan.counts.fetch_required} + blocked {plan.counts.blocked_required}.</p>
      <p>Arithmetic: {auditPlanArithmetic(plan.counts).pass ? "PASS" : "FAIL"} · Known bytes: {plan.estimated_download_bytes_known.toLocaleString()} · Unknown-size assets: {plan.unknown_size_assets}.</p>
      <p>Cache: NOT CHECKED. Usable-data coverage: UNKNOWN. Footprints are not valid-data masks.</p>
      {plan.unresolved_reasons.length > 0 && <div role="alert"><strong>Unresolved planning residue</strong>{plan.unresolved_reasons.map((reason, i) => <p key={i}>{reason}</p>)}</div>}
      <p>Execution blocked: {plan.execution_blockers.join("; ")}</p>
      <div style={{ overflowX: "auto", maxHeight: "28dvh" }} tabIndex={0} aria-label="Complete candidate set, paginated">
        <table><caption>All {plan.assets.length} rows; page {current + 1} of {pageCount}. Exclusions are not removed.</caption>
          <thead><tr><th>Row / asset</th><th>Source / product</th><th>AOI / processing</th><th>Decision</th><th>Cache / acquire / validate</th><th>Reasons</th></tr></thead>
          <tbody>{plan.assets.slice(current * 100, (current + 1) * 100).map((asset) => <tr key={asset.row_id}>
            <td>{asset.row_id}<br />{asset.asset_id}</td><td>{asset.source}<br />{asset.product}</td>
            <td>{asset.relation}<br />{asset.processing_relation}</td><td>{asset.disposition}</td>
            <td>{asset.cache_state}<br />{asset.acquisition_state}<br />{asset.validation_state}</td><td>{asset.reasons.join("; ") || "—"}</td>
          </tr>)}</tbody>
        </table>
      </div>
      <div className="row"><button type="button" disabled={current === 0} onClick={() => setPage(current - 1)}>Previous rows</button><button type="button" disabled={current + 1 >= pageCount} onClick={() => setPage(current + 1)}>Next rows</button></div>
      <p style={{ overflowWrap: "anywhere" }}>Frozen plan: {plan.plan_id}</p>
    </>}
  </section>;
}

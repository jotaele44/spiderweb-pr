export type AcquisitionPlane = "STATIC_DOWNLOAD" | "WFS" | "WMS" | "REST" | "RASTER";
export type AcquisitionDisposition = "FROZEN" | "ZERO_RESULT" | "BLOCKED" | "FAILED" | "OPEN";

export interface SpatialSourceRequirement {
  sourceId: string;
  plane: AcquisitionPlane;
  mutable: boolean;
  required: boolean;
  authority: "AUTHORITATIVE" | "SUPPORTING" | "CONTEXT";
}

export interface SpatialAcquisitionRecord {
  sourceId: string;
  plane: AcquisitionPlane;
  disposition: AcquisitionDisposition;
  manifestationSha256: string | null;
  retrievedAt: string | null;
  locator: string;
  rowOrFeatureCount: number | null;
  parserContract: string | null;
  evidenceNote?: string;
}

export interface AcquisitionCoverageReceipt {
  schema: "spiderweb-acquisition-coverage/v1";
  required: number;
  frozen: number;
  zeroResult: number;
  blocked: number;
  failed: number;
  open: number;
  omitted: string[];
  duplicates: string[];
  planeArithmetic: Record<AcquisitionPlane, { required: number; terminal: number; open: number }>;
  state: "PASS" | "OPEN" | "BLOCKED";
  certificationEligible: boolean;
}

export function closeAcquisitionCoverage(requirements: SpatialSourceRequirement[], records: SpatialAcquisitionRecord[]): AcquisitionCoverageReceipt {
  const requiredRows = requirements.filter(row => row.required);
  const recordIds = records.map(row => row.sourceId);
  const duplicates = [...new Set(recordIds.filter((id,index)=>recordIds.indexOf(id)!==index))].sort();
  const byId = new Map(records.map(row => [row.sourceId,row]));
  const omitted = requiredRows.filter(row => !byId.has(row.sourceId)).map(row => row.sourceId).sort();
  const dispositions = requiredRows.map(req => byId.get(req.sourceId)?.disposition ?? "OPEN");
  const counts = {
    frozen: dispositions.filter(v=>v==="FROZEN").length,
    zeroResult: dispositions.filter(v=>v==="ZERO_RESULT").length,
    blocked: dispositions.filter(v=>v==="BLOCKED").length,
    failed: dispositions.filter(v=>v==="FAILED").length,
    open: dispositions.filter(v=>v==="OPEN").length + omitted.length,
  };
  const planeArithmetic = Object.fromEntries((["STATIC_DOWNLOAD","WFS","WMS","REST","RASTER"] as AcquisitionPlane[]).map(plane=>{
    const req=requiredRows.filter(row=>row.plane===plane);
    const rows=req.map(row=>byId.get(row.sourceId));
    const terminal=rows.filter(row=>row && ["FROZEN","ZERO_RESULT","BLOCKED","FAILED"].includes(row.disposition)).length;
    return [plane,{required:req.length,terminal,open:req.length-terminal}];
  })) as AcquisitionCoverageReceipt["planeArithmetic"];
  const terminalArithmetic = counts.frozen + counts.zeroResult + counts.blocked + counts.failed + counts.open;
  if (terminalArithmetic !== requiredRows.length + omitted.length) {
    throw new Error("Acquisition arithmetic failed to close.");
  }
  const invalidFrozen = requiredRows.filter(req => {
    const row=byId.get(req.sourceId);
    return row?.disposition==="FROZEN" && (!row.manifestationSha256 || !row.retrievedAt || !row.parserContract);
  });
  const unresolved = counts.open>0 || duplicates.length>0 || invalidFrozen.length>0;
  const blocked = counts.blocked>0 || counts.failed>0;
  return {
    schema:"spiderweb-acquisition-coverage/v1",
    required:requiredRows.length,
    ...counts,
    omitted,
    duplicates,
    planeArithmetic,
    state: unresolved ? "OPEN" : blocked ? "BLOCKED" : "PASS",
    certificationEligible: !unresolved && !blocked && counts.zeroResult + counts.frozen === requiredRows.length,
  };
}

export function shouldReacquireMutableSource(requirement: SpatialSourceRequirement, latest: SpatialAcquisitionRecord | null) {
  if (!requirement.mutable) return { reacquire:false, reason:"IMMUTABLE_SOURCE" as const };
  if (!latest) return { reacquire:true, reason:"NO_SNAPSHOT" as const };
  if (latest.disposition !== "FROZEN") return { reacquire:true, reason:"NO_FROZEN_CURRENT_SNAPSHOT" as const };
  if (!latest.manifestationSha256 || !latest.retrievedAt) return { reacquire:true, reason:"INCOMPLETE_FROZEN_SNAPSHOT" as const };
  return { reacquire:false, reason:"FROZEN_SNAPSHOT_AVAILABLE" as const };
}

export function acquisitionUsePolicy(record: SpatialAcquisitionRecord) {
  if (record.plane === "WMS") return { dataAuthority:false, use:"RENDER_OR_CONTEXT_ONLY" as const };
  if (record.disposition !== "FROZEN") return { dataAuthority:false, use:"NO_DATA_PROMOTION" as const };
  return { dataAuthority:true, use:"SOURCE_MANIFESTATION" as const };
}
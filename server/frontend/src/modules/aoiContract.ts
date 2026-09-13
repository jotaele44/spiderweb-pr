/** Wire protocol v1.1. Backend is authoritative; these are rejection gates only. */
export type Position = [number, number];
export type AoiGeometry = { type: "Polygon"; coordinates: Position[][] }
  | { type: "MultiPolygon"; coordinates: Position[][][] };
export type AoiMode = "idle" | "draw" | "edit";
export type SpatialRelation = "FULLY_WITHIN" | "PARTIAL" | "TOUCH_ONLY" | "OUTSIDE" | "NULL_EMPTY" | "UNRESOLVED";
export interface AcquisitionPlanCounts {
  discovered: number; retained: number; excluded: number; unresolved: number;
  required: number; cache_valid: number; fetch_required: number; blocked_required: number;
}
export interface AcquisitionAssetRow {
  row_id: string; asset_id: string; source: string; dataset_id: string; product: string;
  source_status: string; relation: SpatialRelation; processing_relation: SpatialRelation;
  source_footprint: AoiGeometry | null; asset_key: string | null;
  disposition: "RETAINED" | "EXCLUDED" | "UNRESOLVED"; required: boolean;
  cache_state: string; acquisition_state: string; validation_state: string; reasons: string[];
  size_bytes: number | null;
}
export interface FrozenAcquisitionPlan {
  schema_version: "aoi_acquisition_plan.v1.1"; plan_id: string; plan_sha256: string;
  aoi_sha256: string; state: "PLAN_READY" | "BLOCKED"; planning_gate: "PASS" | "BLOCKED";
  certification: "OPEN"; capabilities: { fetch: false }; execution_blockers: string[];
  normalized_aoi: AoiGeometry; processing_geometry: AoiGeometry; discovery_bbox: number[];
  diagnostics: { geometry_type: string; crs: string; vertex_count: number; area_km2: number; valid: boolean; messages: string[] };
  counts: AcquisitionPlanCounts; assets: AcquisitionAssetRow[]; arithmetic_closed: boolean;
  estimated_download_bytes_known: number; unknown_size_assets: number;
  coverage: null; coverage_state: "UNKNOWN"; unresolved_reasons: string[];
}
const RELATIONS = ["FULLY_WITHIN", "PARTIAL", "TOUCH_ONLY", "OUTSIDE", "NULL_EMPTY", "UNRESOLVED"];
const COUNT_KEYS = ["discovered", "retained", "excluded", "unresolved", "required", "cache_valid", "fetch_required", "blocked_required"] as const;
function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Expected object");
  return value as Record<string, unknown>;
}
function strings(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item: unknown) => typeof item === "string");
}
function count(value: unknown): value is number { return Number.isSafeInteger(value) && Number(value) >= 0; }
export function readGeometry(value: unknown): AoiGeometry {
  const doc = record(value);
  if ("crs" in doc) {
    const name = record(record(doc.crs).properties).name;
    if (!["EPSG:4326", "OGC:CRS84", "urn:ogc:def:crs:OGC:1.3:CRS84"].includes(String(name))) throw new Error("CRS unresolved; convert explicitly");
  }
  if (doc.type === "FeatureCollection") {
    if (!Array.isArray(doc.features) || doc.features.length !== 1) throw new Error("Select exactly one feature; no implicit merge");
    return readGeometry(doc.features[0]);
  }
  if (doc.type === "Feature") return readGeometry(doc.geometry);
  if (doc.type !== "Polygon" && doc.type !== "MultiPolygon") throw new Error("Polygon or MultiPolygon required");
  const parts: unknown = doc.type === "Polygon" ? [doc.coordinates] : doc.coordinates;
  if (!Array.isArray(parts) || parts.length === 0) throw new Error("Empty polygon");
  let vertices = 0;
  for (const part of parts as unknown[]) {
    if (!Array.isArray(part) || part.length === 0) throw new Error("Empty polygon part");
    for (const ring of part as unknown[]) {
      if (!Array.isArray(ring) || ring.length < 4) throw new Error("Closed rings need four positions");
      for (const p of ring as unknown[]) {
        if (!Array.isArray(p) || p.length !== 2 || !p.every((n: unknown) => typeof n === "number" && Number.isFinite(n))) throw new Error("Finite 2D coordinates required; Z is not discarded");
        if (Math.abs(Number(p[0])) > 180 || Math.abs(Number(p[1])) > 90) throw new Error("Coordinates outside CRS84 range");
      }
      if (JSON.stringify(ring[0]) !== JSON.stringify(ring.at(-1))) throw new Error("Unclosed ring; no silent repair");
      vertices += ring.length - 1;
    }
  }
  if (vertices > 20000) throw new Error("AOI vertex limit exceeded");
  // Only structure is checked here. Topology/identity/selection remain server-owned.
  return structuredClone(doc) as AoiGeometry;
}
export function polygonParts(geometry: AoiGeometry): Position[][][] {
  return geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
}
export function moveVertex(geometry: AoiGeometry, part: number, ring: number, vertex: number, point: Position): AoiGeometry {
  const next = structuredClone(geometry);
  const selected = polygonParts(next)[part]?.[ring];
  if (!selected || vertex < 0 || vertex >= selected.length - 1) throw new Error("Unknown vertex");
  selected[vertex] = [...point];
  if (vertex === 0) selected[selected.length - 1] = [...point];
  return readGeometry(next);
}
export function auditPlanArithmetic(c: AcquisitionPlanCounts) {
  const finiteCounts = COUNT_KEYS.every((key) => count(c[key]));
  const discoveredClosed = finiteCounts && c.discovered === c.retained + c.excluded + c.unresolved;
  const requiredClosed = finiteCounts && c.required === c.cache_valid + c.fetch_required + c.blocked_required;
  return { discoveredClosed, requiredClosed, pass: discoveredClosed && requiredClosed };
}
export function parseFrozenPlan(value: unknown): FrozenAcquisitionPlan {
  const p = record(value), c = record(p.counts), d = record(p.diagnostics);
  if (p.schema_version !== "aoi_acquisition_plan.v1.1") throw new Error("Unsupported AOI plan schema");
  if (typeof p.plan_sha256 !== "string" || !/^[a-f0-9]{64}$/.test(p.plan_sha256) || p.plan_id !== `aoi-${p.plan_sha256}`) throw new Error("Invalid frozen plan identifier");
  if (typeof p.aoi_sha256 !== "string" || !/^[a-f0-9]{64}$/.test(p.aoi_sha256)) throw new Error("Missing AOI binding");
  if (!COUNT_KEYS.every((key) => count(c[key]))) throw new Error("Invalid counts");
  const counts = c as unknown as AcquisitionPlanCounts;
  if (!auditPlanArithmetic(counts).pass || p.arithmetic_closed !== true) throw new Error("Plan arithmetic does not close");
  if (!Array.isArray(p.assets) || p.assets.length !== counts.discovered) throw new Error("Candidate row denominator mismatch");
  const ids = new Set<string>();
  let required = 0, retained = 0, excluded = 0, unresolved = 0, fetchRequired = 0, blockedRequired = 0;
  for (const item of p.assets as unknown[]) {
    const row = record(item);
    for (const field of ["row_id", "asset_id", "source", "dataset_id", "product", "source_status", "cache_state", "acquisition_state", "validation_state"]) {
      if (typeof row[field] !== "string" || !row[field]) throw new Error(`Invalid asset ${field}`);
    }
    if (ids.has(String(row.row_id))) throw new Error("Duplicate candidate row ID");
    ids.add(String(row.row_id));
    if (!RELATIONS.includes(String(row.relation)) || !RELATIONS.includes(String(row.processing_relation))) throw new Error("Unknown spatial relation");
    if (!strings(row.reasons) || typeof row.required !== "boolean") throw new Error("Missing row decision");
    if (row.source_footprint !== null) readGeometry(row.source_footprint);
    if (row.disposition === "RETAINED") retained++;
    else if (row.disposition === "EXCLUDED") excluded++;
    else if (row.disposition === "UNRESOLVED") unresolved++;
    else throw new Error("Unknown disposition");
    if (row.required) {
      required++;
      if (!["FULLY_WITHIN", "PARTIAL"].includes(String(row.processing_relation)) || row.source_footprint === null) throw new Error("Non-area candidate marked required");
      if (row.disposition === "RETAINED") {
        if (row.source_status !== "SOURCE_BOUND" || typeof row.asset_key !== "string" || !/^[a-f0-9]{64}$/.test(row.asset_key)) throw new Error("Required identity unbound");
        fetchRequired++;
      } else if (row.disposition === "UNRESOLVED") blockedRequired++;
      else throw new Error("Excluded row marked required");
    } else if (row.disposition === "RETAINED") throw new Error("Retained row not marked required");
    if (row.size_bytes !== null && !count(row.size_bytes)) throw new Error("Invalid size");
    // v1.1 dry-run adapter has no cache validator. Reject invented cache PASS.
    if (row.cache_state !== "NOT_CHECKED" || row.validation_state !== "NOT_RUN" || !["QUEUED", "UNRESOLVED"].includes(String(row.acquisition_state))) throw new Error("Unsupported acquisition/cache promotion");
  }
  if (counts.required !== required || counts.retained !== retained || counts.excluded !== excluded || counts.unresolved !== unresolved || counts.fetch_required !== fetchRequired || counts.blocked_required !== blockedRequired || counts.cache_valid !== 0) throw new Error("Counters disagree with actual candidate decisions");
  readGeometry(p.normalized_aoi); readGeometry(p.processing_geometry);
  if (!Array.isArray(p.discovery_bbox) || p.discovery_bbox.length !== 4 || !p.discovery_bbox.every((v: unknown) => typeof v === "number" && Number.isFinite(v))) throw new Error("Invalid backend discovery bbox");
  if (Number(p.discovery_bbox[0]) >= Number(p.discovery_bbox[2]) || Number(p.discovery_bbox[1]) >= Number(p.discovery_bbox[3])) throw new Error("Invalid bbox ordering");
  if (d.valid !== true || !["Polygon", "MultiPolygon"].includes(String(d.geometry_type)) || d.crs !== "OGC:CRS84" || !count(d.vertex_count) || typeof d.area_km2 !== "number" || !Number.isFinite(d.area_km2) || d.area_km2 <= 0 || !strings(d.messages)) throw new Error("Invalid backend diagnostics");
  if (!strings(p.unresolved_reasons) || !strings(p.execution_blockers)) throw new Error("Missing residue lists");
  if (p.state !== "PLAN_READY" && p.state !== "BLOCKED") throw new Error("Unsupported workflow state");
  if (p.planning_gate !== "PASS" && p.planning_gate !== "BLOCKED") throw new Error("Invalid plan gate");
  if ((p.state === "PLAN_READY") !== (p.planning_gate === "PASS")) throw new Error("Conflicting plan states");
  if (p.planning_gate === "PASS" && (required === 0 || unresolved > 0 || blockedRequired > 0 || p.unresolved_reasons.length > 0)) throw new Error("Empty/partial plan promoted to ready");
  if (record(p.capabilities).fetch !== false || p.certification !== "OPEN" || p.coverage !== null || p.coverage_state !== "UNKNOWN") throw new Error("Unsupported execution or coverage claim");
  if (!count(p.estimated_download_bytes_known) || !count(p.unknown_size_assets)) throw new Error("Invalid transfer estimate");
  return value as FrozenAcquisitionPlan;
}
/** Invalidates late HTTP/import results after every geometry/filter/clear change. */
export class PlanRevisionGate {
  private revision = 0;
  invalidate() { this.revision += 1; return this.revision; }
  current(revision: number) { return revision === this.revision; }
}

export function assertPlanMatchesAoi(plan: FrozenAcquisitionPlan, geometry: AoiGeometry) {
  if (plan.normalized_aoi.type !== geometry.type || JSON.stringify(plan.normalized_aoi.coordinates) !== JSON.stringify(geometry.coordinates)) throw new Error("Response belongs to a different AOI");
}

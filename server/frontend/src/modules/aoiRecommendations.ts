/** Rejection gates for server-owned recommendations. No client-side spatial ranking. */
import { parseFrozenPlan } from "./aoiContract";
import type { AcquisitionAssetRow, FrozenAcquisitionPlan } from "./aoiContract";

export const DATASET_STATES = ["RECOMMENDED", "RELEVANT_UNRESOLVED", "FILTERED_OUT",
  "PROCESSING_ONLY", "NO_MATCH_IN_SNAPSHOT", "UNRESOLVED"] as const;
export type DatasetState = typeof DATASET_STATES[number];
export interface DatasetRecommendation {
  dataset_id: string; label_raw: string; provider_id: string | null;
  catalog_sha256: string | null; recommendation_state: DatasetState; recommended: boolean;
  spatial_relevance: "RELEVANT" | "UNRESOLVED" | "NO_POSITIVE_OVERLAP_IN_SNAPSHOT";
  file_resolution_state: "PASS" | "UNRESOLVED";
  counts: { examined: number; spatial_matches: number; applicable_files: number;
    processing_only_files: number; excluded: number; unresolved: number };
  all_row_ids: string[]; spatial_match_row_ids: string[]; applicable_file_row_ids: string[];
  processing_only_file_row_ids: string[]; unresolved_row_ids: string[];
  known_applicable_bytes: number; unknown_applicable_sizes: number;
  comparison_relation: "UNADJUDICATED"; reasons: string[];
}
export interface DatasetRecommendations {
  schema_version: "aoi_dataset_relevance.v1.0"; response_id: string; response_sha256: string;
  aoi_sha256: string; registry_sha256: string; plan: FrozenAcquisitionPlan;
  datasets: DatasetRecommendation[]; recommended_dataset_ids: string[];
  processing_only_dataset_ids: string[]; unresolved_dataset_ids: string[];
  counts: { datasets_examined: number; file_rows_examined: number;
    dataset_states: Record<DatasetState, number> };
  fetch_enabled: false; certification: "OPEN"; coverage_state: "UNKNOWN";
}
function obj(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) throw new Error("Expected object");
  return value as Record<string, unknown>;
}
function requireValue(ok: unknown, message: string): asserts ok { if (!ok) throw new Error(message); }
function nonnegative(value: unknown): value is number { return Number.isSafeInteger(value) && Number(value) >= 0; }
function list(value: unknown): string[] {
  requireValue(Array.isArray(value) && value.every((v) => typeof v === "string"), "Expected string list");
  return value;
}
function sameIds(actual: unknown, expected: string[], label: string) {
  const ids = list(actual), unique = new Set(ids);
  requireValue(ids.length === unique.size && ids.length === expected.length && expected.every((id) => unique.has(id)), `${label} membership mismatch`);
}
function hash(value: unknown): value is string { return typeof value === "string" && /^[a-f0-9]{64}$/.test(value); }
const positive = (row: AcquisitionAssetRow) => ["FULLY_WITHIN", "PARTIAL"].includes(row.relation);
export function sourceUrl(row: AcquisitionAssetRow): string | null {
  const value = (row as unknown as Record<string, unknown>).source_url;
  if (typeof value !== "string") return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" && !url.username && !url.password ? value : null;
  } catch { return null; }
}

export function parseDatasetRecommendations(value: unknown): DatasetRecommendations {
  const r = obj(value), counts = obj(r.counts);
  requireValue(r.schema_version === "aoi_dataset_relevance.v1.0", "Unsupported recommendations schema");
  requireValue(hash(r.response_sha256) && r.response_id === `aoi-relevance-${r.response_sha256}`, "Invalid response identifier");
  const plan = parseFrozenPlan(r.plan), rawPlan = obj(r.plan);
  requireValue(r.aoi_sha256 === plan.aoi_sha256 && hash(r.registry_sha256) &&
    r.registry_sha256 === rawPlan.provider_registry_sha256, "AOI/registry binding mismatch");
  requireValue(r.fetch_enabled === false && r.certification === "OPEN" && r.coverage_state === "UNKNOWN" &&
    r.source_equivalence === "NOT_INFERRED" && r.global_catalog_completeness === "UNRESOLVED" &&
    r.scope === "configured_hash_pinned_catalog_snapshots_only" && r.arithmetic_closed === true,
  "Unsupported completeness, equivalence or execution promotion");
  requireValue(Array.isArray(r.datasets) && Array.isArray(rawPlan.catalogs), "Missing dataset/catalog census");
  const catalogs = new Map<string, Record<string, unknown>>();
  for (const value of rawPlan.catalogs) {
    const c = obj(value);
    requireValue(typeof c.dataset_id === "string" && !catalogs.has(c.dataset_id), "Invalid/duplicate catalog ID");
    requireValue(["PASS", "BLOCKED"].includes(String(c.state)) && nonnegative(c.records), "Invalid catalog status/count");
    requireValue(c.state !== "PASS" || hash(c.sha256), "Unbound catalog hash");
    catalogs.set(c.dataset_id, c);
  }
  const rows = new Map<string, AcquisitionAssetRow[]>();
  for (const row of plan.assets) {
    requireValue(catalogs.has(row.dataset_id), "Orphan source row");
    if (row.disposition === "RETAINED") requireValue(sourceUrl(row), "Unsafe/missing asset URL");
    const members = rows.get(row.dataset_id) ?? []; members.push(row); rows.set(row.dataset_id, members);
  }
  const seen = new Set<string>();
  const stateCounts = Object.fromEntries(DATASET_STATES.map((state) => [state, 0])) as Record<DatasetState, number>;
  for (const value of r.datasets) {
    const d = obj(value), dc = obj(d.counts), id = d.dataset_id;
    requireValue(typeof id === "string" && catalogs.has(id) && !seen.has(id), "Missing/duplicate/orphan dataset");
    seen.add(id);
    const catalog = catalogs.get(id)!, members = rows.get(id) ?? [];
    const spatial = members.filter(positive);
    const applicable = spatial.filter((row) => row.disposition === "RETAINED");
    const processing = members.filter((row) => !positive(row) &&
      ["FULLY_WITHIN", "PARTIAL"].includes(row.processing_relation) && row.disposition === "RETAINED");
    const unknownGeometry = members.some((row) => ["NULL_EMPTY", "UNRESOLVED"].includes(row.relation));
    const unresolved = members.filter((row) => row.disposition === "UNRESOLVED");
    const state: DatasetState = applicable.length ? "RECOMMENDED" :
      catalog.state !== "PASS" || unknownGeometry ? "UNRESOLVED" :
      spatial.some((row) => row.disposition === "UNRESOLVED") ? "RELEVANT_UNRESOLVED" :
      spatial.length ? "FILTERED_OUT" : processing.length ? "PROCESSING_ONLY" : "NO_MATCH_IN_SNAPSHOT";
    requireValue(d.recommendation_state === state && d.recommended === Boolean(applicable.length), "Recommendation contradicts file decisions");
    const relevance = spatial.length ? "RELEVANT" : catalog.state !== "PASS" || unknownGeometry ? "UNRESOLVED" : "NO_POSITIVE_OVERLAP_IN_SNAPSHOT";
    requireValue(d.spatial_relevance === relevance, "Spatial relevance mismatch");
    requireValue(d.file_resolution_state === (catalog.state === "PASS" && !unresolved.length ? "PASS" : "UNRESOLVED"), "False complete file list");
    requireValue(catalog.records === members.length && (catalog.state === "PASS" || !members.length), "Catalog row conservation failed");
    requireValue(typeof d.label_raw === "string" && (d.provider_id === null || typeof d.provider_id === "string") &&
      d.catalog_sha256 === catalog.sha256 && d.comparison_relation === "UNADJUDICATED" && d.scope === "configured_snapshot_only", "Dataset metadata/binding mismatch");
    list(d.reasons);
    const expected = { examined: members.length, spatial_matches: spatial.length, applicable_files: applicable.length,
      processing_only_files: processing.length, excluded: members.filter((row) => row.disposition === "EXCLUDED").length,
      unresolved: unresolved.length };
    for (const [key, count] of Object.entries(expected)) requireValue(nonnegative(dc[key]) && dc[key] === count, `Dataset ${key} mismatch`);
    for (const [key, group] of [["all_row_ids", members], ["spatial_match_row_ids", spatial],
      ["applicable_file_row_ids", applicable], ["processing_only_file_row_ids", processing], ["unresolved_row_ids", unresolved]] as const) {
      sameIds(d[key], group.map((row) => row.row_id), key);
    }
    const bytes = applicable.reduce((sum, row) => sum + (row.size_bytes ?? 0), 0);
    requireValue(nonnegative(bytes) && d.known_applicable_bytes === bytes &&
      d.unknown_applicable_sizes === applicable.filter((row) => row.size_bytes === null).length, "Transfer estimate mismatch");
    stateCounts[state]++;
  }
  sameIds([...seen], [...catalogs.keys()], "Dataset census");
  const datasets = r.datasets as unknown as DatasetRecommendation[];
  sameIds(r.recommended_dataset_ids, datasets.filter((d) => d.recommended).map((d) => d.dataset_id), "Recommended datasets");
  sameIds(r.unresolved_dataset_ids, datasets.filter((d) => d.file_resolution_state === "UNRESOLVED").map((d) => d.dataset_id), "Unresolved datasets");
  sameIds(r.processing_only_dataset_ids, datasets.filter((d) => d.recommendation_state === "PROCESSING_ONLY").map((d) => d.dataset_id), "Processing-only datasets");
  requireValue(counts.datasets_examined === seen.size && counts.file_rows_examined === plan.assets.length, "Global denominator mismatch");
  const states = obj(counts.dataset_states);
  requireValue(Object.keys(states).length === DATASET_STATES.length && DATASET_STATES.every((s) => states[s] === stateCounts[s]), "Dataset partition mismatch");
  // Identifiers are server-generated hash bindings, not client-verified signatures.
  return value as DatasetRecommendations;
}

export function selectedApplicableRows(response: DatasetRecommendations, datasetIds: string[]): AcquisitionAssetRow[] {
  sameIds(datasetIds, [...new Set(datasetIds)], "Selection");
  const datasets = new Map(response.datasets.map((d) => [d.dataset_id, d]));
  const rowIds = new Set<string>();
  for (const id of datasetIds) {
    const dataset = datasets.get(id);
    requireValue(dataset?.recommended, "Selection contains a stale or nonrecommended dataset");
    for (const row of dataset.applicable_file_row_ids) rowIds.add(row);
  }
  const result = response.plan.assets.filter((row) => rowIds.has(row.row_id));
  requireValue(result.length === rowIds.size, "Selected source row missing");
  return result;
}

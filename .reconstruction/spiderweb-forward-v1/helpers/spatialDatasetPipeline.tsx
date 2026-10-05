export type UploadKind =
  | "geojson" | "json" | "kml" | "csv"
  | "shp" | "shx" | "dbf" | "prj" | "cpg"
  | "kmz" | "zip" | "gpkg" | "tif" | "tiff" | "unknown";

export type DatasetRole = "PRIMARY" | "COMPARISON" | "CONTEXT" | "REFERENCE";
export type DatasetState = "READY" | "BLOCKED" | "REVIEW";
export type DatasetCapability = "VECTOR" | "RASTER" | "EXACT_ID" | "TOPOLOGY" | "TERRAIN_ATTRIBUTE";
export type PresetId = "EXACT_ID_DIFF" | "TOPOLOGY_REVIEW" | "TERRAIN_CANDIDATES" | "MANIFEST_AUDIT";

export interface UploadFileInput {
  name: string;
  size: number;
  mime?: string;
  relativePath?: string;
  sha256?: string;
}

export interface UploadManifestEntry extends UploadFileInput {
  ordinal: number;
  kind: UploadKind;
  sourceId: string;
  contentSha256: string | null;
  runtimeId: string;
  stem: string;
  extension: string;
  manifestationState: "HASHED" | "UNHASHED";
}

export interface DatasetIssue {
  code: string;
  severity: "BLOCK" | "REVIEW";
  detail: string;
}

export interface SpatialDataset {
  datasetId: string;
  sourceIds: string[];
  runtimeIds: string[];
  role: DatasetRole;
  format: "GEOJSON" | "KML" | "CSV" | "SHAPEFILE" | "KMZ" | "ZIP" | "GEOPACKAGE" | "RASTER" | "UNKNOWN";
  state: DatasetState;
  capabilities: DatasetCapability[];
  declaredCrs: string | null;
  issues: DatasetIssue[];
  sourceIdentityRule: "SOURCE_MANIFESTATION_NOT_FILENAME";
  provenancePlane: "RAW";
}

export interface DatasetObservation {
  datasetId: string;
  featureCount?: number;
  exactIds?: string[];
  unidentifiedCount?: number;
  duplicateIds?: string[];
  unsupportedGeometryCount?: number;
  nullGeometryCount?: number;
  hasTerrainAttributes?: boolean;
  declaredCrs?: string | null;
}

export interface PreflightResult {
  state: "PASS" | "BLOCK" | "REVIEW";
  selectedDatasetIds: string[];
  issues: DatasetIssue[];
  arithmetic: {
    selected: number;
    ready: number;
    blocked: number;
    review: number;
    observed: number;
  };
}

export interface AnalysisReceipt {
  schema: "spiderweb-analysis-receipt/v1";
  preset: PresetId;
  state: "PASS" | "BLOCKED";
  selectedDatasetIds: string[];
  sourceIds: string[];
  preflightState: PreflightResult["state"];
  graph: Array<{ id: string; kind: "MANIFEST" | "DATASET" | "PREFLIGHT" | "ANALYSIS" | "RECEIPT"; dependsOn: string[] }>;
  arithmetic: PreflightResult["arithmetic"];
  fingerprint: string;
  authority: "ANALYSIS_ONLY";
  planes: ["RAW", "NORMALIZED", "CANONICAL"];
}

const SHAPEFILE_SIDECARS = new Set<UploadKind>(["shp", "shx", "dbf", "prj", "cpg"]);
const REQUIRED_SHAPEFILE = ["shp", "shx", "dbf"] as const;

export function extensionOf(name: string): string {
  const base = name.split(/[\\/]/).at(-1) ?? name;
  const dot = base.lastIndexOf(".");
  return dot <= 0 ? "" : base.slice(dot + 1).toLowerCase();
}

export function stemOf(name: string): string {
  const base = name.split(/[\\/]/).at(-1) ?? name;
  const dot = base.lastIndexOf(".");
  return (dot <= 0 ? base : base.slice(0, dot)).toLowerCase();
}

export function classifyUploadKind(name: string): UploadKind {
  const ext = extensionOf(name);
  if (ext === "geojson") return "geojson";
  if (ext === "json") return "json";
  if (["kml", "csv", "shp", "shx", "dbf", "prj", "cpg", "kmz", "zip", "gpkg", "tif", "tiff"].includes(ext)) return ext as UploadKind;
  return "unknown";
}

export function buildUploadManifest(files: UploadFileInput[]): UploadManifestEntry[] {
  return files.map((file, index) => {
    const kind = classifyUploadKind(file.name);
    const contentSha256 = file.sha256 ? file.sha256.toLowerCase() : null;
    const sourceId = `source-manifestation:${index + 1}`;
    return {
      ...file,
      ordinal: index + 1,
      kind,
      contentSha256,
      extension: extensionOf(file.name),
      stem: stemOf(file.name),
      sourceId,
      runtimeId: `runtime-upload:${index + 1}`,
      manifestationState: file.sha256 ? "HASHED" : "UNHASHED",
    };
  });
}

function datasetFromSingle(entry: UploadManifestEntry, role: DatasetRole): SpatialDataset {
  const issues: DatasetIssue[] = [];
  let format: SpatialDataset["format"] = "UNKNOWN";
  let state: DatasetState = "READY";
  let capabilities: DatasetCapability[] = [];
  if (entry.kind === "geojson") { format = "GEOJSON"; capabilities = ["VECTOR", "EXACT_ID", "TOPOLOGY"]; }
  else if (entry.kind === "json") { format = "UNKNOWN"; state = "REVIEW"; issues.push(review("JSON_CONTENT_CLASSIFICATION_REQUIRED", "Generic .json must be content-classified before it can claim GeoJSON/vector capability.")); }
  else if (entry.kind === "kml") { format = "KML"; capabilities = ["VECTOR", "TOPOLOGY"]; }
  else if (entry.kind === "csv") { format = "CSV"; capabilities = ["VECTOR"]; }
  else if (entry.kind === "kmz") { format = "KMZ"; state = "BLOCKED"; issues.push(block("KMZ_ADAPTER_UNVERIFIED", "KMZ requires a verified container/member adapter before analysis.")); }
  else if (entry.kind === "zip") { format = "ZIP"; state = "BLOCKED"; issues.push(block("ARCHIVE_RELATION_UNPROVEN", "Archive members must be enumerated and bound before grouping or analysis.")); }
  else if (entry.kind === "gpkg") { format = "GEOPACKAGE"; state = "BLOCKED"; issues.push(block("GEOPACKAGE_BLOCKED", "Direct GeoPackage support is blocked until a genuine native/WASM SQLite adapter passes parser contracts.")); }
  else if (entry.kind === "tif" || entry.kind === "tiff") { format = "RASTER"; state = "BLOCKED"; capabilities = ["RASTER"]; issues.push(block("RASTER_ADAPTER_UNVERIFIED", "Raster analysis is blocked until the specialized adapter passes its parser contract.")); }
  else { state = "BLOCKED"; issues.push(block("UNSUPPORTED_FILE_TYPE", `Unsupported upload type: ${entry.extension || "none"}`)); }
  return makeDataset(`dataset:${entry.ordinal}`, [entry], role, format, state, capabilities, issues);
}

function makeDataset(
  datasetId: string,
  entries: UploadManifestEntry[],
  role: DatasetRole,
  format: SpatialDataset["format"],
  state: DatasetState,
  capabilities: DatasetCapability[],
  issues: DatasetIssue[],
): SpatialDataset {
  const provenanceIssues = entries.some(row => row.manifestationState === "UNHASHED")
    ? [review("UNHASHED_SOURCE_MANIFESTATION", "Source bytes have not yet been SHA-256 bound; analysis may proceed only as provisional analyst state.")]
    : [];
  const allIssues = [...issues, ...provenanceIssues];
  const finalState: DatasetState = state === "BLOCKED" ? "BLOCKED" : allIssues.length ? "REVIEW" : state;
  return {
    datasetId,
    sourceIds: entries.map(row => row.sourceId),
    runtimeIds: entries.map(row => row.runtimeId),
    role,
    format,
    state: finalState,
    capabilities: [...new Set(capabilities)],
    declaredCrs: null,
    issues: allIssues,
    sourceIdentityRule: "SOURCE_MANIFESTATION_NOT_FILENAME",
    provenancePlane: "RAW",
  };
}

export function buildSpatialDatasets(manifest: UploadManifestEntry[], roles: Partial<Record<string, DatasetRole>> = {}): SpatialDataset[] {
  const output: SpatialDataset[] = [];
  const consumed = new Set<number>();
  const shapeGroups = new Map<string, UploadManifestEntry[]>();
  for (const entry of manifest) if (SHAPEFILE_SIDECARS.has(entry.kind)) {
    const key = `${directoryOf(entry.relativePath ?? "")}|${entry.stem}`;
    shapeGroups.set(key, [...(shapeGroups.get(key) ?? []), entry]);
  }

  for (const [key, entries] of [...shapeGroups.entries()].sort(([a], [b]) => a.localeCompare(b))) {
    entries.forEach(row => consumed.add(row.ordinal));
    const byKind = new Map<UploadKind, UploadManifestEntry[]>();
    entries.forEach(row => byKind.set(row.kind, [...(byKind.get(row.kind) ?? []), row]));
    const issues: DatasetIssue[] = [];
    for (const required of REQUIRED_SHAPEFILE) {
      if ((byKind.get(required)?.length ?? 0) === 0) issues.push(block("PARTIAL_SHAPEFILE", `Missing required .${required} sidecar for ${key}.`));
    }
    for (const [kind, rows] of byKind) if (rows.length > 1) issues.push(block("SIDECAR_TIE", `Multiple .${kind} files compete for one Shapefile dataset; relation is unresolved.`));
    issues.push(block("SHAPEFILE_ADAPTER_UNVERIFIED", "Shapefile sidecar relation is structurally grouped, but analysis remains blocked until a verified parser adapter passes its contract."));
    const state: DatasetState = "BLOCKED";
    output.push(makeDataset(`dataset:shapefile:${key}`, entries, roles[key] ?? "PRIMARY", "SHAPEFILE", state, [], issues));
  }

  for (const entry of manifest) {
    if (consumed.has(entry.ordinal)) continue;
    const role = roles[entry.sourceId] ?? (output.length === 0 ? "PRIMARY" : "CONTEXT");
    output.push(datasetFromSingle(entry, role));
  }
  return output;
}

export const PRESETS: Record<PresetId, { minReady: number; capability: DatasetCapability; minWithCapability: number }> = {
  EXACT_ID_DIFF: { minReady: 2, capability: "EXACT_ID", minWithCapability: 2 },
  TOPOLOGY_REVIEW: { minReady: 1, capability: "TOPOLOGY", minWithCapability: 1 },
  TERRAIN_CANDIDATES: { minReady: 1, capability: "TERRAIN_ATTRIBUTE", minWithCapability: 1 },
  MANIFEST_AUDIT: { minReady: 1, capability: "VECTOR", minWithCapability: 0 },
};

export function applyDatasetObservations(datasets: SpatialDataset[], observations: DatasetObservation[]): SpatialDataset[] {
  const byId = new Map(observations.map(row => [row.datasetId, row]));
  return datasets.map(dataset => {
    const observation = byId.get(dataset.datasetId);
    if (!observation) return dataset;
    const issues = [...dataset.issues];
    if ((observation.unidentifiedCount ?? 0) > 0) issues.push(review("UNIDENTIFIED_FEATURE_IDS", `${observation.unidentifiedCount} feature(s) lack stable IDs.`));
    if ((observation.duplicateIds?.length ?? 0) > 0) issues.push(block("DUPLICATE_FEATURE_IDS", `Duplicate feature IDs: ${[...new Set(observation.duplicateIds)].sort().join(", ")}`));
    if ((observation.unsupportedGeometryCount ?? 0) > 0) issues.push(block("UNSUPPORTED_GEOMETRY", `${observation.unsupportedGeometryCount} unsupported geometry record(s).`));
    if ((observation.nullGeometryCount ?? 0) > 0) issues.push(review("NULL_GEOMETRY", `${observation.nullGeometryCount} null geometry record(s).`));
    const capabilities = [...dataset.capabilities];
    if (observation.hasTerrainAttributes && !capabilities.includes("TERRAIN_ATTRIBUTE")) capabilities.push("TERRAIN_ATTRIBUTE");
    const state: DatasetState = issues.some(row => row.severity === "BLOCK") ? "BLOCKED" : issues.length ? "REVIEW" : dataset.state;
    return { ...dataset, capabilities, state, issues, declaredCrs: observation.declaredCrs ?? dataset.declaredCrs };
  });
}

export function presetEligibility(preset: PresetId, datasets: SpatialDataset[]) {
  const rule = PRESETS[preset];
  const ready = datasets.filter(row => row.state !== "BLOCKED");
  const withCapability = ready.filter(row => row.capabilities.includes(rule.capability));
  const eligible = ready.length >= rule.minReady && withCapability.length >= rule.minWithCapability;
  return {
    preset,
    eligible,
    readyDatasetIds: ready.map(row => row.datasetId),
    capableDatasetIds: withCapability.map(row => row.datasetId),
    reason: eligible ? "ELIGIBLE" : `Requires ${rule.minReady} ready dataset(s) and ${rule.minWithCapability} with ${rule.capability}.`,
  };
}

export function preflightAnalysis(preset: PresetId, datasets: SpatialDataset[]): PreflightResult {
  const issues = datasets.flatMap(row => row.issues.map(issue => ({ ...issue, detail: `${row.datasetId}: ${issue.detail}` })));
  const active = datasets.filter(row => row.role !== "REFERENCE");
  const crs = [...new Set(active.map(row => row.declaredCrs).filter((value): value is string => Boolean(value)))];
  if (crs.length > 1) issues.push(block("MIXED_CRS_UNRESOLVED", `Selected datasets declare multiple CRS values: ${crs.sort().join(", ")}`));
  const eligibility = presetEligibility(preset, active);
  if (!eligibility.eligible) issues.push(block("PRESET_INELIGIBLE", eligibility.reason));
  const arithmetic = {
    selected: active.length,
    ready: active.filter(row => row.state === "READY").length,
    blocked: active.filter(row => row.state === "BLOCKED").length,
    review: active.filter(row => row.state === "REVIEW").length,
    observed: active.filter(row => row.declaredCrs !== null || row.capabilities.includes("TERRAIN_ATTRIBUTE") || row.issues.length > 0).length,
  };
  const state: PreflightResult["state"] = issues.some(row => row.severity === "BLOCK") ? "BLOCK" : issues.length ? "REVIEW" : "PASS";
  return { state, selectedDatasetIds: active.map(row => row.datasetId), issues, arithmetic };
}

export function buildAnalysisReceipt(preset: PresetId, datasets: SpatialDataset[]): AnalysisReceipt {
  const preflight = preflightAnalysis(preset, datasets);
  const selected = datasets.filter(row => preflight.selectedDatasetIds.includes(row.datasetId));
  const graph: AnalysisReceipt["graph"] = [
    { id: "manifest", kind: "MANIFEST", dependsOn: [] },
    ...selected.map(row => ({ id: row.datasetId, kind: "DATASET" as const, dependsOn: ["manifest"] })),
    { id: "preflight", kind: "PREFLIGHT", dependsOn: selected.map(row => row.datasetId) },
    { id: `analysis:${preset}`, kind: "ANALYSIS", dependsOn: ["preflight"] },
    { id: "receipt", kind: "RECEIPT", dependsOn: [`analysis:${preset}`] },
  ];
  const basis = canonicalStringify({
    preset,
    selectedDatasetIds: preflight.selectedDatasetIds,
    sourceIds: selected.flatMap(row => row.sourceIds).sort(),
    preflightState: preflight.state,
    arithmetic: preflight.arithmetic,
    issues: preflight.issues.map(row => [row.code, row.severity, row.detail]).sort(),
    graph,
  });
  return {
    schema: "spiderweb-analysis-receipt/v1",
    preset,
    state: preflight.state === "BLOCK" ? "BLOCKED" : "PASS",
    selectedDatasetIds: preflight.selectedDatasetIds,
    sourceIds: selected.flatMap(row => row.sourceIds).sort(),
    preflightState: preflight.state,
    graph,
    arithmetic: preflight.arithmetic,
    fingerprint: fnv1a(basis),
    authority: "ANALYSIS_ONLY",
    planes: ["RAW", "NORMALIZED", "CANONICAL"],
  };
}

export function closeDatasetArithmetic(manifest: UploadManifestEntry[], datasets: SpatialDataset[]) {
  const bound = new Set(datasets.flatMap(row => row.runtimeIds));
  const unbound = manifest.filter(row => !bound.has(row.runtimeId));
  const duplicateBindings = datasets.flatMap(row => row.runtimeIds).filter((id, index, all) => all.indexOf(id) !== index);
  return {
    inputManifestations: manifest.length,
    boundManifestations: bound.size,
    unboundManifestations: unbound.map(row => row.runtimeId),
    duplicateBindings: [...new Set(duplicateBindings)].sort(),
    closed: manifest.length === bound.size && unbound.length === 0 && duplicateBindings.length === 0,
  };
}

function directoryOf(relativePath: string): string {
  if (!relativePath) return "";
  const normalized = relativePath.replace(/\\/g, "/");
  const slash = normalized.lastIndexOf("/");
  return slash < 0 ? "" : normalized.slice(0, slash).toLowerCase();
}

function canonicalStringify(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalStringify).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>).sort(([a], [b]) => a.localeCompare(b)).map(([key, item]) => `${JSON.stringify(key)}:${canonicalStringify(item)}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function fnv1a(text: string): string {
  let hash = 0x811c9dc5;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return `fnv1a32:${hash.toString(16).padStart(8, "0")}`;
}

function block(code: string, detail: string): DatasetIssue { return { code, severity: "BLOCK", detail }; }
function review(code: string, detail: string): DatasetIssue { return { code, severity: "REVIEW", detail }; }
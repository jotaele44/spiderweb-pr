export type TransportPlane = "STATIC_DOWNLOAD" | "WFS" | "WMS" | "REST" | "RASTER";
export type EquivalenceState = "VERIFIED_EQUIVALENT" | "NOT_EQUIVALENT" | "UNRESOLVED";

export interface SourceManifestation {
  manifestationId: string;
  transport: TransportPlane;
  sha256: string | null;
  sourceUri: string;
  acquiredAt: string | null;
  mutable: boolean;
  sourceId: string;
}

export interface SpatialEvidenceSummary {
  manifestationId: string;
  stableIds: string[];
  schemaFields: string[];
  declaredCrs: string | null;
  verifiedTransformTo?: string | null;
  geometryHashById: Record<string, string>;
  topologyHashById?: Record<string, string>;
  attributeHashById: Record<string, string>;
  namesById?: Record<string, string>;
  featureCount: number;
}

export interface EquivalenceFalsifier {
  code: string;
  state: "PASS" | "FAIL" | "OPEN";
  detail: string;
}

export interface EquivalenceAdjudication {
  state: EquivalenceState;
  leftManifestationId: string;
  rightManifestationId: string;
  falsifiers: EquivalenceFalsifier[];
  prohibitedShortcuts: ["NAME_ONLY", "COUNT_EQUALITY", "NEAREST_ONLY", "PROXIMITY_ONLY", "SOURCE_ABSENCE"];
}

export interface SourceDriftChange { path: string; blobSha: string; }
export interface SourceDriftResult {
  state: "PASS" | "REOPEN";
  scopedChanges: SourceDriftChange[];
  outOfScopeChanges: SourceDriftChange[];
  changedFileSetFingerprint: string;
}

export function adjudicateSpatialEquivalence(
  left: SpatialEvidenceSummary,
  right: SpatialEvidenceSummary,
): EquivalenceAdjudication {
  const falsifiers: EquivalenceFalsifier[] = [];
  const leftIds = sortedUnique(left.stableIds);
  const rightIds = sortedUnique(right.stableIds);
  const stableIdClosed = equalArrays(leftIds, rightIds);
  falsifiers.push({ code: "STABLE_ID_SET", state: stableIdClosed ? "PASS" : "FAIL", detail: stableIdClosed ? `${leftIds.length} stable IDs close exactly.` : "Stable-ID sets differ; count/name equality cannot substitute." });

  const leftSchema = sortedUnique(left.schemaFields);
  const rightSchema = sortedUnique(right.schemaFields);
  const schemaClosed = equalArrays(leftSchema, rightSchema);
  falsifiers.push({ code: "SCHEMA_FIELDS", state: schemaClosed ? "PASS" : "FAIL", detail: schemaClosed ? "Schema field sets match." : "Schema field sets differ." });

  let crsState: EquivalenceFalsifier["state"] = "OPEN";
  let crsDetail = "CRS unresolved.";
  if (left.declaredCrs && right.declaredCrs && left.declaredCrs === right.declaredCrs) {
    crsState = "PASS"; crsDetail = `Both manifestations declare ${left.declaredCrs}.`;
  } else if (left.declaredCrs && right.declaredCrs) {
    const leftVerified = left.verifiedTransformTo === right.declaredCrs;
    const rightVerified = right.verifiedTransformTo === left.declaredCrs;
    if (leftVerified || rightVerified) { crsState = "PASS"; crsDetail = "Cross-CRS comparison is allowed only through the declared verified transform."; }
    else { crsState = "OPEN"; crsDetail = `${left.declaredCrs} vs ${right.declaredCrs} requires a verified transform.`; }
  }
  falsifiers.push({ code: "CRS", state: crsState, detail: crsDetail });

  const geometry = comparePerStableId(leftIds, rightIds, left.geometryHashById, right.geometryHashById);
  falsifiers.push({ code: "GEOMETRY_HASH", state: geometry.state, detail: geometry.detail });
  const topology = left.topologyHashById || right.topologyHashById
    ? comparePerStableId(leftIds, rightIds, left.topologyHashById ?? {}, right.topologyHashById ?? {})
    : { state: "OPEN" as const, detail: "Topology hashes were not supplied on both manifestations." };
  falsifiers.push({ code: "TOPOLOGY_HASH", state: topology.state, detail: topology.detail });
  const attributes = comparePerStableId(leftIds, rightIds, left.attributeHashById, right.attributeHashById);
  falsifiers.push({ code: "ATTRIBUTE_HASH", state: attributes.state, detail: attributes.detail });

  const anyFail = falsifiers.some(row => row.state === "FAIL");
  const allPass = falsifiers.every(row => row.state === "PASS");
  return {
    state: anyFail ? "NOT_EQUIVALENT" : allPass ? "VERIFIED_EQUIVALENT" : "UNRESOLVED",
    leftManifestationId: left.manifestationId,
    rightManifestationId: right.manifestationId,
    falsifiers,
    prohibitedShortcuts: ["NAME_ONLY", "COUNT_EQUALITY", "NEAREST_ONLY", "PROXIMITY_ONLY", "SOURCE_ABSENCE"],
  };
}

export function preserveManifestationPlanes(manifestations: SourceManifestation[]) {
  const ids = manifestations.map(row => row.manifestationId);
  const duplicates = ids.filter((id, index) => ids.indexOf(id) !== index);
  const missingHashes = manifestations.filter(row => !row.sha256).map(row => row.manifestationId);
  const byTransport = Object.fromEntries((["STATIC_DOWNLOAD","WFS","WMS","REST","RASTER"] as TransportPlane[]).map(kind => [kind, manifestations.filter(row => row.transport === kind).map(row => row.manifestationId)]));
  return {
    manifestations: manifestations.length,
    uniqueManifestations: new Set(ids).size,
    duplicates: sortedUnique(duplicates),
    missingHashes: sortedUnique(missingHashes),
    byTransport,
    state: duplicates.length === 0 && missingHashes.length === 0 ? "PASS" as const : "OPEN" as const,
  };
}

export function adjudicateSourceDrift(changes: SourceDriftChange[], scopedRoots: string[]): SourceDriftResult {
  const normalizedRoots = scopedRoots.map(root => root.endsWith("/") ? root : `${root}/`);
  const scopedChanges = changes.filter(change => normalizedRoots.some(root => change.path.startsWith(root)));
  const outOfScopeChanges = changes.filter(change => !scopedChanges.includes(change));
  const serialized = [...changes].sort((a,b)=>a.path.localeCompare(b.path)).map(row => `${row.path}\t${row.blobSha}`).join("\n");
  return {
    state: scopedChanges.length ? "REOPEN" : "PASS",
    scopedChanges,
    outOfScopeChanges,
    changedFileSetFingerprint: fnv1a(serialized),
  };
}

export function buildEquivalenceCandidateSet<T extends { candidateId: string }>(candidates: T[]) {
  const sorted = [...candidates].sort((a,b)=>a.candidateId.localeCompare(b.candidateId));
  const duplicateIds = sorted.map(row=>row.candidateId).filter((id,index,all)=>all.indexOf(id)!==index);
  return {
    candidates: sorted,
    duplicateIds: sortedUnique(duplicateIds),
    state: duplicateIds.length ? "UNRESOLVED" as const : sorted.length ? "READY" as const : "EMPTY" as const,
  };
}

function comparePerStableId(idsA: string[], idsB: string[], a: Record<string,string>, b: Record<string,string>) {
  if (!equalArrays(idsA, idsB)) return { state: "FAIL" as const, detail: "Stable-ID sets must close before per-ID comparison." };
  const missing = idsA.filter(id => !a[id] || !b[id]);
  if (missing.length) return { state: "OPEN" as const, detail: `Missing per-ID evidence for: ${missing.join(", ")}` };
  const mismatched = idsA.filter(id => a[id] !== b[id]);
  return mismatched.length
    ? { state: "FAIL" as const, detail: `Per-ID evidence differs for: ${mismatched.join(", ")}` }
    : { state: "PASS" as const, detail: `${idsA.length} per-ID evidence rows match.` };
}
function sortedUnique(values:string[]){return [...new Set(values)].sort();}
function equalArrays(a:string[],b:string[]){return a.length===b.length&&a.every((value,index)=>value===b[index]);}
function fnv1a(text:string){let hash=0x811c9dc5;for(let i=0;i<text.length;i++){hash^=text.charCodeAt(i);hash=Math.imul(hash,0x01000193)>>>0;}return `fnv1a32:${hash.toString(16).padStart(8,"0")}`;}
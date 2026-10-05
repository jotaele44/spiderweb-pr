export type SurfaceValidationState = "PASS" | "BLOCKED";
export type SampleState = "VALUE" | "NODATA" | "OUTSIDE" | "UNRESOLVED";

export interface SurfaceManifest {
  surfaceId: string;
  sourceManifestationSha256: string | null;
  horizontalCrs: string | null;
  horizontalDatum: string | null;
  verticalDatum: string | null;
  units: string | null;
  width: number | null;
  height: number | null;
  resolutionX: number | null;
  resolutionY: number | null;
  noDataValue: number | null | "UNDECLARED";
  band: number | null;
}

export interface SurfaceValidation {
  state: SurfaceValidationState;
  issues: string[];
  samplingEligible: boolean;
}

export interface TrajectorySampleInput {
  observationId: string;
  longitude: number;
  latitude: number;
  sourceGeometryRef: string;
  value: number | null;
  state: SampleState;
}

export interface SurfaceSampleReceipt {
  schema: "spiderweb.surface-sample-receipt/v1";
  surfaceId: string;
  sourceManifestationSha256: string;
  sampleCount: number;
  valueCount: number;
  noDataCount: number;
  outsideCount: number;
  unresolvedCount: number;
  uniqueObservationIds: number;
  duplicateObservationIds: string[];
  geometryRefs: string[];
  state: "PASS" | "BLOCKED";
  authority: "SPIDERWEB_GEOMETRY_ONLY";
  identityRule: "NO_AIRCRAFT_IDENTITY_INFERENCE";
  fingerprint: string;
}

export interface SkywatcherSpatialArtifact {
  schema: "spiderweb.skywatcher-spatial-artifact/v1";
  producer: "spiderweb-pr";
  consumer: "skywatcher-pr";
  surfaceId: string;
  sourceManifestationSha256: string;
  observationIds: string[];
  geometryRefs: string[];
  sampleReceiptFingerprint: string;
  geometryAuthority: "SPIDERWEB";
  observationIdentityAuthority: "SKYWATCHER";
  promotedAircraftIdentity: false;
  state: "PASS" | "BLOCKED";
}

export function validateSurfaceManifest(manifest: SurfaceManifest): SurfaceValidation {
  const issues: string[] = [];
  if (!manifest.sourceManifestationSha256) issues.push("SOURCE_MANIFESTATION_HASH_REQUIRED");
  if (!manifest.horizontalCrs) issues.push("HORIZONTAL_CRS_REQUIRED");
  if (!manifest.horizontalDatum) issues.push("HORIZONTAL_DATUM_REQUIRED");
  if (!manifest.verticalDatum) issues.push("VERTICAL_DATUM_REQUIRED");
  if (!manifest.units) issues.push("SURFACE_UNITS_REQUIRED");
  if (!Number.isInteger(manifest.width) || (manifest.width ?? 0) <= 0) issues.push("VALID_WIDTH_REQUIRED");
  if (!Number.isInteger(manifest.height) || (manifest.height ?? 0) <= 0) issues.push("VALID_HEIGHT_REQUIRED");
  if (!Number.isFinite(manifest.resolutionX) || (manifest.resolutionX ?? 0) <= 0) issues.push("VALID_RESOLUTION_X_REQUIRED");
  if (!Number.isFinite(manifest.resolutionY) || (manifest.resolutionY ?? 0) <= 0) issues.push("VALID_RESOLUTION_Y_REQUIRED");
  if (manifest.noDataValue === "UNDECLARED") issues.push("NODATA_DECLARATION_REQUIRED");
  if (!Number.isInteger(manifest.band) || (manifest.band ?? 0) <= 0) issues.push("VALID_BAND_REQUIRED");
  return { state: issues.length ? "BLOCKED" : "PASS", issues, samplingEligible: issues.length === 0 };
}

export function buildSurfaceSampleReceipt(manifest: SurfaceManifest, samples: TrajectorySampleInput[]): SurfaceSampleReceipt {
  const validation = validateSurfaceManifest(manifest);
  const ids = samples.map(row => row.observationId);
  const duplicateObservationIds = [...new Set(ids.filter((id,index)=>ids.indexOf(id)!==index))].sort();
  const geometryRefs = [...new Set(samples.map(row => row.sourceGeometryRef))].sort();
  const invalidCoordinates = samples.filter(row => !Number.isFinite(row.longitude) || !Number.isFinite(row.latitude) || Math.abs(row.longitude)>180 || Math.abs(row.latitude)>90);
  const valueStateMismatch = samples.filter(row => row.state === "VALUE" && !Number.isFinite(row.value));
  const nullStateMismatch = samples.filter(row => ["NODATA","OUTSIDE","UNRESOLVED"].includes(row.state) && row.value !== null);
  const blocked = validation.state === "BLOCKED" || duplicateObservationIds.length>0 || invalidCoordinates.length>0 || valueStateMismatch.length>0 || nullStateMismatch.length>0;
  const body = {
    schema:"spiderweb.surface-sample-receipt/v1" as const,
    surfaceId:manifest.surfaceId,
    sourceManifestationSha256:manifest.sourceManifestationSha256 ?? "UNRESOLVED",
    sampleCount:samples.length,
    valueCount:samples.filter(row=>row.state==="VALUE").length,
    noDataCount:samples.filter(row=>row.state==="NODATA").length,
    outsideCount:samples.filter(row=>row.state==="OUTSIDE").length,
    unresolvedCount:samples.filter(row=>row.state==="UNRESOLVED").length,
    uniqueObservationIds:new Set(ids).size,
    duplicateObservationIds,
    geometryRefs,
    state:blocked?"BLOCKED" as const:"PASS" as const,
    authority:"SPIDERWEB_GEOMETRY_ONLY" as const,
    identityRule:"NO_AIRCRAFT_IDENTITY_INFERENCE" as const,
  };
  return {...body,fingerprint:fnv1a(canonicalStringify(body))};
}

export function buildSkywatcherSpatialArtifact(manifest: SurfaceManifest, samples: TrajectorySampleInput[]): SkywatcherSpatialArtifact {
  const receipt = buildSurfaceSampleReceipt(manifest,samples);
  return {
    schema:"spiderweb.skywatcher-spatial-artifact/v1",
    producer:"spiderweb-pr",
    consumer:"skywatcher-pr",
    surfaceId:manifest.surfaceId,
    sourceManifestationSha256:receipt.sourceManifestationSha256,
    observationIds:[...new Set(samples.map(row=>row.observationId))].sort(),
    geometryRefs:receipt.geometryRefs,
    sampleReceiptFingerprint:receipt.fingerprint,
    geometryAuthority:"SPIDERWEB",
    observationIdentityAuthority:"SKYWATCHER",
    promotedAircraftIdentity:false,
    state:receipt.state,
  };
}

function canonicalStringify(value:unknown):string{if(Array.isArray(value))return`[${value.map(canonicalStringify).join(",")}]`;if(value&&typeof value==="object")return`{${Object.entries(value as Record<string,unknown>).sort(([a],[b])=>a.localeCompare(b)).map(([k,v])=>`${JSON.stringify(k)}:${canonicalStringify(v)}`).join(",")}}`;return JSON.stringify(value);}
function fnv1a(text:string){let hash=0x811c9dc5;for(let i=0;i<text.length;i++){hash^=text.charCodeAt(i);hash=Math.imul(hash,0x01000193)>>>0;}return`fnv1a32:${hash.toString(16).padStart(8,"0")}`;}
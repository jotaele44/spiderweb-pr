import type { AcquisitionCoverageReceipt } from "./spatialAcquisitionManifest";
import type { SourceManifestation } from "./spatialSourceEquivalence";

export interface SpiderwebProducerInput {
  sourceCommit: string;
  packageVersion: string;
  stableEntityIds: string[];
  geometryRefs: string[];
  sourceManifestations: SourceManifestation[];
  acquisitionCoverage: AcquisitionCoverageReceipt;
  unresolvedIdentityCount: number;
  unresolvedGeometryCount: number;
}

export interface SpiderwebProducerPackage {
  schema: "spiderweb.producer-package/v1";
  producer: "spiderweb-pr";
  packageVersion: string;
  sourceCommit: string;
  authority: { geometry:"SPIDERWEB"; identity:"EVIDENCE_BOUND_ONLY" };
  stableEntityIds: string[];
  geometryRefs: string[];
  sourceManifestations: SourceManifestation[];
  arithmetic: { entities:number; uniqueEntities:number; geometryRefs:number; manifestations:number; uniqueManifestations:number };
  releaseState: "PASS" | "OPEN" | "BLOCKED";
  unresolved: string[];
  packageFingerprint: string;
}

export interface ConsumerReceipt {
  schema:"federation.consumer-receipt/v1";
  producer:"spiderweb-pr";
  consumer:"thehub-pr";
  packageFingerprint:string;
  observedFingerprint:string;
  state:"PASS"|"FAIL";
}

export function buildSpiderwebProducerPackage(input: SpiderwebProducerInput): SpiderwebProducerPackage {
  const stableEntityIds=[...input.stableEntityIds].sort();
  const geometryRefs=[...input.geometryRefs].sort();
  const manifestations=[...input.sourceManifestations].sort((a,b)=>a.manifestationId.localeCompare(b.manifestationId));
  const unresolved:string[]=[];
  if (new Set(stableEntityIds).size!==stableEntityIds.length) unresolved.push("DUPLICATE_STABLE_ENTITY_ID");
  if (new Set(manifestations.map(row=>row.manifestationId)).size!==manifestations.length) unresolved.push("DUPLICATE_MANIFESTATION_ID");
  if (manifestations.some(row=>!row.sha256)) unresolved.push("UNHASHED_SOURCE_MANIFESTATION");
  if (input.unresolvedIdentityCount>0) unresolved.push(`UNRESOLVED_IDENTITY:${input.unresolvedIdentityCount}`);
  if (input.unresolvedGeometryCount>0) unresolved.push(`UNRESOLVED_GEOMETRY:${input.unresolvedGeometryCount}`);
  if (input.acquisitionCoverage.state!=="PASS") unresolved.push(`ACQUISITION:${input.acquisitionCoverage.state}`);
  const releaseState = input.acquisitionCoverage.state==="BLOCKED" ? "BLOCKED" : unresolved.length ? "OPEN" : "PASS";
  const arithmetic={entities:stableEntityIds.length,uniqueEntities:new Set(stableEntityIds).size,geometryRefs:geometryRefs.length,manifestations:manifestations.length,uniqueManifestations:new Set(manifestations.map(row=>row.manifestationId)).size};
  const body={schema:"spiderweb.producer-package/v1" as const,producer:"spiderweb-pr" as const,packageVersion:input.packageVersion,sourceCommit:input.sourceCommit,authority:{geometry:"SPIDERWEB" as const,identity:"EVIDENCE_BOUND_ONLY" as const},stableEntityIds,geometryRefs,sourceManifestations:manifestations,arithmetic,releaseState,unresolved};
  return {...body,packageFingerprint:fnv1a(canonicalStringify(body))};
}

export function verifyTheHubConsumerReceipt(pkg: SpiderwebProducerPackage, observedFingerprint:string):ConsumerReceipt{
  return {schema:"federation.consumer-receipt/v1",producer:"spiderweb-pr",consumer:"thehub-pr",packageFingerprint:pkg.packageFingerprint,observedFingerprint,state:pkg.packageFingerprint===observedFingerprint?"PASS":"FAIL"};
}

function canonicalStringify(value:unknown):string{if(Array.isArray(value))return`[${value.map(canonicalStringify).join(",")}]`;if(value&&typeof value==="object")return`{${Object.entries(value as Record<string,unknown>).sort(([a],[b])=>a.localeCompare(b)).map(([k,v])=>`${JSON.stringify(k)}:${canonicalStringify(v)}`).join(",")}}`;return JSON.stringify(value);}
function fnv1a(text:string){let hash=0x811c9dc5;for(let i=0;i<text.length;i++){hash^=text.charCodeAt(i);hash=Math.imul(hash,0x01000193)>>>0;}return`fnv1a32:${hash.toString(16).padStart(8,"0")}`;}
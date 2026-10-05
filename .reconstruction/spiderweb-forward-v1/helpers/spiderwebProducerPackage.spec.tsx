import { buildSpiderwebProducerPackage, verifyTheHubConsumerReceipt } from "./spiderwebProducerPackage";
import { closeAcquisitionCoverage } from "./spatialAcquisitionManifest";

const requirement={sourceId:"s",plane:"WFS" as const,mutable:true,required:true,authority:"AUTHORITATIVE" as const};
const record={sourceId:"s",plane:"WFS" as const,disposition:"FROZEN" as const,manifestationSha256:"h",retrievedAt:"2026-10-05T00:00:00Z",locator:"https://x",rowOrFeatureCount:1,parserContract:"p/v1"};
const coverage=closeAcquisitionCoverage([requirement],[record]);
const manifestation={manifestationId:"m",transport:"WFS" as const,sha256:"h",sourceUri:"https://x",acquiredAt:"2026-10-05T00:00:00Z",mutable:true,sourceId:"s"};
const input=(overrides:Record<string,unknown>={})=>({sourceCommit:"a".repeat(40),packageVersion:"1.0.0",stableEntityIds:["E1"],geometryRefs:["spiderweb:layer:L1"],sourceManifestations:[manifestation],acquisitionCoverage:coverage,unresolvedIdentityCount:0,unresolvedGeometryCount:0,...overrides}) as any;

describe("Spiderweb producer package",()=>{
  it("builds a deterministic PASS package when provenance and arithmetic close",()=>{const a=buildSpiderwebProducerPackage(input());const b=buildSpiderwebProducerPackage(input());expect(a.releaseState).toBe("PASS");expect(a.packageFingerprint).toBe(b.packageFingerprint);});
  it("retains Spiderweb as geometry authority",()=>{expect(buildSpiderwebProducerPackage(input()).authority.geometry).toBe("SPIDERWEB");});
  it("never promotes identity beyond evidence-bound state",()=>{expect(buildSpiderwebProducerPackage(input()).authority.identity).toBe("EVIDENCE_BOUND_ONLY");});
  it("reopens the package on duplicate stable entity IDs",()=>{const p=buildSpiderwebProducerPackage(input({stableEntityIds:["E1","E1"]}));expect(p.releaseState).toBe("OPEN");expect(p.unresolved).toContain("DUPLICATE_STABLE_ENTITY_ID");});
  it("reopens the package on un-hashed source manifestations",()=>{const p=buildSpiderwebProducerPackage(input({sourceManifestations:[{...manifestation,sha256:null}]}));expect(p.releaseState).toBe("OPEN");expect(p.unresolved).toContain("UNHASHED_SOURCE_MANIFESTATION");});
  it("preserves unresolved identity and geometry residue",()=>{const p=buildSpiderwebProducerPackage(input({unresolvedIdentityCount:2,unresolvedGeometryCount:1}));expect(p.unresolved).toContain("UNRESOLVED_IDENTITY:2");expect(p.unresolved).toContain("UNRESOLVED_GEOMETRY:1");});
  it("cannot PASS when acquisition coverage is blocked",()=>{const blocked=closeAcquisitionCoverage([requirement],[{...record,disposition:"BLOCKED",manifestationSha256:null}]);expect(buildSpiderwebProducerPackage(input({acquisitionCoverage:blocked})).releaseState).toBe("BLOCKED");});
  it("closes package arithmetic without duplicate manifestations",()=>{const p=buildSpiderwebProducerPackage(input());expect(p.arithmetic).toEqual({entities:1,uniqueEntities:1,geometryRefs:1,manifestations:1,uniqueManifestations:1});});
  it("accepts TheHub only when it observes the exact package fingerprint",()=>{const p=buildSpiderwebProducerPackage(input());expect(verifyTheHubConsumerReceipt(p,p.packageFingerprint).state).toBe("PASS");});
  it("fails the consumer receipt on any fingerprint mismatch",()=>{const p=buildSpiderwebProducerPackage(input());expect(verifyTheHubConsumerReceipt(p,"fnv1a32:deadbeef").state).toBe("FAIL");});
});
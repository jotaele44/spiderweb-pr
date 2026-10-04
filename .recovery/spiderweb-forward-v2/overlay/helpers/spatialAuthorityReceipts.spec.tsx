import { buildAuthorityConsumerReceipt, selectSpatialProvider, validateSpatialAuthorityReceipt, type SpatialAuthorityReceipt } from "./spatialAuthorityReceipts";

const base=(patch:Partial<SpatialAuthorityReceipt>={}):SpatialAuthorityReceipt=>({
 schema:"spiderweb-spatial-authority-receipt/v1",authorityId:"archipelago:2026-08-22",family:"ARCHIPELAGO_GEOGRAPHY",sourceRepository:"jotaele44/spiderweb-pr",sourceCommit:"bb917932cb8707071483b06e1a9ebd5f0f0a9015",retrievedAt:"2026-08-22T00:00:00Z",
 sourceManifestations:[{manifestationId:"s1",sha256:"a".repeat(64),bytes:123,role:"SOURCE"}],
 denominator:{source:10,retained:8,excluded:2,unresolved:0},
 geometry:{state:"PASS",crs:"EPSG:4326",identityBasis:"COMPONENT_GRAPH",residue:0},
 equivalence:{kind:"CROSS_SOURCE",state:"PASS",candidateCount:10,matched:8,excluded:2,unresolved:0},
 provider:{providerId:"pr-archipelago",state:"READY",requiresCredential:false},
 certification:"PASS",...patch
});

describe("Spiderweb authoritative spatial receipt gates",()=>{
 it("admits a fully closed authoritative receipt",()=>{const g=validateSpatialAuthorityReceipt(base());expect(g.state).toBe("PASS");expect(g.admissibleForAnalysis).toBeTrue();expect(g.admissibleForCanonicalGeometry).toBeTrue()});
 it("fails closed on unresolved source denominator residue",()=>{const g=validateSpatialAuthorityReceipt(base({denominator:{source:10,retained:8,excluded:1,unresolved:1}}));expect(g.state).toBe("BLOCKED");expect(g.issues.some(i=>i.code==="DENOMINATOR_UNRESOLVED")).toBeTrue()});
 it("fails closed when source arithmetic does not conserve",()=>{const g=validateSpatialAuthorityReceipt(base({denominator:{source:10,retained:8,excluded:1,unresolved:0}}));expect(g.issues.some(i=>i.code==="DENOMINATOR_ARITHMETIC")).toBeTrue()});
 it("requires archive-WFS candidate arithmetic and zero unresolved equivalence",()=>{const g=validateSpatialAuthorityReceipt(base({family:"ARCHIVE_WFS_EQUIVALENCE",equivalence:{kind:"ARCHIVE_WFS",state:"PROVISIONAL",candidateCount:7,matched:5,excluded:1,unresolved:1}}));expect(g.state).toBe("BLOCKED");expect(g.issues.some(i=>i.code==="EQUIVALENCE_NOT_CLOSED")).toBeTrue()});
 it("rejects malformed manifestation and commit identities",()=>{const g=validateSpatialAuthorityReceipt(base({sourceCommit:"name-not-a-sha",sourceManifestations:[{manifestationId:"bad",sha256:"no",bytes:1,role:"SOURCE"}]}));expect(g.state).toBe("BLOCKED");expect(g.issues.some(i=>i.code==="SOURCE_COMMIT_INVALID")).toBeTrue();expect(g.issues.some(i=>i.code==="SOURCE_SHA_INVALID")).toBeTrue()});
 it("keeps credential-ready providers analyzable but not canonical until credentials execute",()=>{const g=validateSpatialAuthorityReceipt(base({provider:{providerId:"imagery",state:"READY_WITH_CREDENTIALS",requiresCredential:true,credentialPresent:false}}));expect(g.state).toBe("PASS");expect(g.admissibleForAnalysis).toBeTrue();expect(g.admissibleForCanonicalGeometry).toBeFalse();expect(g.issues.some(i=>i.code==="CREDENTIAL_DEFERRED"&&i.severity==="WARN")).toBeTrue()});
 it("selects providers fail-closed on absence and ambiguity",()=>{expect(selectSpatialProvider("HYDROGRAPHY",[]).state).toBe("BLOCKED");const candidates=[{providerId:"a",families:["HYDROGRAPHY" as const],state:"READY" as const,requiresCredential:false},{providerId:"b",families:["HYDROGRAPHY" as const],state:"READY" as const,requiresCredential:false}];expect(selectSpatialProvider("HYDROGRAPHY",candidates).state).toBe("BLOCKED")});
 it("closes aggregate authority arithmetic without hiding exclusions",()=>{const r=buildAuthorityConsumerReceipt([base(),base({authorityId:"hydro:2026-09-03",family:"HYDROGRAPHY",sourceCommit:"87f9122dc0cf5c562b0d7c653e3c1c17b36b7218",denominator:{source:4,retained:3,excluded:1,unresolved:0},equivalence:undefined})]);expect(r.state).toBe("PASS");expect(r.arithmetic).toEqual({receipts:2,sourceManifestations:2,sourceRows:14,retained:11,excluded:3,unresolved:0,conserved:true})});
});
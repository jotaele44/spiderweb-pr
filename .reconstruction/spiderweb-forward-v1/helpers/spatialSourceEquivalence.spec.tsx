import { adjudicateSourceDrift, adjudicateSpatialEquivalence, buildEquivalenceCandidateSet, preserveManifestationPlanes } from "./spatialSourceEquivalence";

const base=(overrides:Record<string,unknown>={})=>({manifestationId:"A",stableIds:["1","2"],schemaFields:["id","name"],declaredCrs:"EPSG:4326",geometryHashById:{"1":"g1","2":"g2"},topologyHashById:{"1":"t1","2":"t2"},attributeHashById:{"1":"a1","2":"a2"},featureCount:2,...overrides}) as any;

describe("Spiderweb archive/live equivalence",()=>{
  it("certifies only after stable ID, schema, CRS, geometry, topology and attributes close",()=>{
    const result=adjudicateSpatialEquivalence(base(),base({manifestationId:"B"}));
    expect(result.state).toBe("VERIFIED_EQUIVALENT");
    expect(result.falsifiers.every((row:any)=>row.state==="PASS")).toBeTrue();
  });
  it("rejects count equality when stable IDs differ",()=>{
    const result=adjudicateSpatialEquivalence(base(),base({manifestationId:"B",stableIds:["3","4"]}));
    expect(result.state).toBe("NOT_EQUIVALENT");
    expect(result.falsifiers.find((row:any)=>row.code==="STABLE_ID_SET")?.state).toBe("FAIL");
  });
  it("does not use equal names as identity evidence",()=>{
    const result=adjudicateSpatialEquivalence(base({namesById:{"1":"Road","2":"Road"}}),base({manifestationId:"B",stableIds:["3","4"],namesById:{"3":"Road","4":"Road"}}));
    expect(result.state).toBe("NOT_EQUIVALENT");
    expect(result.prohibitedShortcuts).toContain("NAME_ONLY");
  });
  it("keeps mixed CRS unresolved without a verified transform",()=>{
    const result=adjudicateSpatialEquivalence(base(),base({manifestationId:"B",declaredCrs:"EPSG:32161"}));
    expect(result.state).toBe("UNRESOLVED");
    expect(result.falsifiers.find((row:any)=>row.code==="CRS")?.state).toBe("OPEN");
  });
  it("accepts mixed CRS only when an explicit transform is verified",()=>{
    const result=adjudicateSpatialEquivalence(base({verifiedTransformTo:"EPSG:32161"}),base({manifestationId:"B",declaredCrs:"EPSG:32161"}));
    expect(result.state).toBe("VERIFIED_EQUIVALENT");
  });
  it("falsifies geometry mismatch",()=>{
    const result=adjudicateSpatialEquivalence(base(),base({manifestationId:"B",geometryHashById:{"1":"DIFF","2":"g2"}}));
    expect(result.state).toBe("NOT_EQUIVALENT");
  });
  it("falsifies attribute mismatch",()=>{
    const result=adjudicateSpatialEquivalence(base(),base({manifestationId:"B",attributeHashById:{"1":"a1","2":"DIFF"}}));
    expect(result.state).toBe("NOT_EQUIVALENT");
  });
  it("keeps absent topology evidence unresolved rather than assuming equivalence",()=>{
    const left=base(); delete left.topologyHashById;
    const right=base({manifestationId:"B"}); delete right.topologyHashById;
    expect(adjudicateSpatialEquivalence(left,right).state).toBe("UNRESOLVED");
  });
  it("preserves static, WFS, WMS, REST and raster manifestations independently",()=>{
    const rows=["STATIC_DOWNLOAD","WFS","WMS","REST","RASTER"].map((transport,index)=>({manifestationId:`m${index}`,transport,sha256:`h${index}`,sourceUri:`https://x/${index}`,acquiredAt:"2026-01-01T00:00:00Z",mutable:true,sourceId:`s${index}`})) as any;
    const result=preserveManifestationPlanes(rows);
    expect(result.state).toBe("PASS");
    expect(result.manifestations).toBe(5);
    expect(result.byTransport.WFS).toEqual(["m1"]);
  });
  it("reopens manifestation closure on duplicate IDs or missing hashes",()=>{
    const result=preserveManifestationPlanes([
      {manifestationId:"m",transport:"WFS",sha256:"h",sourceUri:"x",acquiredAt:null,mutable:true,sourceId:"s"},
      {manifestationId:"m",transport:"STATIC_DOWNLOAD",sha256:null,sourceUri:"y",acquiredAt:null,mutable:false,sourceId:"s2"},
    ] as any);
    expect(result.state).toBe("OPEN");
    expect(result.duplicates).toEqual(["m"]);
    expect(result.missingHashes).toEqual(["m"]);
  });
  it("keeps out-of-scope repository drift compatible",()=>{
    const result=adjudicateSourceDrift([{path:"docs/README.md",blobSha:"a"}], ["server/frontend","server/backend"]);
    expect(result.state).toBe("PASS");
    expect(result.scopedChanges).toEqual([]);
  });
  it("reopens certification when application-scoped files drift",()=>{
    const result=adjudicateSourceDrift([{path:"server/frontend/map.ts",blobSha:"a"},{path:"docs/README.md",blobSha:"b"}], ["server/frontend","server/backend"]);
    expect(result.state).toBe("REOPEN");
    expect(result.scopedChanges.map(row=>row.path)).toEqual(["server/frontend/map.ts"]);
    expect(result.changedFileSetFingerprint).toContain("fnv1a32:");
  });
  it("preserves deterministic complete candidate sets and exposes duplicate candidate IDs",()=>{
    const ready=buildEquivalenceCandidateSet([{candidateId:"b"},{candidateId:"a"}]);
    expect(ready.candidates.map(row=>row.candidateId)).toEqual(["a","b"]);
    expect(ready.state).toBe("READY");
    const tied=buildEquivalenceCandidateSet([{candidateId:"a"},{candidateId:"a"}]);
    expect(tied.state).toBe("UNRESOLVED");
  });
});
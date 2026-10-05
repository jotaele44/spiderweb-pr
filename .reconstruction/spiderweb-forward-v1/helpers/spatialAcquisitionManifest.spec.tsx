import { acquisitionUsePolicy, closeAcquisitionCoverage, shouldReacquireMutableSource } from "./spatialAcquisitionManifest";

const req=(sourceId:string,plane:any="WFS",mutable=true)=>({sourceId,plane,mutable,required:true,authority:"AUTHORITATIVE" as const});
const frozen=(sourceId:string,plane:any="WFS")=>({sourceId,plane,disposition:"FROZEN" as const,manifestationSha256:`hash-${sourceId}`,retrievedAt:"2026-10-05T00:00:00Z",locator:`https://example/${sourceId}`,rowOrFeatureCount:1,parserContract:"parser/v1"});

describe("Spiderweb acquisition coverage",()=>{
  it("closes required-source arithmetic across all manifestation planes",()=>{
    const requirements=[req("a","STATIC_DOWNLOAD"),req("b","WFS"),req("c","WMS"),req("d","REST"),req("e","RASTER")];
    const result=closeAcquisitionCoverage(requirements,requirements.map(row=>frozen(row.sourceId,row.plane)));
    expect(result.required).toBe(5);expect(result.frozen).toBe(5);expect(result.state).toBe("PASS");expect(result.certificationEligible).toBeTrue();
  });
  it("preserves authoritative zero-result searches as terminal evidence",()=>{
    const result=closeAcquisitionCoverage([req("a")],[{...frozen("a"),disposition:"ZERO_RESULT",manifestationSha256:"zero-hash",rowOrFeatureCount:0}]);
    expect(result.zeroResult).toBe(1);expect(result.state).toBe("PASS");expect(result.certificationEligible).toBeTrue();
  });
  it("preserves blocked and failed acquisitions without pretending completeness",()=>{
    const result=closeAcquisitionCoverage([req("a"),req("b")],[{...frozen("a"),disposition:"BLOCKED",manifestationSha256:null},{...frozen("b"),disposition:"FAILED",manifestationSha256:null}]);
    expect(result.state).toBe("BLOCKED");expect(result.certificationEligible).toBeFalse();
  });
  it("keeps omitted required sources OPEN",()=>{
    const result=closeAcquisitionCoverage([req("a"),req("b")],[frozen("a")]);
    expect(result.state).toBe("OPEN");expect(result.omitted).toEqual(["b"]);expect(result.open).toBe(2);
  });
  it("reopens duplicate source bindings",()=>{
    const result=closeAcquisitionCoverage([req("a")],[frozen("a"),frozen("a")]);
    expect(result.state).toBe("OPEN");expect(result.duplicates).toEqual(["a"]);
  });
  it("requires hash, retrieval time and parser contract for FROZEN",()=>{
    const result=closeAcquisitionCoverage([req("a")],[{...frozen("a"),manifestationSha256:null}]);
    expect(result.state).toBe("OPEN");expect(result.certificationEligible).toBeFalse();
  });
  it("reacquires mutable sources only when a usable frozen snapshot is absent",()=>{
    expect(shouldReacquireMutableSource(req("a"),null).reacquire).toBeTrue();
    expect(shouldReacquireMutableSource(req("a"),frozen("a")).reacquire).toBeFalse();
  });
  it("does not reacquire immutable sources merely because they are old",()=>{
    expect(shouldReacquireMutableSource(req("a","WFS",false),null)).toEqual({reacquire:false,reason:"IMMUTABLE_SOURCE"});
  });
  it("never promotes WMS rendering into data authority",()=>{
    expect(acquisitionUsePolicy(frozen("a","WMS"))).toEqual({dataAuthority:false,use:"RENDER_OR_CONTEXT_ONLY"});
  });
  it("never promotes blocked or failed source records into data authority",()=>{
    expect(acquisitionUsePolicy({...frozen("a"),disposition:"BLOCKED"})).toEqual({dataAuthority:false,use:"NO_DATA_PROMOTION"});
  });
});
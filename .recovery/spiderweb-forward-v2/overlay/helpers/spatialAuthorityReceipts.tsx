export type AuthorityFamily="ARCHIPELAGO_GEOGRAPHY"|"HYDROGRAPHY"|"PR_GRID_V2"|"ARCHIVE_WFS_EQUIVALENCE"|"OTHER_SPATIAL";
export type AuthorityState="PASS"|"PROVISIONAL"|"BLOCKED";
export type ProviderState="READY"|"READY_WITH_CREDENTIALS"|"EXCLUDED"|"BLOCKED";
export type SpatialAuthorityReceipt={
 schema:"spiderweb-spatial-authority-receipt/v1";
 authorityId:string;
 family:AuthorityFamily;
 sourceRepository:string;
 sourceCommit:string;
 retrievedAt:string|null;
 sourceManifestations:Array<{manifestationId:string;sha256:string;bytes:number;role:"SOURCE"|"SUPPORTING"|"CONTROL"}>;
 denominator:{source:number;retained:number;excluded:number;unresolved:number};
 geometry:{state:"PASS"|"PROVISIONAL"|"BLOCKED";crs:string|null;identityBasis:"STABLE_ID"|"EXACT_GEOMETRY"|"TOPOLOGICAL"|"COMPONENT_GRAPH"|"UNRESOLVED";residue:number};
 equivalence?:{kind:"ARCHIVE_WFS"|"CROSS_SOURCE"|"TEMPORAL";state:"PASS"|"PROVISIONAL"|"BLOCKED";candidateCount:number;matched:number;excluded:number;unresolved:number};
 provider:{providerId:string;state:ProviderState;requiresCredential:boolean;credentialPresent?:boolean};
 certification:AuthorityState;
 notes?:string[];
};
export type AuthorityGateIssue={code:string;severity:"BLOCK"|"WARN";detail:string};
export type AuthorityGateResult={schema:"spiderweb-spatial-authority-gate/v1";authorityId:string;state:"PASS"|"BLOCKED";issues:AuthorityGateIssue[];admissibleForAnalysis:boolean;admissibleForCanonicalGeometry:boolean};
export type ProviderCandidate={providerId:string;families:AuthorityFamily[];state:ProviderState;requiresCredential:boolean};
const sha=/^[0-9a-f]{64}$/i,commit=/^[0-9a-f]{40}$/i,repo=/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;
export function validateSpatialAuthorityReceipt(receipt:SpatialAuthorityReceipt):AuthorityGateResult{
 const issues:AuthorityGateIssue[]=[];
 if(!receipt.authorityId.trim())issues.push({code:"AUTHORITY_ID_MISSING",severity:"BLOCK",detail:"Authority receipt requires a stable authorityId."});
 if(!repo.test(receipt.sourceRepository))issues.push({code:"SOURCE_REPOSITORY_INVALID",severity:"BLOCK",detail:"sourceRepository must be owner/repository."});
 if(!commit.test(receipt.sourceCommit))issues.push({code:"SOURCE_COMMIT_INVALID",severity:"BLOCK",detail:"sourceCommit must be one immutable 40-character Git SHA."});
 if(!receipt.sourceManifestations.length)issues.push({code:"SOURCE_MANIFESTATION_EMPTY",severity:"BLOCK",detail:"At least one source manifestation is required."});
 const mids=new Set<string>();for(const row of receipt.sourceManifestations){if(mids.has(row.manifestationId))issues.push({code:"DUPLICATE_MANIFESTATION_ID",severity:"BLOCK",detail:`Duplicate manifestationId ${row.manifestationId}.`});mids.add(row.manifestationId);if(!sha.test(row.sha256))issues.push({code:"SOURCE_SHA_INVALID",severity:"BLOCK",detail:`Manifestation ${row.manifestationId} lacks a valid SHA-256.`});if(!Number.isInteger(row.bytes)||row.bytes<0)issues.push({code:"SOURCE_BYTES_INVALID",severity:"BLOCK",detail:`Manifestation ${row.manifestationId} has invalid byte count.`})}
 const d=receipt.denominator;if([d.source,d.retained,d.excluded,d.unresolved].some(v=>!Number.isInteger(v)||v<0))issues.push({code:"DENOMINATOR_INVALID",severity:"BLOCK",detail:"Denominator counts must be non-negative integers."});if(d.retained+d.excluded+d.unresolved!==d.source)issues.push({code:"DENOMINATOR_ARITHMETIC",severity:"BLOCK",detail:`Expected retained + excluded + unresolved = source (${d.retained} + ${d.excluded} + ${d.unresolved} != ${d.source}).`});if(d.unresolved>0)issues.push({code:"DENOMINATOR_UNRESOLVED",severity:"BLOCK",detail:`${d.unresolved} source rows remain unresolved.`});
 if(receipt.geometry.state!=="PASS")issues.push({code:"GEOMETRY_NOT_PASS",severity:"BLOCK",detail:`Geometry state is ${receipt.geometry.state}.`});if(receipt.geometry.residue!==0)issues.push({code:"GEOMETRY_RESIDUE",severity:"BLOCK",detail:`Geometry residue is ${receipt.geometry.residue}.`});if(receipt.geometry.identityBasis==="UNRESOLVED")issues.push({code:"GEOMETRY_IDENTITY_UNRESOLVED",severity:"BLOCK",detail:"Geometry identity basis is unresolved."});
 if(receipt.equivalence){const e=receipt.equivalence;if(e.matched+e.excluded+e.unresolved!==e.candidateCount)issues.push({code:"EQUIVALENCE_ARITHMETIC",severity:"BLOCK",detail:"Equivalence candidate arithmetic does not close."});if(e.state!=="PASS"||e.unresolved>0)issues.push({code:"EQUIVALENCE_NOT_CLOSED",severity:"BLOCK",detail:`Equivalence state ${e.state}, unresolved ${e.unresolved}.`})}
 if(receipt.provider.state==="BLOCKED")issues.push({code:"PROVIDER_BLOCKED",severity:"BLOCK",detail:`Provider ${receipt.provider.providerId} is blocked.`});if(receipt.provider.requiresCredential&&!receipt.provider.credentialPresent)issues.push({code:"CREDENTIAL_DEFERRED",severity:"WARN",detail:`Provider ${receipt.provider.providerId} requires credentials; credential-dependent execution remains deferred.`});
 if(receipt.certification!=="PASS")issues.push({code:"CERTIFICATION_NOT_PASS",severity:"BLOCK",detail:`Authority certification is ${receipt.certification}.`});
 const blocks=issues.filter(i=>i.severity==="BLOCK"),analysis=blocks.length===0,canonical=analysis&&receipt.provider.state!=="READY_WITH_CREDENTIALS";
 return{schema:"spiderweb-spatial-authority-gate/v1",authorityId:receipt.authorityId,state:blocks.length?"BLOCKED":"PASS",issues,admissibleForAnalysis:analysis,admissibleForCanonicalGeometry:canonical}
}
export function selectSpatialProvider(family:AuthorityFamily,candidates:ProviderCandidate[]){
 const matching=candidates.filter(p=>p.families.includes(family)&&p.state!=="EXCLUDED");
 if(matching.length===0)return{state:"BLOCKED" as const,provider:null,reason:`No provider matches ${family}; fetch fails closed.`};
 const ready=matching.filter(p=>p.state==="READY"||p.state==="READY_WITH_CREDENTIALS");
 if(ready.length===0)return{state:"BLOCKED" as const,provider:null,reason:`No admitted provider is ready for ${family}.`};
 if(ready.length>1)return{state:"BLOCKED" as const,provider:null,reason:`Multiple providers match ${family}; ambiguous provider selection is not automatic.`};
 const provider=ready[0];if(provider.requiresCredential&&provider.state==="READY_WITH_CREDENTIALS")return{state:"CREDENTIAL_DEFERRED" as const,provider,reason:"Provider contract is ready but credential-dependent acquisition remains deferred."};
 return{state:"PASS" as const,provider,reason:null}
}
export function buildAuthorityConsumerReceipt(receipts:SpatialAuthorityReceipt[]){
 const gates=receipts.map(validateSpatialAuthorityReceipt),ids=receipts.map(r=>r.authorityId),duplicateIds=[...new Set(ids.filter((id,i)=>ids.indexOf(id)!==i))].sort(),issues=[...gates.flatMap(g=>g.issues),...duplicateIds.map(id=>({code:"DUPLICATE_AUTHORITY_ID",severity:"BLOCK" as const,detail:`Duplicate authorityId ${id}.`}))],blocks=issues.filter(i=>i.severity==="BLOCK");
 const sourceManifestations=receipts.reduce((n,r)=>n+r.sourceManifestations.length,0),sourceRows=receipts.reduce((n,r)=>n+r.denominator.source,0),retained=receipts.reduce((n,r)=>n+r.denominator.retained,0),excluded=receipts.reduce((n,r)=>n+r.denominator.excluded,0),unresolved=receipts.reduce((n,r)=>n+r.denominator.unresolved,0);
 return{schema:"spiderweb-authority-consumer-receipt/v1" as const,state:blocks.length?"BLOCKED" as const:"PASS" as const,authorityIds:[...ids].sort(),gates,issues,arithmetic:{receipts:receipts.length,sourceManifestations,sourceRows,retained,excluded,unresolved,conserved:retained+excluded+unresolved===sourceRows}}
}
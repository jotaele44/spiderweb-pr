export type GridIdentityState = "VERIFIED" | "CANDIDATE_NOT_IDENTITY" | "UNRESOLVED";
export type GridAuthorityState = "PASS" | "PROVISIONAL" | "BLOCKED";

export interface LegacyGridEvidence {
  sourceId: string;
  sourceSha256: string | null;
  cellIdPresent: boolean;
  cellSetPresent: boolean;
  reconstructionSucceeded: boolean;
  authoritativeBindingPresent: boolean;
  consumerManifestCount: number;
  consumerManifestHashesComplete: boolean;
}

export interface LegacyGridAdjudication {
  authority: GridAuthorityState;
  identity: GridIdentityState;
  reasons: string[];
  consumerManifestCount: number;
}

export function adjudicateLegacyGrid(e: LegacyGridEvidence): LegacyGridAdjudication {
  const reasons: string[] = [];
  if (!e.sourceSha256) reasons.push("SOURCE_HASH_MISSING");
  if (!e.cellIdPresent && e.cellSetPresent) reasons.push("CELL_ID_ABSENT_CELL_SET_PRESENT");
  if (!e.reconstructionSucceeded) reasons.push("RECONSTRUCTION_FAILED_PRESERVED");
  if (!e.authoritativeBindingPresent) reasons.push("AUTHORITATIVE_BINDING_MISSING");
  if (!e.consumerManifestHashesComplete) reasons.push("CONSUMER_MANIFEST_HASH_RESIDUE");

  const identity: GridIdentityState =
    e.cellIdPresent && e.authoritativeBindingPresent
      ? "VERIFIED"
      : e.cellSetPresent
        ? "CANDIDATE_NOT_IDENTITY"
        : "UNRESOLVED";

  const authority: GridAuthorityState =
    !e.sourceSha256 || !e.cellSetPresent
      ? "BLOCKED"
      : reasons.length === 0
        ? "PASS"
        : "PROVISIONAL";

  return { authority, identity, reasons, consumerManifestCount: e.consumerManifestCount };
}

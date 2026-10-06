import { adjudicateLegacyGrid } from "./spiderwebLegacyGridAuthority";

describe("Spiderweb legacy grid authority", () => {
  it("preserves Cell_Set evidence without promoting missing Cell_ID to identity", () => {
    const result = adjudicateLegacyGrid({
      sourceId: "pr-grid-393",
      sourceSha256: "a".repeat(64),
      cellIdPresent: false,
      cellSetPresent: true,
      reconstructionSucceeded: false,
      authoritativeBindingPresent: false,
      consumerManifestCount: 6,
      consumerManifestHashesComplete: true,
    });
    expect(result.identity).toBe("CANDIDATE_NOT_IDENTITY");
    expect(result.authority).toBe("PROVISIONAL");
    expect(result.reasons).toContain("CELL_ID_ABSENT_CELL_SET_PRESENT");
    expect(result.reasons).toContain("RECONSTRUCTION_FAILED_PRESERVED");
  });

  it("fails closed when the source hash is absent", () => {
    const result = adjudicateLegacyGrid({
      sourceId: "grid",
      sourceSha256: null,
      cellIdPresent: true,
      cellSetPresent: true,
      reconstructionSucceeded: true,
      authoritativeBindingPresent: true,
      consumerManifestCount: 1,
      consumerManifestHashesComplete: true,
    });
    expect(result.authority).toBe("BLOCKED");
  });

  it("does not erase consumer-manifest residue", () => {
    const result = adjudicateLegacyGrid({
      sourceId: "grid",
      sourceSha256: "b".repeat(64),
      cellIdPresent: true,
      cellSetPresent: true,
      reconstructionSucceeded: true,
      authoritativeBindingPresent: true,
      consumerManifestCount: 6,
      consumerManifestHashesComplete: false,
    });
    expect(result.authority).toBe("PROVISIONAL");
    expect(result.reasons).toContain("CONSUMER_MANIFEST_HASH_RESIDUE");
  });
});

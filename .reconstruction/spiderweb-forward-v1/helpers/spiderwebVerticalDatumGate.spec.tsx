import { evaluatePuertoRicoVerticalDatum } from "./spiderwebVerticalDatumGate";

describe("Spiderweb Puerto Rico vertical datum gate", () => {
  it("allows absolute comparison when PRVD02 evidence closes", () => {
    const result = evaluatePuertoRicoVerticalDatum({
      reportedDatum: "PRVD02",
      authoritativePuertoRicoDatum: "PRVD02",
      explicitSupportedTransform: false,
      syntheticOffsetRequested: false,
    });
    expect(result.absoluteComparisonAllowed).toBeTrue();
    expect(result.geometryAuthority).toBe("SPIDERWEB");
    expect(result.proximityIdentity).toBe("DENY");
  });

  it("fails closed on source-reported NAVD88 in Puerto Rico without an explicit supported transform", () => {
    const result = evaluatePuertoRicoVerticalDatum({
      reportedDatum: "NAVD88",
      authoritativePuertoRicoDatum: "PRVD02",
      explicitSupportedTransform: false,
      syntheticOffsetRequested: false,
    });
    expect(result.absoluteComparisonAllowed).toBeFalse();
    expect(result.reasons).toContain("PR_SCOPE_NAVD88_FAIL_CLOSED");
  });

  it("forbids synthetic PRVD02 to NAVD88 offsets", () => {
    const result = evaluatePuertoRicoVerticalDatum({
      reportedDatum: "NAVD88",
      authoritativePuertoRicoDatum: "PRVD02",
      explicitSupportedTransform: true,
      syntheticOffsetRequested: true,
    });
    expect(result.absoluteComparisonAllowed).toBeFalse();
    expect(result.reasons).toContain("SYNTHETIC_VERTICAL_OFFSET_FORBIDDEN");
  });

  it("keeps consumers computed-context-only even when comparison is allowed", () => {
    const result = evaluatePuertoRicoVerticalDatum({
      reportedDatum: "PRVD02",
      authoritativePuertoRicoDatum: "PRVD02",
      explicitSupportedTransform: false,
      syntheticOffsetRequested: false,
    });
    expect(result.consumerAuthority).toBe("COMPUTED_CONTEXT_ONLY");
  });
});

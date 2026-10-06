export type PuertoRicoVerticalDatum = "PRVD02" | "NAVD88" | "MSL" | "UNKNOWN";

export interface VerticalDatumEvidence {
  reportedDatum: PuertoRicoVerticalDatum;
  authoritativePuertoRicoDatum: PuertoRicoVerticalDatum;
  explicitSupportedTransform: boolean;
  syntheticOffsetRequested: boolean;
}

export interface VerticalDatumGateResult {
  absoluteComparisonAllowed: boolean;
  geometryAuthority: "SPIDERWEB";
  consumerAuthority: "COMPUTED_CONTEXT_ONLY";
  proximityIdentity: "DENY";
  reasons: string[];
}

export function evaluatePuertoRicoVerticalDatum(e: VerticalDatumEvidence): VerticalDatumGateResult {
  const reasons: string[] = [];
  if (e.authoritativePuertoRicoDatum !== "PRVD02") reasons.push("AUTHORITATIVE_PR_DATUM_NOT_PRVD02");
  if (e.reportedDatum !== "PRVD02" && !e.explicitSupportedTransform) reasons.push("UNSUPPORTED_DATUM_COMPARISON");
  if (e.reportedDatum === "NAVD88" && !e.explicitSupportedTransform) reasons.push("PR_SCOPE_NAVD88_FAIL_CLOSED");
  if (e.syntheticOffsetRequested) reasons.push("SYNTHETIC_VERTICAL_OFFSET_FORBIDDEN");

  return {
    absoluteComparisonAllowed: reasons.length === 0,
    geometryAuthority: "SPIDERWEB",
    consumerAuthority: "COMPUTED_CONTEXT_ONLY",
    proximityIdentity: "DENY",
    reasons,
  };
}

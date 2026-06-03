import type { EvidenceTier, PriisData, QueryResponse } from "../types/priis";
import { evidenceTierBreakdown } from "../lib/evidence";

const EMPTY_BREAKDOWN: Record<EvidenceTier, number> = { T1: 0, T2: 0, T3: 0, T4: 0 };

export function runPriisQuery(query: string, data: PriisData): Promise<QueryResponse> {
  const normalized = query.toLowerCase();
  // Promise.resolve() wraps synchronous computation for uniform async interface
  const relevant = normalized.includes("vieques") ? data.anomalies.find((a) => a.id === "A-021") : data.anomalies[0];
  const events = relevant ? data.events.filter((event) => relevant.events.includes(event.id)) : [];

  // Shared tier rollup. Previously this adapter dumped every contract into
  // the T2 bucket regardless of its actual `contract.tier` — fixed by using
  // the same helper AnomalyWorkbench consumes.
  const breakdown = relevant
    ? evidenceTierBreakdown(relevant, data).byTier
    : EMPTY_BREAKDOWN;

  return Promise.resolve({
    finding: relevant
      ? `${relevant.id} is the strongest matching pattern-convergence result for: “${query}”. The output remains an analytical lead unless source records are attached and contradictions are resolved.`
      : `No matching anomaly was found for: “${query}”.`,
    evidence: events.slice(0, 5).map((event) => ({
      tier: event.tier ?? "T4",
      label: event.label,
      detail: `${event.kind} event at ${event.siteId} on ${event.at}`,
      entity: { kind: "event", id: event.id }
    })),
    sourceTierBreakdown: breakdown,
    confidence: relevant?.confidence ?? 1,
    contradictions: relevant?.contradictions ?? [],
    missingData: [
      "Attach original procurement records and amendments.",
      "Attach source imagery metadata and collection timestamps.",
      "Validate geocoding against parcel or facility boundaries."
    ],
    recommendedAction: "Open the anomaly, inspect linked contracts and events, then export a source-ledger brief."
  });
}

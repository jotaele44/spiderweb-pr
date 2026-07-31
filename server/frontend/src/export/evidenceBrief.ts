import type { Anomaly, PriisData } from "../types/priis";

function fmtDate(): string {
  return new Date().toISOString().slice(0, 10);
}

function fmtMoney(n: number): string {
  return n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
}

/** Generate a markdown evidence brief for a given anomaly. */
export function buildEvidenceBrief(anomalyId: string, data: PriisData): string {
  const anomaly: Anomaly | undefined = data.anomalies.find((a) => a.id === anomalyId);
  if (!anomaly) return `# Evidence Brief\n\nAnomaly ${anomalyId} not found.`;

  const site = data.sites.find((s) => s.id === anomaly.siteId);
  const contracts = data.contracts.filter((c) => anomaly.contracts.includes(c.id));
  const events = data.events.filter((e) => anomaly.events.includes(e.id));
  const totalValue = contracts.reduce((sum, c) => sum + c.amount, 0);

  const lines: string[] = [
    `# PRIIS Evidence Brief — ${anomaly.id}`,
    `Generated: ${fmtDate()} · UNCLASSIFIED · DEMO`,
    "",
    `## ${anomaly.title}`,
    "",
    `**Site:** ${site?.name ?? anomaly.siteId}  `,
    `**Category:** ${anomaly.category}  `,
    `**Score:** ${anomaly.score} (${anomaly.band.toUpperCase()})  `,
    `**Confidence:** ${["", "Low", "Medium", "High"][anomaly.confidence]}  `,
    "",
    `## Summary`,
    anomaly.summary,
    "",
    `## Evidence Factors`,
    ...anomaly.factors.map((f) => `- **[${f.tag.toUpperCase()}]** ${f.note}`),
    "",
    `## Contracts (${fmtMoney(totalValue)} total)`,
    "| ID | Vendor | Amount | Status | Procurement |",
    "|----|--------|--------|--------|-------------|",
    ...contracts.map((c) => `| ${c.id} | ${c.vendor} | ${fmtMoney(c.amount)} | ${c.status} | ${c.procurement_method ?? "—"} |`),
    "",
    `## Events`,
    "| ID | Kind | Date | Label | Tier |",
    "|----|------|------|-------|------|",
    ...events.map((e) => `| ${e.id} | ${e.kind} | ${e.at} | ${e.label} | ${e.tier ?? "—"} |`),
    "",
  ];

  if (anomaly.contradictions.length > 0) {
    lines.push("## Contradictions");
    lines.push(...anomaly.contradictions.map((c) => `- ${c}`));
    lines.push("");
  }

  lines.push("## Required Next Steps");
  lines.push("1. Attach original procurement records and amendments.");
  lines.push("2. Attach source imagery metadata and collection timestamps.");
  lines.push("3. Validate geocoding against parcel or facility boundaries.");
  lines.push("4. Resolve any open contradictions before raising confidence.");

  return lines.join("\n");
}

export function downloadBrief(anomalyId: string, data: PriisData): void {
  const content = buildEvidenceBrief(anomalyId, data);
  const blob = new Blob([content], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `priis-brief-${anomalyId}-${new Date().toISOString().slice(0, 10)}.md`;
  a.click();
  URL.revokeObjectURL(url);
}

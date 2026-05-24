import type { Contract, PriisData } from "../types/priis";

function escapeCell(value: unknown): string {
  const s = String(value ?? "");
  if (s.includes(",") || s.includes('"') || s.includes("\n")) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

function toCsv(headers: string[], rows: string[][]): string {
  return [headers.map(escapeCell).join(","), ...rows.map((r) => r.map(escapeCell).join(","))].join(
    "\n",
  );
}

function download(filename: string, content: string, mime = "text/csv"): void {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function exportContractsCsv(data: PriisData): void {
  const headers = ["id", "signed", "agency", "vendor", "site", "amount", "status", "tier", "note", "procurement_method"];
  const rows = data.contracts.map((c: Contract) => [
    c.id, c.signed, c.agency, c.vendor, c.site ?? "", c.amount, c.status, c.tier,
    c.note ?? "", c.procurement_method ?? "",
  ]);
  download(`priis-contracts-${new Date().toISOString().slice(0, 10)}.csv`, toCsv(headers, rows as string[][]));
}

export function exportAnomaliesCsv(data: PriisData): void {
  const headers = ["id", "title", "category", "score", "band", "siteId", "confidence"];
  const rows = data.anomalies.map((a) => [
    a.id, a.title, a.category, a.score, a.band, a.siteId ?? "", a.confidence,
  ]);
  download(`priis-anomalies-${new Date().toISOString().slice(0, 10)}.csv`, toCsv(headers, rows as string[][]));
}

import type { Contract, PriisData } from "../types/priis";
import { download } from "./download";

function escapeCell(value: string | number | boolean | null | undefined): string {
  const s = value == null ? "" : String(value);
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

function downloadCsv(filename: string, content: string): void {
  download(filename, content, "text/csv");
}

export function exportContractsCsv(data: PriisData): void {
  const headers = ["id", "signed", "agency", "vendor", "site", "amount", "status", "tier", "note", "procurement_method"];
  const rows = data.contracts.map((c: Contract) => [
    c.id, c.signed, c.agency, c.vendor, c.site ?? "", c.amount, c.status, c.tier,
    c.note ?? "", c.procurement_method ?? "",
  ]);
  downloadCsv(`priis-contracts-${new Date().toISOString().slice(0, 10)}.csv`, toCsv(headers, rows as string[][]));
}

export function exportAnomaliesCsv(data: PriisData): void {
  const headers = ["id", "title", "category", "score", "band", "siteId", "confidence"];
  const rows = data.anomalies.map((a) => [
    a.id, a.title, a.category, a.score, a.band, a.siteId ?? "", a.confidence,
  ]);
  downloadCsv(`priis-anomalies-${new Date().toISOString().slice(0, 10)}.csv`, toCsv(headers, rows as string[][]));
}

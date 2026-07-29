import type { PriisData, Selection, ModuleId } from "../types/priis";

interface FilterItem { key: string; label: string; color?: string }

export interface SessionSnapshot {
  timestamp: string;
  module: ModuleId;
  selection: Selection | null;
  activeInvestigation: string;
  query: string;
  cursor: string;
  filters: FilterItem[];
  live: boolean;
  dataStats: {
    contracts: number;
    anomalies: number;
    alerts: number;
  };
}

export function captureSession(
  module: ModuleId,
  selection: Selection | null,
  activeInvestigation: string,
  query: string,
  cursor: string,
  filters: FilterItem[],
  live: boolean,
  data: PriisData,
): SessionSnapshot {
  return {
    timestamp: new Date().toISOString(),
    module,
    selection,
    activeInvestigation,
    query,
    cursor,
    filters,
    live,
    dataStats: {
      contracts: data.contracts.length,
      anomalies: data.anomalies.length,
      alerts: data.alerts.length,
    },
  };
}

export function downloadSessionLog(snapshot: SessionSnapshot): void {
  const content = JSON.stringify(snapshot, null, 2);
  const blob = new Blob([content], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `priis-session-${snapshot.timestamp.replace(/[:.]/g, "-")}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

import { describe, expect, it } from "vitest";

import { contractMatchesGlobalFilter } from "./FinanceIntelligence";
import type { Contract, PriisData } from "../types/priis";

const contract: Contract = {
  id: "C-1",
  agency: "AG-1",
  vendor: "V-1024",
  site: "S-001",
  amount: 12_500_000,
  signed: "2026-01-02",
  status: "executed",
  tier: "T2",
};

const data = {
  agencies: [{ id: "AG-1", code: "AAA", name: "Aqueduct Authority" }],
  vendors: [{ id: "V-1024", name: "Caribe Engineering", risk: 1, tier: "T2" }],
  sites: [{ id: "S-001", name: "Roosevelt Roads", kind: "facility", lat: 18.2, lng: -65.6 }],
  contracts: [contract],
  events: [],
  anomalies: [],
  sources: [],
  investigations: [],
  alerts: [],
  watchlist: [],
} satisfies PriisData;

describe("contractMatchesGlobalFilter", () => {
  it("matches the rendered vendor name", () => {
    expect(contractMatchesGlobalFilter(contract, data, "Caribe")).toBe(true);
  });

  it("matches the rendered site name", () => {
    expect(contractMatchesGlobalFilter(contract, data, "Roosevelt")).toBe(true);
  });

  it("matches the rendered agency code and formatted amount", () => {
    expect(contractMatchesGlobalFilter(contract, data, "AAA")).toBe(true);
    expect(contractMatchesGlobalFilter(contract, data, "$12,500,000")).toBe(true);
  });

  it("does not synthesize a match from unrelated hidden text", () => {
    expect(contractMatchesGlobalFilter(contract, data, "Monacillo")).toBe(false);
  });
});

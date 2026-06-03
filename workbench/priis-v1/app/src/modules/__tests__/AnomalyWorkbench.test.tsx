/* @vitest-environment jsdom */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { AnomalyWorkbench } from "../AnomalyWorkbench";
import type { Anomaly, Contract, PriisData } from "../../types/priis";

function makeData(anomaly: Anomaly, contracts: Contract[]): PriisData {
  return {
    agencies: [],
    vendors: [],
    sites: [
      { id: "S-1", name: "site one", kind: "site", lat: 18.4, lng: -66 },
    ],
    contracts,
    events: [],
    anomalies: [anomaly],
    sources: [],
    investigations: [],
    alerts: [],
    watchlist: [],
  };
}

describe("AnomalyWorkbench HANDOFF guardrail", () => {
  it("renders the HIGH CONFIDENCE WITHOUT T1/T2 EVIDENCE pill for a violating anomaly", () => {
    // confidence=3 (high) with only T3/T4 contracts → guardrail should trip.
    // This exercises the visual that the seed data couldn't trigger (all
    // seed anomalies have at least one T1 or T2 source).
    const anomaly: Anomaly = {
      id: "A-test",
      title: "Synthetic guardrail trip",
      category: "financial",
      score: 0.9,
      band: "hi",
      siteId: "S-1",
      summary: "high-confidence anomaly with no T1/T2 evidence",
      factors: [],
      contracts: ["C-low-1", "C-low-2"],
      events: [],
      confidence: 3,
      contradictions: [],
    };
    const contracts: Contract[] = [
      { id: "C-low-1", agency: "AG", vendor: "V", site: "S-1", amount: 1, signed: "2024-01-01", status: "executed", tier: "T3" },
      { id: "C-low-2", agency: "AG", vendor: "V", site: "S-1", amount: 1, signed: "2024-01-01", status: "executed", tier: "T4" },
    ];

    render(
      <AnomalyWorkbench
        data={makeData(anomaly, contracts)}
        selection={{ kind: "anomaly", id: "A-test" }}
        setSelection={() => {}}
      />,
    );

    expect(
      screen.getByText(/HIGH CONFIDENCE WITHOUT T1\/T2 EVIDENCE/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/pattern convergence alone is a lead/i),
    ).toBeInTheDocument();
  });

  it("does NOT show the warning when the anomaly has T1 or T2 evidence", () => {
    const anomaly: Anomaly = {
      id: "A-ok",
      title: "Well-supported anomaly",
      category: "financial",
      score: 0.9,
      band: "hi",
      siteId: "S-1",
      summary: "",
      factors: [],
      contracts: ["C-good"],
      events: [],
      confidence: 3,
      contradictions: [],
    };
    const contracts: Contract[] = [
      { id: "C-good", agency: "AG", vendor: "V", site: "S-1", amount: 1, signed: "2024-01-01", status: "executed", tier: "T1" },
    ];

    render(
      <AnomalyWorkbench
        data={makeData(anomaly, contracts)}
        selection={{ kind: "anomaly", id: "A-ok" }}
        setSelection={() => {}}
      />,
    );

    expect(
      screen.queryByText(/HIGH CONFIDENCE WITHOUT T1\/T2 EVIDENCE/i),
    ).toBeNull();
  });
});

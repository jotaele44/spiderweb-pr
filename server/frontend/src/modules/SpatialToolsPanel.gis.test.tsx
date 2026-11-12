import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { SpatialToolsPanel, type useSpatialTools } from "./SpatialToolsPanel";

type PanelState = ReturnType<typeof useSpatialTools>;

function baseState(overrides: Partial<PanelState>): PanelState {
  return {
    mode: "off",
    setMode: vi.fn(),
    gisEnabled: true,
    exportable: () => false,
    drawVertices: [],
    drawAreaM2: 0,
    identifyState: { status: "idle" },
    queryState: { status: "idle" },
    exportError: null,
    runPolygonQuery: vi.fn(),
    exportPolygonQuery: vi.fn(),
    targetKey: "",
    setTargetKey: vi.fn(),
    targetKeys: [],
    measurePoints: [],
    measureLengthKm: 0,
    bufferRadiusKm: 5,
    setBufferRadiusKm: vi.fn(),
    bufferResult: null,
    nearestResult: null,
    clearAll: vi.fn(),
    ...overrides,
  };
}

describe("SpatialToolsPanel backend GIS modes", () => {
  it("offers identify and polygon query only when a GIS client is wired", () => {
    const { rerender } = render(<SpatialToolsPanel {...baseState({})} />);
    expect(screen.getByRole("button", { name: "Identify" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Polygon query" })).toBeTruthy();
    rerender(<SpatialToolsPanel {...baseState({ gisEnabled: false })} />);
    expect(screen.queryByRole("button", { name: "Identify" })).toBeNull();
    expect(screen.getByRole("button", { name: "Area" })).toBeTruthy();
  });

  it("shows identify hits, location context and external links", () => {
    render(
      <SpatialToolsPanel
        {...baseState({
          mode: "identify",
          identifyState: {
            status: "ready",
            data: {
              point: { lon: -66.7156, lat: 18.4723 },
              tolerance_m: 25,
              evidence_state: "COMPUTED",
              location: {
                municipio: { name: "Arecibo", id: "72013" },
                grid_v2: { status: "OK", cell_ids: ["PRG2:L3:R1:C1"], binding: "CURSOR_LOOKUP_NOT_RECORD_BINDING" },
              },
              hits: [{ layer_id: "gazetteer_pr_domestic_names", feature_id: "x1", distance_m: 3.2, properties: { canonical_name: "Punta X" }, anchor: null, bbox: null }],
            },
          },
        })}
      />,
    );
    expect(screen.getByText(/Arecibo \(72013\)/)).toBeTruthy();
    expect(screen.getByText(/PRG2:L3:R1:C1 \(CURSOR_LOOKUP_NOT_RECORD_BINDING\)/)).toBeTruthy();
    expect(screen.getByText("Punta X")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Street View" }).getAttribute("href")).toContain("viewpoint=18.472300%2C-66.715600");
  });

  it("hides export for non-exportable layers and reports exclusions", () => {
    const queryState: PanelState["queryState"] = {
      status: "ready",
      data: {
        contract_version: "gis-query/1.0",
        total_matched: 4,
        summary: {},
        evidence_state: "COMPUTED",
        layers: [{ layer_id: "anomalies", matched_count: 4, returned_count: 4, excluded_count: 2, truncated: false, error: null, features: [] }],
      },
    };
    const { rerender } = render(<SpatialToolsPanel {...baseState({ mode: "query", drawVertices: [[0, 0], [1, 0], [1, 1]], queryState })} />);
    expect(screen.getByText(/anomalies: 4 · 2 without usable geometry · not exportable/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Export CSV" })).toBeNull();
    rerender(<SpatialToolsPanel {...baseState({ mode: "query", drawVertices: [[0, 0], [1, 0], [1, 1]], queryState, exportable: () => true })} />);
    expect(screen.getByRole("button", { name: "Export CSV" })).toBeTruthy();
  });
});

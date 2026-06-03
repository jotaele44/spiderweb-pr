/* @vitest-environment jsdom */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Inspector } from "../Inspector";
import type { PriisData, SpatialFilter } from "../../types/priis";

function emptyData(): PriisData {
  return {
    agencies: [],
    vendors: [],
    sites: [],
    contracts: [],
    events: [],
    anomalies: [],
    sources: [],
    investigations: [],
    alerts: [],
    watchlist: [],
  };
}

function dataWithCarolinaSites(): PriisData {
  return {
    ...emptyData(),
    sites: [
      { id: "S-A", name: "A", kind: "site", lat: 18.4, lng: -66, municipio_geoid: "72031" },
      { id: "S-B", name: "B", kind: "site", lat: 18.3, lng: -66, municipio_geoid: "72031" },
      { id: "S-C", name: "C", kind: "site", lat: 18.2, lng: -66, municipio_geoid: "72127" },
    ],
    contracts: [
      { id: "C-1", agency: "AG", vendor: "V", site: "S-A", amount: 100, signed: "2024-01-01", status: "executed", tier: "T2" },
      { id: "C-2", agency: "AG", vendor: "V", site: "S-C", amount: 200, signed: "2024-01-01", status: "executed", tier: "T2" },
    ],
  };
}

describe("Inspector with a spatial filter", () => {
  it("renders the GEOGRAPHY FILTER card with the right contained-counts", () => {
    const filter: SpatialFilter = { kind: "municipios", geoid: "72031", label: "Carolina" };
    render(
      <Inspector
        data={dataWithCarolinaSites()}
        selection={null}
        setSelection={() => {}}
        spatialFilter={filter}
        clearSpatialFilter={() => {}}
        flightTrack={null}
        watchlist={[]}
        pinToWatchlist={() => {}}
        unpinFromWatchlist={() => {}}
      />,
    );

    // The label renders twice (once in the head h2 for "No selection",
    // once in the SpatialFilterCard) — assert it shows AT LEAST that pair.
    expect(screen.getByText(/GEOGRAPHY FILTER/i)).toBeInTheDocument();
    expect(screen.getAllByText("Carolina").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/municipios · 72031/i)).toBeInTheDocument();
    // Two sites in Carolina, one contract via S-A
    expect(screen.getByText(/sites/).textContent).toContain("2");
    expect(screen.getByText(/contracts/).textContent).toContain("1");
  });

  it("calls clearSpatialFilter when CLEAR is clicked", async () => {
    const clear = vi.fn();
    const filter: SpatialFilter = { kind: "municipios", geoid: "72031", label: "Carolina" };
    render(
      <Inspector
        data={dataWithCarolinaSites()}
        selection={null}
        setSelection={() => {}}
        spatialFilter={filter}
        clearSpatialFilter={clear}
        flightTrack={null}
        watchlist={[]}
        pinToWatchlist={() => {}}
        unpinFromWatchlist={() => {}}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: /clear/i }));
    expect(clear).toHaveBeenCalledOnce();
  });

  it("shows an 'informational only' note for filter kinds not joined to sites", () => {
    const filter: SpatialFilter = { kind: "places", geoid: "7212345", label: "Bayamón" };
    render(
      <Inspector
        data={dataWithCarolinaSites()}
        selection={null}
        setSelection={() => {}}
        spatialFilter={filter}
        clearSpatialFilter={() => {}}
        flightTrack={null}
        watchlist={[]}
        pinToWatchlist={() => {}}
        unpinFromWatchlist={() => {}}
      />,
    );

    expect(screen.getByText(/informational only/i)).toBeInTheDocument();
  });
});

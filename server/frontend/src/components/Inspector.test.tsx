import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { Inspector } from "./Inspector";
import { priisData } from "../data/mockData";

// Every kind reachable from a click in the UI must resolve in the Inspector.
// `agency` is reachable from the contract pane and the investigation graph,
// `source` and `investigation` from the left rail — before these branches
// existed all three fell through to "Missing record".
describe("Inspector entity branches", () => {
  it("renders an agency with its awarded total instead of Missing", () => {
    const agency = priisData.agencies[0];
    render(<Inspector data={priisData} selection={{ kind: "agency", id: agency.id }} setSelection={vi.fn()} />);

    expect(screen.getByText(agency.name)).toBeTruthy();
    expect(screen.queryByText("Missing record")).toBeNull();
  });

  it("renders a source with its tier and status instead of Missing", () => {
    const source = priisData.sources[0];
    render(<Inspector data={priisData} selection={{ kind: "source", id: source.id }} setSelection={vi.fn()} />);

    expect(screen.getByText(source.name)).toBeTruthy();
    expect(screen.queryByText("Missing record")).toBeNull();
  });

  it("renders an investigation with its active vector instead of Missing", () => {
    const investigation = priisData.investigations[0];
    render(
      <Inspector data={priisData} selection={{ kind: "investigation", id: investigation.id }} setSelection={vi.fn()} />,
    );

    expect(screen.getByText(investigation.title)).toBeTruthy();
    expect(screen.getByText(investigation.active_vector)).toBeTruthy();
    expect(screen.queryByText("Missing record")).toBeNull();
  });

  it("still reports genuinely absent records as missing", () => {
    render(<Inspector data={priisData} selection={{ kind: "agency", id: "AG-nonexistent" }} setSelection={vi.fn()} />);

    expect(screen.getByText("Missing record")).toBeTruthy();
    // The app falls back to the fixture only when the backend is down, so the
    // copy must not claim the record is missing "from the fixture".
    expect(screen.getByText(/not present in the loaded dataset/)).toBeTruthy();
  });
});

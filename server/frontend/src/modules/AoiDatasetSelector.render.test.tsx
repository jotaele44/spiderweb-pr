// @vitest-environment jsdom
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import fixture from "../../../../tests/fixtures/aoi_recommendations_v1.json";
import { AoiDatasetSelector } from "./AoiDatasetSelector";
import { parseDatasetRecommendations } from "./aoiRecommendations";
afterEach(cleanup);
function Harness() {
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  return <AoiDatasetSelector response={parseDatasetRecommendations(structuredClone(fixture))}
    selectedIds={selectedIds} onSelectionChange={setSelectedIds} />;
}
describe("AOI dataset selector", () => {
  it("starts with no preferred or automatically selected source", () => {
    render(<Harness />);
    const choices = screen.getAllByRole("checkbox") as HTMLInputElement[];
    expect(choices).toHaveLength(2);
    expect(choices.every((choice) => !choice.checked)).toBe(true);
    expect(screen.getByText(/0 datasets selected/)).toBeTruthy();
  });
  it("selects independent datasets and resolves the exact rows", () => {
    render(<Harness />);
    const choices = screen.getAllByRole("checkbox");
    fireEvent.click(choices[0]); fireEvent.click(choices[1]);
    const table = screen.getByRole("table");
    expect(within(table).getByText("A:0", {exact:false})).toBeTruthy();
    expect(within(table).getByText("B:0", {exact:false})).toBeTruthy();
    expect(within(table).queryByText("A:1", {exact:false})).toBeNull();
    expect(screen.getByText(/2 datasets selected.*2 corresponding source files/)).toBeTruthy();
  });
  it("keeps nonmatching datasets outside the applicable menu", () => {
    render(<Harness />);
    expect(screen.getByText(/Other dataset decisions/)).toBeTruthy();
    expect(screen.getByText(/NO_MATCH_IN_SNAPSHOT/)).toBeTruthy();
    expect(screen.getAllByRole("checkbox")).toHaveLength(2);
  });
  it("clears selection without dropping the source census", () => {
    render(<Harness />); fireEvent.click(screen.getAllByRole("checkbox")[0]);
    fireEvent.click(screen.getByRole("button", {name:"Clear comparison selection"}));
    expect(screen.getByText(/0 datasets selected/)).toBeTruthy();
    expect(screen.getAllByRole("checkbox")).toHaveLength(2);
  });
});

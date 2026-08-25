import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { priisData } from "../data/mockData";
import { FinanceIntelligence } from "./FinanceIntelligence";

describe("FinanceIntelligence visible-value filtering", () => {
  it("finds contracts by the rendered vendor name rather than only the raw vendor id", () => {
    render(<FinanceIntelligence data={priisData} selection={null} setSelection={vi.fn()} />);

    fireEvent.change(screen.getByRole("textbox", { name: "Filter contracts" }), {
      target: { value: "Caribe" },
    });

    const table = screen.getByRole("grid", { name: "Contracts" });
    const dataRows = within(table).getAllByRole("row").slice(1);

    expect(dataRows).toHaveLength(4);
    for (const row of dataRows) {
      expect(within(row).queryByText("Caribe Civil Works LLC")).not.toBeNull();
    }
  });

  it("preserves raw foreign-key ids as searchable discovery terms", () => {
    render(<FinanceIntelligence data={priisData} selection={null} setSelection={vi.fn()} />);

    fireEvent.change(screen.getByRole("textbox", { name: "Filter contracts" }), {
      target: { value: "V-1024" },
    });

    const table = screen.getByRole("grid", { name: "Contracts" });
    expect(within(table).getAllByRole("row").slice(1)).toHaveLength(4);
  });

  it("fails closed to an explicit empty state for a non-match", () => {
    render(<FinanceIntelligence data={priisData} selection={null} setSelection={vi.fn()} />);

    fireEvent.change(screen.getByRole("textbox", { name: "Filter contracts" }), {
      target: { value: "NO_SUCH_VISIBLE_VALUE" },
    });

    expect(screen.queryByText(/No contracts match/)).not.toBeNull();
  });
});

import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { priisData } from "../data/mockData";
import { FinanceIntelligence } from "./FinanceIntelligence";

describe("FinanceIntelligence visible-value filtering", () => {
  it("applies the initial descending amount sort through the v9 row model", () => {
    const largestContract = priisData.contracts.reduce((largest, contract) =>
      contract.amount > largest.amount ? contract : largest,
    );

    render(<FinanceIntelligence data={priisData} selection={null} setSelection={vi.fn()} />);

    const firstDataRow = within(screen.getByRole("grid", { name: "Contracts" })).getAllByRole("row")[1];
    if (!firstDataRow) throw new Error("Expected at least one contract row");
    expect(within(firstDataRow).queryByText(largestContract.id)).not.toBeNull();
  });

  it("sorts string ids through the registered v9 alphanumeric comparator", () => {
    const firstContractId = priisData.contracts
      .map((contract) => contract.id)
      .sort((left, right) => left.localeCompare(right, undefined, { numeric: true }))[0];
    const warn = vi.spyOn(console, "warn");

    try {
      render(<FinanceIntelligence data={priisData} selection={null} setSelection={vi.fn()} />);
      fireEvent.click(screen.getByRole("button", { name: "ID" }));

      expect(screen.getByRole("columnheader", { name: "ID" }).getAttribute("aria-sort")).toBe("ascending");
      const firstDataRow = within(screen.getByRole("grid", { name: "Contracts" })).getAllByRole("row")[1];
      if (!firstDataRow || !firstContractId) throw new Error("Expected at least one contract row");
      expect(within(firstDataRow).queryByText(firstContractId)).not.toBeNull();
      expect(warn.mock.calls.flat().join(" ")).not.toMatch(/sort.*not registered/i);
    } finally {
      warn.mockRestore();
    }
  });

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

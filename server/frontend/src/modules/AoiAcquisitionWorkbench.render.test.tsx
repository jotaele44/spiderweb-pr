import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { AoiAcquisitionWorkbench } from "./AoiAcquisitionWorkbench";
describe("AOI entry and execution gates", () => {
  it("offers the first Dry Run without requiring a previous plan", () => {
    const run = vi.fn();
    render(<AoiAcquisitionWorkbench plan={null} busy={false} canDryRun onDryRun={run} onExportManifest={vi.fn()} />);
    fireEvent.click(screen.getByRole("button",{name:"Dry run"}));
    expect(run).toHaveBeenCalledTimes(1);
    expect((screen.getByRole("button",{name:"Fetch disabled"}) as HTMLButtonElement).disabled).toBe(true);
  });
});

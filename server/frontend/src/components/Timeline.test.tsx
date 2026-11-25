import { describe, expect, it, vi } from "vitest";
import { render, within } from "@testing-library/react";

import { Timeline } from "./Timeline";
import { priisData } from "../data/mockData";

const normalise = (text: string): string => text.replace(/\s+/g, " ").trim().toLowerCase();

// A control's accessible name must contain the text it shows, so a person
// using speech input can say what they see (WCAG 2.5.3). axe-core checks this
// with label-content-name-mismatch, but jsdom has no layout, so the rule cannot
// run here; this asserts the same property directly.
describe("Timeline event buttons", () => {
  it("are named starting with their visible text", () => {
    const { container } = render(
      <Timeline events={priisData.events} cursor="2024-08-14" setCursor={vi.fn()} setSelection={vi.fn()} />,
    );
    const list = within(container).getByRole("list", { name: "Timeline events" });
    const buttons = within(list).getAllByRole("button");
    expect(buttons).toHaveLength(priisData.events.length);
    for (const button of buttons) {
      const visible = normalise(button.textContent ?? "");
      const name = normalise(button.getAttribute("aria-label") ?? "");
      expect(visible).not.toBe("");
      expect(name.startsWith(visible)).toBe(true);
    }
  });

  it("keep the event's label and time in the name", () => {
    const event = priisData.events[0];
    const { container } = render(
      <Timeline events={[event]} cursor="2024-08-14" setCursor={vi.fn()} setSelection={vi.fn()} />,
    );
    const name = within(container).getByRole("button").getAttribute("aria-label") ?? "";
    expect(name).toContain(event.label);
    expect(name).toContain(event.at);
  });
});

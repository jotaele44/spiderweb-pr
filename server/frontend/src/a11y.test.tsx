import { describe, expect, it, vi, beforeAll, afterEach } from "vitest";
import { render } from "@testing-library/react";
import axe, { type Result } from "axe-core";
import type { ReactElement } from "react";

import { priisData } from "./data/mockData";
import { CommandCenter } from "./modules/CommandCenter";
import { FinanceIntelligence } from "./modules/FinanceIntelligence";
import { AnomalyWorkbench } from "./modules/AnomalyWorkbench";
import { InvestigationGraph } from "./modules/InvestigationGraph";
import { QueryLayer } from "./modules/QueryLayer";
import { Inspector } from "./components/Inspector";
import { LeftRail } from "./components/LeftRail";
import { CommandBar } from "./components/CommandBar";
import { Timeline } from "./components/Timeline";

// The automated a11y gate the UI cleanup plan called for (Phase 5) and never
// got. It runs inside `npm run test`, which CI already gates, rather than as a
// separate workflow job.
//
// Scoped to moderate and above; "minor" is mostly best-practice noise.
// Colour-contrast is excluded because jsdom does not
// compute layout or resolve CSS custom properties, so axe cannot evaluate it —
// that check belongs in a real browser, not here.
//
// SpatialIntelligence is not covered: it constructs a MapLibre GL map on mount,
// which needs WebGL and is unavailable in jsdom.

const noop = (): void => undefined;

async function violations(ui: ReactElement): Promise<Result[]> {
  const { container } = render(ui);
  const results = await axe.run(container, {
    resultTypes: ["violations"],
    rules: { "color-contrast": { enabled: false } },
  });
  return results.violations.filter((v) => v.impact !== "minor");
}

const describeViolations = (found: Result[]): string =>
  found.map((v) => `${v.id} (${v.impact}): ${v.nodes.map((n) => n.html).join(" | ")}`).join("\n");

beforeAll(() => {
  // maplibre-gl's CSS import and ResizeObserver are not needed by these trees,
  // but jsdom lacks ResizeObserver entirely and TanStack Table touches it.
  if (!("ResizeObserver" in globalThis)) {
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe = noop;
        unobserve = noop;
        disconnect = noop;
      },
    );
  }
});

afterEach(() => vi.restoreAllMocks());

const cases: [string, () => ReactElement][] = [
  ["CommandCenter", () => <CommandCenter data={priisData} setSelection={noop} setModule={noop} />],
  [
    "FinanceIntelligence",
    () => <FinanceIntelligence data={priisData} selection={null} setSelection={noop} />,
  ],
  [
    "AnomalyWorkbench",
    () => <AnomalyWorkbench data={priisData} selection={null} setSelection={noop} />,
  ],
  ["InvestigationGraph", () => <InvestigationGraph data={priisData} setSelection={noop} />],
  ["QueryLayer", () => <QueryLayer data={priisData} setSelection={noop} />],
  [
    "Inspector",
    () => (
      <Inspector data={priisData} selection={{ kind: "anomaly", id: priisData.anomalies[0].id }} setSelection={noop} />
    ),
  ],
  [
    "LeftRail",
    () => (
      <LeftRail
        data={priisData}
        moduleId="command"
        setModule={noop}
        activeInvestigation={priisData.investigations[0].id}
        setActiveInvestigation={noop}
        setSelection={noop}
      />
    ),
  ],
  [
    "CommandBar",
    () => (
      <CommandBar
        query="vendors near restricted sites"
        setQuery={noop}
        onSubmit={noop}
        onRunPipeline={noop}
        onToggleTheme={noop}
      />
    ),
  ],
  [
    "Timeline",
    () => (
      <Timeline events={priisData.events} cursor="2024-08-14" setCursor={noop} setSelection={noop} />
    ),
  ],
];

describe("accessibility", () => {
  it.each(cases)("%s has no moderate-or-worse axe violations", async (_name, build) => {
    const found = await violations(build());
    expect(describeViolations(found)).toBe("");
  });
});

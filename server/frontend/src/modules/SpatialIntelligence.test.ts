import { describe, expect, it } from "vitest";

import { layerStatusText } from "./SpatialIntelligence";

describe("layerStatusText", () => {
  it("does not call fetched source data rendered", () => {
    expect(layerStatusText(true, "source-ready")).toBe("source ready");
  });

  it("only reports rendered after the map layer reaches loaded", () => {
    expect(layerStatusText(true, "loaded")).toBe("rendered");
  });

  it("preserves disabled and error states", () => {
    expect(layerStatusText(false, "loaded")).toBe("off");
    expect(layerStatusText(true, "error")).toBe("error");
  });
});

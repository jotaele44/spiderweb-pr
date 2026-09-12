import { describe, expect, it } from "vitest";

import {
  densityStatusText,
  layerStatusText,
  parseDensityEnvelope,
} from "./SpatialIntelligence";

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

describe("gazetteer density contract", () => {
  const ready = {
    status: "ready" as const,
    data: parseDensityEnvelope({
      by_geoid: { "72127": 2 },
      matched_count: 2,
      unmatched: 1,
      total_features: 3,
      scope: { identity_effect: "NONE", state: "CANDIDATE_NOT_IDENTITY" },
    }),
  };

  it("validates arithmetic and identity scope", () => {
    expect(ready.data.byGeoid).toEqual({ "72127": 2 });
    expect(ready.data.matchedCount + ready.data.unmatchedCount).toBe(ready.data.totalFeatures);
    expect(() => parseDensityEnvelope({
      by_geoid: { "72127": 2 },
      matched_count: 2,
      unmatched: 0,
      total_features: 3,
      scope: { identity_effect: "NONE" },
    })).toThrow("arithmetic does not close");
  });

  it("does not report errors or unresolved evidence as on", () => {
    expect(densityStatusText(true, { status: "error", message: "HTTP 503" })).toBe("error");
    expect(densityStatusText(true, ready)).toBe("rendered");
    expect(densityStatusText(false, ready)).toBe("off");
  });
});

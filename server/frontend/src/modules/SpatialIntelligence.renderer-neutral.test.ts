import { describe, expect, it } from "vitest";
import source from "./SpatialIntelligence.tsx?raw";

describe("SpatialIntelligence renderer boundary", () => {
  it("keeps normal layer and marker rendering behind semantic adapters", () => {
    expect(source).not.toContain(".addSource(");
    expect(source).not.toContain("getMapLibreInstance");
  });

  it("uses the semantic adapter boundary", () => {
    expect(source).toContain("adaptersRef");
    expect(source).toContain("addGeoJsonPolygonLayer");
    expect(source).toContain("addGeoJsonCircleLayer");
    expect(source).toContain("addVectorTilePolygonLayer");
    expect(source).toContain("adapters.marker.addMarker");
    expect(source).toContain("camera.setView");
  });

  it("surfaces unsupported renderer capabilities instead of silently omitting them", () => {
    expect(source).toContain('"unsupported"');
    expect(source).toContain("Active renderer does not support:");
  });

  it("fences MapLibre-only analysis tools to the active MapLibre runtime", () => {
    expect(source).toContain('from "maplibre-gl"');
    expect(source).toContain('activeMode === "maplibre"');
    expect(source).toContain("useSpatialTools");
    expect(source).toContain("setFeatureState");
  });
});

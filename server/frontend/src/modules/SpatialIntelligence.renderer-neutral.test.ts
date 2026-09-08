import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const source = readFileSync(
  fileURLToPath(new URL("./SpatialIntelligence.tsx", import.meta.url)),
  "utf8",
);

describe("SpatialIntelligence renderer boundary", () => {
  it("does not import or invoke MapLibre directly", () => {
    expect(source).not.toContain('from "maplibre-gl"');
    expect(source).not.toContain("maplibregl.");
    expect(source).not.toContain(".addSource(");
    expect(source).not.toContain(".addLayer(");
    expect(source).not.toContain("getMapLibreInstance");
    expect(source).not.toContain("mapRef");
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
});

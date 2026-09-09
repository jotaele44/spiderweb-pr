import { render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { priisData } from "../data/mockData";

// Every Marker the module builds, so a test can assert both that markers appear
// on a freshly-booted map and that the previous map's markers were removed.
const markers: { added: number; removed: boolean }[] = [];

vi.mock("maplibre-gl", () => {
  class FakeMarker {
    private readonly record = { added: 0, removed: false };
    constructor() {
      markers.push(this.record);
    }
    setLngLat() {
      return this;
    }
    addTo() {
      this.record.added += 1;
      return this;
    }
    remove() {
      this.record.removed = true;
      return this;
    }
  }
  // The module does `import * as maplibregl`, so these must be named exports.
  return { Marker: FakeMarker, Map: class {}, NavigationControl: class {} };
});

// A distinct fake map per boot, mirroring how a 2D/3D switch swaps
// mapRef.current behind the same ref object.
function makeFakeRuntime() {
  const map = { isStyleLoaded: () => false, getStyle: () => undefined, on: vi.fn(), off: vi.fn(), getSource: () => undefined };
  return {
    initialize: vi.fn(() => Promise.resolve()),
    destroy: vi.fn(),
    setView: vi.fn(),
    getView: vi.fn(() => ({ center: [0, 0] as [number, number], zoom: 0 })),
    resize: vi.fn(),
    onBasemapError: vi.fn(() => () => undefined),
    getMapLibreInstance: vi.fn(() => map),
  };
}

vi.mock("../spatial/runtime/RuntimeFactory", () => ({
  createSpatialRuntime: vi.fn(() => makeFakeRuntime()),
  createCesiumRuntime: vi.fn(() => Promise.resolve(makeFakeRuntime())),
}));

const { SpatialIntelligence } = await import("./SpatialIntelligence");

describe("SpatialIntelligence marker lifecycle across runtime swaps", () => {
  beforeEach(() => {
    markers.length = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve({ ok: false, status: 503, json: () => Promise.resolve({}) })),
    );
  });

  it("rebuilds markers on the new map and tears down the old ones", async () => {
    const view = render(
      <SpatialIntelligence data={priisData} selection={null} setSelection={vi.fn()} />,
    );
    await waitFor(() => expect(markers.length).toBeGreaterThan(0));
    const firstBoot = [...markers];
    expect(firstBoot.every((m) => m.added === 1)).toBe(true);

    // Remounting the module boots a fresh runtime, which swaps mapRef.current
    // behind the same ref object. Markers must follow the new map instead of
    // staying bound to the destroyed one.
    view.unmount();
    markers.length = 0;
    render(<SpatialIntelligence data={priisData} selection={null} setSelection={vi.fn()} />);

    await waitFor(() => expect(markers.length).toBeGreaterThan(0));
    expect(markers.every((m) => m.added === 1)).toBe(true);
    // The first boot's markers were all detached rather than leaked.
    expect(firstBoot.every((m) => m.removed)).toBe(true);
  });
});

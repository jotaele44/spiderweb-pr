import { act, render, waitFor } from "@testing-library/react";
import { useEffect } from "react";
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";

import type { SpatialSceneConfig, Unsubscribe } from "./SpatialRuntime";

// jsdom has no WebGL, so canvas.getContext("webgl2"/"webgl") always returns
// null (see HTMLCanvasElement's getContext() in jsdom). useSpatialRuntime
// probes it directly, ahead of the mocked RuntimeFactory below, so without
// this stub every render would take the "graphics unavailable" branch and
// never reach the fake runtime this suite is testing against.
let getContextSpy: MockInstance<typeof HTMLCanvasElement.prototype.getContext>;
beforeAll(() => {
  getContextSpy = vi
    .spyOn(HTMLCanvasElement.prototype, "getContext")
    .mockReturnValue({} as unknown as RenderingContext);
});
afterAll(() => {
  getContextSpy.mockRestore();
});

// Captures the basemap-error listener the hook registers, so a test can fire a
// tile failure the way MapLibre would.
let basemapErrorListener: (() => void) | null = null;
let initializeCalls = 0;

const fakeMap = {} as unknown;

function makeFakeRuntime() {
  return {
    initialize: vi.fn(() => {
      initializeCalls += 1;
      return Promise.resolve();
    }),
    destroy: vi.fn(),
    setView: vi.fn(),
    getView: vi.fn(() => ({ center: [0, 0] as [number, number], zoom: 0 })),
    resize: vi.fn(),
    onBasemapError: vi.fn((listener: () => void): Unsubscribe => {
      basemapErrorListener = listener;
      return () => {
        basemapErrorListener = null;
      };
    }),
    getMapLibreInstance: vi.fn(() => fakeMap),
  };
}

vi.mock("./RuntimeFactory", () => ({
  createSpatialRuntime: vi.fn(() => makeFakeRuntime()),
  createCesiumRuntime: vi.fn(() => Promise.resolve(makeFakeRuntime())),
}));

// Imported after the mock so the hook binds to the mocked factory.
const { useSpatialRuntime } = await import("./useSpatialRuntime");

const CONFIG = {
  basemapStyle: { version: 8, sources: {}, layers: [] },
  basemapSourceId: "osm",
  initialView: { center: [-66.35, 18.22], zoom: 8.4 },
} as unknown as SpatialSceneConfig;

/** Renders the hook against a real host element and exposes its state. */
function Harness({
  mode,
  onState,
}: {
  mode: "maplibre" | "cesium";
  onState: (state: { ready: boolean; tilesFailed: boolean }) => void;
}) {
  const { hostRef, ready, tilesFailed } = useSpatialRuntime(CONFIG, mode);
  useEffect(() => {
    onState({ ready, tilesFailed });
  }, [ready, tilesFailed, onState]);
  return <div ref={hostRef} />;
}

describe("useSpatialRuntime basemap-error state", () => {
  beforeEach(() => {
    basemapErrorListener = null;
    initializeCalls = 0;
  });

  it("clears a latched tile failure when the runtime is rebooted", async () => {
    let state = { ready: false, tilesFailed: false };
    const onState = (next: { ready: boolean; tilesFailed: boolean }) => {
      state = next;
    };

    const view = render(<Harness mode="maplibre" onState={onState} />);
    await waitFor(() => expect(state.ready).toBe(true));
    expect(state.tilesFailed).toBe(false);

    // MapLibre reports its raster source failing.
    act(() => {
      basemapErrorListener?.();
    });
    await waitFor(() => expect(state.tilesFailed).toBe(true));

    // Switching mode tears the runtime down and boots a new one. The failure
    // belonged to the old instance, so it must not survive: otherwise the
    // "base map tiles unavailable" notice sticks, and would even show while
    // Cesium — which has no basemap tile source — is active.
    view.rerender(<Harness mode="cesium" onState={onState} />);
    await waitFor(() => expect(initializeCalls).toBeGreaterThan(1));
    await waitFor(() => expect(state.tilesFailed).toBe(false));
  });
});

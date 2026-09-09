import { describe, expect, it, vi } from "vitest";
import type { SpatialSceneConfig } from "./SpatialRuntime";

const mocks = vi.hoisted(() => ({ setWorkerUrl: vi.fn(), remove: vi.fn() }));
vi.mock("maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url", () => ({ default: "/worker.mjs" }));
vi.mock("maplibre-gl", () => ({
  setWorkerUrl: mocks.setWorkerUrl,
  NavigationControl: class {},
  Map: class {
    listeners = new Map<string, () => void>();
    addControl = vi.fn();
    remove = mocks.remove;
    on(event: string, callback: () => void) { this.listeners.set(event, callback); }
    off(event: string) { this.listeners.delete(event); }
  },
}));

import { MapLibreRuntime } from "./MapLibreRuntime";

const config = {
  basemapSourceId: "base",
  basemapStyle: { version: 8, sources: {}, layers: [] },
  initialView: { center: [0, 0], zoom: 1 },
} as SpatialSceneConfig;

describe("MapLibre initialization boundary", () => {
  it("registers the bundled worker and waits for the style before readiness", async () => {
    const runtime = new MapLibreRuntime();
    let ready = false;
    const pending = runtime.initialize(document.createElement("div"), config).then(() => { ready = true; });
    await Promise.resolve();
    expect(ready).toBe(false);
    expect(mocks.setWorkerUrl).toHaveBeenCalledWith("/worker.mjs");
    const map = runtime.getMapLibreInstance() as unknown as { listeners: Map<string, () => void> };
    map.listeners.get("style.load")?.();
    await pending;
    expect(ready).toBe(true);
    expect(map.listeners.has("style.load")).toBe(false);
    runtime.destroy();
  });

  it("settles pending initialization and removes the listener during teardown", async () => {
    const runtime = new MapLibreRuntime();
    const pending = runtime.initialize(document.createElement("div"), config);
    const map = runtime.getMapLibreInstance() as unknown as { listeners: Map<string, () => void> };
    runtime.destroy();
    await pending;
    expect(runtime.getMapLibreInstance()).toBeNull();
    expect(map.listeners.has("style.load")).toBe(false);
    expect(mocks.remove).toHaveBeenCalled();
  });
});

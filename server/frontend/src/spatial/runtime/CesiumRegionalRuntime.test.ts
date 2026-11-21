import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { SpatialSceneConfig } from "./SpatialRuntime";

// Cesium needs WebGL, which jsdom does not have, so the runtime is exercised
// against a fake Cesium that models only what the provider lifecycle touches:
// the viewer's primitive collection and the tileset's tileLoad/tileFailed
// events. Real Cesium behaviour these tests rely on (checked against Cesium
// 1.144.0): tile content failures are raised only through tileset.tileFailed,
// tileLoad fires when a tile's content has loaded, and removing a primitive
// from a PrimitiveCollection destroys it.
const h = vi.hoisted(() => {
  class FakeEvent {
    readonly listeners = new Set<() => void>();
    addEventListener = (listener: () => void): void => {
      this.listeners.add(listener);
    };
    removeEventListener = (listener: () => void): void => {
      this.listeners.delete(listener);
    };
    raise(): void {
      [...this.listeners].forEach((listener) => listener());
    }
  }

  class FakeTileset {
    readonly tileLoad = new FakeEvent();
    readonly tileFailed = new FakeEvent();
    destroyed = false;
    readonly destroy = vi.fn(() => {
      this.destroyed = true;
    });
    isDestroyed(): boolean {
      return this.destroyed;
    }
  }

  class FakeViewer {
    destroyed = false;
    readonly items: FakeTileset[] = [];
    readonly scene = {
      backgroundColor: null as unknown,
      globe: { baseColor: null as unknown, show: true },
      primitives: {
        add: (primitive: FakeTileset): FakeTileset => {
          this.items.push(primitive);
          return primitive;
        },
        remove: (primitive: FakeTileset): boolean => {
          const index = this.items.indexOf(primitive);
          if (index < 0) return false;
          this.items.splice(index, 1);
          primitive.destroy();
          return true;
        },
      },
      screenSpaceCameraController: {} as Record<string, unknown>,
      requestRender: vi.fn(),
      render: vi.fn(),
    };
    readonly imageryLayers = { addImageryProvider: vi.fn() };
    readonly entities = { add: vi.fn() };
    readonly camera = { setView: vi.fn() };
    readonly resize = vi.fn();
    constructor() {
      state.viewers.push(this);
    }
    isDestroyed(): boolean {
      return this.destroyed;
    }
    destroy(): void {
      this.destroyed = true;
    }
  }

  const state = {
    token: "test-token",
    viewers: [] as FakeViewer[],
  };
  const createGoogle = vi.fn();

  return { FakeEvent, FakeTileset, FakeViewer, state, createGoogle };
});

// Partial mock: other modules (regionalScene) read tile settings from config, so
// keep the real module and override only the token, through a getter so each
// test can choose a token or none.
vi.mock("../../config", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../config")>();
  return Object.defineProperty({ ...actual }, "CESIUM_ION_TOKEN", {
    enumerable: true,
    get: (): string => h.state.token,
  });
});

vi.mock("cesium", () => {
  const color = (): { withAlpha: () => unknown } => ({ withAlpha: () => color() });
  return {
    Ion: { defaultAccessToken: "" },
    Viewer: h.FakeViewer,
    Color: { WHITE: color(), fromCssColorString: () => color() },
    GridImageryProvider: class {},
    Rectangle: { fromDegrees: () => ({}) },
    Cartesian2: class {},
    Cartesian3: { fromDegrees: () => ({}) },
    Cartographic: { fromCartesian: () => ({}) },
    LabelStyle: { FILL_AND_OUTLINE: 0 },
    Math: { toRadians: (degrees: number) => degrees, toDegrees: (radians: number) => radians },
    createGooglePhotorealistic3DTileset: h.createGoogle,
  };
});

const { CesiumRegionalRuntime } = await import("./CesiumRegionalRuntime");

const CONFIG = {
  basemapStyle: { version: 8, sources: {}, layers: [] },
  basemapSourceId: "osm",
  initialView: { center: [-66.35, 18.22], zoom: 8.4 },
} as unknown as SpatialSceneConfig;

const TIMEOUT_MS = 15_000;

async function start() {
  const runtime = new CesiumRegionalRuntime();
  const container = document.createElement("div");
  const onError = vi.fn();
  runtime.onBasemapError(onError);
  await runtime.initialize(container, CONFIG);
  const viewer = h.state.viewers[h.state.viewers.length - 1];
  return { runtime, container, onError, viewer };
}

/** Starts the runtime with a Google tileset whose root resolves immediately. */
async function startWithRoot() {
  const tileset = new h.FakeTileset();
  h.createGoogle.mockResolvedValue(tileset);
  const started = await start();
  await vi.advanceTimersByTimeAsync(0);
  return { ...started, tileset };
}

const marker = (container: HTMLElement): string | undefined => container.dataset.spatialBasemap;

beforeEach(() => {
  vi.useFakeTimers();
  vi.spyOn(window, "requestAnimationFrame").mockReturnValue(1);
  vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => undefined);
  h.state.token = "test-token";
  h.state.viewers.length = 0;
  h.createGoogle.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("CesiumRegionalRuntime Google provider lifecycle", () => {
  it("stays google-loading after the root tileset resolves and falls back at the timeout if no content loads", async () => {
    const { container, onError, viewer, tileset } = await startWithRoot();

    // The root resolving alone must not count as success.
    expect(marker(container)).toBe("google-loading");
    expect(viewer.items).toContain(tileset);

    await vi.advanceTimersByTimeAsync(TIMEOUT_MS - 1);
    expect(marker(container)).toBe("google-loading");
    expect(onError).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(1);
    expect(marker(container)).toBe("grid-fallback");
    expect(viewer.scene.globe.show).toBe(true);
    expect(viewer.imageryLayers.addImageryProvider).toHaveBeenCalledTimes(1);
    expect(viewer.items).toHaveLength(0);
    expect(tileset.destroyed).toBe(true);
    expect(tileset.tileLoad.listeners.size).toBe(0);
    expect(tileset.tileFailed.listeners.size).toBe(0);
    expect(onError).toHaveBeenCalledTimes(1);
  });

  it("marks google-photorealistic on the first tileLoad and stops the timeout", async () => {
    const { container, onError, viewer, tileset } = await startWithRoot();

    tileset.tileLoad.raise();
    expect(marker(container)).toBe("google-photorealistic");
    expect(tileset.tileLoad.listeners.size).toBe(0);
    expect(tileset.tileFailed.listeners.size).toBe(0);

    await vi.advanceTimersByTimeAsync(TIMEOUT_MS * 4);
    expect(marker(container)).toBe("google-photorealistic");
    expect(viewer.items).toContain(tileset);
    expect(viewer.scene.globe.show).toBe(false);
    expect(onError).not.toHaveBeenCalled();
  });

  it("falls back immediately when a tile fails before any content has loaded", async () => {
    const { container, onError, viewer, tileset } = await startWithRoot();

    tileset.tileFailed.raise();
    expect(marker(container)).toBe("grid-fallback");
    expect(viewer.items).toHaveLength(0);
    expect(tileset.destroyed).toBe(true);
    expect(onError).toHaveBeenCalledTimes(1);

    // The timeout was cleared by the fallback, so it must not fire a second one.
    await vi.advanceTimersByTimeAsync(TIMEOUT_MS * 2);
    expect(onError).toHaveBeenCalledTimes(1);
  });

  it("ignores tile failures after content has loaded", async () => {
    const { container, onError, viewer, tileset } = await startWithRoot();

    tileset.tileLoad.raise();
    tileset.tileFailed.raise();

    expect(marker(container)).toBe("google-photorealistic");
    expect(viewer.items).toContain(tileset);
    expect(onError).not.toHaveBeenCalled();
  });

  it("does nothing after destroy() when the timeout or tile events arrive late", async () => {
    const { runtime, container, onError, tileset } = await startWithRoot();

    runtime.destroy();
    expect(tileset.tileLoad.listeners.size).toBe(0);
    expect(tileset.tileFailed.listeners.size).toBe(0);

    tileset.tileFailed.raise();
    tileset.tileLoad.raise();
    await vi.advanceTimersByTimeAsync(TIMEOUT_MS * 2);

    expect(marker(container)).toBe("google-loading");
    expect(onError).not.toHaveBeenCalled();
  });

  it("destroys a tileset whose root resolves after destroy() and leaves the marker alone", async () => {
    const tileset = new h.FakeTileset();
    let resolveRoot: (value: unknown) => void = () => undefined;
    h.createGoogle.mockReturnValue(new Promise((resolve) => { resolveRoot = resolve; }));
    const { runtime, container, onError, viewer } = await start();

    runtime.destroy();
    resolveRoot(tileset);
    await vi.advanceTimersByTimeAsync(0);

    expect(tileset.destroy).toHaveBeenCalled();
    expect(viewer.items).toHaveLength(0);
    expect(marker(container)).toBe("google-loading");
    expect(onError).not.toHaveBeenCalled();
  });

  it("falls back when the tileset creation rejects", async () => {
    h.createGoogle.mockRejectedValue(new Error("401"));
    const { container, onError, viewer } = await start();
    await vi.advanceTimersByTimeAsync(0);

    expect(marker(container)).toBe("grid-fallback");
    expect(viewer.scene.globe.show).toBe(true);
    expect(onError).toHaveBeenCalledTimes(1);
  });

  it("falls back when the root request never answers", async () => {
    h.createGoogle.mockReturnValue(new Promise(() => undefined));
    const { container, onError } = await start();

    await vi.advanceTimersByTimeAsync(TIMEOUT_MS);
    expect(marker(container)).toBe("grid-fallback");
    expect(onError).toHaveBeenCalledTimes(1);
  });

  it("stays on the deterministic grid and never calls Google without a token", async () => {
    h.state.token = "";
    const { container, onError, viewer } = await start();
    await vi.advanceTimersByTimeAsync(TIMEOUT_MS * 2);

    expect(marker(container)).toBe("grid");
    expect(h.createGoogle).not.toHaveBeenCalled();
    expect(viewer.scene.globe.show).toBe(true);
    expect(onError).not.toHaveBeenCalled();
  });
});

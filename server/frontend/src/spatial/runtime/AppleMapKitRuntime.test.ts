import { describe, expect, it, vi } from "vitest";

import { AppleMapKitRuntime, type AppleMapHandle, type AppleMapKitFactory } from "./AppleMapKitRuntime";

function fakeFactory(): { factory: AppleMapKitFactory; handle: AppleMapHandle } {
  let view = { center: [-66.4, 18.2] as [number, number], cameraDistanceMeters: 20_000 };
  const handle: AppleMapHandle = {
    setCenter: vi.fn((center: [number, number]) => { view = { ...view, center }; }),
    setCameraDistanceMeters: vi.fn((distance: number) => { view = { ...view, cameraDistanceMeters: distance }; }),
    setMapType: vi.fn(),
    getCameraView: vi.fn(() => view),
    destroy: vi.fn(),
  };
  return {
    handle,
    factory: { create: vi.fn(async () => handle) },
  };
}

describe("AppleMapKitRuntime", () => {
  it("runs through an injected factory without embedding credentials", async () => {
    const { factory, handle } = fakeFactory();
    const runtime = new AppleMapKitRuntime(factory);
    const container = document.createElement("div");

    await runtime.initialize(container, {
      mapType: "satellite",
      initialView: { center: [-66.4, 18.2], cameraDistanceMeters: 20_000 },
    });
    runtime.setMapType("hybrid");
    runtime.setView({ center: [-66.1, 18.45], cameraDistanceMeters: 8_000 }, false);

    expect(factory.create).toHaveBeenCalledOnce();
    expect(handle.setMapType).toHaveBeenCalledWith("hybrid");
    expect(runtime.getView()).toEqual({ center: [-66.1, 18.45], cameraDistanceMeters: 8_000 });

    runtime.destroy();
    expect(handle.destroy).toHaveBeenCalledOnce();
  });

  it("fails closed before initialization and for invalid WGS84 camera state", async () => {
    const { factory } = fakeFactory();
    const runtime = new AppleMapKitRuntime(factory);
    expect(() => runtime.getView()).toThrow("not initialized");

    await expect(runtime.initialize(document.createElement("div"), {
      mapType: "satellite",
      initialView: { center: [181, 18.2], cameraDistanceMeters: 20_000 },
    })).rejects.toThrow("outside WGS84 bounds");
  });

  it("does not silently permit double initialization", async () => {
    const { factory } = fakeFactory();
    const runtime = new AppleMapKitRuntime(factory);
    const options = {
      mapType: "satellite" as const,
      initialView: { center: [-66.4, 18.2] as [number, number], cameraDistanceMeters: 20_000 },
    };
    await runtime.initialize(document.createElement("div"), options);
    await expect(runtime.initialize(document.createElement("div"), options)).rejects.toThrow("already initialized");
  });
});

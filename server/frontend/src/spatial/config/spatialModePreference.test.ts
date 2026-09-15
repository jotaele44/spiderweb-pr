import { describe, expect, it, vi } from "vitest";

import {
  readSpatialMode,
  SPATIAL_MODE_STORAGE_KEY,
  writeSpatialMode,
} from "./spatialModePreference";

describe("spatial mode preference", () => {
  it("restores only the supported 3D value", () => {
    expect(readSpatialMode({ getItem: () => "cesium" })).toBe("cesium");
    expect(readSpatialMode({ getItem: () => "maplibre" })).toBe("maplibre");
    expect(readSpatialMode({ getItem: () => "invalid" })).toBe("maplibre");
    expect(readSpatialMode({ getItem: () => null })).toBe("maplibre");
  });

  it("fails safely when storage is unavailable", () => {
    expect(readSpatialMode({ getItem: () => { throw new Error("blocked"); } })).toBe("maplibre");
    expect(writeSpatialMode("cesium", { setItem: () => { throw new Error("blocked"); } })).toBe(false);
  });

  it("writes the stable key and requested mode", () => {
    const setItem = vi.fn();
    expect(writeSpatialMode("cesium", { setItem })).toBe(true);
    expect(setItem).toHaveBeenCalledWith(SPATIAL_MODE_STORAGE_KEY, "cesium");
  });
});

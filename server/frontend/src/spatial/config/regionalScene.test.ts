import { describe, expect, it } from "vitest";
import {
  clampRegionalCameraHeight,
  REGIONAL_CAMERA_CONSTRAINTS,
} from "./regionalScene";

describe("regional camera constraints", () => {
  it("keeps the initial 3D height inside the permitted range", () => {
    const { initialHeightMeters, minimumHeightMeters, maximumHeightMeters } =
      REGIONAL_CAMERA_CONSTRAINTS.cesium;

    expect(minimumHeightMeters).toBeLessThan(initialHeightMeters);
    expect(initialHeightMeters).toBeLessThan(maximumHeightMeters);
  });

  it("locks the approved Puerto Rico regional limits", () => {
    expect(REGIONAL_CAMERA_CONSTRAINTS.center).toEqual([-66.35, 18.22]);
    expect(REGIONAL_CAMERA_CONSTRAINTS.cesium).toMatchObject({
      initialHeightMeters: 450_000,
      minimumHeightMeters: 250,
      maximumHeightMeters: 1_050_000,
      headingDegrees: 0,
      pitchDegrees: -55,
    });
    expect(REGIONAL_CAMERA_CONSTRAINTS.mapLibre).toEqual({
      minimumZoom: 7.4,
      maximumZoom: 19,
    });
  });

  it.each([
    [-1, 250],
    [0, 250],
    [249, 250],
    [250, 250],
    [450_000, 450_000],
    [1_050_000, 1_050_000],
    [1_050_001, 1_050_000],
    [Number.POSITIVE_INFINITY, 450_000],
    [Number.NaN, 450_000],
  ])("clamps requested height %s to %s", (requested, expected) => {
    expect(clampRegionalCameraHeight(requested)).toBe(expected);
  });

  it("uses ordered geographic bounds containing the regional center", () => {
    const [[west, south], [east, north]] = REGIONAL_CAMERA_CONSTRAINTS.bounds;
    const [longitude, latitude] = REGIONAL_CAMERA_CONSTRAINTS.center;

    expect(west).toBeLessThan(east);
    expect(south).toBeLessThan(north);
    expect(longitude).toBeGreaterThanOrEqual(west);
    expect(longitude).toBeLessThanOrEqual(east);
    expect(latitude).toBeGreaterThanOrEqual(south);
    expect(latitude).toBeLessThanOrEqual(north);
  });
});

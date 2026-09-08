import { describe, expect, it } from "vitest";

import {
  APPLE_MAPKIT_CAPABILITY,
  createExternalRenderObservation,
} from "./ExternalRenderProvider";

describe("APPLE_MAPKIT_CAPABILITY", () => {
  it("cannot be promoted to source authority or persistent raster storage", () => {
    expect(APPLE_MAPKIT_CAPABILITY.classification).toBe("EXTERNAL_RENDER_PROVIDER");
    expect(APPLE_MAPKIT_CAPABILITY.authority).toBe("NONE");
    expect(APPLE_MAPKIT_CAPABILITY.pixelPersistenceAllowed).toBe(false);
    expect(APPLE_MAPKIT_CAPABILITY.tileHarvestAllowed).toBe(false);
    expect(APPLE_MAPKIT_CAPABILITY.secondaryDatabaseAllowed).toBe(false);
  });

  it("declares only supported presentation modes", () => {
    expect(APPLE_MAPKIT_CAPABILITY.mapTypes).toEqual(["standard", "satellite", "hybrid"]);
  });
});

describe("createExternalRenderObservation", () => {
  it("forces visual corroboration with no identity effect", () => {
    const observation = createExternalRenderObservation({
      observationId: "OBS-1",
      provider: "apple-mapkit",
      observedAtUtc: "2026-09-07T23:30:00Z",
      view: { center: [-66.1057, 18.4663], zoom: 14 },
      mapType: "satellite",
      targetEntityId: "LOCAL-1",
      note: "Structure visually inspected.",
    });

    expect(observation.evidenceClass).toBe("VISUAL_CORROBORATION");
    expect(observation.identityEffect).toBe("NONE");
  });

  it("fails closed on empty notes and non-finite camera state", () => {
    const base = {
      observationId: "OBS-2",
      provider: "apple-mapkit" as const,
      observedAtUtc: "2026-09-07T23:30:00Z",
      mapType: "hybrid" as const,
    };

    expect(() => createExternalRenderObservation({
      ...base,
      view: { center: [-66.1, 18.4], zoom: 12 },
      note: " ",
    })).toThrow("observation note is required");

    expect(() => createExternalRenderObservation({
      ...base,
      view: { center: [Number.NaN, 18.4], zoom: 12 },
      note: "valid",
    })).toThrow("observation center must be finite");
  });
});

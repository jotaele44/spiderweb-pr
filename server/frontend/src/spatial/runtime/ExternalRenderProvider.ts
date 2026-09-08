import type { CameraView } from "./SpatialRuntime";

export type ExternalRenderProviderId = "apple-mapkit";
export type ExternalRenderMapType = "standard" | "satellite" | "hybrid";

export interface ExternalRenderObservation {
  observationId: string;
  provider: ExternalRenderProviderId;
  observedAtUtc: string;
  view: CameraView;
  mapType: ExternalRenderMapType;
  targetEntityId?: string;
  note: string;
  evidenceClass: "VISUAL_CORROBORATION";
  identityEffect: "NONE";
}

export interface ExternalRenderProviderCapability {
  id: ExternalRenderProviderId;
  classification: "EXTERNAL_RENDER_PROVIDER";
  authority: "NONE";
  mapTypes: readonly ExternalRenderMapType[];
  credentialsRequired: boolean;
  pixelPersistenceAllowed: false;
  tileHarvestAllowed: false;
  secondaryDatabaseAllowed: false;
}

/**
 * Capability declaration only. Provider SDK lifecycle belongs in its runtime
 * adapter; federation geometry and observations remain provider independent.
 */
export const APPLE_MAPKIT_CAPABILITY: ExternalRenderProviderCapability = Object.freeze({
  id: "apple-mapkit",
  classification: "EXTERNAL_RENDER_PROVIDER",
  authority: "NONE",
  mapTypes: ["standard", "satellite", "hybrid"],
  credentialsRequired: true,
  pixelPersistenceAllowed: false,
  tileHarvestAllowed: false,
  secondaryDatabaseAllowed: false,
});

export function createExternalRenderObservation(
  input: Omit<ExternalRenderObservation, "evidenceClass" | "identityEffect">,
): ExternalRenderObservation {
  if (!input.observationId.trim()) throw new Error("observationId is required");
  if (!input.note.trim()) throw new Error("observation note is required");
  if (!Number.isFinite(input.view.center[0]) || !Number.isFinite(input.view.center[1])) {
    throw new Error("observation center must be finite");
  }
  if (!Number.isFinite(input.view.zoom)) throw new Error("observation zoom must be finite");

  return Object.freeze({
    ...input,
    evidenceClass: "VISUAL_CORROBORATION",
    identityEffect: "NONE",
  });
}

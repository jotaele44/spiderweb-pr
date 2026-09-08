import type { ExternalRenderMapType } from "./ExternalRenderProvider";

export interface AppleCameraView {
  center: [number, number];
  cameraDistanceMeters: number;
}

export interface AppleMapHandle {
  setCenter(center: [number, number], animated: boolean): void;
  setCameraDistanceMeters(distance: number, animated: boolean): void;
  setMapType(mapType: ExternalRenderMapType): void;
  getCameraView(): AppleCameraView;
  destroy(): void;
}

export interface AppleMapKitFactory {
  /**
   * Live implementations may initialize MapKit JS only after authorization is
   * supplied at the final integration stage. Tests inject a credential-free
   * fake. The factory must never expose provider tiles/pixels to callers.
   */
  create(
    container: HTMLElement,
    options: { mapType: ExternalRenderMapType; initialView: AppleCameraView },
  ): Promise<AppleMapHandle>;
}

/**
 * Provider-neutral lifecycle shell for Apple MapKit. It intentionally does
 * not implement SpatialRuntime yet: SpatialRuntime currently carries a
 * MapLibre StyleSpecification and zoom semantics. Claiming conformance before
 * that contract is generalized would silently imply overlay/camera parity.
 */
export class AppleMapKitRuntime {
  private handle: AppleMapHandle | null = null;

  constructor(private readonly factory: AppleMapKitFactory) {}

  async initialize(
    container: HTMLElement,
    options: { mapType: ExternalRenderMapType; initialView: AppleCameraView },
  ): Promise<void> {
    if (this.handle) throw new Error("AppleMapKitRuntime already initialized");
    this.assertView(options.initialView);
    this.handle = await this.factory.create(container, options);
  }

  destroy(): void {
    this.handle?.destroy();
    this.handle = null;
  }

  setView(view: AppleCameraView, animated = true): void {
    this.assertInitialized();
    this.assertView(view);
    this.handle!.setCenter(view.center, animated);
    this.handle!.setCameraDistanceMeters(view.cameraDistanceMeters, animated);
  }

  getView(): AppleCameraView {
    this.assertInitialized();
    return this.handle!.getCameraView();
  }

  setMapType(mapType: ExternalRenderMapType): void {
    this.assertInitialized();
    this.handle!.setMapType(mapType);
  }

  private assertInitialized(): void {
    if (!this.handle) throw new Error("AppleMapKitRuntime is not initialized");
  }

  private assertView(view: AppleCameraView): void {
    const [lng, lat] = view.center;
    if (!Number.isFinite(lng) || !Number.isFinite(lat)) {
      throw new Error("Apple camera center must be finite");
    }
    if (lng < -180 || lng > 180 || lat < -90 || lat > 90) {
      throw new Error("Apple camera center is outside WGS84 bounds");
    }
    if (!Number.isFinite(view.cameraDistanceMeters) || view.cameraDistanceMeters < 0) {
      throw new Error("Apple camera distance must be finite and non-negative");
    }
  }
}

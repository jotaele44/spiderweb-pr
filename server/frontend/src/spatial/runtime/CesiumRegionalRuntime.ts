import * as Cesium from "cesium";
// Sizes the Cesium widget/canvas to fill its container (among other base
// chrome styling) — without it the canvas stays at the browser's default
// 300×150 intrinsic size. Imported here (not injected via a <link> tag) so
// Vite code-splits it into this lazy chunk's CSS output alongside the JS —
// it doesn't load until 3D mode is actually used, matching everything else
// in this file.
import "cesium/Build/Cesium/Widgets/widgets.css";
import type { CameraView, SpatialRuntime, SpatialSceneConfig, Unsubscribe } from "./SpatialRuntime";

// Cesium resolves Workers/ThirdParty/Assets/Widgets via runtime string paths
// (Web Workers, textures) rather than import statements, so Rollup can't
// bundle them — they're copied to public/cesium/ by
// scripts/copy-cesium-assets.mjs (postinstall) and served as plain static
// files. This must be set before any Cesium code that spawns a worker or
// loads a static asset runs — module-load time, before the Viewer is
// constructed, is early enough. See vite.config.ts for why this isn't
// vite-plugin-cesium's job.
(globalThis as { CESIUM_BASE_URL?: string }).CESIUM_BASE_URL = "/cesium/";

// No Cesium ion account/token is used anywhere in this runtime (no default
// imagery, no ion terrain, geocoder disabled) — set an empty token so Cesium
// doesn't warn about the shared demo token on every load.
Cesium.Ion.defaultAccessToken = "";

// Rough zoom(0-22, MapLibre-style)→altitude(meters) mapping so the same
// SpatialSceneConfig.initialView works for both runtimes. This is NOT a
// precise equivalence with MapLibre's Web Mercator zoom — it's anchored so
// zoom 0 is roughly a full-globe view and each level halves the altitude,
// which is close enough for "start looking at roughly the same place at
// roughly the same scale." Do not rely on it for anything that needs exact
// parity between 2D and 3D camera framing.
const ZOOM0_ALTITUDE_M = 40_000_000;

function zoomToAltitude(zoom: number): number {
  return ZOOM0_ALTITUDE_M / Math.pow(2, zoom);
}

function altitudeToZoom(altitudeM: number): number {
  return Math.log2(ZOOM0_ALTITUDE_M / Math.max(altitudeM, 1));
}

/**
 * Regional 3D shell — Phase 2. Deliberately minimal: no imagery layer (no
 * Cesium ion token, no network dependency for the base globe — just the
 * default ellipsoid), no terrain provider (flat WGS84 ellipsoid; real
 * terrain is Phase 4, pending the GEBCO vertical-datum work), no stock
 * Cesium UI widgets (this is a producer-local diagnostic scene, not a
 * general-purpose Cesium app shell). Site markers, boundary overlays, and
 * altitude-dependent LOD are later Phase 2/3 increments, not this file.
 */
export class CesiumRegionalRuntime implements SpatialRuntime {
  private viewer: Cesium.Viewer | null = null;
  private firstFrame: number | null = null;

  initialize(container: HTMLElement, config: SpatialSceneConfig): Promise<void> {
    const viewer = new Cesium.Viewer(container, {
      baseLayer: false,
      baseLayerPicker: false,
      geocoder: false,
      homeButton: false,
      sceneModePicker: false,
      navigationHelpButton: false,
      animation: false,
      timeline: false,
      fullscreenButton: false,
      infoBox: false,
      selectionIndicator: false,
      shouldAnimate: false,
    });
    viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString("#0a1a2a");
    this.viewer = viewer;
    const [longitude, latitude] = config.initialView.center;
    viewer.camera.setView({
      destination: Cesium.Rectangle.fromDegrees(
        longitude - 1.6,
        latitude - 0.8,
        longitude + 1.6,
        latitude + 0.8,
      ),
    });
    viewer.resize();
    viewer.scene.requestRender();
    this.firstFrame = window.requestAnimationFrame(() => {
      this.firstFrame = null;
      viewer.resize();
      viewer.scene.render();
    });
    return Promise.resolve();
  }

  destroy(): void {
    if (this.firstFrame !== null) window.cancelAnimationFrame(this.firstFrame);
    this.firstFrame = null;
    this.viewer?.destroy();
    this.viewer = null;
  }

  setView(view: CameraView, options?: { animate?: boolean; speed?: number }): void {
    if (!this.viewer) return;
    const destination = Cesium.Cartesian3.fromDegrees(
      view.center[0],
      view.center[1],
      zoomToAltitude(view.zoom),
    );
    // Orientation must be explicit: setView/flyTo inherit the camera's current
    // pitch when it's omitted, so moving to a low regional altitude while the
    // camera still holds the default global-view pitch aims it at the horizon
    // (empty space) instead of the ground — a black scene, not an error.
    const orientation = {
      heading: 0,
      pitch: -Cesium.Math.PI_OVER_TWO,
      roll: 0,
    };
    if (options?.animate === false) {
      this.viewer.camera.setView({ destination, orientation });
    } else {
      void this.viewer.camera.flyTo({
        destination,
        orientation,
        duration: options?.speed ? Math.min(3, 1 / options.speed) : 1.5,
      });
    }
  }

  getView(): CameraView {
    if (!this.viewer) return { center: [0, 0], zoom: 0 };
    const carto = Cesium.Cartographic.fromCartesian(this.viewer.camera.position);
    return {
      center: [Cesium.Math.toDegrees(carto.longitude), Cesium.Math.toDegrees(carto.latitude)],
      zoom: altitudeToZoom(carto.height),
    };
  }

  resize(): void {
    this.viewer?.resize();
  }

  onBasemapError(_listener: () => void): Unsubscribe {
    // No imagery layer is loaded (baseLayer: false, no ion token) — there is
    // nothing that can fail the way MapLibre's raster tile source can.
    // eslint-disable-next-line @typescript-eslint/no-empty-function
    return () => {};
  }
}

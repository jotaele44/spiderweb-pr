import * as maplibregl from "maplibre-gl";
import maplibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import { REGIONAL_CAMERA_CONSTRAINTS } from "../config/regionalScene";
import type { CameraView, SpatialRuntime, SpatialSceneConfig, Unsubscribe } from "./SpatialRuntime";

maplibregl.setWorkerUrl(maplibreWorkerUrl);

export class MapLibreRuntime implements SpatialRuntime {
  private map: maplibregl.Map | null = null;
  private finishInitialization: (() => void) | null = null;
  private initialized = false;
  private basemapSourceId = "";
  private readonly basemapErrorListeners = new Set<() => void>();

  initialize(container: HTMLElement, config: SpatialSceneConfig): Promise<void> {
    this.initialized = false;
    this.basemapSourceId = config.basemapSourceId;
    const map = new maplibregl.Map({
      container,
      center: config.initialView.center,
      zoom: config.initialView.zoom,
      minZoom: REGIONAL_CAMERA_CONSTRAINTS.mapLibre.minimumZoom,
      maxZoom: REGIONAL_CAMERA_CONSTRAINTS.mapLibre.maximumZoom,
      maxBounds: REGIONAL_CAMERA_CONSTRAINTS.bounds,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-left");
    // Scoping to basemapSourceId keeps benign per-tile/abort noise for other
    // sources (backend GeoJSON layers report their own status separately) out
    // of the basemap-error signal.
    map.on("error", (e: maplibregl.ErrorEvent) => {
      if ("sourceId" in e && e.sourceId === this.basemapSourceId) {
        this.basemapErrorListeners.forEach((listener) => listener());
      }
    });
    this.map = map;
    return new Promise<void>((resolve) => {
      let finished = false;
      const finish = () => {
        if (finished) return;
        finished = true;
        map.off("style.load", finish);
        if (this.finishInitialization === finish) this.finishInitialization = null;
        this.initialized = true;
        resolve();
      };
      this.finishInitialization = finish;

      // Register readiness before style initialization begins. Passing the
      // style into the constructor races Firefox: style.load can occur before
      // our listener exists, while probing isStyleLoaded() that early can
      // itself warn that no style has been added. Explicit setStyle() makes
      // the event ordering deterministic across engines.
      map.on("style.load", finish);
      map.setStyle(config.basemapStyle);
    });
  }

  destroy(): void {
    this.finishInitialization?.();
    this.finishInitialization = null;
    this.initialized = false;

    const map = this.map;
    this.map = null;
    if (map) {
      try {
        map.remove();
      } catch (error) {
        // React StrictMode deliberately mounts and immediately tears down once in
        // development. Firefox can enter MapLibre's remove() before its WebGL
        // painter exists; MapLibre then throws while dereferencing painter.destroy.
        // That is a teardown-only race, not an initialized-runtime failure.
        const message = error instanceof Error ? error.message : String(error);
        const prePainterTeardown =
          error instanceof TypeError &&
          /painter/i.test(message) &&
          /(undefined|destroy)/i.test(message);
        if (!prePainterTeardown) throw error;
      }
    }
    this.basemapErrorListeners.clear();
  }

  setView(view: CameraView, options?: { animate?: boolean; speed?: number }): void {
    if (!this.map) return;
    if (options?.animate === false) {
      this.map.jumpTo({ center: view.center, zoom: view.zoom });
    } else {
      this.map.flyTo({ center: view.center, zoom: view.zoom, speed: options?.speed ?? 1.2 });
    }
  }

  getView(): CameraView {
    if (!this.map) return { center: [0, 0], zoom: 0 };
    const center = this.map.getCenter();
    return { center: [center.lng, center.lat], zoom: this.map.getZoom() };
  }

  resize(): void {
    if (!this.initialized) return;
    this.map?.resize();
  }

  onBasemapError(listener: () => void): Unsubscribe {
    this.basemapErrorListeners.add(listener);
    return () => this.basemapErrorListeners.delete(listener);
  }

  /**
   * MapLibreRuntime-specific escape hatch, not part of SpatialRuntime. Lets
   * existing layer/marker code in SpatialIntelligence.tsx keep operating on
   * the raw maplibregl.Map until it moves onto a generic layer adapter
   * (Phase 3, alongside PMTiles delivery).
   */
  getMapLibreInstance(): maplibregl.Map | null {
    return this.map;
  }
}

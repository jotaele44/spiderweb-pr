import maplibregl from "maplibre-gl";
import type { CameraView, SpatialRuntime, SpatialSceneConfig, Unsubscribe } from "./SpatialRuntime";

export class MapLibreRuntime implements SpatialRuntime {
  private map: maplibregl.Map | null = null;
  private basemapSourceId = "";
  private readonly basemapErrorListeners = new Set<() => void>();

  initialize(container: HTMLElement, config: SpatialSceneConfig): Promise<void> {
    this.basemapSourceId = config.basemapSourceId;
    const map = new maplibregl.Map({
      container,
      style: config.basemapStyle,
      center: config.initialView.center,
      zoom: config.initialView.zoom,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-left");
    // Scoping to basemapSourceId keeps benign per-tile/abort noise for other
    // sources (backend GeoJSON layers report their own status separately) out
    // of the basemap-error signal.
    map.on("error", (e: { sourceId?: string }) => {
      if (e.sourceId === this.basemapSourceId) {
        this.basemapErrorListeners.forEach((listener) => listener());
      }
    });
    this.map = map;
    return Promise.resolve();
  }

  destroy(): void {
    this.map?.remove();
    this.map = null;
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

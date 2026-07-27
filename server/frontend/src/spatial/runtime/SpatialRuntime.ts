import type maplibregl from "maplibre-gl";

export interface CameraView {
  center: [number, number];
  zoom: number;
}

export interface SpatialSceneConfig {
  basemapStyle: maplibregl.StyleSpecification;
  /** Source id within basemapStyle used to scope onBasemapError to base-map tile failures. */
  basemapSourceId: string;
  initialView: CameraView;
}

export type Unsubscribe = () => void;

/**
 * Minimal lifecycle contract shared by map runtimes (MapLibre today, a future
 * regional Cesium mode later). Deliberately narrow: only what
 * SpatialIntelligence.tsx actually uses today. Layer/selection APIs are
 * added once a second runtime implementation needs a shared contract for
 * them.
 */
export interface SpatialRuntime {
  initialize(container: HTMLElement, config: SpatialSceneConfig): Promise<void>;
  destroy(): void;
  setView(view: CameraView, options?: { animate?: boolean; speed?: number }): void;
  getView(): CameraView;
  resize(): void;
  onBasemapError(listener: () => void): Unsubscribe;
}

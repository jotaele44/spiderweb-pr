import type { GeoJSON } from "geojson";
import type { CameraView } from "./SpatialRuntime";

export type SpatialRendererId = "maplibre" | "cesium" | "apple-mapkit";

export interface SpatialCapabilitySet {
  geoJsonPolygon: boolean;
  geoJsonCircle: boolean;
  vectorTilePolygon: boolean;
  investigationMarker: boolean;
  camera: boolean;
  popup: boolean;
  featureSelection: boolean;
}

export interface PolygonRenderStyle {
  fillOpacity: number;
  fillColor: string;
  lineColor: string;
  lineWidth?: number;
  lineOpacity?: number;
}

export interface CircleRenderStyle {
  color: string;
  radius: number;
  opacity?: number;
  strokeColor?: string;
  strokeWidth?: number;
}

export interface SpatialLayerHandle {
  remove(): void;
}

export interface GeoJsonPolygonLayerSpec {
  id: string;
  data: GeoJSON;
  style: PolygonRenderStyle;
}

export interface GeoJsonCircleLayerSpec {
  id: string;
  data: GeoJSON;
  style: CircleRenderStyle;
}

export interface VectorTilePolygonLayerSpec {
  id: string;
  tiles: string[];
  sourceLayer: string;
  minZoom: number;
  maxZoom: number;
  style: PolygonRenderStyle;
  onError?: () => void;
}

export interface SpatialLayerAdapter {
  readonly capabilities: Pick<
    SpatialCapabilitySet,
    "geoJsonPolygon" | "geoJsonCircle" | "vectorTilePolygon"
  >;
  addGeoJsonPolygonLayer(spec: GeoJsonPolygonLayerSpec): Promise<SpatialLayerHandle>;
  addGeoJsonCircleLayer(spec: GeoJsonCircleLayerSpec): Promise<SpatialLayerHandle>;
  addVectorTilePolygonLayer(spec: VectorTilePolygonLayerSpec): Promise<SpatialLayerHandle>;
}

export type SpatialMarkerTone = "primary" | "warning" | "alert";

export interface SpatialMarkerSpec {
  coordinate: [number, number];
  label: string;
  sizePx: number;
  tone: SpatialMarkerTone;
  onActivate(): void;
}

export interface SpatialMarkerHandle {
  remove(): void;
}

export interface SpatialMarkerAdapter {
  readonly supported: boolean;
  addMarker(spec: SpatialMarkerSpec): SpatialMarkerHandle;
}

export interface SpatialCameraAdapter {
  readonly supported: boolean;
  setView(view: CameraView, options?: { animate?: boolean; speed?: number }): void;
  getView(): CameraView;
  resize(): void;
}

export interface SpatialAdapters {
  readonly renderer: SpatialRendererId;
  readonly capabilities: SpatialCapabilitySet;
  readonly layer: SpatialLayerAdapter;
  readonly marker: SpatialMarkerAdapter;
  readonly camera: SpatialCameraAdapter;
}

export class UnsupportedSpatialCapabilityError extends Error {
  constructor(renderer: SpatialRendererId, capability: keyof SpatialCapabilitySet) {
    super(`${renderer} does not support spatial capability: ${capability}`);
    this.name = "UnsupportedSpatialCapabilityError";
  }
}

export function assertFiniteWgs84Coordinate(coordinate: [number, number]): void {
  const [lng, lat] = coordinate;
  if (!Number.isFinite(lng) || !Number.isFinite(lat)) {
    throw new Error("spatial coordinate must be finite");
  }
  if (lng < -180 || lng > 180 || lat < -90 || lat > 90) {
    throw new Error("spatial coordinate is outside WGS84 bounds");
  }
}

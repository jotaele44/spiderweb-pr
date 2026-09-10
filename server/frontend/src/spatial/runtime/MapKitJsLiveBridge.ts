import type { GeoJSON, Geometry, Polygon, MultiPolygon } from "geojson";
import type { ExternalRenderMapType } from "./ExternalRenderProvider";
import type { AppleMapHandle, AppleMapKitFactory } from "./AppleMapKitRuntime";
import type { AppleOverlayBridge } from "./AppleSpatialAdapters";
import { UnsupportedSpatialCapabilityError, assertFiniteWgs84Coordinate, type GeoJsonPolygonLayerSpec, type SpatialLayerHandle, type SpatialMarkerHandle, type SpatialMarkerSpec } from "./SpatialAdapters";

interface MapKitCoordinateLike {
  latitude: number;
  longitude: number;
}

interface MapKitEventTargetLike {
  addEventListener(type: string, listener: () => void): boolean;
  removeEventListener?(type: string, listener: () => void): boolean;
}

interface MapKitMapLike {
  center: MapKitCoordinateLike;
  cameraDistance: number;
  mapType: string;
  addOverlay(overlay: object): object | null;
  removeOverlay(overlay: object): object;
  addAnnotation(annotation: object): object | null;
  removeAnnotation(annotation: object): object;
  destroy?(): void;
}

interface MapKitNamespaceLike {
  init(options: { authorizationCallback: (done: (token: string) => void) => void }): void;
  Map: new (container: HTMLElement, options: { mapType: string; center: MapKitCoordinateLike; cameraDistance: number }) => MapKitMapLike;
  Coordinate: new (latitude: number, longitude: number) => MapKitCoordinateLike;
  Style: new (options: {
    fillColor?: string;
    fillOpacity?: number;
    strokeColor?: string;
    strokeOpacity?: number;
    lineWidth?: number;
    lineJoin?: string;
  }) => object;
  PolygonOverlay: new (points: MapKitCoordinateLike[] | MapKitCoordinateLike[][], options: { style: object }) => object;
  Annotation: new (
    coordinate: MapKitCoordinateLike,
    factory: () => HTMLElement,
    options?: { title?: string; calloutEnabled?: boolean },
  ) => MapKitEventTargetLike;
}

export type MapKitJsAuthorizationProvider = (done: (token: string) => void) => void;

function toMapType(mapType: ExternalRenderMapType): "standard" | "satellite" | "hybrid" {
  switch (mapType) {
    case "standard": return "standard";
    case "satellite": return "satellite";
    case "hybrid": return "hybrid";
  }
}

/**
 * Creates the documented MapKit JS runtime factory without embedding or
 * retrieving credentials. Authorization is supplied by the caller only at the
 * final integration stage; tests provide a fake callback and namespace.
 */
export function createMapKitJsFactory(
  mapkit: MapKitNamespaceLike,
  authorizationProvider: MapKitJsAuthorizationProvider,
  onMapCreated?: (map: MapKitMapLike) => void,
): AppleMapKitFactory {
  let initialized = false;
  return {
    async create(container, options): Promise<AppleMapHandle> {
      if (!initialized) {
        mapkit.init({ authorizationCallback: authorizationProvider });
        initialized = true;
      }
      assertFiniteWgs84Coordinate(options.initialView.center);
      const [lng, lat] = options.initialView.center;
      const center = new mapkit.Coordinate(lat, lng);
      const map = new mapkit.Map(container, {
        mapType: toMapType(options.mapType),
        center,
        cameraDistance: options.initialView.cameraDistanceMeters,
      });
      onMapCreated?.(map);
      return {
        setCenter(next, _animated) {
          assertFiniteWgs84Coordinate(next);
          map.center = new mapkit.Coordinate(next[1], next[0]);
        },
        setCameraDistanceMeters(distance, _animated) {
          if (!Number.isFinite(distance) || distance < 0) throw new Error("Apple camera distance must be finite and non-negative");
          map.cameraDistance = distance;
        },
        setMapType(nextType) {
          map.mapType = toMapType(nextType);
        },
        getCameraView() {
          return {
            center: [map.center.longitude, map.center.latitude],
            cameraDistanceMeters: map.cameraDistance,
          };
        },
        destroy() {
          map.destroy?.();
        },
      };
    },
  };
}

function polygonParts(geometry: Geometry): number[][][][] {
  if (geometry.type === "Polygon") return [(geometry as Polygon).coordinates];
  if (geometry.type === "MultiPolygon") return (geometry as MultiPolygon).coordinates;
  return [];
}

function polygonOverlays(
  mapkit: MapKitNamespaceLike,
  data: GeoJSON,
  spec: GeoJsonPolygonLayerSpec,
): object[] {
  if (data.type !== "FeatureCollection") throw new Error("polygon layer requires a GeoJSON FeatureCollection");
  const style = new mapkit.Style({
    fillColor: spec.style.fillColor,
    fillOpacity: spec.style.fillOpacity,
    strokeColor: spec.style.lineColor,
    strokeOpacity: spec.style.lineOpacity ?? 0.6,
    lineWidth: spec.style.lineWidth ?? 0.8,
    lineJoin: "round",
  });
  const overlays: object[] = [];
  for (const feature of data.features) {
    if (!feature.geometry) continue;
    for (const polygon of polygonParts(feature.geometry)) {
      const rings = polygon.map((ring) => ring.map(([lng, lat]) => {
        assertFiniteWgs84Coordinate([lng, lat]);
        return new mapkit.Coordinate(lat, lng);
      }));
      if (rings.length > 0) overlays.push(new mapkit.PolygonOverlay(rings, { style }));
    }
  }
  return overlays;
}

function markerElement(spec: SpatialMarkerSpec): HTMLElement {
  if (!Number.isFinite(spec.sizePx) || spec.sizePx <= 0) throw new Error("marker size must be positive");
  const el = document.createElement("button");
  el.type = "button";
  el.className = "map-marker";
  const tone = spec.tone === "alert" ? "var(--alert)" : spec.tone === "warning" ? "var(--warn)" : "var(--t1)";
  Object.assign(el.style, {
    width: `${spec.sizePx}px`,
    height: `${spec.sizePx}px`,
    borderRadius: "999px",
    border: "2px solid var(--surface-2)",
    background: tone,
    boxShadow: "0 0 0 1px var(--ink)",
  });
  el.title = spec.label;
  el.setAttribute("aria-label", spec.label);
  return el;
}

/**
 * Credential-free semantic bridge over a live MapKit JS map instance.
 * GeoJSON polygon and investigation-marker semantics are implemented. The
 * high-volume GeoJSON point-circle path remains explicitly unsupported until
 * a native/performance-equivalent implementation is proven.
 */
export function createMapKitJsOverlayBridge(
  mapkit: MapKitNamespaceLike,
  map: MapKitMapLike,
): AppleOverlayBridge {
  return {
    capabilities: {
      geoJsonPolygon: true,
      geoJsonCircle: false,
      investigationMarker: true,
    },
    async addGeoJsonPolygonLayer(spec): Promise<SpatialLayerHandle> {
      const overlays = polygonOverlays(mapkit, spec.data, spec);
      overlays.forEach((overlay) => map.addOverlay(overlay));
      let removed = false;
      return {
        remove() {
          if (removed) return;
          removed = true;
          overlays.forEach((overlay) => map.removeOverlay(overlay));
        },
      };
    },
    async addGeoJsonCircleLayer() {
      throw new UnsupportedSpatialCapabilityError("apple-mapkit", "geoJsonCircle");
    },
    addMarker(spec): SpatialMarkerHandle {
      assertFiniteWgs84Coordinate(spec.coordinate);
      const coordinate = new mapkit.Coordinate(spec.coordinate[1], spec.coordinate[0]);
      const annotation = new mapkit.Annotation(coordinate, () => markerElement(spec), {
        title: spec.label,
        calloutEnabled: false,
      });
      const onSelect = () => spec.onActivate();
      annotation.addEventListener("select", onSelect);
      map.addAnnotation(annotation as object);
      let removed = false;
      return {
        remove() {
          if (removed) return;
          removed = true;
          annotation.removeEventListener?.("select", onSelect);
          map.removeAnnotation(annotation as object);
        },
      };
    },
  };
}

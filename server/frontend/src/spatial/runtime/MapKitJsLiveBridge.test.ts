import { describe, expect, it, vi } from "vitest";
import { createMapKitJsFactory, createMapKitJsOverlayBridge } from "./MapKitJsLiveBridge";

function fakeMapKit() {
  class Coordinate {
    constructor(public latitude: number, public longitude: number) {}
  }
  class Style {
    constructor(public options: object) {}
  }
  class PolygonOverlay {
    constructor(public points: Coordinate[] | Coordinate[][], public options: object) {}
  }
  class Annotation {
    listeners = new Map<string, Set<() => void>>();
    constructor(public coordinate: Coordinate, public factory: () => HTMLElement, public options: object) {}
    addEventListener(type: string, listener: () => void) {
      const listeners = this.listeners.get(type) ?? new Set();
      listeners.add(listener);
      this.listeners.set(type, listeners);
      return true;
    }
    removeEventListener(type: string, listener: () => void) {
      this.listeners.get(type)?.delete(listener);
      return true;
    }
    emit(type: string) { this.listeners.get(type)?.forEach((listener) => listener()); }
  }
  class MapObject {
    center: Coordinate;
    cameraDistance: number;
    mapType: string;
    overlays: object[] = [];
    annotations: object[] = [];
    destroyed = false;
    constructor(_container: HTMLElement, options: { mapType: string; center: Coordinate; cameraDistance: number }) {
      this.center = options.center;
      this.cameraDistance = options.cameraDistance;
      this.mapType = options.mapType;
    }
    addOverlay(overlay: object) { this.overlays.push(overlay); return overlay; }
    removeOverlay(overlay: object) { this.overlays = this.overlays.filter((item) => item !== overlay); return overlay; }
    addAnnotation(annotation: object) { this.annotations.push(annotation); return annotation; }
    removeAnnotation(annotation: object) { this.annotations = this.annotations.filter((item) => item !== annotation); return annotation; }
    destroy() { this.destroyed = true; }
  }
  const init = vi.fn();
  return { namespace: { init, Map: MapObject, Coordinate, Style, PolygonOverlay, Annotation }, init, MapObject, Annotation, PolygonOverlay };
}

describe("MapKit JS live bridge boundary", () => {
  it("initializes with injected authorization and supports standard/satellite/hybrid without embedded credentials", async () => {
    const fake = fakeMapKit();
    const authorization = vi.fn((_done: (token: string) => void) => undefined);
    let map: InstanceType<typeof fake.MapObject> | null = null;
    const factory = createMapKitJsFactory(fake.namespace, authorization, (created) => { map = created as InstanceType<typeof fake.MapObject>; });
    const host = document.createElement("div");
    const handle = await factory.create(host, {
      mapType: "standard",
      initialView: { center: [-66.4, 18.2], cameraDistanceMeters: 120000 },
    });

    expect(fake.init).toHaveBeenCalledOnce();
    expect(map?.mapType).toBe("standard");
    handle.setMapType("satellite");
    expect(map?.mapType).toBe("satellite");
    handle.setMapType("hybrid");
    expect(map?.mapType).toBe("hybrid");
    handle.destroy();
    expect(map?.destroyed).toBe(true);
  });

  it("round-trips provider-native center and camera distance without claiming canonical zoom equivalence", async () => {
    const fake = fakeMapKit();
    const factory = createMapKitJsFactory(fake.namespace, () => undefined);
    const handle = await factory.create(document.createElement("div"), {
      mapType: "satellite",
      initialView: { center: [-66.05, 18.45], cameraDistanceMeters: 80000 },
    });
    expect(handle.getCameraView()).toEqual({ center: [-66.05, 18.45], cameraDistanceMeters: 80000 });
    handle.setCenter([-65.9, 18.1], false);
    handle.setCameraDistanceMeters(40000, false);
    expect(handle.getCameraView()).toEqual({ center: [-65.9, 18.1], cameraDistanceMeters: 40000 });
  });

  it("renders Polygon and MultiPolygon GeoJSON with exact semantic style values", async () => {
    const fake = fakeMapKit();
    const map = new fake.MapObject(document.createElement("div"), { mapType: "hybrid", center: new fake.namespace.Coordinate(18, -66), cameraDistance: 1000 });
    const bridge = createMapKitJsOverlayBridge(fake.namespace, map);
    const handle = await bridge.addGeoJsonPolygonLayer({
      id: "geo-municipios",
      data: {
        type: "FeatureCollection",
        features: [
          { type: "Feature", properties: { id: 1 }, geometry: { type: "Polygon", coordinates: [[[-66.1, 18.1], [-66.0, 18.1], [-66.0, 18.2], [-66.1, 18.1]]] } },
          { type: "Feature", properties: { id: 2 }, geometry: { type: "MultiPolygon", coordinates: [[[[-66.3, 18.3], [-66.2, 18.3], [-66.2, 18.4], [-66.3, 18.3]]]] } },
        ],
      },
      style: { fillColor: "#4dc4d6", fillOpacity: 0.08, lineColor: "#4dc4d6", lineWidth: 0.8, lineOpacity: 0.6 },
    });
    expect(map.overlays).toHaveLength(2);
    const first = map.overlays[0] as InstanceType<typeof fake.PolygonOverlay>;
    expect(first.options).toMatchObject({ style: expect.objectContaining({ options: expect.objectContaining({ fillColor: "#4dc4d6", fillOpacity: 0.08, strokeColor: "#4dc4d6", strokeOpacity: 0.6, lineWidth: 0.8 }) }) });
    handle.remove();
    handle.remove();
    expect(map.overlays).toHaveLength(0);
  });

  it("preserves marker accessibility, activation, and cleanup", () => {
    const fake = fakeMapKit();
    const map = new fake.MapObject(document.createElement("div"), { mapType: "standard", center: new fake.namespace.Coordinate(18, -66), cameraDistance: 1000 });
    const bridge = createMapKitJsOverlayBridge(fake.namespace, map);
    const activate = vi.fn();
    const handle = bridge.addMarker({ coordinate: [-66.1, 18.2], label: "Site A · $10 · no anomaly", sizePx: 18, tone: "warning", onActivate: activate });
    expect(map.annotations).toHaveLength(1);
    const annotation = map.annotations[0] as InstanceType<typeof fake.Annotation>;
    const element = annotation.factory();
    expect(element.getAttribute("aria-label")).toBe("Site A · $10 · no anomaly");
    expect(element.style.width).toBe("18px");
    annotation.emit("select");
    expect(activate).toHaveBeenCalledOnce();
    handle.remove();
    annotation.emit("select");
    expect(activate).toHaveBeenCalledOnce();
    expect(map.annotations).toHaveLength(0);
  });
});

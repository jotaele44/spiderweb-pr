import { useEffect, useRef, useState } from "react";
import type maplibregl from "maplibre-gl";
import type { SpatialRuntime, SpatialSceneConfig } from "./SpatialRuntime";
import { createSpatialRuntime } from "./RuntimeFactory";

/**
 * Wires a SpatialRuntime's lifecycle to a host element. `mapRef` exposes the
 * raw maplibregl.Map instance as a transitional escape hatch for existing
 * layer/marker code that hasn't moved onto a generic layer adapter yet — see
 * MapLibreRuntime.getMapLibreInstance.
 */
export function useSpatialRuntime(config: SpatialSceneConfig) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const runtimeRef = useRef<SpatialRuntime | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [ready, setReady] = useState(false);
  const [tilesFailed, setTilesFailed] = useState(false);

  useEffect(() => {
    if (!hostRef.current || runtimeRef.current) return;
    const runtime = createSpatialRuntime("maplibre");
    let cancelled = false;
    const unsubscribeError = runtime.onBasemapError(() => setTilesFailed(true));

    void runtime.initialize(hostRef.current, config).then(() => {
      if (cancelled) return;
      runtimeRef.current = runtime;
      mapRef.current = runtime.getMapLibreInstance();
      setReady(true);
    });

    return () => {
      cancelled = true;
      unsubscribeError();
      runtime.destroy();
      runtimeRef.current = null;
      mapRef.current = null;
      setReady(false);
    };
    // config is a stable module-level constant (DEFAULT_REGIONAL_SCENE_CONFIG),
    // so this stays a mount-once effect, matching the original map-init effect.
  }, [config]);

  return { hostRef, mapRef, runtimeRef, ready, tilesFailed, setTilesFailed };
}

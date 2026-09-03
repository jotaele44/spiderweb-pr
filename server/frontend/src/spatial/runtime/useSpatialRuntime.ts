import { useEffect, useRef, useState } from "react";
import type * as maplibregl from "maplibre-gl";
import type { SpatialRuntime, SpatialSceneConfig, Unsubscribe } from "./SpatialRuntime";
import { createSpatialRuntime, createCesiumRuntime, type SpatialRuntimeMode } from "./RuntimeFactory";
import type { MapLibreRuntime } from "./MapLibreRuntime";

/**
 * Wires a SpatialRuntime's lifecycle to a host element. `mapRef` exposes the
 * raw maplibregl.Map instance as a transitional escape hatch for existing
 * layer/marker code that hasn't moved onto a generic layer adapter yet — see
 * MapLibreRuntime.getMapLibreInstance. It's null whenever the active runtime
 * is Cesium.
 *
 * `mode` requests "maplibre" or "cesium"; `activeMode` reports what's
 * actually running — they differ when Cesium fails to initialize (no WebGL,
 * etc.) and this hook falls back to MapLibre, surfacing why via
 * `fallbackReason` so the caller can show a notice instead of failing silently.
 */
export function useSpatialRuntime(
  config: SpatialSceneConfig,
  mode: SpatialRuntimeMode = "maplibre",
) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const runtimeRef = useRef<SpatialRuntime | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [ready, setReady] = useState(false);
  const [tilesFailed, setTilesFailed] = useState(false);
  const [activeMode, setActiveMode] = useState<SpatialRuntimeMode>(mode);
  const [fallbackReason, setFallbackReason] = useState<string | null>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    let cancelled = false;
    // eslint-disable-next-line @typescript-eslint/no-empty-function
    let unsubscribeError: Unsubscribe = () => {};

    const bootMapLibre = async (): Promise<{ runtime: SpatialRuntime; mapLibre: MapLibreRuntime }> => {
      const runtime = createSpatialRuntime("maplibre");
      await runtime.initialize(host, config);
      return { runtime, mapLibre: runtime };
    };

    const boot = async () => {
      let resolvedMode: SpatialRuntimeMode = mode;
      let fallback: string | null = null;
      let runtime: SpatialRuntime;
      let mapLibre: MapLibreRuntime | null = null;

      if (mode === "cesium") {
        const cesiumRuntime = await createCesiumRuntime();
        try {
          await cesiumRuntime.initialize(host, config);
          runtime = cesiumRuntime;
        } catch (err) {
          cesiumRuntime.destroy();
          console.error("Cesium runtime failed to initialize — falling back to MapLibre:", err);
          const fallbackBoot = await bootMapLibre();
          runtime = fallbackBoot.runtime;
          mapLibre = fallbackBoot.mapLibre;
          resolvedMode = "maplibre";
          fallback = err instanceof Error ? err.message : "3D runtime unavailable";
        }
      } else {
        const mapLibreBoot = await bootMapLibre();
        runtime = mapLibreBoot.runtime;
        mapLibre = mapLibreBoot.mapLibre;
      }

      if (cancelled) {
        runtime.destroy();
        return;
      }
      unsubscribeError = runtime.onBasemapError(() => setTilesFailed(true));
      runtimeRef.current = runtime;
      mapRef.current = mapLibre?.getMapLibreInstance() ?? null;
      setActiveMode(resolvedMode);
      setFallbackReason(fallback);
      setReady(true);
    };

    void boot();

    return () => {
      cancelled = true;
      unsubscribeError();
      runtimeRef.current?.destroy();
      runtimeRef.current = null;
      mapRef.current = null;
      setReady(false);
    };
    // config is a stable module-level constant (DEFAULT_REGIONAL_SCENE_CONFIG);
    // mode changes intentionally tear down and reboot the runtime (2D/3D switch).
  }, [config, mode]);

  // Container-size tracking, independent of the boot effect above. MapLibre's
  // canvas auto-fills its container via its own internal ResizeObserver;
  // Cesium's does not — it only sizes its canvas at construction and on
  // window resize, so a layout shift that doesn't change the window size
  // (e.g. the header row growing when the mode-toggle label changes) leaves
  // its canvas stuck at a stale size. One ResizeObserver here covers both
  // runtimes generically rather than hand-wiring every layout-shifting state
  // value into a resize effect.
  useEffect(() => {
    const host = hostRef.current;
    if (!host || typeof ResizeObserver === "undefined") return;
    let width = host.clientWidth;
    let height = host.clientHeight;
    let frame: number | null = null;
    const observer = new ResizeObserver(([entry]) => {
      if (!entry) return;
      const nextWidth = Math.round(entry.contentRect.width);
      const nextHeight = Math.round(entry.contentRect.height);
      if (nextWidth === width && nextHeight === height) return;
      width = nextWidth;
      height = nextHeight;
      if (frame !== null) window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(() => {
        frame = null;
        runtimeRef.current?.resize();
      });
    });
    observer.observe(host);
    return () => {
      observer.disconnect();
      if (frame !== null) window.cancelAnimationFrame(frame);
    };
  }, []);

  return {
    hostRef,
    mapRef,
    runtimeRef,
    ready,
    tilesFailed,
    setTilesFailed,
    activeMode,
    fallbackReason,
  };
}

import { useEffect, useRef, useState } from "react";
import type { SpatialRuntime, SpatialSceneConfig, Unsubscribe } from "./SpatialRuntime";
import { createSpatialRuntime, createCesiumRuntime, type SpatialRuntimeMode } from "./RuntimeFactory";
import { createMapLibreSpatialAdapters } from "./MapLibreSpatialAdapters";
import { createCameraOnlySpatialAdapters } from "./LimitedSpatialAdapters";
import type { SpatialAdapters, SpatialCapabilitySet } from "./SpatialAdapters";

/**
 * Wires a SpatialRuntime's lifecycle to a host element and exposes only the
 * semantic adapter contract to domain modules. Raw MapLibre/Cesium objects stay
 * inside renderer infrastructure and cannot leak into SpatialIntelligence.
 *
 * `mode` requests "maplibre" or "cesium"; `activeMode` reports what's
 * actually running — they differ when Cesium fails to initialize and this
 * hook falls back to MapLibre while surfacing the reason.
 */
export function useSpatialRuntime(
  config: SpatialSceneConfig,
  mode: SpatialRuntimeMode = "maplibre",
) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const runtimeRef = useRef<SpatialRuntime | null>(null);
  const adaptersRef = useRef<SpatialAdapters | null>(null);
  const [capabilities, setCapabilities] = useState<SpatialCapabilitySet | null>(null);
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

    const bootMapLibre = async (): Promise<{ runtime: SpatialRuntime; adapters: SpatialAdapters }> => {
      const mapLibre = createSpatialRuntime("maplibre");
      await mapLibre.initialize(host, config);
      const map = mapLibre.getMapLibreInstance();
      if (!map) {
        mapLibre.destroy();
        throw new Error("MapLibre initialized without a map instance");
      }
      return { runtime: mapLibre, adapters: createMapLibreSpatialAdapters(map, mapLibre) };
    };

    const boot = async () => {
      let resolvedMode: SpatialRuntimeMode = mode;
      let fallback: string | null = null;
      let runtime: SpatialRuntime;
      let adapters: SpatialAdapters;

      if (mode === "cesium") {
        const cesiumRuntime = await createCesiumRuntime();
        try {
          await cesiumRuntime.initialize(host, config);
          runtime = cesiumRuntime;
          adapters = createCameraOnlySpatialAdapters("cesium", cesiumRuntime);
        } catch (err) {
          cesiumRuntime.destroy();
          console.error("Cesium runtime failed to initialize — falling back to MapLibre:", err);
          const fallbackBoot = await bootMapLibre();
          runtime = fallbackBoot.runtime;
          adapters = fallbackBoot.adapters;
          resolvedMode = "maplibre";
          fallback = err instanceof Error ? err.message : "3D runtime unavailable";
        }
      } else {
        const mapLibreBoot = await bootMapLibre();
        runtime = mapLibreBoot.runtime;
        adapters = mapLibreBoot.adapters;
      }

      if (cancelled) {
        runtime.destroy();
        return;
      }
      unsubscribeError = runtime.onBasemapError(() => setTilesFailed(true));
      runtimeRef.current = runtime;
      adaptersRef.current = adapters;
      setCapabilities({ ...adapters.capabilities });
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
      adaptersRef.current = null;
      setCapabilities(null);
      setReady(false);
    };
    // config is a stable module-level constant (DEFAULT_REGIONAL_SCENE_CONFIG);
    // mode changes intentionally tear down and reboot the runtime (2D/3D switch).
  }, [config, mode]);

  // Container-size tracking stays renderer-neutral and uses the runtime
  // lifecycle itself, never a raw renderer instance.
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
        adaptersRef.current?.camera.resize();
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
    adaptersRef,
    runtimeRef,
    capabilities,
    ready,
    tilesFailed,
    setTilesFailed,
    activeMode,
    fallbackReason,
  };
}

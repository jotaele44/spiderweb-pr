import { useEffect, useEffectEvent } from "react";
import type * as maplibregl from "maplibre-gl";
import { eriFootprintSchema, type EriDataset, type EriFootprint } from "./eriApi";
import {
  ERI_FOOTPRINT_LAYERS,
  ERI_FOOTPRINTS_ID,
  ERI_IMAGERY_ID,
  addEriFootprints,
  addEriImagery,
  removeEriFootprints,
  removeEriImagery,
  setEriImageryOpacity,
  setSelectedFootprint,
} from "./eriLayers";

export type ImageryStatus = "off" | "loading" | "loaded" | "error";

/**
 * Binds the selected ERI flight to the MapLibre map: the raster imagery layer,
 * the footprint outlines, and click-to-identify on a footprint.
 *
 * `ready` is in every effect's deps for the same reason as the marker effect
 * in SpatialIntelligence: a 2D/3D switch swaps the map behind the same ref.
 */
export function useEriImagery(opts: {
  mapRef: React.MutableRefObject<maplibregl.Map | null>;
  ready: boolean;
  dataset: EriDataset | null;
  attribution: string;
  opacity: number;
  showFootprints: boolean;
  selectedName: string | null;
  /** True while another map tool owns clicks (measure, buffer, …). */
  clickSuppressedRef: React.MutableRefObject<boolean>;
  onStatus: (status: ImageryStatus) => void;
  onFootprintStatus: (status: ImageryStatus) => void;
  onIdentify: (footprint: EriFootprint | null) => void;
}) {
  const { mapRef, ready, dataset, attribution, opacity, showFootprints, selectedName, clickSuppressedRef } = opts;
  const onStatus = useEffectEvent(opts.onStatus);
  const onFootprintStatus = useEffectEvent(opts.onFootprintStatus);
  const onIdentify = useEffectEvent(opts.onIdentify);
  const initialOpacity = useEffectEvent(() => opacity);

  // Imagery raster layer.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !dataset) {
      onStatus("off");
      return;
    }
    onStatus("loading");
    const onData = (event: maplibregl.MapSourceDataEvent) => {
      if (event.sourceId === ERI_IMAGERY_ID && map.isSourceLoaded(ERI_IMAGERY_ID)) onStatus("loaded");
    };
    const onError = (event: maplibregl.ErrorEvent) => {
      if ("sourceId" in event && event.sourceId === ERI_IMAGERY_ID) onStatus("error");
    };
    map.on("sourcedata", onData);
    map.on("error", onError);
    addEriImagery(map, dataset, initialOpacity(), attribution);
    return () => {
      map.off("sourcedata", onData);
      map.off("error", onError);
      removeEriImagery(map);
    };
  }, [mapRef, ready, dataset, attribution]);

  useEffect(() => {
    const map = mapRef.current;
    if (map && ready && dataset) setEriImageryOpacity(map, opacity);
  }, [mapRef, ready, dataset, opacity]);

  // Footprint outlines + identify.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !dataset || !showFootprints) {
      onFootprintStatus("off");
      return;
    }
    onFootprintStatus("loading");
    const onData = (event: maplibregl.MapSourceDataEvent) => {
      if (event.sourceId === ERI_FOOTPRINTS_ID && map.isSourceLoaded(ERI_FOOTPRINTS_ID)) onFootprintStatus("loaded");
    };
    const onError = (event: maplibregl.ErrorEvent) => {
      if ("sourceId" in event && event.sourceId === ERI_FOOTPRINTS_ID) onFootprintStatus("error");
    };
    const onClick = (event: maplibregl.MapLayerMouseEvent) => {
      if (clickSuppressedRef.current) return;
      const parsed = eriFootprintSchema.safeParse(event.features?.[0]?.properties);
      onIdentify(parsed.success ? parsed.data : null);
    };
    const pointer = () => {
      if (!clickSuppressedRef.current) map.getCanvas().style.cursor = "pointer";
    };
    const unpointer = () => {
      if (!clickSuppressedRef.current) map.getCanvas().style.cursor = "";
    };
    map.on("sourcedata", onData);
    map.on("error", onError);
    addEriFootprints(map, dataset);
    map.on("click", ERI_FOOTPRINT_LAYERS.fill, onClick);
    map.on("mouseenter", ERI_FOOTPRINT_LAYERS.fill, pointer);
    map.on("mouseleave", ERI_FOOTPRINT_LAYERS.fill, unpointer);
    return () => {
      map.off("sourcedata", onData);
      map.off("error", onError);
      map.off("click", ERI_FOOTPRINT_LAYERS.fill, onClick);
      map.off("mouseenter", ERI_FOOTPRINT_LAYERS.fill, pointer);
      map.off("mouseleave", ERI_FOOTPRINT_LAYERS.fill, unpointer);
      removeEriFootprints(map);
      onIdentify(null);
    };
  }, [mapRef, ready, dataset, showFootprints, clickSuppressedRef]);

  useEffect(() => {
    const map = mapRef.current;
    if (map && ready && dataset && showFootprints) setSelectedFootprint(map, selectedName);
  }, [mapRef, ready, dataset, showFootprints, selectedName]);
}

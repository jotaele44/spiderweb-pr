import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type * as maplibregl from "maplibre-gl";
import {
  datasetCenter,
  datasetContains,
  fetchEriCatalog,
  type EriDataset,
  type EriFootprint,
} from "./eriApi";
import { ERI_FOOTPRINTS_ID } from "./eriLayers";
import type { CatalogState, ImageryPanelProps } from "./ImageryPanel";
import { useEriImagery, type ImageryStatus } from "./useEriImagery";
import { formatViewHash, parseViewHash, type MapViewState } from "./viewHash";

/** Centre of the footprint nearest `from`, among those MapLibre has loaded. */
function nearestFootprintCenter(map: maplibregl.Map, from: maplibregl.LngLat): [number, number] | null {
  if (!map.getSource(ERI_FOOTPRINTS_ID)) return null;
  let best: [number, number] | null = null;
  let bestDistance = Infinity;
  for (const feature of map.querySourceFeatures(ERI_FOOTPRINTS_ID)) {
    if (feature.geometry.type !== "Polygon") continue;
    const ring = feature.geometry.coordinates[0];
    const lng = (ring[0][0] + ring[2][0]) / 2;
    const lat = (ring[0][1] + ring[2][1]) / 2;
    const distance = (lng - from.lng) ** 2 + (lat - from.lat) ** 2;
    if (distance < bestDistance) {
      bestDistance = distance;
      best = [lng, lat];
    }
  }
  return best;
}

/**
 * State for the imagery controls: the flight catalog, the selected flight and
 * its display options, the base-map toggle, and the shareable URL fragment.
 * SpatialIntelligence owns the map; this owns everything imagery-related.
 */
export function useImageryController(opts: {
  mapRef: React.MutableRefObject<maplibregl.Map | null>;
  /** True once the MapLibre map is usable (false in 3D mode). */
  ready: boolean;
  basemapLayerId: string;
  clickSuppressedRef: React.MutableRefObject<boolean>;
}) {
  const { mapRef, ready, basemapLayerId, clickSuppressedRef } = opts;
  const [initial] = useState<MapViewState>(() => parseViewHash(window.location.hash));
  const [catalogState, setCatalogState] = useState<CatalogState>({ status: "loading" });
  const [catalogAttempt, setCatalogAttempt] = useState(0);
  const [datasetId, setDatasetId] = useState<string | null>(initial.imagery ?? null);
  const [compareId, setCompareId] = useState<string | null>(initial.compare ?? null);
  const [opacity, setOpacity] = useState(initial.opacity ?? 1);
  const [showFootprints, setShowFootprints] = useState(initial.footprints ?? true);
  const [basemapVisible, setBasemapVisible] = useState(initial.basemap ?? true);
  const [imageryStatus, setImageryStatus] = useState<ImageryStatus>("off");
  const [footprintStatus, setFootprintStatus] = useState<ImageryStatus>("off");
  const [identified, setIdentified] = useState<EriFootprint | null>(null);
  const [zoom, setZoom] = useState<number | null>(null);
  const [linkCopied, setLinkCopied] = useState(false);
  const initialViewApplied = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    fetchEriCatalog(controller.signal)
      .then((catalog) => setCatalogState({ status: "ready", catalog }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setCatalogState({
          status: "error",
          message: error instanceof Error ? error.message : "request failed",
        });
      });
    return () => controller.abort();
  }, [catalogAttempt]);

  const datasets = useMemo(
    () => (catalogState.status === "ready" ? catalogState.catalog.datasets : []),
    [catalogState],
  );
  const attribution = catalogState.status === "ready" ? catalogState.catalog.attribution : "";
  const dataset: EriDataset | null = datasets.find((entry) => entry.id === datasetId) ?? null;
  const compareDataset: EriDataset | null =
    dataset && compareId !== dataset.id ? (datasets.find((entry) => entry.id === compareId) ?? null) : null;

  useEriImagery({
    mapRef,
    ready,
    dataset,
    attribution,
    opacity,
    showFootprints,
    selectedName: identified?.name ?? null,
    clickSuppressedRef,
    onStatus: setImageryStatus,
    onFootprintStatus: setFootprintStatus,
    onIdentify: setIdentified,
  });

  // A link's camera is applied once, to the first map that boots.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || initialViewApplied.current) return;
    initialViewApplied.current = true;
    if (initial.view) {
      map.jumpTo({ center: [initial.view.lng, initial.view.lat], zoom: initial.view.zoom });
    }
  }, [mapRef, ready, initial]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const onZoom = () => setZoom(map.getZoom());
    map.on("zoom", onZoom);
    onZoom();
    return () => {
      map.off("zoom", onZoom);
      setZoom(null);
    };
  }, [mapRef, ready]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !map.getLayer(basemapLayerId)) return;
    map.setLayoutProperty(basemapLayerId, "visibility", basemapVisible ? "visible" : "none");
  }, [mapRef, ready, basemapLayerId, basemapVisible]);

  // Keep the URL fragment describing the current view, so the address bar is
  // always a shareable link. replaceState: panning must not flood history.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const write = () => {
      // Until the catalog resolves the selected flight is unknown; writing now
      // would strip `eri=` from a link that was just opened.
      if (catalogState.status === "loading") return;
      const center = map.getCenter();
      const hash = formatViewHash(
        {
          view: { zoom: map.getZoom(), lat: center.lat, lng: center.lng },
          imagery: dataset?.id,
          opacity,
          compare: compareDataset?.id,
          footprints: showFootprints,
          basemap: basemapVisible,
        },
        window.location.hash,
      );
      window.history.replaceState(
        window.history.state,
        "",
        `${window.location.pathname}${window.location.search}${hash}`,
      );
    };
    map.on("moveend", write);
    write();
    return () => {
      map.off("moveend", write);
    };
  }, [mapRef, ready, dataset, compareDataset, opacity, showFootprints, basemapVisible, catalogState.status]);

  useEffect(() => {
    if (!linkCopied) return;
    const timer = window.setTimeout(() => setLinkCopied(false), 2000);
    return () => window.clearTimeout(timer);
  }, [linkCopied]);

  const onZoomToImagery = useCallback(() => {
    const map = mapRef.current;
    if (!map || !dataset) return;
    const center = map.getCenter();
    const zoomTarget = Math.max(dataset.min_zoom + 1, map.getZoom());
    const nearest = nearestFootprintCenter(map, center);
    const target: [number, number] =
      nearest ?? (datasetContains(dataset, center.lng, center.lat) ? [center.lng, center.lat] : datasetCenter(dataset));
    map.flyTo({ center: target, zoom: zoomTarget, speed: 1.4 });
  }, [mapRef, dataset]);

  const onCopyLink = useCallback(() => {
    void navigator.clipboard?.writeText(window.location.href).then(
      () => setLinkCopied(true),
      () => setLinkCopied(false),
    );
  }, []);

  const panelProps: ImageryPanelProps = {
    catalogState,
    onRetryCatalog: () => {
      setCatalogState({ status: "loading" });
      setCatalogAttempt((attempt) => attempt + 1);
    },
    datasetId: dataset?.id ?? null,
    onDataset: (id) => {
      setDatasetId(id);
      setIdentified(null);
      if (id === null || id === compareId) setCompareId(null);
    },
    opacity,
    onOpacity: setOpacity,
    showFootprints,
    onShowFootprints: setShowFootprints,
    compareId: compareDataset?.id ?? null,
    onCompare: setCompareId,
    basemapVisible,
    onBasemapVisible: setBasemapVisible,
    imageryStatus,
    footprintStatus,
    zoom,
    onZoomToImagery,
    identified,
    onClearIdentified: () => setIdentified(null),
    onCopyLink,
    linkCopied,
  };

  return { panelProps, dataset, compareDataset, attribution, opacity, basemapVisible };
}

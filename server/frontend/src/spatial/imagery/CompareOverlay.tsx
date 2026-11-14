import { useEffect, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import type { EriDataset } from "./eriApi";
import { addEriImagery, setEriImageryOpacity } from "./eriLayers";

/**
 * Swipe comparison: a second, non-interactive map stacked on the main one and
 * clipped to the right of a draggable divider. The main map keeps every
 * interaction (pan, zoom, tools, identify); this one only mirrors its camera
 * and draws the comparison flight, so there is no two-way sync to get wrong.
 */
export function CompareOverlay({
  mapRef,
  basemapStyle,
  basemapLayerId,
  basemapVisible,
  dataset,
  attribution,
  opacity,
  leftLabel,
}: {
  mapRef: React.MutableRefObject<maplibregl.Map | null>;
  basemapStyle: maplibregl.StyleSpecification;
  basemapLayerId: string;
  basemapVisible: boolean;
  dataset: EriDataset;
  attribution: string;
  opacity: number;
  leftLabel: string;
}) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const shellRef = useRef<HTMLDivElement | null>(null);
  const overlayRef = useRef<maplibregl.Map | null>(null);
  const [overlayReady, setOverlayReady] = useState(false);
  const [split, setSplit] = useState(50);

  // Boot the mirror map once and keep its camera locked to the main map.
  useEffect(() => {
    const main = mapRef.current;
    const host = hostRef.current;
    if (!main || !host) return;
    const overlay = new maplibregl.Map({
      container: host,
      style: basemapStyle,
      center: main.getCenter(),
      zoom: main.getZoom(),
      bearing: main.getBearing(),
      pitch: main.getPitch(),
      interactive: false,
      attributionControl: false,
    });
    overlayRef.current = overlay;
    const sync = () =>
      overlay.jumpTo({
        center: main.getCenter(),
        zoom: main.getZoom(),
        bearing: main.getBearing(),
        pitch: main.getPitch(),
      });
    const resize = () => overlay.resize();
    const loaded = () => setOverlayReady(true);
    overlay.on("load", loaded);
    main.on("move", sync);
    main.on("resize", resize);
    return () => {
      main.off("move", sync);
      main.off("resize", resize);
      overlay.off("load", loaded);
      overlayRef.current = null;
      setOverlayReady(false);
      overlay.remove();
    };
  }, [mapRef, basemapStyle]);

  useEffect(() => {
    const overlay = overlayRef.current;
    if (!overlay || !overlayReady) return;
    addEriImagery(overlay, dataset, 1, attribution);
  }, [overlayReady, dataset, attribution]);

  useEffect(() => {
    const overlay = overlayRef.current;
    if (overlay && overlayReady) setEriImageryOpacity(overlay, opacity);
  }, [overlayReady, dataset, opacity]);

  useEffect(() => {
    const overlay = overlayRef.current;
    if (!overlay || !overlayReady || !overlay.getLayer(basemapLayerId)) return;
    overlay.setLayoutProperty(basemapLayerId, "visibility", basemapVisible ? "visible" : "none");
  }, [overlayReady, basemapLayerId, basemapVisible]);

  function splitFromPointer(clientX: number) {
    const rect = shellRef.current?.getBoundingClientRect();
    if (!rect || rect.width === 0) return;
    setSplit(Math.min(98, Math.max(2, ((clientX - rect.left) / rect.width) * 100)));
  }

  function onPointerDown(event: React.PointerEvent<HTMLDivElement>) {
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    splitFromPointer(event.clientX);
  }

  function onPointerMove(event: React.PointerEvent<HTMLDivElement>) {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) splitFromPointer(event.clientX);
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    const step = event.shiftKey ? 10 : 2;
    if (event.key === "ArrowLeft") setSplit((value) => Math.max(2, value - step));
    else if (event.key === "ArrowRight") setSplit((value) => Math.min(98, value + step));
    else if (event.key === "Home") setSplit(2);
    else if (event.key === "End") setSplit(98);
    else return;
    event.preventDefault();
  }

  return (
    <div ref={shellRef} className="map-compare" data-testid="map-compare">
      <div
        ref={hostRef}
        className="map-compare-host"
        style={{ clipPath: `inset(0 0 0 ${split}%)` }}
        aria-hidden="true"
      />
      {/* Each label is confined to its own side of the divider. */}
      <span
        className="map-compare-label"
        data-side="left"
        style={{ maxWidth: `max(0px, calc(${split}% - 76px))` }}
      >
        {leftLabel}
      </span>
      <span
        className="map-compare-label"
        data-side="right"
        style={{ maxWidth: `max(0px, calc(${100 - split}% - 34px))` }}
      >
        {dataset.label}
      </span>
      <div
        className="map-compare-divider"
        style={{ left: `${split}%` }}
        role="slider"
        tabIndex={0}
        aria-label="Imagery comparison divider"
        aria-orientation="horizontal"
        aria-valuemin={2}
        aria-valuemax={98}
        aria-valuenow={Math.round(split)}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onKeyDown={onKeyDown}
      >
        <span className="map-compare-grip" aria-hidden="true" />
      </div>
    </div>
  );
}

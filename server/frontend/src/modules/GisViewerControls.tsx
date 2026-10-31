import { useEffect, useMemo, useRef, useState } from "react";
import type { MutableRefObject } from "react";
import * as maplibregl from "maplibre-gl";
import type { GisCatalog, GisClient, SearchHit } from "../spatial/gis/gisApi";
import { ExtentHistory } from "../spatial/gis/extentHistory";
import {
  decodeMapState,
  deleteBookmark,
  encodeMapState,
  readBookmarks,
  saveBookmark,
  type MapBookmark,
  type MapViewState,
} from "../spatial/gis/mapState";
import { setSourceOpacity } from "../spatial/gis/opacity";
import { buildPrintSidecar, printMap } from "../spatial/gis/printMap";

/**
 * Viewer-level GIS controls for the MapLibre runtime: search, home/previous/
 * next extent, scale bar and cursor coordinates, saved views (URL hash +
 * named bookmarks), map print with a provenance sidecar, and per-layer
 * opacity. Map-click tools (identify, polygon query, measure) live in
 * SpatialToolsPanel so they share one exclusive tool mode.
 */
export interface GisViewerOptions {
  mapRef: MutableRefObject<maplibregl.Map | null>;
  mapReady: boolean;
  client: GisClient;
  producerRepo: string;
  homeView: { center: [number, number]; zoom: number };
  /** Catalog layer ids currently switched on in the host's layer control. */
  activeLayers: string[];
  /** Style source id that renders a catalog layer, or null when not mapped. */
  sourceIdFor: (layerId: string) => string | null;
  /** Switch catalog layers on/off when a saved view is restored. */
  applyLayerVisibility: (visible: Record<string, boolean>) => void;
}

function currentView(map: maplibregl.Map, layers: Record<string, number>): MapViewState {
  const center = map.getCenter();
  return { center: [center.lng, center.lat], zoom: map.getZoom(), bearing: map.getBearing(), pitch: map.getPitch(), layers };
}

function attributionText(map: maplibregl.Map): string {
  const style = map.getStyle();
  const parts = new Set<string>();
  for (const source of Object.values(style.sources ?? {})) {
    const attribution = (source as { attribution?: unknown }).attribution;
    if (typeof attribution === "string" && attribution) parts.add(attribution.replace(/<[^>]+>/g, ""));
  }
  return [...parts].join(" · ");
}

export function useGisViewer(options: GisViewerOptions) {
  const { mapRef, mapReady, client, producerRepo, homeView, activeLayers, sourceIdFor, applyLayerVisibility } = options;
  const historyRef = useRef(new ExtentHistory());
  const restoredRef = useRef(false);
  const [nav, setNav] = useState({ canBack: false, canForward: false });
  const [cursor, setCursor] = useState<[number, number] | null>(null);
  // Opacity from a shared URL (#map=...&layers=id:opacity) seeds the initial state.
  const [opacity, setOpacity] = useState<Record<string, number>>(
    () => decodeMapState(window.location.hash)?.layers ?? {},
  );
  const syncNav = () => setNav({ canBack: historyRef.current.canBack, canForward: historyRef.current.canForward });
  const [catalog, setCatalog] = useState<GisCatalog | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [bookmarks, setBookmarks] = useState<MapBookmark[]>(() => readBookmarks(localStorage));
  const [printError, setPrintError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    client
      .catalog(controller.signal)
      .then(setCatalog)
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setCatalogError(error instanceof Error ? error.message : String(error));
      });
    return () => controller.abort();
  }, [client]);

  // Scale bar, cursor readout and extent history are bound per map instance
  // (a 2D/3D switch rebuilds the map behind the same ref).
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const scale = new maplibregl.ScaleControl({ unit: "metric" });
    map.addControl(scale, "bottom-left");
    const onMove = (event: maplibregl.MapMouseEvent) => setCursor([event.lngLat.lng, event.lngLat.lat]);
    const onOut = () => setCursor(null);
    const record = () => {
      const center = map.getCenter();
      historyRef.current.push({ center: [center.lng, center.lat], zoom: map.getZoom() });
    };
    const onMoveEnd = () => {
      record();
      setNav({ canBack: historyRef.current.canBack, canForward: historyRef.current.canForward });
    };
    map.on("mousemove", onMove);
    map.on("mouseout", onOut);
    map.on("moveend", onMoveEnd);
    record();
    return () => {
      map.off("mousemove", onMove);
      map.off("mouseout", onOut);
      map.off("moveend", onMoveEnd);
      try {
        map.removeControl(scale);
      } catch { /* map already torn down */ }
    };
  }, [mapRef, mapReady]);

  // Restore a view from the URL hash once per page load.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || restoredRef.current) return;
    restoredRef.current = true;
    const state = decodeMapState(window.location.hash);
    if (!state) return;
    map.jumpTo({ center: state.center, zoom: state.zoom, bearing: state.bearing, pitch: state.pitch });
    if (Object.keys(state.layers).length) {
      applyLayerVisibility(Object.fromEntries(Object.keys(state.layers).map((id) => [id, true])));
    }
  }, [mapRef, mapReady, applyLayerVisibility]);

  // Re-apply opacity whenever it changes or a layer's source (re)loads.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const apply = () => {
      for (const layerId of activeLayers) {
        const sourceId = sourceIdFor(layerId);
        if (sourceId && map.getSource(sourceId)) setSourceOpacity(map, sourceId, opacity[layerId] ?? 1);
      }
    };
    apply();
    const onSourceData = (event: maplibregl.MapSourceDataEvent) => {
      if (event.isSourceLoaded && activeLayers.some((id) => sourceIdFor(id) === event.sourceId)) apply();
    };
    map.on("sourcedata", onSourceData);
    return () => {
      map.off("sourcedata", onSourceData);
    };
  }, [activeLayers, mapReady, mapRef, opacity, sourceIdFor]);

  const layerOpacity = useMemo(
    () => Object.fromEntries(activeLayers.map((id) => [id, opacity[id] ?? 1])),
    [activeLayers, opacity],
  );

  const goTo = (view: { center: [number, number]; zoom: number }) => {
    mapRef.current?.flyTo({ center: view.center, zoom: view.zoom, speed: 1.4 });
  };

  const flyToHit = (hit: SearchHit) => {
    const map = mapRef.current;
    if (!map) return;
    if (hit.bbox && (hit.bbox[0] !== hit.bbox[2] || hit.bbox[1] !== hit.bbox[3])) {
      map.fitBounds([[hit.bbox[0], hit.bbox[1]], [hit.bbox[2], hit.bbox[3]]], { padding: 40, maxZoom: 15 });
    } else if (hit.anchor) {
      map.flyTo({ center: hit.anchor, zoom: Math.max(map.getZoom(), 13) });
    }
  };

  const saveViewToUrl = () => {
    const map = mapRef.current;
    if (!map) return null;
    const encoded = encodeMapState(currentView(map, layerOpacity));
    window.history.replaceState(null, "", `#${encoded}`);
    return window.location.href;
  };

  const restoreBookmark = (bookmark: MapBookmark) => {
    const map = mapRef.current;
    if (!map) return;
    const { state } = bookmark;
    map.jumpTo({ center: state.center, zoom: state.zoom, bearing: state.bearing, pitch: state.pitch });
    applyLayerVisibility(Object.fromEntries(Object.keys(state.layers).map((id) => [id, true])));
    setOpacity((current) => ({ ...current, ...state.layers }));
  };

  const print = () => {
    const map = mapRef.current;
    if (!map) return;
    setPrintError(null);
    const bounds = map.getBounds();
    const view = currentView(map, layerOpacity);
    const sidecar = buildPrintSidecar({
      producerRepo,
      bbox: [bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()],
      center: view.center,
      zoom: view.zoom,
      bearing: view.bearing,
      pitch: view.pitch,
      layers: layerOpacity,
      attribution: attributionText(map),
    });
    printMap(map, sidecar).catch((error: unknown) => setPrintError(error instanceof Error ? error.message : String(error)));
  };

  return {
    client,
    catalog,
    catalogError,
    cursor,
    canBack: nav.canBack,
    canForward: nav.canForward,
    goHome: () => goTo(homeView),
    goBack: () => {
      const view = historyRef.current.back();
      if (view) goTo(view);
      syncNav();
    },
    goForward: () => {
      const view = historyRef.current.forward();
      if (view) goTo(view);
      syncNav();
    },
    flyToHit,
    layerOpacity,
    setLayerOpacity: (layerId: string, value: number) => setOpacity((current) => ({ ...current, [layerId]: value })),
    saveViewToUrl,
    bookmarks,
    saveBookmark: (name: string) => {
      const map = mapRef.current;
      if (map) setBookmarks(saveBookmark(localStorage, name, currentView(map, layerOpacity)));
    },
    deleteBookmark: (name: string) => setBookmarks(deleteBookmark(localStorage, name)),
    restoreBookmark,
    print,
    printError,
  };
}

export function GisViewerControls(state: ReturnType<typeof useGisViewer>) {
  const { client, catalog, catalogError, cursor, canBack, canForward, goHome, goBack, goForward, flyToHit, layerOpacity, setLayerOpacity, saveViewToUrl, bookmarks, saveBookmark: save, deleteBookmark: remove, restoreBookmark, print, printError } = state;
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<{ query: string; hits: SearchHit[]; error: string | null }>({ query: "", hits: [], error: null });
  const trimmedQuery = query.trim();
  // Results are shown only for the query that produced them, so stale hits
  // never linger after the box is cleared or edited.
  const hits = results.query === trimmedQuery ? results.hits : [];
  const searchError = results.query === trimmedQuery ? results.error : null;
  const [bookmarkName, setBookmarkName] = useState("");
  const [savedUrl, setSavedUrl] = useState<string | null>(null);
  const titles = useMemo(
    () => Object.fromEntries((catalog?.layers ?? []).map((layer) => [layer.layer_id, layer.title])),
    [catalog],
  );

  useEffect(() => {
    if (trimmedQuery.length < 2) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      client
        .search(trimmedQuery, controller.signal)
        .then((found) => setResults({ query: trimmedQuery, hits: found, error: null }))
        .catch((error: unknown) => {
          if (error instanceof DOMException && error.name === "AbortError") return;
          setResults({ query: trimmedQuery, hits: [], error: error instanceof Error ? error.message : String(error) });
        });
    }, 250);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [client, trimmedQuery]);

  return (
    <div className="tools-panel">
      <h2>Map</h2>
      <label className="tools-target">
        <span>Search place, feature or coordinates</span>
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="e.g. Arecibo, 18.4723, -66.7156"
          aria-label="Search the map"
        />
      </label>
      {searchError && <p role="alert">Search failed: {searchError}</p>}
      {hits.length > 0 && (
        <ul className="col" aria-label="Search results">
          {hits.map((hit, index) => (
            <li key={`${hit.layer_id ?? "coord"}-${hit.feature_id ?? index}`}>
              <button className="linklike" onClick={() => flyToHit(hit)}>
                {hit.label} · {hit.kind === "coordinate" ? "coordinate" : titles[hit.layer_id ?? ""] ?? hit.layer_id}
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="row">
        <button className="navbtn" onClick={goHome} title="Full extent">Home</button>
        <button className="navbtn" onClick={goBack} disabled={!canBack} title="Previous extent">Back</button>
        <button className="navbtn" onClick={goForward} disabled={!canForward} title="Next extent">Forward</button>
        <button className="navbtn" onClick={print} title="Download PNG with scale, north, attribution + JSON sidecar">Print</button>
      </div>
      <p className="subtle" aria-live="polite">
        {cursor ? `${cursor[1].toFixed(5)}, ${cursor[0].toFixed(5)}` : "Move over the map for coordinates"} · Shift-drag to zoom to a box
      </p>
      {printError && <p role="alert">Print failed: {printError}</p>}
      {Object.keys(layerOpacity).length > 0 && (
        <div className="col">
          {Object.entries(layerOpacity).map(([layerId, value]) => (
            <label key={layerId} className="tools-target">
              <span>{titles[layerId] ?? layerId} opacity {Math.round(value * 100)}%</span>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={value}
                onChange={(event) => setLayerOpacity(layerId, Number(event.target.value))}
              />
            </label>
          ))}
        </div>
      )}
      <div className="row">
        <button className="navbtn" onClick={() => setSavedUrl(saveViewToUrl())}>Save view to URL</button>
      </div>
      {savedUrl && <p className="subtle">Saved: {savedUrl}</p>}
      <div className="row">
        <input
          type="text"
          value={bookmarkName}
          onChange={(event) => setBookmarkName(event.target.value)}
          placeholder="Bookmark name"
          aria-label="Bookmark name"
        />
        <button
          className="navbtn"
          disabled={!bookmarkName.trim()}
          onClick={() => {
            save(bookmarkName);
            setBookmarkName("");
          }}
        >
          Save bookmark
        </button>
      </div>
      {bookmarks.map((bookmark) => (
        <div key={bookmark.name} className="row">
          <button className="linklike" onClick={() => restoreBookmark(bookmark)}>{bookmark.name}</button>
          <button className="linklike" onClick={() => remove(bookmark.name)} aria-label={`Delete bookmark ${bookmark.name}`}>delete</button>
        </div>
      ))}
      {catalogError && <p role="alert">GIS catalog unavailable: {catalogError}</p>}
    </div>
  );
}

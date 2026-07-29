import { useEffect, useMemo, useRef, useState } from 'react';
import maplibregl, { type Map as MapLibreMap, type StyleSpecification } from 'maplibre-gl';
import { getGeoLayer } from '../lib/api';
import type {
  Anomaly,
  CatalogLayer,
  EventRecord,
  LayerCatalog,
  LayerRuntimeStatus,
  Selection,
  Site,
} from '../types/gis';

const style: StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: 'raster',
      tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      tileSize: 256,
      attribution: '© OpenStreetMap contributors',
    },
  },
  layers: [{ id: 'osm', type: 'raster', source: 'osm' }],
};

type LayerLoadStatus = LayerRuntimeStatus | 'loading' | 'error';

function safeId(value: string): string {
  return value.replace(/[^a-zA-Z0-9_-]/g, '-');
}

function removeGeoLayer(map: MapLibreMap, layerId: string): void {
  const sourceId = `catalog-${safeId(layerId)}`;
  for (const suffix of ['point', 'line', 'fill', 'outline']) {
    const renderedId = `${sourceId}-${suffix}`;
    if (map.getLayer(renderedId)) map.removeLayer(renderedId);
  }
  if (map.getSource(sourceId)) map.removeSource(sourceId);
}

function addGeoLayer(
  map: MapLibreMap,
  layerId: string,
  data: GeoJSON.FeatureCollection,
): void {
  const sourceId = `catalog-${safeId(layerId)}`;
  map.addSource(sourceId, { type: 'geojson', data });
  map.addLayer({
    id: `${sourceId}-fill`,
    type: 'fill',
    source: sourceId,
    filter: ['==', '$type', 'Polygon'],
    paint: { 'fill-color': '#dc2626', 'fill-opacity': 0.12 },
  });
  map.addLayer({
    id: `${sourceId}-outline`,
    type: 'line',
    source: sourceId,
    filter: ['==', '$type', 'Polygon'],
    paint: { 'line-color': '#f87171', 'line-width': 1.2 },
  });
  map.addLayer({
    id: `${sourceId}-line`,
    type: 'line',
    source: sourceId,
    filter: ['==', '$type', 'LineString'],
    paint: { 'line-color': '#38bdf8', 'line-width': 2 },
  });
  map.addLayer({
    id: `${sourceId}-point`,
    type: 'circle',
    source: sourceId,
    filter: ['==', '$type', 'Point'],
    paint: {
      'circle-color': '#fbbf24',
      'circle-radius': 5,
      'circle-stroke-color': '#111827',
      'circle-stroke-width': 1,
    },
  });
}

export function MapWorkspace({
  sites,
  events,
  anomalies,
  catalog,
  enabledLayers,
  onLayerStatus,
  onSelect,
}: {
  sites: Site[];
  events: EventRecord[];
  anomalies: Anomaly[];
  catalog: LayerCatalog | null;
  enabledLayers: Set<string>;
  onLayerStatus: (layerId: string, status: LayerLoadStatus, message?: string) => void;
  onSelect: (selection: Selection) => void;
}) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);
  const loadedRef = useRef<Set<string>>(new Set());
  const [ready, setReady] = useState(false);
  const [baseMapError, setBaseMapError] = useState(false);

  const catalogById = useMemo(
    () => new Map(
      catalog?.families.flatMap((family) => family.layers)
        .map((layer) => [layer.layer_id, layer] as const) ?? [],
    ),
    [catalog],
  );

  useEffect(() => {
    if (!hostRef.current || mapRef.current) return;
    const loadedLayers = loadedRef.current;
    const map = new maplibregl.Map({
      container: hostRef.current,
      style,
      center: [-66.45, 18.2],
      zoom: 8.25,
      attributionControl: true,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-left');
    map.on('load', () => setReady(true));
    map.on('error', (event) => {
      if ((event as { sourceId?: string }).sourceId === 'osm') setBaseMapError(true);
    });
    map.on('click', (event) => {
      const feature = map.queryRenderedFeatures(event.point)
        .find((candidate) => candidate.source.startsWith('catalog-'));
      if (!feature) return;
      const sourceId = String(feature.source);
      const layerId = [...loadedLayers]
        .find((candidate) => sourceId === `catalog-${safeId(candidate)}`);
      if (!layerId) return;
      const properties = feature.properties ?? {};
      onSelect({
        kind: 'feature',
        id: String(feature.id ?? properties.id ?? properties.GEOID ?? 'feature'),
        layerId,
        properties,
      });
    });
    mapRef.current = map;
    return () => {
      markersRef.current.forEach((marker) => marker.remove());
      map.remove();
      mapRef.current = null;
      loadedLayers.clear();
    };
  }, [onSelect]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    let cancelled = false;

    for (const layerId of [...loadedRef.current]) {
      if (enabledLayers.has(layerId)) continue;
      removeGeoLayer(map, layerId);
      loadedRef.current.delete(layerId);
      onLayerStatus(layerId, catalogById.get(layerId)?.runtime_status ?? 'deferred');
    }

    for (const layerId of enabledLayers) {
      if (loadedRef.current.has(layerId)) continue;
      const layer: CatalogLayer | undefined = catalogById.get(layerId);
      if (!layer || !['live', 'empty'].includes(layer.runtime_status ?? 'deferred')) {
        onLayerStatus(layerId, 'error', 'Layer is not available from the backend.');
        continue;
      }
      onLayerStatus(layerId, 'loading');
      void getGeoLayer(layerId)
        .then((collection) => {
          if (cancelled || !mapRef.current) return;
          addGeoLayer(mapRef.current, layerId, collection as GeoJSON.FeatureCollection);
          loadedRef.current.add(layerId);
          onLayerStatus(layerId, collection.features.length ? 'live' : 'empty');
        })
        .catch((error: unknown) => {
          if (!cancelled) {
            onLayerStatus(
              layerId,
              'error',
              error instanceof Error ? error.message : String(error),
            );
          }
        });
    }
    return () => {
      cancelled = true;
    };
  }, [catalogById, enabledLayers, onLayerStatus, ready]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    markersRef.current.forEach((marker) => marker.remove());
    markersRef.current = [];
    const anomalySites = new Map(
      anomalies.filter((anomaly) => anomaly.siteId)
        .map((anomaly) => [anomaly.siteId as string, anomaly]),
    );

    for (const site of sites) {
      if (!Number.isFinite(site.lat) || !Number.isFinite(site.lng)) continue;
      const anomaly = anomalySites.get(site.id);
      const element = document.createElement('button');
      element.className = 'map-marker';
      element.dataset.kind = anomaly ? 'anomaly' : site.sensitive ? 'sensitive' : 'site';
      element.type = 'button';
      element.title = anomaly ? `${site.name} · ${anomaly.title}` : site.name;
      element.setAttribute('aria-label', element.title);
      element.addEventListener('click', (event) => {
        event.stopPropagation();
        onSelect(anomaly
          ? { kind: 'anomaly', id: anomaly.id }
          : { kind: 'site', id: site.id });
      });
      markersRef.current.push(
        new maplibregl.Marker({ element }).setLngLat([site.lng, site.lat]).addTo(map),
      );
    }

    const bySite = new Map(sites.map((site) => [site.id, site]));
    for (const eventRecord of events) {
      const site = eventRecord.siteId ? bySite.get(eventRecord.siteId) : undefined;
      if (!site) continue;
      const element = document.createElement('button');
      element.className = 'event-marker';
      element.dataset.tier = eventRecord.tier ?? 'unassigned';
      element.type = 'button';
      element.title = `${eventRecord.label} · ${eventRecord.at}`;
      element.setAttribute('aria-label', element.title);
      element.addEventListener('click', (event) => {
        event.stopPropagation();
        onSelect({ kind: 'event', id: eventRecord.id });
      });
      markersRef.current.push(
        new maplibregl.Marker({ element, offset: [9, -9] })
          .setLngLat([site.lng, site.lat])
          .addTo(map),
      );
    }
  }, [anomalies, events, onSelect, ready, sites]);

  useEffect(() => {
    window.setTimeout(() => mapRef.current?.resize(), 120);
  }, [sites.length, events.length]);

  return (
    <section className="map-region" aria-label="Puerto Rico spatial intelligence map">
      <div ref={hostRef} className="map-host" data-testid="gis-map" />
      {!sites.length && (
        <div className="map-notice" role="status">
          Map ready. No site geometry is available from the current data source.
        </div>
      )}
      {baseMapError && (
        <div className="map-notice map-notice--warning" role="status">
          Base-map tiles are unavailable. Operational layers remain inspectable.
        </div>
      )}
    </section>
  );
}

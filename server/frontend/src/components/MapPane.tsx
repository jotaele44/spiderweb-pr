import React, { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { getSites, Site } from '../lib/api';
import { useAppStore } from '../state/store';

// Puerto Rico view. Dark CARTO raster basemap (no key) matches the workbench.
const PR_CENTER: [number, number] = [-66.45, 18.22];
const STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    carto: {
      type: 'raster',
      tiles: ['https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png'],
      tileSize: 256,
      attribution: '© OpenStreetMap, © CARTO',
    },
  },
  layers: [{ id: 'carto', type: 'raster', source: 'carto' }],
};

/**
 * MapPane renders sites (GET /sites) as clickable markers on a Puerto Rico map.
 * Selecting a marker publishes the site to the shared store (inspector reflects it).
 * Wires the previously-unused maplibre-gl dependency and the typed API client.
 */
export const MapPane: React.FC = () => {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const setSelection = useAppStore((s) => s.setSelection);
  const [count, setCount] = useState<number | null>(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: STYLE,
      center: PR_CENTER,
      zoom: 8.2,
      attributionControl: true,
    });
    mapRef.current = map;

    let disposed = false;
    getSites().then((sites: Site[]) => {
      if (disposed) return;
      setCount(sites.length);
      for (const site of sites) {
        if (typeof site.lat !== 'number' || typeof site.lng !== 'number') continue;
        const el = document.createElement('button');
        el.type = 'button';
        el.setAttribute('aria-label', site.name || site.id);
        el.style.cssText =
          'width:12px;height:12px;border-radius:9999px;border:2px solid #fff;cursor:pointer;' +
          `background:${site.sensitive ? '#ef4444' : '#0d9488'};`;
        el.addEventListener('click', (e) => {
          e.stopPropagation();
          setSelection(site);
        });
        new maplibregl.Marker({ element: el }).setLngLat([site.lng, site.lat]).addTo(map);
      }
    });

    return () => {
      disposed = true;
      map.remove();
      mapRef.current = null;
    };
  }, [setSelection]);

  return (
    <section className="pane" aria-label="Spatial">
      <div className="pane__header">
        Spatial
        <span className="muted">{count === null ? 'loading…' : `${count} sites`}</span>
      </div>
      <div className="pane__body">
        <div className="map-canvas" ref={containerRef} />
      </div>
    </section>
  );
};

import { useState } from 'react';
import { MapContainer, TileLayer, GeoJSON, useMapEvents, FeatureGroup } from 'react-leaflet';
import L from 'leaflet';
import { cn } from '@/lib/utils';
import { Square } from 'lucide-react';
import MapFlyTo from './MapFlyTo';

// Fix Leaflet default icon
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
});

function MapClickHandler({ onPointClick }) {
  useMapEvents({
    click(e) {
      if (onPointClick) onPointClick({ latlng: e.latlng, properties: null, layerName: null });
    },
  });
  return null;
}

function LayerRenderer({ layer, onPointClick }) {
  if (!layer.visible || !layer.data) return null;

  const style = {
    color: layer.color,
    fillColor: layer.color,
    fillOpacity: layer.opacity * 0.4,
    weight: 1.5,
    opacity: layer.opacity,
  };

  const pointToLayer = (feature, latlng) =>
    L.circleMarker(latlng, {
      radius: 6,
      fillColor: layer.color,
      color: layer.color,
      weight: 1,
      opacity: layer.opacity,
      fillOpacity: layer.opacity * 0.8,
    });

  return (
    <GeoJSON
      key={`${layer.id}-${layer.color}-${layer.opacity}-${layer.visible}`}
      data={layer.data}
      style={() => style}
      pointToLayer={pointToLayer}
      onEachFeature={(feature, leafletLayer) => {
        if (feature.properties) {
          const props = Object.entries(feature.properties)
            .map(([k, v]) => `<div style="display:flex;gap:8px;font-family:monospace;font-size:11px"><span style="color:#888">${k}</span><span style="color:#00E5FF">${v ?? '—'}</span></div>`)
            .join('');
          leafletLayer.bindPopup(
            `<div style="background:#0F1923;border:1px solid rgba(0,229,255,0.3);border-radius:4px;padding:8px;min-width:160px">${props}</div>`,
            { className: 'geo-popup', maxWidth: 300 }
          );
          if (onPointClick) {
            leafletLayer.on('click', (ev) => {
              onPointClick({ latlng: ev.latlng, properties: feature.properties, layerName: layer.name });
            });
          }
        }
      }}
    />
  );
}

function MapMoveHandler({ onMapMove }) {
  useMapEvents({
    moveend: (e) => {
      const c = e.target.getCenter();
      onMapMove({ lat: c.lat, lng: c.lng });
    },
  });
  return null;
}

export default function MapView({ layers, overlays = [], onRegionDrawn, drawMode, setDrawMode, flyToTarget, onPointClick, onMapMove }) {
  const [mapReady, setMapReady] = useState(false);

  return (
    <div className="relative flex-1 min-h-0">
      <MapContainer
        center={[18.2208, -66.5901]}
        zoom={8}
        minZoom={7}
        maxZoom={18}
        maxBounds={[[14.5, -72.0], [22.5, -61.0]]}
        maxBoundsViscosity={1.0}
        className="w-full h-full"
        style={{ background: '#0a1520' }}
        whenReady={() => setMapReady(true)}
        zoomControl={false}
      >
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          maxZoom={19}
        />

        {/* Active overlay tile layers */}
        {overlays.map((o) => (
          <TileLayer
            key={o.id}
            url={o.url}
            attribution={o.attribution}
            opacity={o.opacity}
            maxZoom={o.maxZoom || 19}
          />
        ))}

        {layers.map((layer) => (
          <LayerRenderer key={layer.id} layer={layer} onPointClick={onPointClick} />
        ))}

        <MapFlyTo target={flyToTarget} />
        <MapClickHandler onPointClick={onPointClick} />
        {onMapMove && <MapMoveHandler onMapMove={onMapMove} />}

        {drawMode && onRegionDrawn && (
          <FeatureGroup>
            <DrawControl onRegionDrawn={onRegionDrawn} setDrawMode={setDrawMode} />
          </FeatureGroup>
        )}
      </MapContainer>

      {/* Draw mode indicator */}
      {drawMode && (
        <div className="absolute top-3 left-1/2 -translate-x-1/2 z-[1000] panel-glass px-3 py-1.5 rounded flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />
          <span className="font-mono text-xs text-primary">Draw region to analyze — click to place vertices, double-click to finish</span>
          <button
            onClick={() => setDrawMode(false)}
            className="ml-2 text-muted-foreground hover:text-destructive font-mono text-xs"
          >
            Cancel
          </button>
        </div>
      )}

      {/* Map controls */}
      <div className="absolute bottom-4 right-4 z-[1000] flex flex-col gap-1">
        <button
          onClick={() => setDrawMode(!drawMode)}
          className={cn(
            'w-8 h-8 panel-glass rounded flex items-center justify-center transition-all',
            drawMode ? 'text-primary glow-cyan' : 'text-muted-foreground hover:text-primary'
          )}
          title="Draw region for analysis"
        >
          <Square className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}

function DrawControl({ onRegionDrawn, setDrawMode }) {
  // Leaflet Draw is heavy — use a simple click-based polygon approach instead
  const [points, setPoints] = useState([]);
  const [previewLayer, setPreviewLayer] = useState(null);

  useMapEvents({
    click(e) {
      setPoints((prev) => [...prev, [e.latlng.lat, e.latlng.lng]]);
    },
    dblclick(e) {
      const pts = [...points, [e.latlng.lat, e.latlng.lng]];
      if (pts.length >= 3) {
        const coords = pts.map(([lat, lng]) => [lng, lat]);
        coords.push(coords[0]); // close ring
        const geojson = {
          type: 'Feature',
          properties: {},
          geometry: { type: 'Polygon', coordinates: [coords] },
        };
        onRegionDrawn(geojson);
        setDrawMode(false);
      }
      setPoints([]);
    },
  });

  return null;
}
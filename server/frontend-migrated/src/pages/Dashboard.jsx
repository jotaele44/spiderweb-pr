import { useState, useEffect, useCallback, useRef } from 'react';
import TopBar from '@/components/TopBar';
import MapView from '@/components/MapView';
import ChatPanel from '@/components/ChatPanel';
import StatusBar from '@/components/StatusBar';
import PointInspectorPanel from '@/components/PointInspectorPanel';
import SidePanel from '@/components/SidePanel';
import LocationAnalyticsPanel from '@/components/LocationAnalyticsPanel';
import { checkConnection, uploadGeodata, streamQuery } from '@/lib/api';
import { parseUploadedFile, getNextColor, generateLayerId, generateMockGeoJSON } from '@/lib/layerUtils';

const MOCK_OFFLINE_RESPONSE = (prompt) =>
  `[OFFLINE MODE]\n\nBackend at localhost:8000 is unreachable.\n\nYour query: "${prompt}"\n\nStart your backend server and click the status indicator to reconnect.`;

export default function Dashboard() {
  // ── State ──
  const [layers, setLayers] = useState([]);
  const [selectedLayerId, setSelectedLayerId] = useState(null);
  const [connectionStatus, setConnectionStatus] = useState({ connected: false, lastChecked: null });
  const [isUploading, setIsUploading] = useState(false);
  const [drawMode, setDrawMode] = useState(false);
  const [pendingRegion, setPendingRegion] = useState(null);
  const [history, setHistory] = useState([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingText, setStreamingText] = useState('');
  const stopStreamRef = useRef(null);
  const [inspectorCollapsed, setInspectorCollapsed] = useState(false);
  const [clickedPoint, setClickedPoint] = useState(null);
  const [flyToTarget, setFlyToTarget] = useState(null);
  const [locationGroups, setLocationGroups] = useState([]);
  const [mapCenter, setMapCenter] = useState({ lat: 18.2208, lng: -66.5901 });
  const [analyticsOpen, setAnalyticsOpen] = useState(false);
  const [activeOverlays, setActiveOverlays] = useState([]);
  const [recentSelections, setRecentSelections] = useState([]);

  // ── History helper (defined early so it can be used in effects) ──
  const addToHistory = useCallback((item) => {
    setHistory((prev) => [{ id: `h_${Date.now()}_${Math.random()}`, timestamp: new Date().toISOString(), ...item }, ...prev]);
  }, []);

  // ── Demo layer on mount ──
  useEffect(() => {
    const demo = generateMockGeoJSON('Demo: NYC sample points');
    const layer = {
      id: generateLayerId(),
      name: 'Demo: Sample Points',
      type: 'point',
      visible: true,
      color: '#00E5FF',
      opacity: 0.8,
      data: demo,
      source: 'demo',
      createdAt: new Date().toISOString(),
      featureCount: demo.features.length,
    };
    setLayers([layer]);
    setSelectedLayerId(layer.id);
    addToHistory({ mode: 'system', prompt: 'App initialized', response: 'Demo layer loaded. Upload your own geodata or connect to localhost:8000 to begin.' });
  }, [addToHistory]);

  // ── Connection check ──
  const refreshConnection = useCallback(async () => {
    const result = await checkConnection();
    setConnectionStatus({ ...result, lastChecked: new Date().toISOString() });
    return result.connected;
  }, []);

  useEffect(() => {
    refreshConnection();
    const interval = setInterval(refreshConnection, 15000);
    return () => clearInterval(interval);
  }, [refreshConnection]);

  // ── File upload ──
  const handleFileUpload = async (file) => {
    setIsUploading(true);
    try {
      let geojson;
      if (connectionStatus.connected) {
        const result = await uploadGeodata(file);
        geojson = result.geojson || result;
      } else {
        const text = await file.text();
        if (file.name.endsWith('.csv')) {
          geojson = csvToGeoJSON(text);
        } else {
          geojson = JSON.parse(text);
        }
      }
      const color = getNextColor(layers);
      const layer = parseUploadedFile(file, geojson);
      layer.color = color;
      setLayers((prev) => [...prev, layer]);
      setSelectedLayerId(layer.id);
      addToHistory({ mode: 'upload', prompt: `Loaded: ${file.name}`, response: `Layer "${layer.name}" added with ${layer.featureCount} features.` });
    } catch (err) {
      addToHistory({ mode: 'upload', prompt: `Load: ${file.name}`, response: err.message, error: true });
    } finally {
      setIsUploading(false);
    }
  };

  // ── Layer management ──
  const toggleLayerVisibility = (id) =>
    setLayers((prev) => prev.map((l) => (l.id === id ? { ...l, visible: !l.visible } : l)));

  const deleteLayer = (id) => {
    setLayers((prev) => prev.filter((l) => l.id !== id));
    if (selectedLayerId === id) setSelectedLayerId(null);
  };

  const updateLayer = (id, updates) =>
    setLayers((prev) => prev.map((l) => (l.id === id ? { ...l, ...updates } : l)));

  // ── Generic stream helper ──
  const runStream = useCallback((endpoint, payload, mode, onGeoJSON) => {
    if (isStreaming) return;
    setIsStreaming(true);
    setStreamingText('');
    let accumulated = '';

    if (!connectionStatus.connected) {
      setTimeout(() => {
        const mockResp = MOCK_OFFLINE_RESPONSE(payload.question || payload.prompt || JSON.stringify(payload).slice(0, 60));
        addToHistory({ mode, prompt: payload.question || payload.prompt || 'Region analysis', response: mockResp });
        setStreamingText('');
        setIsStreaming(false);
      }, 1200);
      return;
    }

    const stop = streamQuery(
      endpoint,
      payload,
      (token) => { accumulated += token; setStreamingText(accumulated); },
      () => {
        try {
          const parsed = JSON.parse(accumulated);
          if (parsed.type === 'FeatureCollection' && onGeoJSON) {
            onGeoJSON(parsed, payload.prompt || 'Generated layer');
          }
        } catch {}
        addToHistory({ mode, prompt: payload.question || payload.prompt || 'Region analysis', response: accumulated });
        setStreamingText('');
        setIsStreaming(false);
      },
      (err) => {
        addToHistory({ mode, prompt: payload.question || payload.prompt || '...', response: err, error: true });
        setStreamingText('');
        setIsStreaming(false);
      }
    );
    stopStreamRef.current = stop;
  }, [isStreaming, connectionStatus.connected, addToHistory]);

  // ── Location LLM query ──
  const handleSendLocation = (question) => {
    const loc = clickedPoint?.latlng || mapCenter;
    const coordStr = `lat ${loc.lat.toFixed(5)}, lng ${loc.lng.toFixed(5)}`;
    const propsStr = clickedPoint?.properties
      ? ' Properties: ' + Object.entries(clickedPoint.properties).map(([k, v]) => `${k}=${v}`).join(', ')
      : '';
    runStream('/stream/query', { question: `Location context: ${coordStr}.${propsStr}\n\n${question}` }, 'location');
  };

  // ── Query / Region / Generate ──
  const handleSendQuery = (question) => {
    if (!selectedLayerId) return;
    runStream('/stream/query', { layer_id: selectedLayerId, question }, 'query');
  };

  const handleSendRegion = (question) => {
    if (!pendingRegion) return;
    runStream('/stream/analyze-region', { geometry: pendingRegion.geometry, question }, 'region');
  };

  const handleSendGenerate = (prompt) => {
    runStream('/stream/generate', { prompt }, 'generate', (geojson, name) => {
      const color = getNextColor(layers);
      const newLayer = {
        id: generateLayerId(),
        name: `AI: ${name.slice(0, 20)}`,
        type: 'geojson',
        visible: true,
        color,
        opacity: 0.7,
        data: geojson,
        source: 'llm',
        createdAt: new Date().toISOString(),
        featureCount: geojson.features?.length ?? 0,
      };
      setLayers((prev) => [...prev, newLayer]);
      setSelectedLayerId(newLayer.id);
    });
  };

  // ── Region drawn on map ──
  const handleRegionDrawn = (geojson) => {
    setPendingRegion(geojson);
    setDrawMode(false);
    const regionLayer = {
      id: generateLayerId(),
      name: 'Selected Region',
      type: 'polygon',
      visible: true,
      color: '#7C4DFF',
      opacity: 0.5,
      data: { type: 'FeatureCollection', features: [geojson] },
      source: 'draw',
      createdAt: new Date().toISOString(),
      featureCount: 1,
    };
    setLayers((prev) => [...prev.filter((l) => l.source !== 'draw'), regionLayer]);
  };

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-background">
      <TopBar
        connectionStatus={connectionStatus}
        onFileUpload={handleFileUpload}
        onRefreshConnection={refreshConnection}
        isUploading={isUploading}
      />

      <div className="flex flex-1 min-h-0 overflow-hidden">
        <SidePanel
          onFlyTo={(lat, lng, zoom) => setFlyToTarget({ lat, lng, zoom, t: Date.now() })}
          onGroupsChange={setLocationGroups}
          layers={layers}
          selectedLayerId={selectedLayerId}
          onToggleVisibility={toggleLayerVisibility}
          onDeleteLayer={deleteLayer}
          onUpdateLayer={updateLayer}
          onSelectLayer={setSelectedLayerId}
          onOverlaysChange={setActiveOverlays}
          recentSelections={recentSelections}
        />

        <main className="flex-1 min-w-0 flex flex-col overflow-hidden">
          <MapView
            layers={layers}
            overlays={activeOverlays}
            onRegionDrawn={handleRegionDrawn}
            drawMode={drawMode}
            setDrawMode={setDrawMode}
            flyToTarget={flyToTarget}
            onPointClick={(pt) => {
              setClickedPoint(pt);
              setAnalyticsOpen(true);
              setRecentSelections((prev) => {
                const filtered = prev.filter((p) => !(Math.abs(p.latlng.lat - pt.latlng.lat) < 0.0001 && Math.abs(p.latlng.lng - pt.latlng.lng) < 0.0001));
                return [pt, ...filtered].slice(0, 10);
              });
            }}
            onMapMove={setMapCenter}
          />
          <PointInspectorPanel
            collapsed={inspectorCollapsed}
            onToggle={() => setInspectorCollapsed((v) => !v)}
            clickedPoint={clickedPoint}
          />
        </main>

        <ChatPanel
          layers={layers}
          selectedLayerId={selectedLayerId}
          onSendQuery={handleSendQuery}
          onSendRegion={handleSendRegion}
          onSendGenerate={handleSendGenerate}
          onSendLocation={handleSendLocation}
          history={history}
          isStreaming={isStreaming}
          streamingText={streamingText}
          pendingRegion={pendingRegion}
          onClearRegion={() => {
            setPendingRegion(null);
            setLayers((prev) => prev.filter((l) => l.source !== 'draw'));
          }}
          clickedPoint={clickedPoint}
          mapCenter={mapCenter}
        />
      </div>

      <StatusBar layers={layers} history={history} isStreaming={isStreaming} />

      {analyticsOpen && clickedPoint && (
        <LocationAnalyticsPanel
          clickedPoint={clickedPoint}
          layers={layers}
          onClose={() => setAnalyticsOpen(false)}
        />
      )}
    </div>
  );
}

function csvToGeoJSON(text) {
  const lines = text.trim().split('\n');
  const headers = lines[0].split(',').map((h) => h.trim().toLowerCase());
  const latIdx = headers.findIndex((h) => ['lat', 'latitude', 'y'].includes(h));
  const lonIdx = headers.findIndex((h) => ['lon', 'lng', 'longitude', 'x'].includes(h));
  if (latIdx === -1 || lonIdx === -1) throw new Error('CSV must have lat/lon columns');
  const features = lines.slice(1).map((line) => {
    const vals = line.split(',').map((v) => v.trim());
    const props = {};
    headers.forEach((h, i) => { props[h] = vals[i]; });
    return {
      type: 'Feature',
      properties: props,
      geometry: { type: 'Point', coordinates: [parseFloat(vals[lonIdx]), parseFloat(vals[latIdx])] },
    };
  }).filter((f) => !isNaN(f.geometry.coordinates[0]));
  return { type: 'FeatureCollection', features };
}
import { useState, useEffect } from 'react';
import { BarChart2, MapPin, Layers, Brain, AlertCircle, Loader2, RefreshCw, X, Copy, TrendingUp } from 'lucide-react';
import { cn } from '@/lib/utils';
import { federation } from '@/api/federationClient';

function StatCard({ label, value, sub, color = 'text-primary' }) {
  return (
    <div className="rounded border border-border/30 bg-card/30 p-2.5 space-y-0.5">
      <div className="font-mono text-xs text-muted-foreground/50">{label}</div>
      <div className={cn('font-mono text-sm font-semibold', color)}>{value}</div>
      {sub && <div className="font-mono text-xs text-muted-foreground/30">{sub}</div>}
    </div>
  );
}

const LENS_OPTIONS = [
  { id: 'general', label: 'General' },
  { id: 'hydrologic', label: 'Hydrologic' },
  { id: 'topographic', label: 'Topographic' },
  { id: 'seismic', label: 'Seismic' },
  { id: 'vegetation', label: 'Vegetation' },
  { id: 'urban', label: 'Urban / Infrastructure' },
  { id: 'climate', label: 'Climate' },
  { id: 'coastal', label: 'Coastal / Marine' },
  { id: 'geologic', label: 'Geologic' },
  { id: 'socioeconomic', label: 'Socioeconomic' },
];

const LENS_POI_CONTEXT = {
  general: 'notable landmarks, facilities, infrastructure, natural features',
  hydrologic: 'rivers, streams, reservoirs, flood zones, drainage basins, water treatment facilities, wetlands',
  topographic: 'peaks, ridges, valleys, cliffs, notable elevation changes, terrain features',
  seismic: 'fault lines, known seismic zones, emergency response centers, critical infrastructure vulnerable to earthquakes',
  vegetation: 'forests, nature reserves, agricultural land, deforested areas, reforestation projects',
  urban: 'roads, bridges, utilities, commercial zones, hospitals, schools, government buildings',
  climate: 'weather stations, flood-prone areas, hurricane shelters, climate monitoring points',
  coastal: 'beaches, ports, mangroves, coral reefs, coastal erosion points, marine protected areas',
  geologic: 'rock formations, karst features, sinkholes, mineral deposits, geological survey points',
  socioeconomic: 'community centers, economic zones, industrial areas, poverty-affected neighborhoods, employment centers',
};

const LENS_RECOMMENDATION_CONTEXT = {
  general: 'general land use, access, and development',
  hydrologic: 'flood risk mitigation, water resource management, drainage improvements, watershed protection',
  topographic: 'slope stability, landslide risk, terrain-sensitive construction, erosion control',
  seismic: 'seismic retrofitting, emergency preparedness, building code compliance, evacuation routes',
  vegetation: 'reforestation, invasive species management, ecological corridors, fire risk',
  urban: 'infrastructure upgrades, zoning, transportation access, utility resilience',
  climate: 'climate adaptation, heat island mitigation, storm resilience, renewable energy potential',
  coastal: 'coastal erosion management, marine conservation, storm surge barriers, fishing regulations',
  geologic: 'subsurface stability, karst risk, mineral extraction feasibility, foundation engineering',
  socioeconomic: 'community development, economic opportunity zones, social services access, workforce programs',
};

export default function LocationAnalyticsPanel({ clickedPoint, layers, onClose }) {
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [tab, setTab] = useState('overview');
  const [lens, setLens] = useState('general');

  const { latlng, properties, layerName } = clickedPoint || {};

  // Auto-fetch when point or lens changes
  useEffect(() => {
    if (!latlng) return;
    fetchAnalytics();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [latlng?.lat, latlng?.lng, lens]);

  const fetchAnalytics = async () => {
    if (!latlng) return;
    setLoading(true);
    setError('');
    setAnalytics(null);

    // Build context from nearby layers
    const nearbyFeatures = [];
    layers.forEach((layer) => {
      if (!layer.visible || !layer.data?.features) return;
      const nearby = layer.data.features.filter((f) => {
        if (f.geometry?.type !== 'Point') return false;
        const [fLng, fLat] = f.geometry.coordinates;
        const dlat = fLat - latlng.lat;
        const dlng = fLng - latlng.lng;
        return Math.sqrt(dlat * dlat + dlng * dlng) < 0.1; // ~11km radius
      });
      if (nearby.length > 0) nearbyFeatures.push({ layer: layer.name, count: nearby.length, features: nearby.slice(0, 5) });
    });

    const lensLabel = LENS_OPTIONS.find((l) => l.id === lens)?.label || 'General';
    const poisContext = LENS_POI_CONTEXT[lens] || LENS_POI_CONTEXT.general;
    const recsContext = LENS_RECOMMENDATION_CONTEXT[lens] || LENS_RECOMMENDATION_CONTEXT.general;

    try {
      const contextParts = [
        `Coordinates: lat ${latlng.lat.toFixed(6)}, lng ${latlng.lng.toFixed(6)}`,
        `Region: Puerto Rico`,
        `Analysis lens: ${lensLabel}`,
        layerName ? `Source layer: ${layerName}` : '',
        properties && Object.keys(properties).length > 0
          ? `Feature properties: ${Object.entries(properties).map(([k, v]) => `${k}=${v}`).join(', ')}`
          : '',
        nearbyFeatures.length > 0
          ? `Nearby data layers: ${nearbyFeatures.map((n) => `${n.layer} (${n.count} points nearby)`).join(', ')}`
          : 'No nearby layer data loaded.',
      ].filter(Boolean).join('\n');

      const res = await federation.integrations.Core.InvokeLLM({
        prompt: `You are a geospatial data analyst for Puerto Rico specializing in ${lensLabel} analysis. Analyze this map location through the ${lensLabel} lens and return a JSON object with this exact structure:
{
  "location_name": "best guess place name",
  "municipality": "municipality name",
  "region_type": "urban|rural|coastal|mountainous|industrial|residential|commercial",
  "elevation_estimate": "low|medium|high",
  "risk_level": "low|moderate|high (relevant to ${lensLabel} context)",
  "key_facts": ["fact 1 relevant to ${lensLabel}", "fact 2", "fact 3"],
  "nearby_pois": ["list notable nearby ${poisContext}"],
  "data_summary": "2-3 sentence summary focusing on ${lensLabel} characteristics of this location",
  "recommendations": ["actionable recommendation related to ${recsContext}", "recommendation 2"]
}

Context:
${contextParts}

Return ONLY the JSON object, no other text.`,
        response_json_schema: {
          type: 'object',
          properties: {
            location_name: { type: 'string' },
            municipality: { type: 'string' },
            region_type: { type: 'string' },
            elevation_estimate: { type: 'string' },
            risk_level: { type: 'string' },
            key_facts: { type: 'array', items: { type: 'string' } },
            nearby_pois: { type: 'array', items: { type: 'string' } },
            data_summary: { type: 'string' },
            recommendations: { type: 'array', items: { type: 'string' } },
          },
        },
      });

      const parsed = typeof res === 'string' ? JSON.parse(res) : (res?.result ? JSON.parse(res.result) : res);
      setAnalytics({ ...parsed, nearbyFeatures, latlng });
    } catch (err) {
      setError(err.message || 'Failed to analyze location');
    } finally {
      setLoading(false);
    }
  };

  const riskColor = {
    low: 'text-accent',
    moderate: 'text-yellow-400',
    high: 'text-destructive',
  };

  const regionIcon = analytics?.region_type;

  return (
    <div className="fixed right-4 top-16 z-[1500] w-80 panel-glass rounded-lg border border-primary/25 shadow-2xl flex flex-col max-h-[calc(100vh-5rem)]">
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2.5 border-b border-border/50 shrink-0">
        <BarChart2 className="w-3.5 h-3.5 text-primary" />
        <span className="font-mono text-xs text-primary font-semibold tracking-wider flex-1">LOCATION ANALYTICS</span>
        <button onClick={fetchAnalytics} disabled={loading} className="text-muted-foreground/50 hover:text-primary transition-colors disabled:opacity-30" title="Refresh">
          <RefreshCw className={cn('w-3 h-3', loading && 'animate-spin')} />
        </button>
        <button onClick={onClose} className="text-muted-foreground/50 hover:text-foreground transition-colors">
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Coords */}
      {latlng && (
        <div className="flex items-center gap-2 px-3 py-1.5 border-b border-border/30 bg-secondary/20 shrink-0">
          <MapPin className="w-3 h-3 text-primary/60 shrink-0" />
          <span className="font-mono text-xs text-primary/80 flex-1 truncate">
            {latlng.lat.toFixed(5)}, {latlng.lng.toFixed(5)}
          </span>
          {layerName && <span className="font-mono text-xs text-muted-foreground/40 truncate max-w-[90px]">{layerName}</span>}
          <button
            onClick={() => navigator.clipboard.writeText(`${latlng.lat.toFixed(6)}, ${latlng.lng.toFixed(6)}`)}
            className="text-muted-foreground/30 hover:text-primary transition-colors shrink-0"
          >
            <Copy className="w-2.5 h-2.5" />
          </button>
        </div>
      )}

      {/* Lens selector */}
      <div className="px-3 py-2 border-b border-border/30 shrink-0 bg-secondary/10">
        <div className="flex items-center gap-1.5 mb-1.5">
          <Brain className="w-3 h-3 text-muted-foreground/50" />
          <span className="font-mono text-xs text-muted-foreground/50">Analysis Lens</span>
        </div>
        <div className="flex flex-wrap gap-1">
          {LENS_OPTIONS.map((l) => (
            <button
              key={l.id}
              onClick={() => setLens(l.id)}
              className={cn(
                'px-1.5 py-0.5 rounded border font-mono text-xs transition-all',
                lens === l.id
                  ? 'border-primary/60 bg-primary/10 text-primary'
                  : 'border-border/20 text-muted-foreground/40 hover:border-border/50 hover:text-muted-foreground'
              )}
            >
              {l.label}
            </button>
          ))}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-border/40 shrink-0">
        {['overview', 'data', 'insights'].map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              'flex-1 py-1.5 font-mono text-xs transition-all capitalize',
              tab === t ? 'text-primary border-b-2 border-primary bg-primary/5' : 'text-muted-foreground/50 hover:text-foreground'
            )}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {loading && (
          <div className="flex flex-col items-center justify-center gap-3 py-12">
            <Loader2 className="w-6 h-6 text-primary animate-spin" />
            <p className="font-mono text-xs text-muted-foreground/50">Analyzing location...</p>
          </div>
        )}

        {error && !loading && (
          <div className="p-4 space-y-2">
            <div className="flex items-start gap-2 p-3 rounded border border-destructive/30 bg-destructive/10">
              <AlertCircle className="w-4 h-4 text-destructive shrink-0 mt-0.5" />
              <p className="font-mono text-xs text-destructive">{error}</p>
            </div>
            <button onClick={fetchAnalytics} className="w-full py-1.5 rounded border border-border/40 font-mono text-xs text-muted-foreground hover:text-foreground transition-colors">
              Retry
            </button>
          </div>
        )}

        {!loading && !error && analytics && tab === 'overview' && (
          <div className="p-3 space-y-3">
            {/* Place name */}
            <div>
              <h3 className="font-mono text-sm text-foreground font-semibold">{analytics.location_name}</h3>
              {analytics.municipality && (
                <p className="font-mono text-xs text-muted-foreground/60 mt-0.5">{analytics.municipality}, Puerto Rico</p>
              )}
            </div>

            {/* Stat cards */}
            <div className="grid grid-cols-2 gap-2">
              <StatCard label="Region Type" value={analytics.region_type} />
              <StatCard label="Risk Level" value={analytics.risk_level} color={riskColor[analytics.risk_level] || 'text-foreground'} />
              <StatCard label="Elevation" value={analytics.elevation_estimate} />
              <StatCard label="Nearby Layers" value={analytics.nearbyFeatures?.length ?? 0} sub="data layers" />
            </div>

            {/* Summary */}
            {analytics.data_summary && (
              <div className="rounded border border-border/30 bg-card/20 p-2.5">
                <p className="font-mono text-xs text-foreground/70 leading-relaxed">{analytics.data_summary}</p>
              </div>
            )}

            {/* Key facts */}
            {analytics.key_facts?.length > 0 && (
              <div className="space-y-1">
                <div className="font-mono text-xs text-muted-foreground/50 mb-1">Key Facts</div>
                {analytics.key_facts.map((f, i) => (
                  <div key={i} className="flex items-start gap-2 font-mono text-xs text-foreground/70">
                    <span className="text-primary/50 shrink-0 mt-0.5">›</span>
                    <span>{f}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {!loading && !error && analytics && tab === 'data' && (
          <div className="p-3 space-y-3">
            {/* Feature properties */}
            {properties && Object.keys(properties).length > 0 && (
              <div>
                <div className="font-mono text-xs text-muted-foreground/50 mb-1.5">Feature Properties</div>
                <div className="rounded border border-border/30 overflow-hidden">
                  {Object.entries(properties)
                    .filter(([, v]) => v !== null && v !== undefined && v !== '')
                    .map(([k, v]) => (
                      <div key={k} className="flex items-center gap-2 px-2.5 py-1.5 border-b border-border/20 last:border-0 hover:bg-secondary/20 group">
                        <span className="font-mono text-xs text-muted-foreground/50 w-2/5 truncate">{k}</span>
                        <span className="font-mono text-xs text-foreground/80 flex-1 break-all">{String(v)}</span>
                        <button onClick={() => navigator.clipboard.writeText(String(v))} className="opacity-0 group-hover:opacity-100 text-muted-foreground/30 hover:text-primary transition-all">
                          <Copy className="w-2.5 h-2.5" />
                        </button>
                      </div>
                    ))}
                </div>
              </div>
            )}

            {/* Nearby layer data */}
            {analytics.nearbyFeatures?.length > 0 ? (
              <div>
                <div className="font-mono text-xs text-muted-foreground/50 mb-1.5 flex items-center gap-1.5">
                  <Layers className="w-3 h-3" />
                  Nearby Data (~11km) · {LENS_OPTIONS.find((l) => l.id === lens)?.label} lens
                </div>
                {analytics.nearbyFeatures.map((n, i) => (
                  <div key={i} className="mb-2 rounded border border-border/30 bg-card/20 overflow-hidden">
                    <div className="flex items-center gap-2 px-2.5 py-1.5 bg-secondary/20 border-b border-border/20">
                      <span className="font-mono text-xs text-foreground/70 flex-1">{n.layer}</span>
                      <span className="font-mono text-xs text-primary">{n.count} pts</span>
                    </div>
                    {n.features.slice(0, 3).map((f, j) => (
                      <div key={j} className="px-2.5 py-1 font-mono text-xs text-muted-foreground/50 border-b border-border/10 last:border-0">
                        {f.properties?.name || f.properties?.label || `Feature ${j + 1}`}
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-6">
                <Layers className="w-5 h-5 text-muted-foreground/20 mx-auto mb-2" />
                <p className="font-mono text-xs text-muted-foreground/30">No nearby layer data</p>
                <p className="font-mono text-xs text-muted-foreground/20">Upload geodata to see nearby features</p>
              </div>
            )}
          </div>
        )}

        {!loading && !error && analytics && tab === 'insights' && (
          <div className="p-3 space-y-3">
            {/* Nearby POIs */}
            {analytics.nearby_pois?.length > 0 && (
              <div>
                <div className="font-mono text-xs text-muted-foreground/50 mb-1.5 flex items-center gap-1.5">
                  <MapPin className="w-3 h-3" />
                  Notable POIs · {LENS_OPTIONS.find((l) => l.id === lens)?.label} lens
                </div>
                {analytics.nearby_pois.map((p, i) => (
                  <div key={i} className="flex items-start gap-2 font-mono text-xs text-foreground/70 py-1 border-b border-border/20 last:border-0">
                    <span className="text-accent/60 shrink-0">·</span>
                    <span>{p}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Recommendations */}
            {analytics.recommendations?.length > 0 && (
              <div>
                <div className="font-mono text-xs text-muted-foreground/50 mb-1.5 flex items-center gap-1.5">
                  <TrendingUp className="w-3 h-3" />
                  Recommendations · {LENS_OPTIONS.find((l) => l.id === lens)?.label}
                </div>
                {analytics.recommendations.map((r, i) => (
                  <div key={i} className="rounded border border-accent/20 bg-accent/5 p-2 mb-1.5 font-mono text-xs text-foreground/70 leading-relaxed">
                    {r}
                  </div>
                ))}
              </div>
            )}

            {!analytics.nearby_pois?.length && !analytics.recommendations?.length && (
              <div className="text-center py-8">
                <Brain className="w-6 h-6 text-muted-foreground/20 mx-auto mb-2" />
                <p className="font-mono text-xs text-muted-foreground/30">No insights available</p>
              </div>
            )}
          </div>
        )}

        {!loading && !error && !analytics && (
          <div className="flex flex-col items-center justify-center gap-2 py-12">
            <BarChart2 className="w-6 h-6 text-muted-foreground/20" />
            <p className="font-mono text-xs text-muted-foreground/40 text-center px-4">Click a location on the map to view analytics</p>
          </div>
        )}
      </div>
    </div>
  );
}
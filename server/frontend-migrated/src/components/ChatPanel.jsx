import { useState, useRef, useEffect } from 'react';
import { Send, Sparkles, MapPin, Wand2, RotateCcw, Copy, ChevronDown, ChevronUp, Terminal, Navigation, FlaskConical, X } from 'lucide-react';
import { cn } from '@/lib/utils';

const LENSES = [
  { id: 'hydrologic', label: 'Hydrologic', color: '#00B4D8' },
  { id: 'topographic', label: 'Topographic', color: '#90E0EF' },
  { id: 'seismic', label: 'Seismic', color: '#F4A261' },
  { id: 'vegetation', label: 'Vegetation', color: '#52B788' },
  { id: 'urban', label: 'Urban / Infrastructure', color: '#ADB5BD' },
  { id: 'climate', label: 'Climate / Weather', color: '#4CC9F0' },
  { id: 'coastal', label: 'Coastal / Marine', color: '#48CAE4' },
  { id: 'geologic', label: 'Geologic', color: '#E9C46A' },
  { id: 'socioeconomic', label: 'Socioeconomic', color: '#C77DFF' },
];

const TIMEFRAMES = [
  { id: 'current', label: 'Current Snapshot' },
  { id: '1y', label: 'Past 1 Year' },
  { id: '5y', label: 'Past 5 Years' },
  { id: '10y', label: 'Past 10 Years' },
  { id: '30y', label: 'Past 30 Years' },
  { id: 'historical', label: 'Historical (pre-2000)' },
  { id: 'projected', label: 'Future Projection (2030–2050)' },
];

const MODES = [
  { id: 'pipeline', label: 'Analysis Pipeline', icon: FlaskConical, placeholder: 'Additional context or notes...' },
  { id: 'query', label: 'Query Layer', icon: Terminal, placeholder: 'Ask a question about the selected layer...' },
  { id: 'region', label: 'Analyze Region', icon: MapPin, placeholder: 'Describe what to analyze in the drawn region...' },
  { id: 'generate', label: 'Generate Geo', icon: Wand2, placeholder: 'Describe geographic data to generate...' },
  { id: 'location', label: 'Location AI', icon: Navigation, placeholder: 'Ask about the current map view or selected point...' },
];

function PipelineBuilder({ clickedPoint, mapCenter, pendingRegion, onClearRegion, onRun, isStreaming }) {
  const [step, setStep] = useState(1);
  const [areaMode, setAreaMode] = useState('coords'); // 'coords' | 'map' | 'region'
  const [coords, setCoords] = useState({ lat: '', lng: '', radius: '5' });
  const [selectedLenses, setSelectedLenses] = useState([]);
  const [timeframe, setTimeframe] = useState('');
  const [notes, setNotes] = useState('');

  // Auto-fill coords from clicked point
  useEffect(() => {
    if (clickedPoint?.latlng) {
      setCoords((p) => ({ ...p, lat: clickedPoint.latlng.lat.toFixed(6), lng: clickedPoint.latlng.lng.toFixed(6) }));
    }
  }, [clickedPoint]);

  const areaReady = (() => {
    if (areaMode === 'coords') return coords.lat !== '' && coords.lng !== '';
    if (areaMode === 'map') return !!clickedPoint?.latlng;
    if (areaMode === 'region') return !!pendingRegion;
    return false;
  })();

  const canRun = areaReady && selectedLenses.length > 0 && timeframe !== '';

  const toggleLens = (id) => {
    setSelectedLenses((prev) => prev.includes(id) ? prev.filter((l) => l !== id) : [...prev, id]);
  };

  const buildPrompt = () => {
    let areaDesc = '';
    if (areaMode === 'coords') {
      areaDesc = `coordinates lat ${coords.lat}, lng ${coords.lng} (radius: ${coords.radius} km)`;
    } else if (areaMode === 'map' && clickedPoint?.latlng) {
      areaDesc = `selected map point lat ${clickedPoint.latlng.lat.toFixed(6)}, lng ${clickedPoint.latlng.lng.toFixed(6)}`;
    } else if (areaMode === 'region') {
      areaDesc = `drawn region on map`;
    }
    const lensDesc = selectedLenses.map((id) => LENSES.find((l) => l.id === id)?.label).join(', ');
    const timeDesc = TIMEFRAMES.find((t) => t.id === timeframe)?.label || timeframe;
    return `Run a geographic analysis pipeline for Puerto Rico.\n\nArea: ${areaDesc}\nAnalysis lenses: ${lensDesc}\nTimeframe: ${timeDesc}${notes.trim() ? `\nAdditional context: ${notes.trim()}` : ''}\n\nProvide a structured multi-lens analysis report covering each requested lens with relevant data, patterns, risks, and insights for the specified area and timeframe.`;
  };

  const STEP_LABELS = ['1 Area', '2 Lens', '3 Timeframe'];

  return (
    <div className="flex flex-col flex-1 min-h-0 overflow-y-auto">
      {/* Step indicators */}
      <div className="flex shrink-0 border-b border-border/30">
        {STEP_LABELS.map((label, i) => {
          const n = i + 1;
          const done = step > n;
          const active = step === n;
          return (
            <button
              key={n}
              onClick={() => setStep(n)}
              className={cn(
                'flex-1 flex items-center justify-center gap-1.5 py-2 font-mono text-xs transition-all border-b-2',
                active ? 'border-primary text-primary bg-primary/5' : done ? 'border-accent/50 text-accent/70' : 'border-transparent text-muted-foreground/40 hover:text-muted-foreground'
              )}
            >
              <span className={cn('w-4 h-4 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0', active ? 'bg-primary text-primary-foreground' : done ? 'bg-accent/30 text-accent' : 'bg-secondary text-muted-foreground/40')}>
                {done ? '✓' : n}
              </span>
              {label}
            </button>
          );
        })}
      </div>

      {/* Step 1: Area */}
      {step === 1 && (
        <div className="p-3 space-y-3">
          <p className="font-mono text-xs text-muted-foreground/60">Define the area of interest</p>
          {/* Area mode toggle */}
          <div className="flex gap-1">
            {[['coords', 'Coordinates'], ['map', 'Map Point'], ['region', 'Drawn Region']].map(([id, label]) => (
              <button key={id} onClick={() => setAreaMode(id)} className={cn('flex-1 py-1 rounded border font-mono text-xs transition-all', areaMode === id ? 'border-primary/60 bg-primary/10 text-primary' : 'border-border/30 text-muted-foreground/50 hover:border-border hover:text-muted-foreground')}>
                {label}
              </button>
            ))}
          </div>

          {areaMode === 'coords' && (
            <div className="space-y-2">
              <div className="flex gap-2">
                <div className="flex-1">
                  <label className="font-mono text-xs text-muted-foreground/50 block mb-0.5">Latitude</label>
                  <input value={coords.lat} onChange={(e) => setCoords((p) => ({ ...p, lat: e.target.value }))}
                    placeholder="18.4655" className="w-full bg-secondary/50 border border-border rounded px-2 py-1 text-xs font-mono text-foreground placeholder:text-muted-foreground/30 focus:outline-none focus:border-primary/50" />
                </div>
                <div className="flex-1">
                  <label className="font-mono text-xs text-muted-foreground/50 block mb-0.5">Longitude</label>
                  <input value={coords.lng} onChange={(e) => setCoords((p) => ({ ...p, lng: e.target.value }))}
                    placeholder="-66.1057" className="w-full bg-secondary/50 border border-border rounded px-2 py-1 text-xs font-mono text-foreground placeholder:text-muted-foreground/30 focus:outline-none focus:border-primary/50" />
                </div>
              </div>
              <div>
                <label className="font-mono text-xs text-muted-foreground/50 block mb-0.5">Radius (km)</label>
                <input value={coords.radius} onChange={(e) => setCoords((p) => ({ ...p, radius: e.target.value }))}
                  placeholder="5" className="w-32 bg-secondary/50 border border-border rounded px-2 py-1 text-xs font-mono text-foreground placeholder:text-muted-foreground/30 focus:outline-none focus:border-primary/50" />
              </div>
            </div>
          )}

          {areaMode === 'map' && (
            <div className="space-y-2">
              {clickedPoint?.latlng ? (
                <div className="flex items-center gap-2 px-2 py-1.5 rounded border border-accent/30 bg-accent/5">
                  <div className="w-2 h-2 rounded-full bg-accent shrink-0" />
                  <span className="font-mono text-xs text-accent flex-1">{clickedPoint.latlng.lat.toFixed(5)}, {clickedPoint.latlng.lng.toFixed(5)}</span>
                </div>
              ) : (
                <div className="flex items-center gap-2 px-2 py-1.5 rounded border border-border/30 bg-secondary/20">
                  <div className="w-2 h-2 rounded-full bg-muted-foreground/30 shrink-0" />
                  <span className="font-mono text-xs text-muted-foreground/50">Click a point on the map first</span>
                </div>
              )}
              <div>
                <label className="font-mono text-xs text-muted-foreground/50 block mb-0.5">Radius (km)</label>
                <input value={coords.radius} onChange={(e) => setCoords((p) => ({ ...p, radius: e.target.value }))}
                  placeholder="5" className="w-32 bg-secondary/50 border border-border rounded px-2 py-1 text-xs font-mono text-foreground placeholder:text-muted-foreground/30 focus:outline-none focus:border-primary/50" />
              </div>
            </div>
          )}

          {areaMode === 'region' && (
            <div className="space-y-2">
              {pendingRegion ? (
                <div className="flex items-center gap-2 px-2 py-1.5 rounded border border-primary/30 bg-primary/5">
                  <div className="w-2 h-2 rounded-full bg-primary animate-pulse shrink-0" />
                  <span className="font-mono text-xs text-primary flex-1">Region drawn — ready</span>
                  <button onClick={onClearRegion} className="text-muted-foreground hover:text-destructive"><RotateCcw className="w-3 h-3" /></button>
                </div>
              ) : (
                <div className="flex items-center gap-2 px-2 py-1.5 rounded border border-border/30 bg-secondary/20">
                  <div className="w-2 h-2 rounded-full bg-muted-foreground/30 shrink-0" />
                  <span className="font-mono text-xs text-muted-foreground/50">Draw a region on the map first (□ tool)</span>
                </div>
              )}
              <div>
                <label className="font-mono text-xs text-muted-foreground/50 block mb-0.5">Buffer radius (km)</label>
                <input value={coords.radius} onChange={(e) => setCoords((p) => ({ ...p, radius: e.target.value }))}
                  placeholder="5" className="w-32 bg-secondary/50 border border-border rounded px-2 py-1 text-xs font-mono text-foreground placeholder:text-muted-foreground/30 focus:outline-none focus:border-primary/50" />
              </div>
            </div>
          )}

          <button onClick={() => setStep(2)} disabled={!areaReady}
            className="w-full py-1.5 rounded border font-mono text-xs transition-all bg-primary/10 border-primary/30 text-primary hover:bg-primary/20 disabled:opacity-30 disabled:cursor-not-allowed">
            Next →
          </button>
        </div>
      )}

      {/* Step 2: Lens */}
      {step === 2 && (
        <div className="p-3 space-y-3">
          <p className="font-mono text-xs text-muted-foreground/60">Select one or more analysis lenses</p>
          <div className="space-y-1">
            {LENSES.map((lens) => {
              const active = selectedLenses.includes(lens.id);
              return (
                <button key={lens.id} onClick={() => toggleLens(lens.id)}
                  className={cn('w-full flex items-center gap-2 px-2 py-1.5 rounded border font-mono text-xs transition-all text-left', active ? 'border-primary/40 bg-primary/5 text-foreground' : 'border-border/20 text-muted-foreground/60 hover:border-border/50 hover:text-muted-foreground')}>
                  <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: active ? lens.color : 'transparent', border: `1px solid ${lens.color}` }} />
                  {lens.label}
                  {active && <span className="ml-auto text-primary/60">✓</span>}
                </button>
              );
            })}
          </div>
          {selectedLenses.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {selectedLenses.map((id) => {
                const l = LENSES.find((x) => x.id === id);
                return (
                  <span key={id} className="flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-mono border border-border/30 bg-secondary/40"
                    style={{ color: l?.color }}>
                    {l?.label}
                    <button onClick={() => toggleLens(id)} className="hover:text-destructive transition-colors"><X className="w-2.5 h-2.5" /></button>
                  </span>
                );
              })}
            </div>
          )}
          <div className="flex gap-2">
            <button onClick={() => setStep(1)} className="flex-1 py-1.5 rounded border border-border/30 font-mono text-xs text-muted-foreground hover:text-foreground transition-colors">← Back</button>
            <button onClick={() => setStep(3)} disabled={selectedLenses.length === 0}
              className="flex-1 py-1.5 rounded border font-mono text-xs transition-all bg-primary/10 border-primary/30 text-primary hover:bg-primary/20 disabled:opacity-30 disabled:cursor-not-allowed">
              Next →
            </button>
          </div>
        </div>
      )}

      {/* Step 3: Timeframe */}
      {step === 3 && (
        <div className="p-3 space-y-3">
          <p className="font-mono text-xs text-muted-foreground/60">Select the analysis timeframe</p>
          <div className="space-y-1">
            {TIMEFRAMES.map((tf) => (
              <button key={tf.id} onClick={() => setTimeframe(tf.id)}
                className={cn('w-full flex items-center gap-2 px-2 py-1.5 rounded border font-mono text-xs transition-all text-left', timeframe === tf.id ? 'border-primary/40 bg-primary/5 text-primary' : 'border-border/20 text-muted-foreground/60 hover:border-border/50 hover:text-muted-foreground')}>
                <div className={cn('w-2 h-2 rounded-full shrink-0 border', timeframe === tf.id ? 'bg-primary border-primary' : 'border-muted-foreground/30')} />
                {tf.label}
              </button>
            ))}
          </div>

          {/* Optional notes */}
          <div>
            <label className="font-mono text-xs text-muted-foreground/50 block mb-1">Additional context (optional)</label>
            <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} placeholder="Specific focus areas, constraints..."
              className="w-full bg-secondary/50 border border-border rounded px-2 py-1 text-xs font-mono text-foreground placeholder:text-muted-foreground/30 focus:outline-none focus:border-primary/50 resize-none" />
          </div>

          <div className="flex gap-2">
            <button onClick={() => setStep(2)} className="flex-1 py-1.5 rounded border border-border/30 font-mono text-xs text-muted-foreground hover:text-foreground transition-colors">← Back</button>
            <button onClick={() => canRun && onRun(buildPrompt())} disabled={!canRun || isStreaming}
              className="flex-1 py-1.5 rounded border font-mono text-xs transition-all bg-primary/10 border-primary/30 text-primary hover:bg-primary/20 disabled:opacity-30 disabled:cursor-not-allowed flex items-center justify-center gap-1.5">
              <Send className="w-3 h-3" />
              {isStreaming ? 'Running...' : 'Run Pipeline'}
            </button>
          </div>

          {/* Summary preview */}
          {canRun && (
            <div className="rounded border border-border/20 bg-secondary/20 p-2 space-y-1">
              <p className="font-mono text-xs text-muted-foreground/50 font-semibold">Pipeline Summary</p>
              <p className="font-mono text-xs text-muted-foreground/70">
                <span className="text-primary/60">Area:</span> {areaMode === 'coords' ? `${coords.lat}, ${coords.lng}` : areaMode === 'map' ? 'Map selection' : 'Drawn region'}
              </p>
              <p className="font-mono text-xs text-muted-foreground/70">
                <span className="text-primary/60">Lenses:</span> {selectedLenses.length} selected
              </p>
              <p className="font-mono text-xs text-muted-foreground/70">
                <span className="text-primary/60">Timeframe:</span> {TIMEFRAMES.find((t) => t.id === timeframe)?.label}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function ChatPanel({
  layers,
  selectedLayerId,
  onSendQuery,
  onSendRegion,
  onSendGenerate,
  onSendLocation,
  history,
  isStreaming,
  streamingText,
  pendingRegion,
  onClearRegion,
  clickedPoint,
  mapCenter,
}) {
  const [mode, setMode] = useState('pipeline');
  const [input, setInput] = useState('');
  const [collapsed, setCollapsed] = useState(false);
  const bottomRef = useRef();
  const textareaRef = useRef();

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [history, streamingText]);

  const selectedLayer = layers.find((l) => l.id === selectedLayerId);
  const currentMode = MODES.find((m) => m.id === mode);

  const handleSend = () => {
    const text = input.trim();
    if (!text || isStreaming) return;
    setInput('');
    if (mode === 'query') onSendQuery(text);
    else if (mode === 'region') onSendRegion(text);
    else if (mode === 'generate') onSendGenerate(text);
    else if (mode === 'location') onSendLocation && onSendLocation(text);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <aside
      className={cn(
        'panel-glass border-l flex flex-col transition-all duration-300',
        collapsed ? 'w-10' : 'w-80'
      )}
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border/50 shrink-0">
        {!collapsed && (
          <>
            <Sparkles className="w-3.5 h-3.5 text-primary" />
            <span className="font-mono text-xs text-primary font-semibold tracking-wider flex-1">LLM CONSOLE</span>
          </>
        )}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="text-muted-foreground hover:text-primary transition-colors ml-auto"
        >
          {collapsed ? <ChevronDown className="w-3.5 h-3.5 rotate-90" /> : <ChevronUp className="w-3.5 h-3.5 rotate-90" />}
        </button>
      </div>

      {!collapsed && (
        <>
          {/* Mode selector */}
          <div className="flex border-b border-border/50">
            {MODES.map((m) => {
              const Icon = m.icon;
              return (
                <button
                  key={m.id}
                  onClick={() => setMode(m.id)}
                  className={cn(
                    'flex-1 flex items-center justify-center gap-1 py-2 font-mono text-xs transition-all',
                    mode === m.id
                      ? 'text-primary border-b-2 border-primary bg-primary/5'
                      : 'text-muted-foreground hover:text-foreground'
                  )}
                  title={m.label}
                >
                  <Icon className="w-3 h-3" />
                  <span className="hidden xl:inline">{m.label.split(' ')[0]}</span>
                </button>
              );
            })}
          </div>

          {/* Pipeline mode */}
          {mode === 'pipeline' && (
            <PipelineBuilder
              clickedPoint={clickedPoint}
              mapCenter={mapCenter}
              pendingRegion={pendingRegion}
              onClearRegion={onClearRegion}
              isStreaming={isStreaming}
              onRun={(prompt) => onSendLocation && onSendLocation(prompt)}
            />
          )}

          {/* Context info for other modes */}
          {mode === 'query' && (
            <div className="px-3 py-2 border-b border-border/30">
              {selectedLayer ? (
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full" style={{ backgroundColor: selectedLayer.color }} />
                  <span className="font-mono text-xs text-muted-foreground truncate">{selectedLayer.name}</span>
                  <span className="font-mono text-xs text-primary">{selectedLayer.featureCount} features</span>
                </div>
              ) : (
                <span className="font-mono text-xs text-muted-foreground/50">← Select a layer to query</span>
              )}
            </div>
          )}

          {mode === 'region' && (
            <div className="px-3 py-2 border-b border-border/30">
              {pendingRegion ? (
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />
                  <span className="font-mono text-xs text-primary">Region drawn — ready to analyze</span>
                  <button onClick={onClearRegion} className="ml-auto text-muted-foreground hover:text-destructive">
                    <RotateCcw className="w-3 h-3" />
                  </button>
                </div>
              ) : (
                <span className="font-mono text-xs text-muted-foreground/50">← Draw region on map first</span>
              )}
            </div>
          )}

          {mode === 'location' && (
            <div className="px-3 py-2 border-b border-border/30 space-y-1">
              {clickedPoint?.latlng ? (
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-accent animate-pulse" />
                  <span className="font-mono text-xs text-accent">Selected: {clickedPoint.latlng.lat.toFixed(4)}, {clickedPoint.latlng.lng.toFixed(4)}</span>
                </div>
              ) : mapCenter ? (
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-muted-foreground/40" />
                  <span className="font-mono text-xs text-muted-foreground/60">Map center: {mapCenter.lat.toFixed(4)}, {mapCenter.lng.toFixed(4)}</span>
                </div>
              ) : (
                <span className="font-mono text-xs text-muted-foreground/50">Uses current map view as context</span>
              )}
            </div>
          )}

          {/* History — only shown in non-pipeline modes */}
          {mode !== 'pipeline' && (
            <div className="flex-1 overflow-y-auto p-3 space-y-3 min-h-0">
              {history.length === 0 && !isStreaming && (
                <div className="text-center py-8">
                  <Sparkles className="w-6 h-6 text-muted-foreground/20 mx-auto mb-2" />
                  <p className="font-mono text-xs text-muted-foreground/40">No queries yet</p>
                </div>
              )}
              {history.map((item) => (
                <HistoryItem key={item.id} item={item} />
              ))}
              {isStreaming && streamingText && (
                <div className="space-y-1">
                  <div className="font-mono text-xs text-muted-foreground/50">GEOMIND</div>
                  <div className="panel-glass rounded p-2 text-xs font-mono text-foreground leading-relaxed stream-cursor" style={{ borderColor: 'rgba(0,229,255,0.2)' }}>
                    {streamingText}
                  </div>
                </div>
              )}
              {isStreaming && !streamingText && (
                <div className="flex items-center gap-2 px-2">
                  <div className="flex gap-1">
                    {[0, 1, 2].map((i) => (
                      <div key={i} className="w-1.5 h-1.5 rounded-full bg-primary animate-bounce" style={{ animationDelay: `${i * 0.15}s` }} />
                    ))}
                  </div>
                  <span className="font-mono text-xs text-muted-foreground">Processing...</span>
                </div>
              )}
              <div ref={bottomRef} />
            </div>
          )}

          {/* Pipeline results stream */}
          {mode === 'pipeline' && (isStreaming || history.length > 0) && (
            <div className="flex-1 overflow-y-auto p-3 space-y-3 min-h-0 border-t border-border/30">
              {history.filter((h) => h.mode === 'location').map((item) => (
                <HistoryItem key={item.id} item={item} />
              ))}
              {isStreaming && streamingText && (
                <div className="space-y-1">
                  <div className="font-mono text-xs text-muted-foreground/50">PIPELINE RESULT</div>
                  <div className="panel-glass rounded p-2 text-xs font-mono text-foreground leading-relaxed stream-cursor" style={{ borderColor: 'rgba(0,229,255,0.2)' }}>
                    {streamingText}
                  </div>
                </div>
              )}
              {isStreaming && !streamingText && (
                <div className="flex items-center gap-2 px-2">
                  <div className="flex gap-1">
                    {[0, 1, 2].map((i) => (
                      <div key={i} className="w-1.5 h-1.5 rounded-full bg-primary animate-bounce" style={{ animationDelay: `${i * 0.15}s` }} />
                    ))}
                  </div>
                  <span className="font-mono text-xs text-muted-foreground">Running pipeline...</span>
                </div>
              )}
              <div ref={bottomRef} />
            </div>
          )}

          {/* Input for non-pipeline modes */}
          {mode !== 'pipeline' && (
            <div className="p-3 border-t border-border/50 space-y-2">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={currentMode?.placeholder}
                rows={3}
                disabled={isStreaming}
                className={cn(
                  'w-full bg-secondary/50 border border-border rounded text-xs font-mono text-foreground placeholder:text-muted-foreground/40',
                  'p-2 resize-none focus:outline-none focus:border-primary/50 transition-colors',
                  isStreaming && 'opacity-50 cursor-not-allowed'
                )}
              />
              <button
                onClick={handleSend}
                disabled={!input.trim() || isStreaming}
                className={cn(
                  'w-full flex items-center justify-center gap-2 py-1.5 rounded font-mono text-xs transition-all',
                  'bg-primary/10 border border-primary/30 text-primary',
                  'hover:bg-primary/20 hover:border-primary/60',
                  'disabled:opacity-30 disabled:cursor-not-allowed'
                )}
              >
                <Send className="w-3 h-3" />
                {isStreaming ? 'Streaming...' : 'Execute'}
              </button>
            </div>
          )}
        </>
      )}
    </aside>
  );
}

function HistoryItem({ item }) {
  const [expanded, setExpanded] = useState(true);

  const copyToClipboard = () => {
    navigator.clipboard.writeText(item.response || '');
  };

  return (
    <div className="space-y-1.5">
      <div className="flex items-start gap-2">
        <span className="font-mono text-xs text-primary/60 shrink-0 mt-0.5">›</span>
        <p className="font-mono text-xs text-muted-foreground leading-relaxed">{item.prompt}</p>
      </div>
      {item.response && (
        <div className={cn('rounded border p-2 text-xs space-y-1', item.error ? 'border-destructive/30 bg-destructive/5' : 'border-border/40 bg-card/30')}>
          <div className="flex items-center justify-between mb-1">
            <span className={cn('font-mono text-xs', item.error ? 'text-destructive' : 'text-primary/60')}>
              {item.error ? 'ERROR' : 'GEOMIND'}
            </span>
            <div className="flex gap-1">
              <button onClick={copyToClipboard} className="text-muted-foreground/40 hover:text-primary">
                <Copy className="w-2.5 h-2.5" />
              </button>
              <button onClick={() => setExpanded(!expanded)} className="text-muted-foreground/40 hover:text-primary">
                <ChevronDown className={cn('w-2.5 h-2.5 transition-transform', !expanded && 'rotate-180')} />
              </button>
            </div>
          </div>
          {expanded && (
            <div className="font-mono leading-relaxed text-foreground/80 whitespace-pre-wrap">
              {item.response}
            </div>
          )}
        </div>
      )}
      <div className="flex items-center gap-2">
        <span className="font-mono text-xs text-muted-foreground/30">{item.mode}</span>
        <span className="font-mono text-xs text-muted-foreground/20">{new Date(item.timestamp).toLocaleTimeString()}</span>
        {item.layerGenerated && (
          <span className="font-mono text-xs text-accent px-1 rounded border border-accent/30">+layer</span>
        )}
      </div>
    </div>
  );
}
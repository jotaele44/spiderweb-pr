import { useState } from 'react';
import { ChevronDown, MapPin, MousePointer, Copy, Brain, Send, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { federation } from '@/api/federationClient';

export default function PointInspectorPanel({ collapsed, onToggle, clickedPoint }) {
  const { latlng, properties, layerName } = clickedPoint || {};
  const [llmPrompt, setLlmPrompt] = useState('');
  const [llmResponse, setLlmResponse] = useState('');
  const [llmLoading, setLlmLoading] = useState(false);

  const propEntries = properties
    ? Object.entries(properties).filter(([, v]) => v !== null && v !== undefined && v !== '')
    : [];

  const copyCoords = () => {
    if (!latlng) return;
    navigator.clipboard.writeText(`${latlng.lat.toFixed(6)}, ${latlng.lng.toFixed(6)}`);
  };

  const runLlm = async () => {
    if (!llmPrompt.trim() || !latlng) return;
    setLlmLoading(true);
    setLlmResponse('');
    const coordContext = `Location: lat ${latlng.lat.toFixed(6)}, lng ${latlng.lng.toFixed(6)}${layerName ? ` (layer: ${layerName})` : ''}.`;
    const propsContext = propEntries.length
      ? ' Properties: ' + propEntries.map(([k, v]) => `${k}=${v}`).join(', ') + '.'
      : '';
    try {
      const res = await federation.integrations.Core.InvokeLLM({
        prompt: `${coordContext}${propsContext}\n\nUser question: ${llmPrompt}`,
      });
      setLlmResponse(typeof res === 'string' ? res : res?.result || JSON.stringify(res));
    } finally {
      setLlmLoading(false);
    }
  };

  return (
    <div className={cn('panel-glass border-t flex flex-col transition-all duration-300 shrink-0', collapsed ? 'h-8' : 'h-72')}>
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-1.5 border-b border-border/50 shrink-0 cursor-pointer" onClick={onToggle}>
        <MapPin className="w-3.5 h-3.5 text-primary" />
        <span className="font-mono text-xs text-primary font-semibold tracking-wider flex-1">POINT INSPECTOR</span>
        {latlng && !collapsed && (
          <span className="font-mono text-xs text-muted-foreground">
            {latlng.lat.toFixed(4)}, {latlng.lng.toFixed(4)}
          </span>
        )}
        <ChevronDown className={cn('w-3.5 h-3.5 text-muted-foreground transition-transform', !collapsed && 'rotate-180')} />
      </div>

      {!collapsed && (
        <div className="flex flex-1 min-h-0 divide-x divide-border/30">

          {/* Left: coordinates + properties */}
          <div className="flex flex-col w-1/2 min-w-0">
            {!clickedPoint ? (
              <div className="flex-1 flex flex-col items-center justify-center gap-2 text-center px-4">
                <MousePointer className="w-5 h-5 text-muted-foreground/20" />
                <p className="font-mono text-xs text-muted-foreground/40">Click a point on the map to inspect it</p>
              </div>
            ) : (
              <>
                {/* Coords bar */}
                <div className="flex items-center gap-2 px-3 py-1.5 border-b border-border/20 shrink-0">
                  <div className="flex-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 font-mono text-xs">
                    <span className="text-muted-foreground/50">LAT</span>
                    <span className="text-primary">{latlng.lat.toFixed(6)}</span>
                    <span className="text-muted-foreground/50">LNG</span>
                    <span className="text-primary">{latlng.lng.toFixed(6)}</span>
                    {layerName && <span className="text-foreground/50 truncate max-w-[90px]">{layerName}</span>}
                  </div>
                  <button onClick={copyCoords} className="text-muted-foreground/40 hover:text-primary transition-colors shrink-0" title="Copy coords">
                    <Copy className="w-3 h-3" />
                  </button>
                </div>

                {/* Properties table */}
                <div className="flex-1 overflow-y-auto min-h-0">
                  {propEntries.length === 0 ? (
                    <div className="flex items-center justify-center h-full">
                      <p className="font-mono text-xs text-muted-foreground/30">No feature properties</p>
                    </div>
                  ) : (
                    <table className="w-full">
                      <tbody>
                        {propEntries.map(([k, v]) => (
                          <tr key={k} className="border-b border-border/20 hover:bg-primary/5 transition-colors group">
                            <td className="px-3 py-1.5 font-mono text-xs text-muted-foreground/60 w-2/5 truncate">{k}</td>
                            <td className="px-3 py-1.5 font-mono text-xs text-foreground/90 break-all">{String(v)}</td>
                            <td className="px-2 py-1.5 w-5">
                              <button
                                onClick={() => navigator.clipboard.writeText(String(v))}
                                className="opacity-0 group-hover:opacity-100 text-muted-foreground/40 hover:text-primary transition-all"
                              >
                                <Copy className="w-2.5 h-2.5" />
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </>
            )}
          </div>

          {/* Right: LLM analysis */}
          <div className="flex flex-col w-1/2 min-w-0">
            <div className="flex items-center gap-1.5 px-3 py-1.5 border-b border-border/20 shrink-0">
              <Brain className="w-3 h-3 text-primary/70" />
              <span className="font-mono text-xs text-muted-foreground/60">Location Insights</span>
            </div>

            {!clickedPoint ? (
              <div className="flex-1 flex items-center justify-center">
                <p className="font-mono text-xs text-muted-foreground/25 text-center px-4">Select a point to enable analysis</p>
              </div>
            ) : (
              <>
                {/* Response area */}
                <div className="flex-1 overflow-y-auto p-2 min-h-0">
                  {llmLoading && (
                    <div className="flex items-center gap-2 text-muted-foreground font-mono text-xs">
                      <Loader2 className="w-3 h-3 animate-spin" />
                      Analyzing location...
                    </div>
                  )}
                  {!llmLoading && llmResponse && (
                    <div className="font-mono text-xs text-foreground/80 leading-relaxed whitespace-pre-wrap">{llmResponse}</div>
                  )}
                  {!llmLoading && !llmResponse && (
                    <p className="font-mono text-xs text-muted-foreground/30">Ask anything about this location — geography, demographics, risks, nearby POIs...</p>
                  )}
                </div>

                {/* Prompt input */}
                <div className="p-2 border-t border-border/20 flex gap-1.5 shrink-0">
                  <input
                    value={llmPrompt}
                    onChange={(e) => setLlmPrompt(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') runLlm(); }}
                    placeholder="Ask about this location..."
                    disabled={llmLoading}
                    className="flex-1 bg-secondary/50 border border-border rounded px-2 py-1 text-xs font-mono text-foreground placeholder:text-muted-foreground/30 focus:outline-none focus:border-primary/50 transition-colors disabled:opacity-50"
                  />
                  <button
                    onClick={runLlm}
                    disabled={!llmPrompt.trim() || llmLoading}
                    className="px-2 py-1 rounded bg-primary/10 border border-primary/30 text-primary hover:bg-primary/20 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                  >
                    {llmLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Send className="w-3 h-3" />}
                  </button>
                </div>
              </>
            )}
          </div>

        </div>
      )}
    </div>
  );
}
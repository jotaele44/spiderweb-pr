import { Activity, Database, Cpu } from 'lucide-react';

export default function StatusBar({ layers, history, isStreaming }) {
  const totalFeatures = layers.reduce((sum, l) => sum + (l.featureCount || 0), 0);

  return (
    <footer className="h-6 panel-glass border-t flex items-center px-4 gap-6 shrink-0">
      <div className="flex items-center gap-1.5">
        <Activity className="w-3 h-3 text-muted-foreground/50" />
        <span className="font-mono text-xs text-muted-foreground/50">
          {isStreaming ? (
            <span className="text-primary animate-pulse">STREAMING</span>
          ) : (
            'IDLE'
          )}
        </span>
      </div>

      <div className="flex items-center gap-1.5">
        <Database className="w-3 h-3 text-muted-foreground/50" />
        <span className="font-mono text-xs text-muted-foreground/50">
          {layers.length} layers · {totalFeatures.toLocaleString()} features
        </span>
      </div>

      <div className="flex items-center gap-1.5">
        <Cpu className="w-3 h-3 text-muted-foreground/50" />
        <span className="font-mono text-xs text-muted-foreground/50">
          {history.length} queries
        </span>
      </div>

      <div className="flex-1" />

      <span className="font-mono text-xs text-muted-foreground/30">
        GeoMind — GIS + LLM Analysis Platform
      </span>
    </footer>
  );
}
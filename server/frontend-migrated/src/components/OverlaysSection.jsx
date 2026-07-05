import { useState } from 'react';
import { Globe, ChevronDown, Info } from 'lucide-react';
import { cn } from '@/lib/utils';
import { OVERLAYS, CATEGORY_LABELS } from '@/lib/overlayDefs';

export default function OverlaysSection({ activeOverlays, onToggle, onOpacityChange }) {
  const [open, setOpen] = useState(true);
  const [hoveredId, setHoveredId] = useState(null);

  // Group by category
  const byCategory = OVERLAYS.reduce((acc, o) => {
    if (!acc[o.category]) acc[o.category] = [];
    acc[o.category].push(o);
    return acc;
  }, {});

  return (
    <div className="border-b border-border/40">
      {/* Section header */}
      <div
        className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-secondary/30 transition-colors select-none"
        onClick={() => setOpen((v) => !v)}
      >
        <Globe className="w-3.5 h-3.5 text-primary shrink-0" />
        <span className="font-mono text-xs text-primary font-semibold tracking-wider flex-1">MAP OVERLAYS</span>
        <span className="font-mono text-xs text-muted-foreground/50">
          {activeOverlays.length > 0 ? `${activeOverlays.length} active` : ''}
        </span>
        <ChevronDown className={cn('w-3.5 h-3.5 text-muted-foreground transition-transform shrink-0', !open && '-rotate-90')} />
      </div>

      {open && (
        <div className="px-2 pb-2 space-y-3">
          {Object.entries(byCategory).map(([cat, items]) => (
            <div key={cat}>
              <p className="font-mono text-[10px] text-muted-foreground/40 uppercase tracking-widest px-1 mb-1">
                {CATEGORY_LABELS[cat] || cat}
              </p>
              <div className="space-y-1">
                {items.map((overlay) => {
                  const isActive = activeOverlays.some((a) => a.id === overlay.id);
                  const activeEntry = activeOverlays.find((a) => a.id === overlay.id);
                  const opacity = activeEntry?.opacity ?? overlay.opacity;

                  return (
                    <div
                      key={overlay.id}
                      className={cn(
                        'rounded border transition-all',
                        isActive ? 'border-primary/40 bg-primary/5' : 'border-border/30 bg-card/20'
                      )}
                    >
                      <div className="flex items-center gap-2 p-2">
                        <span className="text-sm shrink-0">{overlay.icon}</span>
                        <button
                          className="flex-1 text-left"
                          onClick={() => onToggle(overlay)}
                        >
                          <span className={cn('font-mono text-xs block truncate', isActive ? 'text-primary' : 'text-foreground/80')}>
                            {overlay.name}
                          </span>
                        </button>
                        <button
                          onMouseEnter={() => setHoveredId(overlay.id)}
                          onMouseLeave={() => setHoveredId(null)}
                          className="text-muted-foreground/30 hover:text-muted-foreground transition-colors relative"
                        >
                          <Info className="w-3 h-3" />
                          {hoveredId === overlay.id && (
                            <div className="absolute right-0 bottom-full mb-1 w-40 p-2 rounded border border-border/50 bg-card text-xs font-mono text-muted-foreground z-50 pointer-events-none">
                              {overlay.description}
                            </div>
                          )}
                        </button>
                        {/* Toggle switch */}
                        <button
                          onClick={() => onToggle(overlay)}
                          className={cn(
                            'w-8 h-4 rounded-full transition-colors shrink-0 relative',
                            isActive ? 'bg-primary/60' : 'bg-secondary'
                          )}
                        >
                          <span className={cn(
                            'absolute top-0.5 w-3 h-3 rounded-full transition-all',
                            isActive ? 'left-4 bg-primary' : 'left-0.5 bg-muted-foreground/40'
                          )} />
                        </button>
                      </div>

                      {/* Opacity slider when active */}
                      {isActive && (
                        <div className="px-3 pb-2 flex items-center gap-2">
                          <span className="font-mono text-[10px] text-muted-foreground/50 shrink-0">Opacity</span>
                          <input
                            type="range"
                            min={5} max={100} step={5}
                            value={Math.round(opacity * 100)}
                            onChange={(e) => onOpacityChange(overlay.id, e.target.value / 100)}
                            className="flex-1 h-1 accent-primary cursor-pointer"
                          />
                          <span className="font-mono text-[10px] text-muted-foreground/50 w-6 text-right shrink-0">
                            {Math.round(opacity * 100)}%
                          </span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
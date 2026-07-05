import { useState } from 'react';
import { Eye, EyeOff, Trash2, ChevronDown, ChevronRight, Layers, Filter, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Slider } from '@/components/ui/slider';

export default function LayerPanel({ layers, onToggleVisibility, onDeleteLayer, onUpdateLayer, onSelectLayer, selectedLayerId, locationGroups }) {
  const [collapsed, setCollapsed] = useState(false);
  const [hiddenGroups, setHiddenGroups] = useState(new Set());
  const [filterOpen, setFilterOpen] = useState(false);

  const toggleGroupFilter = (id) => {
    setHiddenGroups((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const allGroups = locationGroups || [];
  const activeFilters = hiddenGroups.size;

  return (
    <aside className={cn('panel-glass border-r flex flex-col transition-all duration-300', collapsed ? 'w-10' : 'w-64')}>
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border/50">
        {!collapsed && (
          <div className="flex items-center gap-2 flex-1">
            <Layers className="w-3.5 h-3.5 text-primary" />
            <span className="font-mono text-xs text-primary font-semibold tracking-wider">LAYERS</span>
            <span className="font-mono text-xs text-muted-foreground">({layers.length})</span>
          </div>
        )}
        {!collapsed && allGroups.length > 0 && (
          <button
            onClick={() => setFilterOpen(!filterOpen)}
            className={cn('relative text-muted-foreground hover:text-primary transition-colors', filterOpen && 'text-primary')}
            title="Filter by group"
          >
            <Filter className="w-3.5 h-3.5" />
            {activeFilters > 0 && (
              <span className="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-primary text-primary-foreground font-mono text-[8px] flex items-center justify-center leading-none">
                {activeFilters}
              </span>
            )}
          </button>
        )}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="text-muted-foreground hover:text-primary transition-colors ml-1"
        >
          {collapsed ? <ChevronRight className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </button>
      </div>

      {!collapsed && (
        <>
          {/* Group filters */}
          {filterOpen && allGroups.length > 0 && (
            <div className="px-3 py-2 border-b border-border/40 bg-secondary/20 space-y-1.5">
              <div className="flex items-center justify-between mb-1">
                <span className="font-mono text-xs text-muted-foreground/60">Show/hide POI groups</span>
                {activeFilters > 0 && (
                  <button
                    onClick={() => setHiddenGroups(new Set())}
                    className="flex items-center gap-1 font-mono text-xs text-muted-foreground/50 hover:text-primary transition-colors"
                  >
                    <X className="w-2.5 h-2.5" />
                    Reset
                  </button>
                )}
              </div>
              {allGroups.map((g) => {
                const hidden = hiddenGroups.has(g.id);
                return (
                  <button
                    key={g.id}
                    onClick={() => toggleGroupFilter(g.id)}
                    className={cn(
                      'w-full flex items-center gap-2 px-2 py-1 rounded border text-xs font-mono transition-all',
                      hidden
                        ? 'border-border/30 bg-transparent text-muted-foreground/40'
                        : 'border-primary/30 bg-primary/5 text-foreground/80'
                    )}
                  >
                    <div className={cn('w-2 h-2 rounded-full border shrink-0', hidden ? 'border-muted-foreground/30 bg-transparent' : 'border-primary bg-primary')} />
                    <span className="flex-1 text-left truncate">{g.name}</span>
                    {hidden && <span className="text-muted-foreground/30">hidden</span>}
                  </button>
                );
              })}
            </div>
          )}

          <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
            {layers.length === 0 && (
              <div className="text-center py-8">
                <Layers className="w-6 h-6 text-muted-foreground/30 mx-auto mb-2" />
                <p className="font-mono text-xs text-muted-foreground/50">No layers loaded</p>
                <p className="font-mono text-xs text-muted-foreground/30 mt-1">Upload geodata to begin</p>
              </div>
            )}

            {layers.map((layer) => (
              <LayerItem
                key={layer.id}
                layer={layer}
                isSelected={selectedLayerId === layer.id}
                onToggleVisibility={() => onToggleVisibility(layer.id)}
                onDelete={() => onDeleteLayer(layer.id)}
                onUpdate={(updates) => onUpdateLayer(layer.id, updates)}
                onSelect={() => onSelectLayer(layer.id)}
              />
            ))}
          </div>
        </>
      )}
    </aside>
  );
}

function LayerItem({ layer, isSelected, onToggleVisibility, onDelete, onUpdate, onSelect }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className={cn('rounded border transition-all', isSelected ? 'border-primary/50 bg-primary/5' : 'border-border/40 hover:border-border bg-card/30')}>
      <div className="flex items-center gap-1.5 p-2 cursor-pointer" onClick={onSelect}>
        <div className="w-2.5 h-2.5 rounded-full shrink-0 border border-white/20" style={{ backgroundColor: layer.color }} />
        <span className={cn('font-mono text-xs flex-1 truncate', layer.visible ? 'text-foreground' : 'text-muted-foreground/40 line-through')}>
          {layer.name}
        </span>
        <button onClick={(e) => { e.stopPropagation(); setExpanded(!expanded); }} className="text-muted-foreground/50 hover:text-primary">
          <ChevronDown className={cn('w-3 h-3 transition-transform', expanded && 'rotate-180')} />
        </button>
        <button onClick={(e) => { e.stopPropagation(); onToggleVisibility(); }} className="text-muted-foreground/50 hover:text-primary">
          {layer.visible ? <Eye className="w-3 h-3" /> : <EyeOff className="w-3 h-3" />}
        </button>
        <button onClick={(e) => { e.stopPropagation(); onDelete(); }} className="text-muted-foreground/50 hover:text-destructive">
          <Trash2 className="w-3 h-3" />
        </button>
      </div>

      {expanded && (
        <div className="px-3 pb-2 space-y-2 border-t border-border/30 pt-2">
          <div className="font-mono text-xs text-muted-foreground space-y-1">
            <div className="flex justify-between"><span>Features</span><span className="text-foreground">{layer.featureCount}</span></div>
            <div className="flex justify-between"><span>Type</span><span className="text-foreground capitalize">{layer.type}</span></div>
            <div className="flex justify-between"><span>Source</span><span className="text-foreground">{layer.source}</span></div>
          </div>
          <div className="space-y-1">
            <div className="flex justify-between font-mono text-xs text-muted-foreground">
              <span>Opacity</span><span>{Math.round(layer.opacity * 100)}%</span>
            </div>
            <Slider value={[layer.opacity * 100]} onValueChange={([v]) => onUpdate({ opacity: v / 100 })} min={10} max={100} step={5} className="w-full" />
          </div>
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs text-muted-foreground">Color</span>
            <input type="color" value={layer.color} onChange={(e) => onUpdate({ color: e.target.value })} className="w-6 h-6 rounded cursor-pointer bg-transparent border border-border" />
            <span className="font-mono text-xs text-muted-foreground">{layer.color}</span>
          </div>
        </div>
      )}
    </div>
  );
}
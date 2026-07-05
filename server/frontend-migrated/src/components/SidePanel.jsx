import { useState } from 'react';
import {
  MapPin, Plus, Trash2, ChevronDown, ChevronRight, FolderOpen, Folder,
  Star, Navigation, Settings2, Upload, Layers, Eye, EyeOff, Filter, X, Clock,
} from 'lucide-react';
import OverlaysSection from './OverlaysSection';
import { cn } from '@/lib/utils';
import { Slider } from '@/components/ui/slider';
import LocationsManager from './LocationsManager';
import BulkImportModal from './BulkImportModal';

// ─── Default data ────────────────────────────────────────────────────────────
const DEFAULT_LOCATIONS = [
  { id: 'pr-overview', name: 'Puerto Rico Overview', lat: 18.2208, lng: -66.5901, zoom: 8, groupId: 'defaults' },
  { id: 'san-juan', name: 'San Juan Metro', lat: 18.4655, lng: -66.1057, zoom: 12, groupId: 'defaults' },
  { id: 'ponce', name: 'Ponce', lat: 18.0110, lng: -66.6141, zoom: 13, groupId: 'defaults' },
  { id: 'mayaguez', name: 'Mayagüez', lat: 18.2013, lng: -67.1397, zoom: 13, groupId: 'defaults' },
  { id: 'caguas', name: 'Caguas', lat: 18.2341, lng: -65.9895, zoom: 13, groupId: 'defaults' },
  { id: 'arecibo', name: 'Arecibo', lat: 18.4724, lng: -66.7220, zoom: 13, groupId: 'defaults' },
  { id: 'vieques', name: 'Vieques Island', lat: 18.1260, lng: -65.4400, zoom: 12, groupId: 'defaults' },
  { id: 'culebra', name: 'Culebra Island', lat: 18.3026, lng: -65.3018, zoom: 13, groupId: 'defaults' },
];

const DEFAULT_GROUPS = [{ id: 'defaults', name: 'Puerto Rico Locations', builtIn: true }];

// ─── Main panel ──────────────────────────────────────────────────────────────
export default function SidePanel({
  // Locations
  onFlyTo,
  onGroupsChange,
  // Layers
  layers,
  selectedLayerId,
  onToggleVisibility,
  onDeleteLayer,
  onUpdateLayer,
  onSelectLayer,
  onOverlaysChange,
  recentSelections,
}) {
  const [panelCollapsed, setPanelCollapsed] = useState(false);
  const [locOpen, setLocOpen] = useState(true);
  const [layOpen, setLayOpen] = useState(true);

  // Locations state
  const [groups, setGroups] = useState(DEFAULT_GROUPS);
  const [locations, setLocations] = useState(DEFAULT_LOCATIONS);
  const [expandedGroups, setExpandedGroups] = useState({ defaults: true });
  const [addingGroup, setAddingGroup] = useState(false);
  const [newGroupName, setNewGroupName] = useState('');
  const [addingLocation, setAddingLocation] = useState(null);
  const [newLoc, setNewLoc] = useState({ name: '', lat: '', lng: '', zoom: '12' });
  const [activeId, setActiveId] = useState(null);
  const [managerOpen, setManagerOpen] = useState(false);
  const [bulkImportOpen, setBulkImportOpen] = useState(false);
  const [recOpen, setRecOpen] = useState(true);

  // Overlays — local state, lifted up via onOverlaysChange
  const [activeOverlays, setActiveOverlays] = useState([]);

  const handleOverlayToggle = (overlay) => {
    setActiveOverlays((prev) => {
      const next = prev.find((a) => a.id === overlay.id)
        ? prev.filter((a) => a.id !== overlay.id)
        : [...prev, { id: overlay.id, url: overlay.url, attribution: overlay.attribution, opacity: overlay.opacity, maxZoom: overlay.maxZoom }];
      onOverlaysChange?.(next);
      return next;
    });
  };

  const handleOverlayOpacity = (id, opacity) => {
    setActiveOverlays((prev) => {
      const next = prev.map((a) => a.id === id ? { ...a, opacity } : a);
      onOverlaysChange?.(next);
      return next;
    });
  };

  // Layers filter state
  const [hiddenGroups, setHiddenGroups] = useState(new Set());
  const [filterOpen, setFilterOpen] = useState(false);

  const updateGroups = (next) => { setGroups(next); onGroupsChange?.(next); };
  const toggleGroupFilter = (id) => setHiddenGroups((prev) => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });

  const addGroup = () => {
    if (!newGroupName.trim()) return;
    const id = `grp_${Date.now()}`;
    updateGroups([...groups, { id, name: newGroupName.trim(), builtIn: false }]);
    setExpandedGroups((p) => ({ ...p, [id]: true }));
    setNewGroupName(''); setAddingGroup(false);
  };

  const deleteGroup = (id) => {
    updateGroups(groups.filter((g) => g.id !== id));
    setLocations((prev) => prev.filter((l) => l.groupId !== id));
  };

  const addLocation = (groupId) => {
    const lat = parseFloat(newLoc.lat), lng = parseFloat(newLoc.lng), zoom = parseInt(newLoc.zoom) || 12;
    if (!newLoc.name.trim() || isNaN(lat) || isNaN(lng)) return;
    setLocations((prev) => [...prev, { id: `loc_${Date.now()}`, name: newLoc.name.trim(), lat, lng, zoom, groupId }]);
    setNewLoc({ name: '', lat: '', lng: '', zoom: '12' });
    setAddingLocation(null);
  };

  const handleFly = (loc) => { setActiveId(loc.id); onFlyTo(loc.lat, loc.lng, loc.zoom); };

  const activeFilters = hiddenGroups.size;

  if (panelCollapsed) {
    return (
      <aside className="panel-glass border-r flex flex-col w-10 transition-all duration-300">
        <button
          onClick={() => setPanelCollapsed(false)}
          className="p-2.5 text-muted-foreground hover:text-primary transition-colors mt-1"
        >
          <ChevronRight className="w-3.5 h-3.5" />
        </button>
      </aside>
    );
  }

  return (
    <>
      <aside className="panel-glass border-r flex flex-col w-64 transition-all duration-300 overflow-hidden">
        {/* Top bar */}
        <div className="flex items-center gap-2 px-3 py-2 border-b border-border/50 shrink-0">
          <span className="font-mono text-xs text-primary font-semibold tracking-wider flex-1">WORKSPACE</span>
          <button onClick={() => setPanelCollapsed(true)} className="text-muted-foreground hover:text-primary transition-colors">
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto min-h-0">

          {/* ── LOCATIONS SECTION ── */}
          <div className="border-b border-border/40">
            {/* Section header */}
            <div
              className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-secondary/30 transition-colors select-none"
              onClick={() => setLocOpen((v) => !v)}
            >
              <MapPin className="w-3.5 h-3.5 text-primary shrink-0" />
              <span className="font-mono text-xs text-primary font-semibold tracking-wider flex-1">LOCATIONS</span>
              {/* action buttons — stop propagation so they don't toggle the section */}
              {locOpen && (
                <>
                  <button onClick={(e) => { e.stopPropagation(); setAddingGroup(true); }} className="text-muted-foreground hover:text-primary transition-colors" title="Add group">
                    <Plus className="w-3 h-3" />
                  </button>
                  <button onClick={(e) => { e.stopPropagation(); setBulkImportOpen(true); }} className="text-muted-foreground hover:text-primary transition-colors" title="Bulk import">
                    <Upload className="w-3 h-3" />
                  </button>
                  <button onClick={(e) => { e.stopPropagation(); setManagerOpen(true); }} className="text-muted-foreground hover:text-primary transition-colors" title="Manage locations">
                    <Settings2 className="w-3 h-3" />
                  </button>
                </>
              )}
              <ChevronDown className={cn('w-3.5 h-3.5 text-muted-foreground transition-transform shrink-0', !locOpen && '-rotate-90')} />
            </div>

            {locOpen && (
              <div className="px-2 pb-2 space-y-2">
                {/* Add group form */}
                {addingGroup && (
                  <div className="p-2 rounded border border-primary/30 bg-primary/5 space-y-1.5">
                    <input
                      autoFocus value={newGroupName}
                      onChange={(e) => setNewGroupName(e.target.value)}
                      onKeyDown={(e) => { if (e.key === 'Enter') addGroup(); if (e.key === 'Escape') setAddingGroup(false); }}
                      placeholder="Group name..."
                      className="w-full bg-secondary/50 border border-border rounded px-2 py-1 text-xs font-mono text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:border-primary/50"
                    />
                    <div className="flex gap-1">
                      <button onClick={addGroup} className="flex-1 text-xs font-mono py-0.5 rounded bg-primary/20 text-primary hover:bg-primary/30">Create</button>
                      <button onClick={() => setAddingGroup(false)} className="flex-1 text-xs font-mono py-0.5 rounded bg-secondary text-muted-foreground hover:text-foreground">Cancel</button>
                    </div>
                  </div>
                )}

                {groups.map((group) => {
                  const groupLocs = locations.filter((l) => l.groupId === group.id);
                  const isExpanded = expandedGroups[group.id];
                  return (
                    <div key={group.id} className="space-y-0.5">
                      <div
                        className="flex items-center gap-1.5 px-1.5 py-1 rounded cursor-pointer hover:bg-secondary/50 transition-colors group"
                        onClick={() => setExpandedGroups((p) => ({ ...p, [group.id]: !p[group.id] }))}
                      >
                        {isExpanded ? <FolderOpen className="w-3 h-3 text-primary/60 shrink-0" /> : <Folder className="w-3 h-3 text-muted-foreground/50 shrink-0" />}
                        <span className="font-mono text-xs text-muted-foreground flex-1 truncate">{group.name}</span>
                        <span className="font-mono text-xs text-muted-foreground/30">{groupLocs.length}</span>
                        {!group.builtIn && (
                          <button onClick={(e) => { e.stopPropagation(); deleteGroup(group.id); }} className="opacity-0 group-hover:opacity-100 text-muted-foreground/40 hover:text-destructive transition-all">
                            <Trash2 className="w-2.5 h-2.5" />
                          </button>
                        )}
                      </div>

                      {isExpanded && (
                        <div className="ml-2 space-y-0.5">
                          {groupLocs.map((loc) => (
                            <div
                              key={loc.id}
                              className={cn('flex items-center gap-1.5 px-2 py-1.5 rounded cursor-pointer transition-all group',
                                activeId === loc.id ? 'bg-primary/10 border border-primary/30' : 'hover:bg-secondary/40 border border-transparent')}
                              onClick={() => handleFly(loc)}
                            >
                              {activeId === loc.id ? <Navigation className="w-2.5 h-2.5 text-primary shrink-0" /> : <Star className="w-2.5 h-2.5 text-muted-foreground/30 shrink-0" />}
                              <span className={cn('font-mono text-xs flex-1 truncate', activeId === loc.id ? 'text-primary' : 'text-foreground/80')}>{loc.name}</span>
                              <span className="font-mono text-xs text-muted-foreground/30 shrink-0">z{loc.zoom}</span>
                              {!group.builtIn && (
                                <button onClick={(e) => { e.stopPropagation(); setLocations((p) => p.filter((l) => l.id !== loc.id)); }} className="opacity-0 group-hover:opacity-100 text-muted-foreground/40 hover:text-destructive transition-all">
                                  <Trash2 className="w-2.5 h-2.5" />
                                </button>
                              )}
                            </div>
                          ))}

                          {addingLocation === group.id ? (
                            <div className="p-2 rounded border border-primary/20 bg-primary/5 space-y-1.5 mt-1">
                              <input autoFocus value={newLoc.name} onChange={(e) => setNewLoc((p) => ({ ...p, name: e.target.value }))} placeholder="Location name..."
                                className="w-full bg-secondary/50 border border-border rounded px-2 py-1 text-xs font-mono text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:border-primary/50" />
                              <div className="flex gap-1">
                                <input value={newLoc.lat} onChange={(e) => setNewLoc((p) => ({ ...p, lat: e.target.value }))} placeholder="Lat"
                                  className="flex-1 bg-secondary/50 border border-border rounded px-2 py-1 text-xs font-mono text-foreground placeholder:text-muted-foreground/40 focus:outline-none" />
                                <input value={newLoc.lng} onChange={(e) => setNewLoc((p) => ({ ...p, lng: e.target.value }))} placeholder="Lng"
                                  className="flex-1 bg-secondary/50 border border-border rounded px-2 py-1 text-xs font-mono text-foreground placeholder:text-muted-foreground/40 focus:outline-none" />
                                <input value={newLoc.zoom} onChange={(e) => setNewLoc((p) => ({ ...p, zoom: e.target.value }))} placeholder="Z"
                                  className="w-10 bg-secondary/50 border border-border rounded px-2 py-1 text-xs font-mono text-foreground placeholder:text-muted-foreground/40 focus:outline-none" />
                              </div>
                              <div className="flex gap-1">
                                <button onClick={() => addLocation(group.id)} className="flex-1 text-xs font-mono py-0.5 rounded bg-primary/20 text-primary hover:bg-primary/30">Save</button>
                                <button onClick={() => setAddingLocation(null)} className="flex-1 text-xs font-mono py-0.5 rounded bg-secondary text-muted-foreground hover:text-foreground">Cancel</button>
                              </div>
                            </div>
                          ) : (
                            <button onClick={() => setAddingLocation(group.id)} className="w-full flex items-center gap-1.5 px-2 py-1 rounded text-muted-foreground/40 hover:text-primary hover:bg-secondary/30 transition-all font-mono text-xs">
                              <Plus className="w-2.5 h-2.5" /> Add location
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* ── RECENT SELECTIONS SECTION ── */}
          {recentSelections && recentSelections.length > 0 && (
            <div className="border-b border-border/40">
              <div
                className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-secondary/30 transition-colors select-none"
                onClick={() => setRecOpen((v) => !v)}
              >
                <Clock className="w-3.5 h-3.5 text-primary shrink-0" />
                <span className="font-mono text-xs text-primary font-semibold tracking-wider flex-1">RECENT</span>
                <span className="font-mono text-xs text-muted-foreground/50">({recentSelections.length})</span>
                <ChevronDown className={cn('w-3.5 h-3.5 text-muted-foreground transition-transform shrink-0', !recOpen && '-rotate-90')} />
              </div>
              {recOpen && (
                <div className="px-2 pb-2 space-y-0.5">
                  {recentSelections.map((pt, i) => (
                    <button
                      key={i}
                      onClick={() => onFlyTo(pt.latlng.lat, pt.latlng.lng, 14)}
                      className="w-full flex items-start gap-2 px-2 py-1.5 rounded hover:bg-secondary/40 border border-transparent hover:border-border/40 transition-all text-left group"
                    >
                      <Navigation className="w-2.5 h-2.5 text-muted-foreground/40 group-hover:text-primary shrink-0 mt-0.5 transition-colors" />
                      <div className="flex-1 min-w-0">
                        <div className="font-mono text-xs text-foreground/80 truncate">
                          {pt.properties?.name || pt.layerName || `${pt.latlng.lat.toFixed(4)}, ${pt.latlng.lng.toFixed(4)}`}
                        </div>
                        <div className="font-mono text-xs text-muted-foreground/40">
                          {pt.latlng.lat.toFixed(4)}, {pt.latlng.lng.toFixed(4)}
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ── OVERLAYS SECTION ── */}
          <OverlaysSection
            activeOverlays={activeOverlays}
            onToggle={handleOverlayToggle}
            onOpacityChange={handleOverlayOpacity}
          />

          {/* ── LAYERS SECTION ── */}
          <div>
            {/* Section header */}
            <div
              className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-secondary/30 transition-colors select-none"
              onClick={() => setLayOpen((v) => !v)}
            >
              <Layers className="w-3.5 h-3.5 text-primary shrink-0" />
              <span className="font-mono text-xs text-primary font-semibold tracking-wider flex-1">LAYERS</span>
              <span className="font-mono text-xs text-muted-foreground/50">({layers.length})</span>
              {layOpen && groups.length > 0 && (
                <button
                  onClick={(e) => { e.stopPropagation(); setFilterOpen((v) => !v); }}
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
              <ChevronDown className={cn('w-3.5 h-3.5 text-muted-foreground transition-transform shrink-0', !layOpen && '-rotate-90')} />
            </div>

            {layOpen && (
              <>
                {/* Group filters */}
                {filterOpen && groups.length > 0 && (
                  <div className="px-3 py-2 border-b border-border/40 bg-secondary/20 space-y-1.5">
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-mono text-xs text-muted-foreground/60">Show/hide POI groups</span>
                      {activeFilters > 0 && (
                        <button onClick={() => setHiddenGroups(new Set())} className="flex items-center gap-1 font-mono text-xs text-muted-foreground/50 hover:text-primary">
                          <X className="w-2.5 h-2.5" /> Reset
                        </button>
                      )}
                    </div>
                    {groups.map((g) => {
                      const hidden = hiddenGroups.has(g.id);
                      return (
                        <button key={g.id} onClick={() => toggleGroupFilter(g.id)}
                          className={cn('w-full flex items-center gap-2 px-2 py-1 rounded border text-xs font-mono transition-all',
                            hidden ? 'border-border/30 bg-transparent text-muted-foreground/40' : 'border-primary/30 bg-primary/5 text-foreground/80')}>
                          <div className={cn('w-2 h-2 rounded-full border shrink-0', hidden ? 'border-muted-foreground/30 bg-transparent' : 'border-primary bg-primary')} />
                          <span className="flex-1 text-left truncate">{g.name}</span>
                          {hidden && <span className="text-muted-foreground/30">hidden</span>}
                        </button>
                      );
                    })}
                  </div>
                )}

                <div className="p-2 space-y-1.5">
                  {layers.length === 0 && (
                    <div className="text-center py-6">
                      <Layers className="w-5 h-5 text-muted-foreground/30 mx-auto mb-2" />
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
          </div>

        </div>
      </aside>

      {/* Modals */}
      {managerOpen && (
        <LocationsManager
          groups={groups} locations={locations}
          onClose={() => setManagerOpen(false)}
          onUpdateGroups={updateGroups}
          onUpdateLocations={setLocations}
        />
      )}
      {bulkImportOpen && (
        <BulkImportModal
          groups={groups}
          onClose={() => setBulkImportOpen(false)}
          onImport={({ locs, groupId, groupName }) => {
            if (groupName) {
              updateGroups([...groups, { id: groupId, name: groupName, builtIn: false }]);
              setExpandedGroups((p) => ({ ...p, [groupId]: true }));
            }
            setLocations((prev) => [...prev, ...locs]);
          }}
        />
      )}
    </>
  );
}

// ─── Layer item ───────────────────────────────────────────────────────────────
function LayerItem({ layer, isSelected, onToggleVisibility, onDelete, onUpdate, onSelect }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className={cn('rounded border transition-all', isSelected ? 'border-primary/50 bg-primary/5' : 'border-border/40 hover:border-border bg-card/30')}>
      <div className="flex items-center gap-1.5 p-2 cursor-pointer" onClick={onSelect}>
        <div className="w-2.5 h-2.5 rounded-full shrink-0 border border-white/20" style={{ backgroundColor: layer.color }} />
        <span className={cn('font-mono text-xs flex-1 truncate', layer.visible ? 'text-foreground' : 'text-muted-foreground/40 line-through')}>{layer.name}</span>
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
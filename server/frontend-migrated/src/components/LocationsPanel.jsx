import { useState } from 'react';
import { MapPin, Plus, Trash2, ChevronDown, ChevronRight, FolderOpen, Folder, Star, Navigation, Settings2, Upload } from 'lucide-react';
import { cn } from '@/lib/utils';
import LocationsManager from './LocationsManager';
import BulkImportModal from './BulkImportModal';

const DEFAULT_LOCATIONS = [
  { id: 'pr-overview', name: 'Puerto Rico Overview', lat: 18.2208, lng: -66.5901, zoom: 8, groupId: 'defaults', pinned: true },
  { id: 'san-juan', name: 'San Juan Metro', lat: 18.4655, lng: -66.1057, zoom: 12, groupId: 'defaults', pinned: true },
  { id: 'ponce', name: 'Ponce', lat: 18.0110, lng: -66.6141, zoom: 13, groupId: 'defaults', pinned: true },
  { id: 'mayaguez', name: 'Mayagüez', lat: 18.2013, lng: -67.1397, zoom: 13, groupId: 'defaults', pinned: true },
  { id: 'caguas', name: 'Caguas', lat: 18.2341, lng: -65.9895, zoom: 13, groupId: 'defaults', pinned: true },
  { id: 'arecibo', name: 'Arecibo', lat: 18.4724, lng: -66.7220, zoom: 13, groupId: 'defaults', pinned: true },
  { id: 'vieques', name: 'Vieques Island', lat: 18.1260, lng: -65.4400, zoom: 12, groupId: 'defaults', pinned: true },
  { id: 'culebra', name: 'Culebra Island', lat: 18.3026, lng: -65.3018, zoom: 13, groupId: 'defaults', pinned: true },
];

const DEFAULT_GROUPS = [
  { id: 'defaults', name: 'Puerto Rico Locations', builtIn: true },
];

export default function LocationsPanel({ onFlyTo, onGroupsChange }) {
  const [collapsed, setCollapsed] = useState(false);
  const [groups, setGroups] = useState(DEFAULT_GROUPS);
  const [locations, setLocations] = useState(DEFAULT_LOCATIONS);

  const updateGroups = (next) => { setGroups(next); onGroupsChange?.(next); };
  const [expandedGroups, setExpandedGroups] = useState({ defaults: true });
  const [addingGroup, setAddingGroup] = useState(false);
  const [newGroupName, setNewGroupName] = useState('');
  const [addingLocation, setAddingLocation] = useState(null); // groupId
  const [newLoc, setNewLoc] = useState({ name: '', lat: '', lng: '', zoom: '12' });
  const [activeId, setActiveId] = useState(null);
  const [managerOpen, setManagerOpen] = useState(false);
  const [bulkImportOpen, setBulkImportOpen] = useState(false);

  const toggleGroup = (id) => setExpandedGroups((prev) => ({ ...prev, [id]: !prev[id] }));

  const addGroup = () => {
    if (!newGroupName.trim()) return;
    const id = `grp_${Date.now()}`;
    updateGroups([...groups, { id, name: newGroupName.trim(), builtIn: false }]);
    setExpandedGroups((prev) => ({ ...prev, [id]: true }));
    setNewGroupName('');
    setAddingGroup(false);
  };

  const deleteGroup = (id) => {
    updateGroups(groups.filter((g) => g.id !== id));
    setLocations((prev) => prev.filter((l) => l.groupId !== id));
  };

  const addLocation = (groupId) => {
    const lat = parseFloat(newLoc.lat);
    const lng = parseFloat(newLoc.lng);
    const zoom = parseInt(newLoc.zoom) || 12;
    if (!newLoc.name.trim() || isNaN(lat) || isNaN(lng)) return;
    const loc = { id: `loc_${Date.now()}`, name: newLoc.name.trim(), lat, lng, zoom, groupId };
    setLocations((prev) => [...prev, loc]);
    setNewLoc({ name: '', lat: '', lng: '', zoom: '12' });
    setAddingLocation(null);
  };

  const deleteLocation = (id) => setLocations((prev) => prev.filter((l) => l.id !== id));

  const handleFly = (loc) => {
    setActiveId(loc.id);
    onFlyTo(loc.lat, loc.lng, loc.zoom);
  };

  return (
    <>
    <aside
      className={cn(
        'panel-glass border-r flex flex-col transition-all duration-300 overflow-hidden',
        collapsed ? 'w-10' : 'w-64'
      )}
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border/50 shrink-0">
        {!collapsed && (
          <>
            <MapPin className="w-3.5 h-3.5 text-primary" />
            <span className="font-mono text-xs text-primary font-semibold tracking-wider flex-1">LOCATIONS</span>
            <button
              onClick={() => setAddingGroup(true)}
              className="text-muted-foreground hover:text-primary transition-colors"
              title="Add group"
            >
              <Plus className="w-3 h-3" />
            </button>
            <button
              onClick={() => setBulkImportOpen(true)}
              className="text-muted-foreground hover:text-primary transition-colors"
              title="Bulk import coordinates"
            >
              <Upload className="w-3 h-3" />
            </button>
            <button
              onClick={() => setManagerOpen(true)}
              className="text-muted-foreground hover:text-primary transition-colors"
              title="Manage locations"
            >
              <Settings2 className="w-3 h-3" />
            </button>
          </>
        )}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="text-muted-foreground hover:text-primary transition-colors ml-auto"
        >
          {collapsed ? <ChevronRight className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </button>
      </div>

      {!collapsed && (
        <div className="flex-1 overflow-y-auto p-2 space-y-2">

          {/* Add group form */}
          {addingGroup && (
            <div className="p-2 rounded border border-primary/30 bg-primary/5 space-y-1.5">
              <input
                autoFocus
                value={newGroupName}
                onChange={(e) => setNewGroupName(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') addGroup(); if (e.key === 'Escape') setAddingGroup(false); }}
                placeholder="Group name..."
                className="w-full bg-secondary/50 border border-border rounded px-2 py-1 text-xs font-mono text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:border-primary/50"
              />
              <div className="flex gap-1">
                <button onClick={addGroup} className="flex-1 text-xs font-mono py-0.5 rounded bg-primary/20 text-primary hover:bg-primary/30 transition-colors">Create</button>
                <button onClick={() => setAddingGroup(false)} className="flex-1 text-xs font-mono py-0.5 rounded bg-secondary text-muted-foreground hover:text-foreground transition-colors">Cancel</button>
              </div>
            </div>
          )}

          {groups.map((group) => {
            const groupLocs = locations.filter((l) => l.groupId === group.id);
            const isExpanded = expandedGroups[group.id];

            return (
              <div key={group.id} className="space-y-0.5">
                {/* Group header */}
                <div
                  className="flex items-center gap-1.5 px-1.5 py-1 rounded cursor-pointer hover:bg-secondary/50 transition-colors group"
                  onClick={() => toggleGroup(group.id)}
                >
                  {isExpanded
                    ? <FolderOpen className="w-3 h-3 text-primary/60 shrink-0" />
                    : <Folder className="w-3 h-3 text-muted-foreground/50 shrink-0" />}
                  <span className="font-mono text-xs text-muted-foreground flex-1 truncate">{group.name}</span>
                  <span className="font-mono text-xs text-muted-foreground/30">{groupLocs.length}</span>
                  {!group.builtIn && (
                    <button
                      onClick={(e) => { e.stopPropagation(); deleteGroup(group.id); }}
                      className="opacity-0 group-hover:opacity-100 text-muted-foreground/40 hover:text-destructive transition-all"
                    >
                      <Trash2 className="w-2.5 h-2.5" />
                    </button>
                  )}
                </div>

                {/* Locations list */}
                {isExpanded && (
                  <div className="ml-2 space-y-0.5">
                    {groupLocs.map((loc) => (
                      <div
                        key={loc.id}
                        className={cn(
                          'flex items-center gap-1.5 px-2 py-1.5 rounded cursor-pointer transition-all group',
                          activeId === loc.id
                            ? 'bg-primary/10 border border-primary/30'
                            : 'hover:bg-secondary/40 border border-transparent'
                        )}
                        onClick={() => handleFly(loc)}
                      >
                        {activeId === loc.id
                          ? <Navigation className="w-2.5 h-2.5 text-primary shrink-0" />
                          : <Star className="w-2.5 h-2.5 text-muted-foreground/30 shrink-0" />}
                        <span className={cn('font-mono text-xs flex-1 truncate', activeId === loc.id ? 'text-primary' : 'text-foreground/80')}>
                          {loc.name}
                        </span>
                        <span className="font-mono text-xs text-muted-foreground/30 shrink-0">z{loc.zoom}</span>
                        {!group.builtIn && (
                          <button
                            onClick={(e) => { e.stopPropagation(); deleteLocation(loc.id); }}
                            className="opacity-0 group-hover:opacity-100 text-muted-foreground/40 hover:text-destructive transition-all"
                          >
                            <Trash2 className="w-2.5 h-2.5" />
                          </button>
                        )}
                      </div>
                    ))}

                    {/* Add location */}
                    {addingLocation === group.id ? (
                      <div className="p-2 rounded border border-primary/20 bg-primary/5 space-y-1.5 mt-1">
                        <input
                          autoFocus
                          value={newLoc.name}
                          onChange={(e) => setNewLoc((p) => ({ ...p, name: e.target.value }))}
                          placeholder="Location name..."
                          className="w-full bg-secondary/50 border border-border rounded px-2 py-1 text-xs font-mono text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:border-primary/50"
                        />
                        <div className="flex gap-1">
                          <input
                            value={newLoc.lat}
                            onChange={(e) => setNewLoc((p) => ({ ...p, lat: e.target.value }))}
                            placeholder="Lat"
                            className="flex-1 bg-secondary/50 border border-border rounded px-2 py-1 text-xs font-mono text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:border-primary/50"
                          />
                          <input
                            value={newLoc.lng}
                            onChange={(e) => setNewLoc((p) => ({ ...p, lng: e.target.value }))}
                            placeholder="Lng"
                            className="flex-1 bg-secondary/50 border border-border rounded px-2 py-1 text-xs font-mono text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:border-primary/50"
                          />
                          <input
                            value={newLoc.zoom}
                            onChange={(e) => setNewLoc((p) => ({ ...p, zoom: e.target.value }))}
                            placeholder="Z"
                            className="w-10 bg-secondary/50 border border-border rounded px-2 py-1 text-xs font-mono text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:border-primary/50"
                          />
                        </div>
                        <div className="flex gap-1">
                          <button onClick={() => addLocation(group.id)} className="flex-1 text-xs font-mono py-0.5 rounded bg-primary/20 text-primary hover:bg-primary/30">Save</button>
                          <button onClick={() => setAddingLocation(null)} className="flex-1 text-xs font-mono py-0.5 rounded bg-secondary text-muted-foreground hover:text-foreground">Cancel</button>
                        </div>
                      </div>
                    ) : (
                      <button
                        onClick={() => setAddingLocation(group.id)}
                        className="w-full flex items-center gap-1.5 px-2 py-1 rounded text-muted-foreground/40 hover:text-primary hover:bg-secondary/30 transition-all font-mono text-xs"
                      >
                        <Plus className="w-2.5 h-2.5" />
                        Add location
                      </button>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </aside>

    {managerOpen && (
      <LocationsManager
        groups={groups}
        locations={locations}
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
            setExpandedGroups((prev) => ({ ...prev, [groupId]: true }));
          }
          setLocations((prev) => [...prev, ...locs]);
        }}
      />
    )}
    </>
  );
}
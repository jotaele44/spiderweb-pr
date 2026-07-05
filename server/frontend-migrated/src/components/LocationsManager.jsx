import { useState, useRef } from 'react';
import { X, Pencil, Trash2, Check, Upload, Plus, FolderOpen, AlertCircle, Download } from 'lucide-react';
import { cn } from '@/lib/utils';

function parseCsv(text) {
  const lines = text.trim().split('\n').filter(Boolean);
  if (lines.length < 2) throw new Error('CSV must have a header row and at least one data row.');
  const headers = lines[0].split(',').map((h) => h.trim().toLowerCase().replace(/['"]/g, ''));

  const latKey = headers.find((h) => ['lat', 'latitude', 'y'].includes(h));
  const lngKey = headers.find((h) => ['lon', 'lng', 'longitude', 'x'].includes(h));
  const nameKey = headers.find((h) => ['name', 'label', 'title', 'place'].includes(h));
  const zoomKey = headers.find((h) => ['zoom', 'z'].includes(h));

  if (!latKey || !lngKey) throw new Error('CSV must contain lat/lng (or latitude/longitude) columns.');

  const latIdx = headers.indexOf(latKey);
  const lngIdx = headers.indexOf(lngKey);
  const nameIdx = nameKey ? headers.indexOf(nameKey) : -1;
  const zoomIdx = zoomKey ? headers.indexOf(zoomKey) : -1;

  const results = [];
  for (let i = 1; i < lines.length; i++) {
    const vals = lines[i].split(',').map((v) => v.trim().replace(/['"]/g, ''));
    const lat = parseFloat(vals[latIdx]);
    const lng = parseFloat(vals[lngIdx]);
    if (isNaN(lat) || isNaN(lng)) continue;
    results.push({
      id: `loc_${Date.now()}_${i}`,
      lat,
      lng,
      zoom: zoomIdx >= 0 ? (parseInt(vals[zoomIdx]) || 12) : 12,
      name: nameIdx >= 0 && vals[nameIdx] ? vals[nameIdx] : `Point ${i}`,
    });
  }
  if (results.length === 0) throw new Error('No valid coordinate rows found in the CSV.');
  return results;
}

export default function LocationsManager({ groups, locations, onClose, onUpdateGroups, onUpdateLocations }) {
  const [renamingId, setRenamingId] = useState(null);
  const [renameValue, setRenameValue] = useState('');
  const [importingGroupId, setImportingGroupId] = useState(null);
  const [importError, setImportError] = useState('');
  const [importPreview, setImportPreview] = useState(null); // { rows, groupId }
  const fileInputRef = useRef();

  // ── Rename group ──
  const startRename = (group) => {
    setRenamingId(group.id);
    setRenameValue(group.name);
  };
  const commitRename = (id) => {
    if (!renameValue.trim()) return;
    onUpdateGroups(groups.map((g) => g.id === id ? { ...g, name: renameValue.trim() } : g));
    setRenamingId(null);
  };

  // ── Delete group ──
  const deleteGroup = (id) => {
    onUpdateGroups(groups.filter((g) => g.id !== id));
    onUpdateLocations(locations.filter((l) => l.groupId !== id));
  };

  // ── Delete location ──
  const deleteLocation = (id) => onUpdateLocations(locations.filter((l) => l.id !== id));

  // ── Add group ──
  const [newGroupName, setNewGroupName] = useState('');
  const [addingGroup, setAddingGroup] = useState(false);
  const addGroup = () => {
    if (!newGroupName.trim()) return;
    const id = `grp_${Date.now()}`;
    onUpdateGroups([...groups, { id, name: newGroupName.trim(), builtIn: false }]);
    setNewGroupName('');
    setAddingGroup(false);
  };

  // ── CSV Import ──
  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImportError('');
    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        const rows = parseCsv(ev.target.result);
        setImportPreview({ rows, groupId: importingGroupId });
      } catch (err) {
        setImportError(err.message);
      }
    };
    reader.readAsText(file);
    e.target.value = '';
  };

  const confirmImport = () => {
    if (!importPreview) return;
    const newLocs = importPreview.rows.map((r) => ({ ...r, groupId: importPreview.groupId }));
    onUpdateLocations([...locations, ...newLocs]);
    setImportPreview(null);
    setImportingGroupId(null);
    setImportError('');
  };

  const cancelImport = () => {
    setImportPreview(null);
    setImportError('');
    setImportingGroupId(null);
  };

  const downloadTemplate = () => {
    const csv = 'name,lat,lng,zoom\nSan Juan,18.4655,-66.1057,12\nPonce,18.0110,-66.6141,13';
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'locations_template.csv'; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="fixed inset-0 z-[2000] flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div
        className="panel-glass rounded-lg w-[560px] max-h-[80vh] flex flex-col shadow-2xl border border-primary/20"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center gap-2 px-4 py-3 border-b border-border/50 shrink-0">
          <FolderOpen className="w-4 h-4 text-primary" />
          <span className="font-mono text-sm text-primary font-semibold tracking-wider flex-1">LOCATIONS MANAGER</span>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4 min-h-0">

          {/* Add group */}
          {addingGroup ? (
            <div className="flex items-center gap-2 p-2 rounded border border-primary/30 bg-primary/5">
              <input
                autoFocus
                value={newGroupName}
                onChange={(e) => setNewGroupName(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') addGroup(); if (e.key === 'Escape') setAddingGroup(false); }}
                placeholder="New category name..."
                className="flex-1 bg-transparent text-xs font-mono text-foreground placeholder:text-muted-foreground/40 focus:outline-none"
              />
              <button onClick={addGroup} className="text-primary hover:text-primary/80"><Check className="w-3.5 h-3.5" /></button>
              <button onClick={() => setAddingGroup(false)} className="text-muted-foreground hover:text-foreground"><X className="w-3.5 h-3.5" /></button>
            </div>
          ) : (
            <button
              onClick={() => setAddingGroup(true)}
              className="w-full flex items-center gap-2 px-3 py-2 rounded border border-dashed border-border/50 text-muted-foreground hover:text-primary hover:border-primary/40 transition-all font-mono text-xs"
            >
              <Plus className="w-3.5 h-3.5" />
              Add new category
            </button>
          )}

          {/* Groups */}
          {groups.map((group) => {
            const groupLocs = locations.filter((l) => l.groupId === group.id);
            const isImporting = importingGroupId === group.id;

            return (
              <div key={group.id} className="rounded border border-border/40 bg-card/30 overflow-hidden">
                {/* Group row */}
                <div className="flex items-center gap-2 px-3 py-2 border-b border-border/30 bg-secondary/20">
                  {renamingId === group.id ? (
                    <input
                      autoFocus
                      value={renameValue}
                      onChange={(e) => setRenameValue(e.target.value)}
                      onKeyDown={(e) => { if (e.key === 'Enter') commitRename(group.id); if (e.key === 'Escape') setRenamingId(null); }}
                      className="flex-1 bg-transparent text-xs font-mono text-foreground focus:outline-none border-b border-primary/50"
                    />
                  ) : (
                    <span className="font-mono text-xs text-foreground font-semibold flex-1">{group.name}</span>
                  )}
                  <span className="font-mono text-xs text-muted-foreground/40">{groupLocs.length} pts</span>

                  {/* Import CSV */}
                  <button
                    onClick={() => { setImportingGroupId(isImporting ? null : group.id); setImportError(''); setImportPreview(null); }}
                    className={cn('text-xs font-mono px-2 py-0.5 rounded border transition-colors flex items-center gap-1',
                      isImporting ? 'border-primary/50 text-primary bg-primary/10' : 'border-border/50 text-muted-foreground hover:text-primary hover:border-primary/40')}
                    title="Import CSV"
                  >
                    <Upload className="w-3 h-3" />
                    Import
                  </button>

                  {!group.builtIn && (
                    <>
                      {renamingId === group.id ? (
                        <button onClick={() => commitRename(group.id)} className="text-primary hover:text-primary/80"><Check className="w-3.5 h-3.5" /></button>
                      ) : (
                        <button onClick={() => startRename(group)} className="text-muted-foreground hover:text-primary transition-colors" title="Rename"><Pencil className="w-3.5 h-3.5" /></button>
                      )}
                      <button onClick={() => deleteGroup(group.id)} className="text-muted-foreground hover:text-destructive transition-colors" title="Delete group"><Trash2 className="w-3.5 h-3.5" /></button>
                    </>
                  )}
                </div>

                {/* CSV Import area */}
                {isImporting && (
                  <div className="px-3 py-3 border-b border-border/30 bg-primary/3 space-y-2">
                    {importPreview ? (
                      <div className="space-y-2">
                        <p className="font-mono text-xs text-primary">{importPreview.rows.length} locations ready to import</p>
                        <div className="max-h-32 overflow-y-auto rounded border border-border/30 bg-background/50">
                          {importPreview.rows.slice(0, 10).map((r, i) => (
                            <div key={i} className="flex items-center gap-3 px-2 py-1 border-b border-border/20 last:border-0 font-mono text-xs">
                              <span className="text-foreground/80 flex-1 truncate">{r.name}</span>
                              <span className="text-muted-foreground/50">{r.lat.toFixed(4)}, {r.lng.toFixed(4)}</span>
                              <span className="text-muted-foreground/30">z{r.zoom}</span>
                            </div>
                          ))}
                          {importPreview.rows.length > 10 && (
                            <div className="px-2 py-1 font-mono text-xs text-muted-foreground/40">+{importPreview.rows.length - 10} more...</div>
                          )}
                        </div>
                        <div className="flex gap-2">
                          <button onClick={confirmImport} className="flex-1 py-1 rounded bg-primary/20 border border-primary/40 text-primary font-mono text-xs hover:bg-primary/30 transition-colors">Confirm Import</button>
                          <button onClick={cancelImport} className="flex-1 py-1 rounded bg-secondary border border-border/40 text-muted-foreground font-mono text-xs hover:text-foreground transition-colors">Cancel</button>
                        </div>
                      </div>
                    ) : (
                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-xs text-muted-foreground">Upload a CSV file with lat, lng columns</span>
                          <button onClick={downloadTemplate} className="flex items-center gap-1 font-mono text-xs text-muted-foreground/50 hover:text-primary transition-colors">
                            <Download className="w-3 h-3" />
                            Template
                          </button>
                        </div>
                        <button
                          onClick={() => fileInputRef.current?.click()}
                          className="w-full flex items-center justify-center gap-2 py-3 rounded border border-dashed border-border/50 hover:border-primary/40 text-muted-foreground hover:text-primary transition-all font-mono text-xs"
                        >
                          <Upload className="w-4 h-4" />
                          Choose CSV file
                        </button>
                        {importError && (
                          <div className="flex items-center gap-2 text-destructive font-mono text-xs">
                            <AlertCircle className="w-3 h-3 shrink-0" />
                            {importError}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {/* Locations list */}
                <div className="divide-y divide-border/20">
                  {groupLocs.length === 0 && (
                    <p className="px-3 py-2 font-mono text-xs text-muted-foreground/30">No locations yet</p>
                  )}
                  {groupLocs.map((loc) => (
                    <div key={loc.id} className="flex items-center gap-2 px-3 py-1.5 hover:bg-secondary/20 transition-colors group">
                      <span className="font-mono text-xs text-foreground/80 flex-1 truncate">{loc.name}</span>
                      <span className="font-mono text-xs text-muted-foreground/40">{loc.lat.toFixed(4)}, {loc.lng.toFixed(4)}</span>
                      <span className="font-mono text-xs text-muted-foreground/25">z{loc.zoom}</span>
                      <button
                        onClick={() => deleteLocation(loc.id)}
                        className="opacity-0 group-hover:opacity-100 text-muted-foreground/40 hover:text-destructive transition-all"
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>

        {/* Hidden file input */}
        <input ref={fileInputRef} type="file" accept=".csv,text/csv" className="hidden" onChange={handleFileChange} />
      </div>
    </div>
  );
}
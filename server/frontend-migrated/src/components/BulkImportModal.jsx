import { useState, useRef, useCallback } from 'react';
import { X, Upload, Download, AlertCircle, CheckCircle2, FileText, Plus, FolderOpen, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

function parseFile(text, filename) {
  const ext = filename.split('.').pop().toLowerCase();

  if (ext === 'json') {
    const data = JSON.parse(text);
    // GeoJSON FeatureCollection
    if (data.type === 'FeatureCollection' && Array.isArray(data.features)) {
      return data.features
        .filter((f) => f.geometry?.type === 'Point')
        .map((f, i) => ({
          id: `loc_${Date.now()}_${i}`,
          lng: f.geometry.coordinates[0],
          lat: f.geometry.coordinates[1],
          zoom: f.properties?.zoom || 12,
          name: f.properties?.name || f.properties?.label || f.properties?.title || `Point ${i + 1}`,
        }));
    }
    // Array of objects
    if (Array.isArray(data)) {
      return data
        .map((r, i) => {
          const lat = parseFloat(r.lat ?? r.latitude ?? r.y);
          const lng = parseFloat(r.lng ?? r.lon ?? r.longitude ?? r.x);
          if (isNaN(lat) || isNaN(lng)) return null;
          return {
            id: `loc_${Date.now()}_${i}`,
            lat, lng,
            zoom: parseInt(r.zoom) || 12,
            name: r.name || r.label || r.title || `Point ${i + 1}`,
          };
        })
        .filter(Boolean);
    }
    throw new Error('JSON must be a GeoJSON FeatureCollection or an array of coordinate objects.');
  }

  // CSV
  const lines = text.trim().split('\n').filter(Boolean);
  if (lines.length < 2) throw new Error('File must have a header row and at least one data row.');
  const headers = lines[0].split(',').map((h) => h.trim().toLowerCase().replace(/['"]/g, ''));
  const latIdx = headers.findIndex((h) => ['lat', 'latitude', 'y'].includes(h));
  const lngIdx = headers.findIndex((h) => ['lon', 'lng', 'longitude', 'x'].includes(h));
  const nameIdx = headers.findIndex((h) => ['name', 'label', 'title', 'place'].includes(h));
  const zoomIdx = headers.findIndex((h) => ['zoom', 'z'].includes(h));

  if (latIdx < 0 || lngIdx < 0) throw new Error('File must contain lat/lng (or latitude/longitude) columns.');

  const results = [];
  for (let i = 1; i < lines.length; i++) {
    const vals = lines[i].split(',').map((v) => v.trim().replace(/['"]/g, ''));
    const lat = parseFloat(vals[latIdx]);
    const lng = parseFloat(vals[lngIdx]);
    if (isNaN(lat) || isNaN(lng)) continue;
    results.push({
      id: `loc_${Date.now()}_${i}`,
      lat, lng,
      zoom: zoomIdx >= 0 ? (parseInt(vals[zoomIdx]) || 12) : 12,
      name: nameIdx >= 0 && vals[nameIdx] ? vals[nameIdx] : `Point ${i}`,
    });
  }
  if (results.length === 0) throw new Error('No valid coordinate rows found.');
  return results;
}

export default function BulkImportModal({ groups, onClose, onImport }) {
  const [dragging, setDragging] = useState(false);
  const [preview, setPreview] = useState(null); // { rows, filename }
  const [error, setError] = useState('');
  const [targetGroupId, setTargetGroupId] = useState(groups[0]?.id || '__new__');
  const [newGroupName, setNewGroupName] = useState('');
  const [importing, setImporting] = useState(false);
  const fileRef = useRef();

  const processFile = (file) => {
    setError('');
    setPreview(null);
    const defaultName = file.name.replace(/\.(csv|json)$/i, '').replace(/[_-]/g, ' ');
    setNewGroupName(defaultName);
    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        const rows = parseFile(ev.target.result, file.name);
        setPreview({ rows, filename: file.name });
      } catch (err) {
        setError(err.message);
      }
    };
    reader.readAsText(file);
  };

  const onDrop = useCallback((e) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) processFile(file);
  }, []);

  const onDragOver = (e) => { e.preventDefault(); setDragging(true); };
  const onDragLeave = () => setDragging(false);

  const downloadTemplate = () => {
    const csv = 'name,lat,lng,zoom\nSan Juan,18.4655,-66.1057,12\nPonce,18.0110,-66.6141,13\nMayagüez,18.2013,-67.1397,13';
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'coordinates_template.csv'; a.click();
    URL.revokeObjectURL(url);
  };

  const handleConfirm = async () => {
    if (!preview) return;
    setImporting(true);
    const groupId = targetGroupId === '__new__' ? `grp_${Date.now()}` : targetGroupId;
    const groupName = targetGroupId === '__new__' ? (newGroupName.trim() || preview.filename) : null;
    const locs = preview.rows.map((r) => ({ ...r, groupId }));
    await onImport({ locs, groupId, groupName });
    setImporting(false);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-[2000] flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div
        className="panel-glass rounded-lg w-[600px] max-h-[85vh] flex flex-col shadow-2xl border border-primary/20"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center gap-2 px-4 py-3 border-b border-border/50 shrink-0">
          <Upload className="w-4 h-4 text-primary" />
          <span className="font-mono text-sm text-primary font-semibold tracking-wider flex-1">BULK IMPORT COORDINATES</span>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground"><X className="w-4 h-4" /></button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4 min-h-0">
          {/* Drop zone */}
          {!preview && (
            <div
              onDrop={onDrop}
              onDragOver={onDragOver}
              onDragLeave={onDragLeave}
              className={cn(
                'border-2 border-dashed rounded-lg p-8 text-center transition-all cursor-pointer',
                dragging
                  ? 'border-primary/70 bg-primary/10 scale-[1.01]'
                  : 'border-border/40 hover:border-primary/40 hover:bg-primary/5'
              )}
              onClick={() => fileRef.current?.click()}
            >
              <Upload className={cn('w-8 h-8 mx-auto mb-3 transition-colors', dragging ? 'text-primary' : 'text-muted-foreground/30')} />
              <p className="font-mono text-sm text-foreground/70 mb-1">Drop file here or click to browse</p>
              <p className="font-mono text-xs text-muted-foreground/40">Supports CSV and JSON (GeoJSON or array)</p>
              <div className="flex items-center justify-center gap-4 mt-4">
                <span className="font-mono text-xs text-muted-foreground/30 flex items-center gap-1"><FileText className="w-3 h-3" />CSV</span>
                <span className="font-mono text-xs text-muted-foreground/30 flex items-center gap-1"><FileText className="w-3 h-3" />GeoJSON</span>
                <span className="font-mono text-xs text-muted-foreground/30 flex items-center gap-1"><FileText className="w-3 h-3" />JSON array</span>
              </div>
            </div>
          )}

          {error && (
            <div className="flex items-start gap-2 p-3 rounded border border-destructive/30 bg-destructive/10">
              <AlertCircle className="w-4 h-4 text-destructive shrink-0 mt-0.5" />
              <div>
                <p className="font-mono text-xs text-destructive">{error}</p>
                <button
                  onClick={() => { setError(''); setPreview(null); fileRef.current?.click(); }}
                  className="font-mono text-xs text-destructive/60 hover:text-destructive mt-1 underline"
                >Try another file</button>
              </div>
            </div>
          )}

          {/* Preview */}
          {preview && (
            <>
              <div className="flex items-center gap-2 p-3 rounded border border-accent/30 bg-accent/10">
                <CheckCircle2 className="w-4 h-4 text-accent shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="font-mono text-xs text-accent">{preview.rows.length} locations parsed from <span className="text-foreground/80">{preview.filename}</span></p>
                </div>
                <button onClick={() => { setPreview(null); setError(''); }} className="font-mono text-xs text-muted-foreground/50 hover:text-foreground underline shrink-0">Change file</button>
              </div>

              {/* Preview table */}
              <div className="rounded border border-border/30 bg-background/40 overflow-hidden">
                <div className="px-3 py-1.5 border-b border-border/20 bg-secondary/20 flex items-center gap-2">
                  <span className="font-mono text-xs text-muted-foreground/50">Preview</span>
                  {preview.rows.length > 8 && <span className="font-mono text-xs text-muted-foreground/30">showing first 8 of {preview.rows.length}</span>}
                </div>
                <div className="divide-y divide-border/20 max-h-40 overflow-y-auto">
                  {preview.rows.slice(0, 8).map((r, i) => (
                    <div key={i} className="flex items-center gap-3 px-3 py-1.5 font-mono text-xs hover:bg-secondary/20 transition-colors">
                      <span className="text-muted-foreground/30 w-5 shrink-0">{i + 1}</span>
                      <span className="text-foreground/80 flex-1 truncate">{r.name}</span>
                      <span className="text-primary/60 shrink-0">{r.lat.toFixed(4)}</span>
                      <span className="text-primary/60 shrink-0">{r.lng.toFixed(4)}</span>
                      <span className="text-muted-foreground/30 shrink-0">z{r.zoom}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Target group */}
              <div className="space-y-2">
                <label className="font-mono text-xs text-muted-foreground/60">Import into group</label>
                <div className="grid grid-cols-2 gap-2">
                  {/* Existing groups */}
                  {groups.map((g) => (
                    <button
                      key={g.id}
                      onClick={() => setTargetGroupId(g.id)}
                      className={cn(
                        'flex items-center gap-2 px-3 py-2 rounded border font-mono text-xs transition-all text-left',
                        targetGroupId === g.id
                          ? 'border-primary/50 bg-primary/10 text-primary'
                          : 'border-border/40 text-muted-foreground hover:border-primary/30 hover:text-foreground'
                      )}
                    >
                      <FolderOpen className="w-3 h-3 shrink-0" />
                      <span className="truncate">{g.name}</span>
                    </button>
                  ))}
                  {/* New group option */}
                  <button
                    onClick={() => setTargetGroupId('__new__')}
                    className={cn(
                      'flex items-center gap-2 px-3 py-2 rounded border font-mono text-xs transition-all text-left',
                      targetGroupId === '__new__'
                        ? 'border-accent/50 bg-accent/10 text-accent'
                        : 'border-dashed border-border/40 text-muted-foreground hover:border-accent/30 hover:text-foreground'
                    )}
                  >
                    <Plus className="w-3 h-3 shrink-0" />
                    <span>New group</span>
                  </button>
                </div>

                {targetGroupId === '__new__' && (
                  <input
                    autoFocus
                    value={newGroupName}
                    onChange={(e) => setNewGroupName(e.target.value)}
                    placeholder="Group name..."
                    className="w-full bg-secondary/50 border border-border rounded px-3 py-1.5 text-xs font-mono text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:border-accent/50 transition-colors"
                  />
                )}
              </div>
            </>
          )}

          {/* Template download */}
          <div className="flex items-center justify-between pt-1 border-t border-border/20">
            <span className="font-mono text-xs text-muted-foreground/40">Need a template?</span>
            <button onClick={downloadTemplate} className="flex items-center gap-1.5 font-mono text-xs text-muted-foreground/50 hover:text-primary transition-colors">
              <Download className="w-3 h-3" />
              Download CSV template
            </button>
          </div>
        </div>

        {/* Footer */}
        <div className="px-4 py-3 border-t border-border/50 flex gap-2 shrink-0">
          <button
            onClick={handleConfirm}
            disabled={!preview || importing}
            className="flex-1 flex items-center justify-center gap-2 py-2 rounded bg-primary/20 border border-primary/40 text-primary font-mono text-xs hover:bg-primary/30 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            {importing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
            {importing ? 'Importing...' : `Import ${preview?.rows.length ?? 0} locations`}
          </button>
          <button onClick={onClose} className="px-4 py-2 rounded bg-secondary border border-border/40 text-muted-foreground font-mono text-xs hover:text-foreground transition-colors">
            Cancel
          </button>
        </div>

        <input ref={fileRef} type="file" accept=".csv,.json,text/csv,application/json" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) processFile(f); e.target.value = ''; }} />
      </div>
    </div>
  );
}
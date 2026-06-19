import React, { useEffect, useMemo, useState } from 'react';
import { getCatalog, LayerCatalog, CatalogFamily } from '../lib/api';

/**
 * LayerCatalogPane renders the Layer Catalog as a visibility-class → family →
 * layer folder tree (configs/layer_catalog.yaml, served by GET /catalog).
 *
 * This is the *labels-only* naming gate: it establishes the organized folder
 * structure ahead of any location data. Every layer is status="deferred" (no
 * geometry yet), so the per-layer toggles are rendered disabled — they exist to
 * show the tree and will become live once pins are wired in a later pass.
 */
const CLASS_ORDER: Array<'V3' | 'V2' | 'V1'> = ['V3', 'V2', 'V1'];

export const LayerCatalogPane: React.FC = () => {
  const [catalog, setCatalog] = useState<LayerCatalog | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let live = true;
    getCatalog().then((c) => {
      if (!live) return;
      if (c) setCatalog(c); else setError(true);
    });
    return () => { live = false; };
  }, []);

  const byClass = useMemo(() => {
    const map: Record<string, CatalogFamily[]> = { V1: [], V2: [], V3: [] };
    catalog?.families.forEach((f) => map[f.visibility]?.push(f));
    return map;
  }, [catalog]);

  if (error) return <div style={box}>Layer catalog unavailable.</div>;
  if (!catalog) return <div style={box}>Loading layer catalog…</div>;

  const layerCount = catalog.families.reduce((n, f) => n + f.layers.length, 0);

  return (
    <div style={box}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 8 }}>
        <strong>Layer Catalog</strong>
        <span style={{ fontSize: 11, color: '#888' }}>
          {layerCount} layers · {catalog.families.length} groups · labels only
        </span>
      </div>
      {CLASS_ORDER.map((vc) => {
        const meta = catalog.visibility_classes[vc];
        const families = byClass[vc];
        if (!meta || !families?.length) return null;
        return (
          <section key={vc} style={{ marginBottom: 10 }}>
            <div style={classHeader}>
              {vc} — {meta.label}
              <span style={{ fontSize: 10, color: '#999', fontWeight: 400 }}> ({meta.access_default})</span>
            </div>
            {families.map((fam) => (
              <FamilyFolder key={fam.id} family={fam} />
            ))}
          </section>
        );
      })}
    </div>
  );
};

const FamilyFolder: React.FC<{ family: CatalogFamily }> = ({ family }) => {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ marginLeft: 8 }}>
      <button onClick={() => setOpen((o) => !o)} style={folderBtn}>
        <span style={{ width: 12, display: 'inline-block' }}>{open ? '▾' : '▸'}</span>
        {family.label}
        <span style={{ fontSize: 10, color: '#999' }}> · {family.layers.length}</span>
      </button>
      {open && (
        <ul style={layerList}>
          {family.layers.map((l) => (
            <li key={l.layer_id} style={layerRow} title="Geometry not yet wired (deferred)">
              <input type="checkbox" disabled />
              <span>{l.label}</span>
              {l.pri_table && (
                <span style={badge(l.pipeline_wired)}>
                  {l.pipeline_wired ? 'wired' : 'pending'}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

const box: React.CSSProperties = {
  fontFamily: 'system-ui, sans-serif', fontSize: 13, padding: 12,
  overflowY: 'auto', maxHeight: 360, border: '1px solid #e2e2e2', borderRadius: 6,
};
const classHeader: React.CSSProperties = {
  fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.4,
  color: '#444', padding: '2px 0', borderBottom: '1px solid #eee', marginBottom: 4,
};
const folderBtn: React.CSSProperties = {
  background: 'none', border: 'none', cursor: 'pointer', padding: '3px 0',
  fontSize: 13, textAlign: 'left', width: '100%', color: '#222',
};
const layerList: React.CSSProperties = { listStyle: 'none', margin: 0, paddingLeft: 22 };
const layerRow: React.CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 6, padding: '1px 0', color: '#555',
};
const badge = (wired?: boolean): React.CSSProperties => ({
  fontSize: 9, padding: '0 4px', borderRadius: 8, marginLeft: 'auto',
  background: wired ? '#e3f3e3' : '#f3ece3', color: wired ? '#2a7' : '#a72',
});

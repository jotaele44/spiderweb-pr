import { useCallback, useEffect, useMemo, useState } from 'react';
import { MapWorkspace } from './components/MapWorkspace';
import { Inspector } from './components/Inspector';
import { Timeline } from './components/Timeline';
import { loadWorkspace } from './lib/api';
import {
  deriveTemporalWindow,
  filterEvents,
  filterSites,
  flattenLayers,
  initialLayerSelection,
  isLayerAvailable,
} from './lib/catalog';
import {
  buildVisibleFeatureCollection,
  downloadText,
  featureCollectionToCsv,
} from './lib/export';
import type {
  EvidenceTier,
  GeoJsonFeatureCollection,
  LoadIssue,
  Selection,
  TemporalWindow,
  WorkspaceData,
} from './types/gis';
import brandMark from './assets/icon-64.png?inline';

const EMPTY_DATA: WorkspaceData = {
  health: null,
  sites: [],
  events: [],
  anomalies: [],
  sources: [],
  catalog: null,
};
const TIERS: EvidenceTier[] = ['T1', 'T2', 'T3', 'T4'];

interface LayerState {
  status: string;
  message?: string;
}

export default function App() {
  const [data, setData] = useState<WorkspaceData>(EMPTY_DATA);
  const [issues, setIssues] = useState<LoadIssue[]>([]);
  const [loading, setLoading] = useState(true);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [query, setQuery] = useState('');
  const [tiers, setTiers] = useState<Set<EvidenceTier>>(new Set(TIERS));
  const [window, setWindow] = useState<TemporalWindow>(() => deriveTemporalWindow([]));
  const [cursor, setCursor] = useState(window.end);
  const [enabledLayers, setEnabledLayers] = useState<Set<string>>(new Set());
  const [layerStates, setLayerStates] = useState<Record<string, LayerState>>({});
  const [layerCollections, setLayerCollections] = useState<
    Record<string, GeoJsonFeatureCollection>
  >({});
  const [layersCollapsed, setLayersCollapsed] = useState(false);
  const [inspectorCollapsed, setInspectorCollapsed] = useState(false);
  const [theme, setTheme] = useState<'dark' | 'light'>('dark');

  const refresh = useCallback(async () => {
    setLoading(true);
    const result = await loadWorkspace();
    setData(result.data);
    setIssues(result.issues);
    const nextWindow = deriveTemporalWindow(result.data.events);
    setWindow(nextWindow);
    setCursor(nextWindow.end);
    setEnabledLayers(initialLayerSelection(result.data.catalog));
    setLayerCollections({});
    setLoading(false);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const visibleSites = useMemo(
    () => filterSites(data.sites, query),
    [data.sites, query],
  );
  const visibleEvents = useMemo(
    () => filterEvents(data.events, window)
      .filter((eventRecord) => !eventRecord.tier || tiers.has(eventRecord.tier)),
    [data.events, tiers, window],
  );
  const visibleAnomalies = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    if (!normalized) return data.anomalies;
    const siteIds = new Set(visibleSites.map((site) => site.id));
    return data.anomalies.filter((anomaly) =>
      (anomaly.siteId && siteIds.has(anomaly.siteId))
      || [anomaly.id, anomaly.title, anomaly.category, anomaly.summary]
        .some((value) => String(value ?? '').toLocaleLowerCase().includes(normalized)),
    );
  }, [data.anomalies, query, visibleSites]);

  const layers = useMemo(() => flattenLayers(data.catalog), [data.catalog]);
  const onLayerStatus = useCallback((layerId: string, status: string, message?: string) => {
    setLayerStates((current) => ({
      ...current,
      [layerId]: { status, message },
    }));
  }, []);
  const onLayerData = useCallback((
    layerId: string,
    collection: GeoJsonFeatureCollection | null,
  ) => {
    setLayerCollections((current) => {
      if (collection) return { ...current, [layerId]: collection };
      const next = { ...current };
      delete next[layerId];
      return next;
    });
  }, []);

  const exportCollection = useMemo(
    () => buildVisibleFeatureCollection(
      visibleSites,
      visibleEvents,
      visibleAnomalies,
      data.sources,
      layers
        .filter((layer) => enabledLayers.has(layer.layer_id))
        .flatMap((layer) => {
          const collection = layerCollections[layer.layer_id];
          return collection ? [{ layer, collection }] : [];
        }),
    ),
    [
      data.sources,
      enabledLayers,
      layerCollections,
      layers,
      visibleAnomalies,
      visibleEvents,
      visibleSites,
    ],
  );

  function toggleTier(tier: EvidenceTier): void {
    setTiers((current) => {
      const next = new Set(current);
      if (next.has(tier)) next.delete(tier);
      else next.add(tier);
      return next;
    });
  }

  function toggleLayer(layerId: string): void {
    setEnabledLayers((current) => {
      const next = new Set(current);
      if (next.has(layerId)) next.delete(layerId);
      else next.add(layerId);
      return next;
    });
  }

  function exportGeoJson(): void {
    downloadText(
      `spiderweb-spatial-${new Date().toISOString().slice(0, 10)}.geojson`,
      JSON.stringify(exportCollection, null, 2),
      'application/geo+json',
    );
  }

  function exportCsv(): void {
    downloadText(
      `spiderweb-spatial-${new Date().toISOString().slice(0, 10)}.csv`,
      featureCollectionToCsv(exportCollection),
      'text/csv',
    );
  }

  return (
    <div
      className="app-shell"
      data-layers-collapsed={layersCollapsed}
      data-inspector-collapsed={inspectorCollapsed}
      data-export-feature-count={exportCollection.features.length}
    >
      <header className="topbar">
        <div className="brand">
          <img src={brandMark} alt="" aria-hidden="true" />
          <div>
            <strong>Spiderweb</strong>
            <span>Spatial intelligence workbench</span>
          </div>
        </div>
        <label className="search">
          <span className="sr-only">Search spatial records</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search site, geography, infrastructure, or record ID"
          />
        </label>
        <div className="topbar-actions">
          <span
            className="status-chip"
            data-status={data.health?.status ?? 'loading'}
            title={data.health?.reason}
          >
            {loading ? 'Loading' : data.health?.status ?? 'API unavailable'}
          </span>
          <button type="button" onClick={exportGeoJson}>Export GeoJSON</button>
          <button type="button" onClick={exportCsv}>Export CSV</button>
          <button
            type="button"
            aria-label="Toggle color theme"
            onClick={() => setTheme((value) => value === 'dark' ? 'light' : 'dark')}
          >
            {theme === 'dark' ? 'Light' : 'Dark'}
          </button>
        </div>
      </header>

      {issues.length > 0 && (
        <section className="error-banner" role="alert">
          <div>
            <strong>Some spatial sources are unavailable.</strong>
            <span>No synthetic or demo records were substituted.</span>
          </div>
          <ul>
            {issues.map((issue) => (
              <li key={issue.endpoint}><code>{issue.endpoint}</code> — {issue.message}</li>
            ))}
          </ul>
          <button type="button" onClick={() => void refresh()}>Retry</button>
        </section>
      )}

      <aside className="layer-sidebar" aria-label="Layer and filter controls">
        <div className="sidebar-heading">
          <div><span>GIS</span><strong>Layer catalog</strong></div>
          <button
            type="button"
            aria-label="Collapse layer controls"
            onClick={() => setLayersCollapsed(true)}
          >«</button>
        </div>

        <section className="filter-section">
          <h2>Temporal window</h2>
          <label>Start<input type="date" value={window.start} onChange={(event) => setWindow((current) => ({ ...current, start: event.target.value }))} /></label>
          <label>End<input type="date" value={window.end} onChange={(event) => setWindow((current) => ({ ...current, end: event.target.value }))} /></label>
        </section>

        <section className="filter-section">
          <h2>Evidence tiers</h2>
          <div className="tier-grid">
            {TIERS.map((tier) => (
              <button
                type="button"
                key={tier}
                data-active={tiers.has(tier)}
                data-tier={tier}
                onClick={() => toggleTier(tier)}
              >{tier}</button>
            ))}
          </div>
        </section>

        <section className="catalog">
          <h2>Spatial layers</h2>
          {!data.catalog && <p className="empty-copy">Catalog unavailable.</p>}
          {data.catalog?.families.map((family) => (
            <details key={family.id} open={family.id === 'admin_geographies'}>
              <summary>{family.label}<span>{family.layers.length}</span></summary>
              {family.layers.map((layer) => {
                const available = isLayerAvailable(layer);
                const runtime = layerStates[layer.layer_id]?.status ?? layer.runtime_status ?? 'deferred';
                return (
                  <button
                    type="button"
                    key={layer.layer_id}
                    className="layer-toggle"
                    disabled={!available}
                    data-active={enabledLayers.has(layer.layer_id)}
                    data-status={runtime}
                    title={layerStates[layer.layer_id]?.message ?? `${layer.label}: ${runtime}`}
                    onClick={() => toggleLayer(layer.layer_id)}
                  >
                    <span>{layer.label}</span>
                    <span>{runtime}</span>
                  </button>
                );
              })}
            </details>
          ))}
        </section>

        <section className="source-ledger">
          <h2>Source ledger</h2>
          {!data.sources.length && <p className="empty-copy">No source records supplied.</p>}
          {data.sources.map((source) => (
            <div key={source.id}>
              <span>{source.name}</span>
              <small>{source.tier ?? 'tier n/a'} · {source.status ?? 'status n/a'}</small>
            </div>
          ))}
        </section>
      </aside>

      {layersCollapsed && (
        <button
          type="button"
          className="restore-panel restore-panel--left"
          onClick={() => setLayersCollapsed(false)}
        >Layers »</button>
      )}

      <main className="workspace">
        <div className="workspace-heading">
          <div>
            <span>Puerto Rico</span>
            <h1>Spatial intelligence</h1>
          </div>
          <div className="workspace-stats">
            <span>{visibleSites.length} sites</span>
            <span>{visibleEvents.length} events</span>
            <span>{visibleAnomalies.length} anomalies</span>
            <span>{layers.filter(isLayerAvailable).length} live/empty catalog layers</span>
          </div>
          <button
            type="button"
            onClick={() => setInspectorCollapsed((value) => !value)}
          >{inspectorCollapsed ? 'Show inspector' : 'Hide inspector'}</button>
        </div>
        <MapWorkspace
          sites={visibleSites}
          events={visibleEvents}
          anomalies={visibleAnomalies}
          catalog={data.catalog}
          enabledLayers={enabledLayers}
          onLayerStatus={onLayerStatus}
          onLayerData={onLayerData}
          onSelect={setSelection}
        />
      </main>

      {!inspectorCollapsed && <Inspector data={data} selection={selection} />}

      <Timeline
        events={visibleEvents}
        window={window}
        cursor={cursor}
        onCursor={setCursor}
        onSelect={setSelection}
      />
    </div>
  );
}

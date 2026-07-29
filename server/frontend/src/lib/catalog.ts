import type {
  CatalogLayer,
  EventRecord,
  LayerCatalog,
  Site,
  TemporalWindow,
} from '../types/gis';

export function flattenLayers(catalog: LayerCatalog | null): CatalogLayer[] {
  return catalog?.families.flatMap((family) => family.layers) ?? [];
}

export function isLayerAvailable(layer: CatalogLayer): boolean {
  return layer.runtime_status === 'live' || layer.runtime_status === 'empty';
}

export function initialLayerSelection(catalog: LayerCatalog | null): Set<string> {
  const preferred = ['municipios', 'tracts', 'places', 'barrios'];
  const available = new Set(
    flattenLayers(catalog).filter(isLayerAvailable).map((layer) => layer.layer_id),
  );
  return new Set(preferred.filter((layerId) => available.has(layerId)));
}

export function filterSites(sites: Site[], query: string): Site[] {
  const normalized = query.trim().toLocaleLowerCase();
  if (!normalized) return sites;
  return sites.filter((site) =>
    [
      site.id,
      site.name,
      site.kind,
      site.infrastructure_class,
      site.municipio_geoid,
      site.tract_geoid,
      site.zcta_geoid,
    ].some((value) => String(value ?? '').toLocaleLowerCase().includes(normalized)),
  );
}

export function filterEvents(events: EventRecord[], window: TemporalWindow): EventRecord[] {
  const start = Date.parse(window.start);
  const end = Date.parse(window.end);
  if (Number.isNaN(start) || Number.isNaN(end)) return events;
  return events.filter((event) => {
    const value = Date.parse(event.at);
    return !Number.isNaN(value) && value >= start && value <= end;
  });
}

export function deriveTemporalWindow(events: EventRecord[]): TemporalWindow {
  const dates = events
    .map((event) => Date.parse(event.at))
    .filter((value) => !Number.isNaN(value));
  const now = new Date();
  if (!dates.length) {
    const start = new Date(now);
    start.setUTCFullYear(start.getUTCFullYear() - 1);
    return {
      start: start.toISOString().slice(0, 10),
      end: now.toISOString().slice(0, 10),
    };
  }
  return {
    start: new Date(Math.min(...dates)).toISOString().slice(0, 10),
    end: new Date(Math.max(...dates)).toISOString().slice(0, 10),
  };
}

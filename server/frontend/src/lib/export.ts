import type {
  Anomaly,
  EventRecord,
  CatalogLayer,
  GeoJsonFeature,
  GeoJsonFeatureCollection,
  Site,
  SourceRecord,
} from '../types/gis';

interface CatalogGeometry {
  layer: CatalogLayer;
  collection: GeoJsonFeatureCollection;
}

function linkedProvenance(
  record: { sourceIds?: string[]; lineage?: unknown[] },
  sources: SourceRecord[],
): Record<string, unknown> {
  const sourceIds = record.sourceIds ?? [];
  const linked = sourceIds
    .map((sourceId) => sources.find((source) => source.id === sourceId))
    .filter((source): source is SourceRecord => Boolean(source));
  return {
    source_ids: sourceIds,
    source_url: linked.find((source) => source.url)?.url ?? null,
    captured_at: linked.find((source) => source.capturedAt)?.capturedAt ?? null,
    hash: linked.find((source) => source.hash)?.hash ?? null,
    lineage: record.lineage?.length
      ? record.lineage
      : linked.flatMap((source) => source.lineage ?? []),
  };
}

function sitePoint(
  site: Site,
  properties: Record<string, unknown>,
  sources: SourceRecord[],
): GeoJsonFeature {
  const featureId = typeof properties.record_id === 'string'
    || typeof properties.record_id === 'number'
    ? properties.record_id
    : site.id;
  return {
    type: 'Feature',
    id: featureId,
    geometry: { type: 'Point', coordinates: [site.lng, site.lat] },
    properties: {
      record_id: site.id,
      source_endpoint: '/sites',
      provenance: `spiderweb-pr:/sites/${site.id}`,
      ...linkedProvenance(site, sources),
      ...properties,
    },
  };
}

export function buildVisibleFeatureCollection(
  sites: Site[],
  events: EventRecord[],
  anomalies: Anomaly[],
  sources: SourceRecord[] = [],
  catalogGeometries: CatalogGeometry[] = [],
): GeoJsonFeatureCollection {
  const byId = new Map(sites.map((site) => [site.id, site]));
  const features: GeoJsonFeature[] = sites.map((site) =>
    sitePoint(site, {
      record_type: 'site',
      name: site.name,
      site_kind: site.kind,
      sensitive: Boolean(site.sensitive),
      evidence_tier: null,
      confidence: null,
      observed_at: null,
    }, sources),
  );

  for (const event of events) {
    const site = event.siteId ? byId.get(event.siteId) : undefined;
    if (!site) continue;
    features.push(sitePoint(site, {
      record_id: event.id,
      record_type: 'event',
      label: event.label,
      event_kind: event.kind,
      evidence_tier: event.tier ?? null,
      confidence: null,
      observed_at: event.at,
      source_endpoint: '/events',
      provenance: `spiderweb-pr:/events/${event.id}`,
      ...linkedProvenance(event, sources),
    }, sources));
  }

  for (const anomaly of anomalies) {
    const site = anomaly.siteId ? byId.get(anomaly.siteId) : undefined;
    if (!site) continue;
    features.push(sitePoint(site, {
      record_id: anomaly.id,
      record_type: 'anomaly',
      label: anomaly.title,
      category: anomaly.category,
      score: anomaly.score,
      evidence_tier: null,
      confidence: anomaly.confidence ?? null,
      observed_at: null,
      source_endpoint: '/anomalies',
      provenance: `spiderweb-pr:/anomalies/${anomaly.id}`,
      ...linkedProvenance(anomaly, sources),
    }, sources));
  }

  for (const { layer, collection } of catalogGeometries) {
    for (const feature of collection.features) {
      const properties = feature.properties ?? {};
      const featureId = feature.id
        ?? properties.record_id
        ?? properties.id
        ?? properties.GEOID
        ?? `${layer.layer_id}-${features.length + 1}`;
      features.push({
        ...feature,
        id: featureId as string | number,
        properties: {
          ...properties,
          record_id: featureId,
          record_type: 'catalog_feature',
          layer_id: layer.layer_id,
          source_endpoint: layer.endpoint ?? `/geo/${layer.layer_id}.geojson`,
          source_ids: properties.source_ids ?? layer.provenance?.source_ids ?? [],
          source_url: properties.source_url ?? properties.url
            ?? layer.provenance?.url ?? null,
          captured_at: properties.captured_at
            ?? layer.provenance?.captured_at ?? null,
          hash: properties.hash ?? layer.provenance?.hash ?? null,
          lineage: properties.lineage ?? layer.provenance?.lineage ?? [],
          catalog_provenance: layer.provenance?.catalog ?? null,
          geometry_source: layer.provenance?.geometry_source ?? null,
          provenance: properties.provenance
            ?? `spiderweb-pr:/geo/${layer.layer_id}/${String(featureId)}`,
        },
      });
    }
  }

  return { type: 'FeatureCollection', features };
}

function escapeCell(value: unknown): string {
  const text = value == null
    ? ''
    : typeof value === 'object'
      ? JSON.stringify(value)
      : String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function featureCollectionToCsv(collection: GeoJsonFeatureCollection): string {
  const headers = [
    'record_id',
    'record_type',
    'label',
    'evidence_tier',
    'confidence',
    'observed_at',
    'source_endpoint',
    'source_ids',
    'source_url',
    'captured_at',
    'hash',
    'lineage',
    'layer_id',
    'catalog_provenance',
    'geometry_source',
    'provenance',
    'geometry_type',
    'geometry_json',
    'longitude',
    'latitude',
  ];
  const rows = collection.features.map((feature) => {
    const properties = feature.properties ?? {};
    const coordinates = feature.geometry?.type === 'Point'
      ? feature.geometry.coordinates as [number, number]
      : [null, null];
    return headers.map((header) => {
      if (header === 'longitude') return coordinates[0];
      if (header === 'latitude') return coordinates[1];
      if (header === 'geometry_type') return feature.geometry?.type;
      if (header === 'geometry_json') return feature.geometry;
      return properties[header];
    });
  });
  return [headers, ...rows].map((row) => row.map(escapeCell).join(',')).join('\n');
}

export function downloadText(filename: string, content: string, type: string): void {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

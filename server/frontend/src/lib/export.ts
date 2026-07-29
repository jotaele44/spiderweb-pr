import type {
  Anomaly,
  EventRecord,
  GeoJsonFeature,
  GeoJsonFeatureCollection,
  Site,
} from '../types/gis';

function sitePoint(site: Site, properties: Record<string, unknown>): GeoJsonFeature {
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
      ...properties,
    },
  };
}

export function buildVisibleFeatureCollection(
  sites: Site[],
  events: EventRecord[],
  anomalies: Anomaly[],
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
    }),
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
    }));
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
    }));
  }

  return { type: 'FeatureCollection', features };
}

function escapeCell(value: unknown): string {
  const text = value == null ? '' : String(value);
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
    'provenance',
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

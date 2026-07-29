import type {
  Anomaly,
  EventRecord,
  GeoJsonFeatureCollection,
  Health,
  LayerCatalog,
  LoadIssue,
  Site,
  SourceRecord,
  WorkspaceData,
} from '../types/gis';

export const API_BASE = (import.meta.env.VITE_API_BASE ?? '').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(
    public readonly endpoint: string,
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(endpoint: string): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    headers: { Accept: 'application/json' },
    signal: AbortSignal.timeout(8_000),
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json() as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // Keep the status text when an upstream proxy returns non-JSON.
    }
    throw new ApiError(endpoint, response.status, detail);
  }
  return response.json() as Promise<T>;
}

const emptyData = (): WorkspaceData => ({
  health: null,
  sites: [],
  events: [],
  anomalies: [],
  sources: [],
  catalog: null,
});

export async function loadWorkspace(): Promise<{
  data: WorkspaceData;
  issues: LoadIssue[];
}> {
  const data = emptyData();
  const issues: LoadIssue[] = [];
  const endpoints = [
    ['/health', 'health'],
    ['/sites', 'sites'],
    ['/events', 'events'],
    ['/anomalies', 'anomalies'],
    ['/sources', 'sources'],
    ['/catalog', 'catalog'],
  ] as const;

  const results = await Promise.allSettled([
    request<Health>('/health'),
    request<Site[]>('/sites'),
    request<EventRecord[]>('/events'),
    request<Anomaly[]>('/anomalies'),
    request<SourceRecord[]>('/sources'),
    request<LayerCatalog>('/catalog'),
  ]);

  results.forEach((result, index) => {
    const [endpoint, key] = endpoints[index];
    if (result.status === 'fulfilled') {
      (data as unknown as Record<string, unknown>)[key] = result.value;
    } else {
      issues.push({
        endpoint,
        message: result.reason instanceof Error ? result.reason.message : String(result.reason),
      });
    }
  });
  return { data, issues };
}

export async function getGeoLayer(layerId: string): Promise<GeoJsonFeatureCollection> {
  const collection = await request<GeoJsonFeatureCollection>(
    `/geo/${encodeURIComponent(layerId)}.geojson`,
  );
  if (collection.type !== 'FeatureCollection' || !Array.isArray(collection.features)) {
    throw new ApiError(`/geo/${layerId}.geojson`, 502, 'invalid GeoJSON FeatureCollection');
  }
  return collection;
}

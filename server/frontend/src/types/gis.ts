export type EvidenceTier = 'T1' | 'T2' | 'T3' | 'T4';

export interface Health {
  status: 'ok' | 'degraded' | string;
  db_exists?: boolean;
  reason?: string;
  table_count?: number;
}

export interface Site {
  id: string;
  name: string;
  kind: string;
  lat: number;
  lng: number;
  sensitive?: boolean;
  infrastructure_class?: string | null;
  municipio_geoid?: string | null;
  tract_geoid?: string | null;
  zcta_geoid?: string | null;
}

export interface EventRecord {
  id: string;
  kind: string;
  at: string;
  siteId?: string | null;
  refId?: string | null;
  label: string;
  tier?: EvidenceTier | null;
}

export interface AnomalyFactor {
  tag: string;
  note: string;
}

export interface Anomaly {
  id: string;
  title: string;
  category: string;
  score: number;
  band: string;
  siteId?: string | null;
  summary?: string | null;
  factors?: AnomalyFactor[];
  confidence?: number | null;
  contradictions?: string[];
}

export interface SourceRecord {
  id: string;
  name: string;
  tier?: EvidenceTier | null;
  kind?: string | null;
  status?: string | null;
}

export type LayerRuntimeStatus = 'live' | 'empty' | 'unavailable' | 'deferred';

export interface CatalogLayer {
  layer_id: string;
  label: string;
  status?: string;
  runtime_status?: LayerRuntimeStatus;
  pipeline_wired?: boolean;
  feature_count?: number | null;
  endpoint?: string;
  provenance?: {
    catalog: string;
    geometry_source: string;
  };
}

export interface CatalogFamily {
  id: string;
  label: string;
  visibility: string;
  domain?: string;
  layers: CatalogLayer[];
}

export interface LayerCatalog {
  version: string;
  binding?: string;
  families: CatalogFamily[];
  visibility_classes?: Record<string, {
    label: string;
    rank: number;
    access_default: string;
  }>;
}

export interface GeoJsonGeometry {
  type: string;
  coordinates?: unknown;
  geometries?: GeoJsonGeometry[];
}

export interface GeoJsonFeature {
  type: 'Feature';
  id?: string | number;
  geometry: GeoJsonGeometry | null;
  properties: Record<string, unknown> | null;
}

export interface GeoJsonFeatureCollection {
  type: 'FeatureCollection';
  features: GeoJsonFeature[];
}

export interface WorkspaceData {
  health: Health | null;
  sites: Site[];
  events: EventRecord[];
  anomalies: Anomaly[];
  sources: SourceRecord[];
  catalog: LayerCatalog | null;
}

export interface LoadIssue {
  endpoint: string;
  message: string;
}

export type Selection =
  | { kind: 'site'; id: string }
  | { kind: 'event'; id: string }
  | { kind: 'anomaly'; id: string }
  | {
      kind: 'feature';
      id: string;
      layerId: string;
      properties: Record<string, unknown>;
    };

export interface TemporalWindow {
  start: string;
  end: string;
}

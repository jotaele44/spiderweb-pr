export type EvidenceTier = 'T1' | 'T2' | 'T3' | 'T4';

export interface Health {
  status: 'ok' | 'degraded' | string;
  db_exists?: boolean;
  reason?: string;
  table_count?: number;
}

export interface LineageStep {
  actor?: string;
  step?: string;
  at?: string | null;
  source?: string | null;
  output?: string | null;
  [key: string]: unknown;
}

export interface ProvenanceLinked {
  sourceIds?: string[];
  lineage?: LineageStep[];
}

export interface Site extends ProvenanceLinked {
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

export interface EventRecord extends ProvenanceLinked {
  id: string;
  kind: string;
  at: string;
  siteId?: string | null;
  refId?: string | null;
  label: string;
  tier?: EvidenceTier | null;
}

export interface AnomalyFactor extends ProvenanceLinked {
  tag: string;
  note: string;
}

export interface Anomaly extends ProvenanceLinked {
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
  publisher?: string | null;
  url?: string | null;
  capturedAt?: string | null;
  hash?: string | null;
  lineage?: LineageStep[];
  provenanceNote?: string | null;
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
    source_ids?: string[];
    url?: string | null;
    captured_at?: string | null;
    hash?: string | null;
    lineage?: LineageStep[];
    manifest?: string | null;
    geometry_path?: string | null;
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

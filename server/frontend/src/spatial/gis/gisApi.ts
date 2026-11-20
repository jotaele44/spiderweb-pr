/**
 * Typed client for the backend /gis/* API (docs/GIS_VIEWER_API.md).
 * Contracts: schemas/gis_layer_catalog_v1.schema.json, gis_query_v1.schema.json.
 */
import type { Feature, Polygon } from "geojson";

export type QueryMode = "point" | "radius" | "bbox" | "polygon";

export interface GisCatalogLayer {
  layer_id: string;
  title: string;
  category: string;
  group: string | null;
  access_default: "PUBLIC" | "RESTRICTED" | "OBSERVE_ONLY" | null;
  status: "active" | "deferred" | "blocked";
  geometry_types: string[];
  min_zoom: number | null;
  max_zoom: number | null;
  identify_fields: string[];
  search_fields: string[];
  query_modes: QueryMode[];
  temporal_field: string | null;
  exportable: boolean;
  data_available?: boolean;
}

export interface GisCatalog {
  contract_version: "gis-layer-catalog/1.0";
  producer_repo: string;
  layers: GisCatalogLayer[];
}

export interface IdentifyHit {
  layer_id: string;
  feature_id: string | null;
  distance_m: number;
  properties: Record<string, unknown>;
  anchor: [number, number] | null;
  bbox: [number, number, number, number] | null;
}

export interface IdentifyResponse {
  point: { lon: number; lat: number };
  tolerance_m: number;
  hits: IdentifyHit[];
  location: Record<string, unknown>;
  evidence_state: "COMPUTED";
}

export interface SearchHit {
  kind: "feature" | "coordinate";
  layer_id: string | null;
  feature_id: string | null;
  label: string;
  field: string | null;
  rank: number;
  anchor: [number, number] | null;
  bbox: [number, number, number, number] | null;
}

export interface QueryLayerResult {
  layer_id: string;
  matched_count: number;
  returned_count: number;
  excluded_count: number;
  truncated: boolean;
  error: string | null;
  features: Feature[];
}

export interface QueryResponse {
  contract_version: "gis-query/1.0";
  layers: QueryLayerResult[];
  total_matched: number;
  summary: Record<string, unknown>;
  evidence_state: "COMPUTED";
}

export interface GisClient {
  catalog(signal?: AbortSignal): Promise<GisCatalog>;
  identify(lon: number, lat: number, layers: string[], toleranceM?: number): Promise<IdentifyResponse>;
  search(query: string, signal?: AbortSignal): Promise<SearchHit[]>;
  queryPolygon(polygon: Feature<Polygon>, layers: string[]): Promise<QueryResponse>;
  exportPolygon(polygon: Feature<Polygon>, layers: string[], format: "geojson" | "csv"): Promise<Blob>;
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = `${detail}: ${body.detail}`;
    } catch { /* non-JSON error body */ }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export function polygonQueryBody(polygon: Feature<Polygon>, layers: string[]) {
  return {
    contract_version: "gis-query/1.0",
    geometry: { type: "polygon", geojson: polygon.geometry },
    layers,
  };
}

export function createGisClient(apiBase: string, fetchImpl: typeof fetch = fetch): GisClient {
  const post = (path: string, body: unknown) =>
    fetchImpl(`${apiBase}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  return {
    async catalog(signal) {
      return readJson<GisCatalog>(await fetchImpl(`${apiBase}/gis/catalog`, { signal }));
    },
    async identify(lon, lat, layers, toleranceM = 25) {
      const params = new URLSearchParams({ lon: String(lon), lat: String(lat), tol_m: String(toleranceM) });
      if (layers.length) params.set("layers", layers.join(","));
      return readJson<IdentifyResponse>(await fetchImpl(`${apiBase}/gis/identify?${params.toString()}`));
    },
    async search(query, signal) {
      const params = new URLSearchParams({ q: query });
      const body = await readJson<{ hits: SearchHit[] }>(await fetchImpl(`${apiBase}/gis/search?${params.toString()}`, { signal }));
      return body.hits;
    },
    async queryPolygon(polygon, layers) {
      return readJson<QueryResponse>(await post("/gis/query", polygonQueryBody(polygon, layers)));
    },
    async exportPolygon(polygon, layers, format) {
      const response = await post("/gis/export", { ...polygonQueryBody(polygon, layers), format });
      if (!response.ok) await readJson<never>(response);
      return response.blob();
    },
  };
}

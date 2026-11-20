import { z } from "zod";
import { API_BASE } from "../../config";

/**
 * Client for the backend's NOAA Emergency Response Imagery routes
 * (server/backend/eri_imagery.py). The bucket publishes GeoTIFFs, not map
 * tiles, so the map never talks to it directly: tiles and footprints both come
 * from the backend, which only reads flights listed in
 * configs/eri_imagery_sources.yaml.
 */

const bbox = z.tuple([z.number(), z.number(), z.number(), z.number()]);

export const eriDatasetSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  event: z.string(),
  flight: z.string(),
  kind: z.enum(["pre_event", "post_event"]),
  acquired: z.string(),
  bbox,
  min_zoom: z.number().int(),
  max_zoom: z.number().int(),
  source_url: z.string(),
});

export const eriCatalogSchema = z.object({
  attribution: z.string(),
  tile_size: z.number().int().positive(),
  datasets: z.array(eriDatasetSchema),
});

export const eriFootprintSchema = z.object({
  name: z.string(),
  dataset_id: z.string(),
  dataset_label: z.string(),
  acquired: z.string(),
  size_bytes: z.number(),
  url: z.string(),
});

export type EriDataset = z.infer<typeof eriDatasetSchema>;
export type EriCatalog = z.infer<typeof eriCatalogSchema>;
export type EriFootprint = z.infer<typeof eriFootprintSchema>;

/**
 * MapLibre resolves tile templates in a worker, where a bare `/imagery/...`
 * path has no base to resolve against. A production build uses a same-origin
 * (empty) API base, so anchor it to the page origin explicitly.
 */
export function eriBaseUrl(apiBase: string = API_BASE, origin: string = window.location.origin): string {
  const base = apiBase.replace(/\/$/, "");
  return /^https?:\/\//.test(base) ? base : `${origin}${base}`;
}

export function eriTileUrlTemplate(datasetId: string, apiBase?: string, origin?: string): string {
  return `${eriBaseUrl(apiBase, origin)}/imagery/eri/${encodeURIComponent(datasetId)}/tiles/{z}/{x}/{y}.png`;
}

export function eriFootprintsUrl(datasetId: string, apiBase?: string, origin?: string): string {
  return `${eriBaseUrl(apiBase, origin)}/imagery/eri/${encodeURIComponent(datasetId)}/footprints.geojson`;
}

export async function fetchEriCatalog(signal?: AbortSignal): Promise<EriCatalog> {
  const response = await fetch(`${eriBaseUrl()}/imagery/eri/datasets`, { signal });
  if (!response.ok) throw new Error(`imagery catalog request failed (${response.status})`);
  return eriCatalogSchema.parse(await response.json());
}

/** Human-readable acquisition date; a bare year is shown as is. */
export function formatAcquired(acquired: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(acquired);
  if (!match) return acquired;
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${Number(match[3])} ${months[Number(match[2]) - 1]} ${match[1]}`;
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "—";
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** True when `[lng, lat]` falls inside the dataset's extent. */
export function datasetContains(dataset: EriDataset, lng: number, lat: number): boolean {
  const [west, south, east, north] = dataset.bbox;
  return lng >= west && lng <= east && lat >= south && lat <= north;
}

export function datasetCenter(dataset: EriDataset): [number, number] {
  const [west, south, east, north] = dataset.bbox;
  return [(west + east) / 2, (south + north) / 2];
}

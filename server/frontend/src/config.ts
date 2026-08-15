/**
 * Runtime configuration. The API base can be overridden at build time with
 * `VITE_API_BASE` (e.g. to point the frontend at a non-local backend).
 *
 * A production build defaults to the empty string so every request is
 * same-origin: the desktop wrapper (desktop/app_server.py) serves this bundle
 * and the FastAPI backend from one ephemeral port, so a hardcoded
 * `localhost:8000` would miss it. `vite dev` still falls back to the local
 * backend's default port.
 */
export const API_BASE: string =
  import.meta.env.VITE_API_BASE ?? (import.meta.env.PROD ? "" : "http://localhost:8000");

/**
 * Martin tile-delivery base URL.
 *
 * Production defaults to `/tiles` so a same-origin reverse proxy can keep
 * Martin private. Vite development uses the same path and proxies it to the
 * local Martin canary. Override only when an explicit deployment requires a
 * different ingress path.
 */
export const MARTIN_BASE: string =
  import.meta.env.VITE_MARTIN_BASE ?? "/tiles";

/** Return the TileJSON URL for an explicitly registered Martin source. */
export function martinTileJsonUrl(sourceId: string): string {
  const base = MARTIN_BASE.replace(/\/$/, "");
  return `${base}/${encodeURIComponent(sourceId)}`;
}

/** Return the MVT template for an explicitly registered Martin source. */
export function martinTileUrlTemplate(sourceId: string): string {
  const base = MARTIN_BASE.replace(/\/$/, "");
  return `${base}/${encodeURIComponent(sourceId)}/{z}/{x}/{y}`;
}

/**
 * Raster base-map tile template for the Spatial module.
 *
 * Defaults to public OpenStreetMap tiles. Override with `VITE_TILE_URL` to point
 * a packaged desktop build at a local or self-hosted tile source — the app is
 * otherwise fully offline-capable (fonts are bundled, the fixture dataset is the
 * fallback), and this is the one runtime asset that still requires the network.
 */
export const TILE_URL: string =
  import.meta.env.VITE_TILE_URL ?? "https://tile.openstreetmap.org/{z}/{x}/{y}.png";

/** Attribution shown on the base map. Override alongside `VITE_TILE_URL`. */
export const TILE_ATTRIBUTION: string =
  import.meta.env.VITE_TILE_ATTRIBUTION ?? "© OpenStreetMap contributors";

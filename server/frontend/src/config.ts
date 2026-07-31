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

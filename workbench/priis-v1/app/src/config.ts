/**
 * Runtime configuration. The API base can be overridden at build time with
 * `VITE_API_BASE` (e.g. to point the workbench at a non-local backend); it
 * falls back to the local FastAPI dev server.
 */
export const API_BASE: string =
  import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

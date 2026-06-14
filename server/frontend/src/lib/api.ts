// Typed REST client for the spiderweb-pr FastAPI backend (server/backend/main.py,
// 18 endpoints, served on :8000). The backend returns camelCase keys for event
// fields (siteId, altitudeFt, flightStatus, …). Every call degrades gracefully:
// on error it resolves to the provided fallback instead of throwing.

import snapshotData from './snapshot.json' // {} in normal builds; populated for VITE_OFFLINE exports
export const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

// Offline export build: resolve from an embedded data snapshot instead of fetching.
// (A file:// page cannot fetch at all, so standalone exports bake the data in.)
const OFFLINE = import.meta.env.VITE_OFFLINE === '1'
const snapshot = snapshotData as Record<string, unknown>

export interface Site {
  id: string; name: string; kind: string; lat: number; lng: number
  sensitive: boolean; infrastructure_class?: string
}
export interface EventRow {
  id: string; kind: string; at: string; label?: string; tier?: string
  siteId?: string; refId?: string; registration?: string | null; callsign?: string | null
  aircraftType?: string | null; flightStatus?: string | null; altitudeFt?: number | null
}
export interface TrackPoint { ts: number; at: string; lat: number; lng: number; altitudeFt?: number | null; speed?: number; direction?: number }
export interface Anomaly {
  id: string; title: string; category?: string; score: number; band: string
  siteId?: string; summary?: string; factors?: { tag: string; note: string }[]
  contracts?: string[]; events?: string[]; confidence?: number; contradictions?: string[]
}
export interface Contract {
  id: string; agency?: string; vendor?: string; site?: string; amount?: number | null
  signed?: string; status?: string; tier?: string; note?: string; procurement_method?: string
}
export interface Source { id: string; name: string; tier?: string; kind?: string; status?: string }
export type GeoJSON = { type: 'FeatureCollection'; features: any[] }

async function getJSON<T>(path: string, fallback: T): Promise<T> {
  if (OFFLINE) {
    const key = path.split('?')[0] // server-side filters degrade to the unfiltered snapshot
    return key in snapshot ? (snapshot[key] as T) : fallback
  }
  try {
    const res = await fetch(`${API_BASE}${path}`, { signal: AbortSignal.timeout(8000) })
    if (!res.ok) return fallback
    return (await res.json()) as T
  } catch {
    return fallback
  }
}

export const getHealth = () => getJSON<{ status: string; table_count?: number }>('/health', { status: 'down' })
export const getSites = () => getJSON<Site[]>('/sites', [])
export const getEvents = () => getJSON<EventRow[]>('/events', [])
export const getEventTrack = (id: string) => getJSON<TrackPoint[]>(`/events/${encodeURIComponent(id)}/track`, [])
export const getAnomalies = () => getJSON<Anomaly[]>('/anomalies', [])
export const getContracts = () => getJSON<Contract[]>('/contracts', [])
export const getSources = () => getJSON<Source[]>('/sources', [])
export const getGeoLayer = (layer: string) => getJSON<GeoJSON | null>(`/geo/${layer}.geojson`, null)

// Streaming RAG query (SSE). Returns an abort function.
export function streamRagQuery(
  payload: { query: string; top_k?: number },
  cb: { onToken?: (t: string) => void; onDone?: () => void; onError?: (m: string) => void },
): () => void {
  const controller = new AbortController()
  fetch(`${API_BASE}/rag/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal: controller.signal,
  })
    .then(async (res) => {
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      for (;;) {
        const { done, value } = await reader.read()
        if (done) { cb.onDone?.(); break }
        const chunk = decoder.decode(value, { stream: true })
        for (const line of chunk.split('\n').filter(Boolean)) {
          const text = line.startsWith('data:') ? line.slice(5).trim() : line
          if (text === '[DONE]') { cb.onDone?.(); return }
          cb.onToken?.(text)
        }
      }
    })
    .catch((err) => { if (err.name !== 'AbortError') cb.onError?.(err.message || 'RAG unavailable') })
  return () => controller.abort()
}

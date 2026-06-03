/**
 * PRIIS API client — typed wrappers for the FastAPI backend.
 * Falls back to mock data when the API is unreachable.
 * All API responses are validated against Zod schemas.
 */
import type { PriisData, TrackPoint } from "../types/priis";
import { priisData } from "../data/mockData";
import {
  parseArray,
  AgencySchema, VendorSchema, SiteSchema, ContractSchema,
  EventRecordSchema, AnomalySchema, SourceRecordSchema,
  InvestigationSchema, AlertRecordSchema,
} from "../schemas/priis";

const BASE = "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

/** Fetch all PRIIS entities and assemble into PriisData shape. */
export async function fetchPriisData(): Promise<PriisData> {
  const [agencies, vendors, sites, contracts, events, anomalies, sources, investigations, alerts] =
    await Promise.all([
      get("/agencies"),
      get("/vendors"),
      get("/sites"),
      get("/contracts"),
      get("/events"),
      get("/anomalies"),
      get("/sources"),
      get("/investigations"),
      get("/alerts"),
    ]);

  return {
    agencies:       parseArray(AgencySchema,       agencies       as unknown[]),
    vendors:        parseArray(VendorSchema,        vendors        as unknown[]),
    sites:          parseArray(SiteSchema,          sites          as unknown[]),
    contracts:      parseArray(ContractSchema,      contracts      as unknown[]),
    events:         parseArray(EventRecordSchema,   events         as unknown[]),
    anomalies:      parseArray(AnomalySchema,       anomalies      as unknown[]),
    sources:        parseArray(SourceRecordSchema,  sources        as unknown[]),
    investigations: parseArray(InvestigationSchema, investigations as unknown[]),
    alerts:         parseArray(AlertRecordSchema,   alerts         as unknown[]),
    watchlist: [],
  };
}

/** Fetch PriisData, falling back to the bundled mock when the server is down. */
export async function fetchPriisDataWithFallback(): Promise<{ data: PriisData; live: boolean }> {
  try {
    const data = await fetchPriisData();
    return { data, live: true };
  } catch {
    return { data: priisData, live: false };
  }
}

// ─── Pipeline ──────────────────────────────────────────────────────────────────

export interface PipelineJob {
  job_id: string;
  status: "running" | "done" | "error";
}

export async function startPipeline(phase?: number): Promise<PipelineJob> {
  const res = await fetch(`${BASE}/pipeline/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phase: phase ?? null }),
  });
  const json: unknown = await res.json();
  return json as PipelineJob;
}

export async function stopPipeline(jobId: string): Promise<void> {
  await fetch(`${BASE}/pipeline/${jobId}`, { method: "DELETE" });
}

/**
 * Open an SSE stream for a running pipeline job.
 * Calls onLine for each stdout line, onDone when the job exits.
 */
export function streamPipeline(
  jobId: string,
  onLine: (line: string) => void,
  onDone: (returncode: number) => void,
): EventSource {
  const es = new EventSource(`${BASE}/pipeline/events/${jobId}`);
  es.onmessage = (ev) => onLine(ev.data as string);
  es.addEventListener("done", (ev) => {
    const msgEv = ev as MessageEvent<string>;
    const payload = JSON.parse(msgEv.data) as { returncode: number };
    onDone(payload.returncode);
    es.close();
  });
  return es;
}

// ─── Flight tracks ─────────────────────────────────────────────────────────────

/**
 * Fetch the per-point ADS-B track for a flight event. Returns an empty array
 * if the backend has no track for this flight_id (the table may be empty
 * until `scripts/parse_adsb_archive.py` has been run).
 */
export async function fetchFlightTrack(flightId: string): Promise<TrackPoint[]> {
  try {
    return (await get<TrackPoint[]>(`/events/${encodeURIComponent(flightId)}/track`)) ?? [];
  } catch {
    return [];
  }
}

/**
 * Kick off a RAG re-index job on the backend. Returns the new job_id
 * immediately; indexing runs asynchronously and the server doesn't expose
 * progress events — the UI surfaces a toast and lets the operator check
 * server logs for progress.
 */
export async function postRagIndex(): Promise<{ job_id: string; status: string }> {
  const res = await fetch(`${BASE}/rag/index`, { method: "POST" });
  if (!res.ok) throw new Error(`/rag/index → ${res.status}`);
  return res.json() as Promise<{ job_id: string; status: string }>;
}

// ─── RAG ───────────────────────────────────────────────────────────────────────

/**
 * Stream a RAG query to the backend.
 * Calls onToken for each output line, onDone when the response ends.
 */
export function streamRagQuery(
  query: string,
  onToken: (token: string) => void,
  onDone: () => void,
): () => void {
  let cancelled = false;

  void (async () => {
    try {
      const res = await fetch(`${BASE}/rag/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, top_k: 5 }),
      });
      if (!res.body) return;
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done || cancelled) break;
        buf += dec.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() ?? "";
        for (const line of lines) {
          if (line.startsWith("data:")) {
            onToken(line.slice(5).trim());
          }
          if (line.startsWith("event: done")) {
            onDone();
            return;
          }
        }
      }
    } catch {
      onDone();
    }
  })();

  return () => { cancelled = true; };
}

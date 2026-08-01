/**
 * PRIIS API client — typed wrappers for the FastAPI backend.
 * Falls back to mock data when the API is unreachable.
 * All API responses are validated against Zod schemas.
 */
import type { PriisData } from "../types/priis";
import { priisData } from "../data/mockData";
import { API_BASE as BASE } from "../config";
import {
  parseArray,
  AgencySchema, VendorSchema, SiteSchema, ContractSchema,
  EventRecordSchema, AnomalySchema, SourceRecordSchema,
  InvestigationSchema, AlertRecordSchema,
} from "../schemas/priis";

/**
 * How long any single backend call may hang before we give up and fall back.
 * Without this a backend that accepts the connection but never answers — a
 * half-open socket after a laptop sleeps, or a wedged worker in the packaged
 * desktop app — leaves the caller pending forever, so the offline fixture
 * fallback never fires and the UI sits on "Loading PRIIS data…".
 */
export const REQUEST_TIMEOUT_MS = 8000;

/** `fetch` with a timeout, so a hung backend rejects instead of hanging. */
export async function fetchWithTimeout(
  input: string,
  init: RequestInit = {},
  timeoutMs = REQUEST_TIMEOUT_MS,
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new Error(`${input} → timed out after ${timeoutMs}ms`);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

async function get<T>(path: string): Promise<T> {
  const res = await fetchWithTimeout(`${BASE}${path}`);
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

  const parsedContracts = parseArray(ContractSchema, contracts  as unknown[]);
  const parsedAnomalies  = parseArray(AnomalySchema,  anomalies  as unknown[]);

  return {
    agencies:       parseArray(AgencySchema,       agencies       as unknown[]),
    vendors:        parseArray(VendorSchema,        vendors        as unknown[]),
    sites:          parseArray(SiteSchema,          sites          as unknown[]),
    contracts:      parsedContracts,
    events:         parseArray(EventRecordSchema,   events         as unknown[]),
    anomalies:      parsedAnomalies,
    sources:        parseArray(SourceRecordSchema,  sources        as unknown[]),
    investigations: parseArray(InvestigationSchema, investigations as unknown[]),
    alerts:         parseArray(AlertRecordSchema,   alerts         as unknown[]),
    // The backend has no watchlist endpoint yet, so derive one from the data —
    // otherwise the left-rail watchlist vanishes in live mode. High-band
    // anomalies and flagged contracts are the review-priority items.
    watchlist: deriveWatchlist(parsedContracts, parsedAnomalies),
  };
}

/** Derive a review watchlist from the highest-priority live records. */
function deriveWatchlist(
  contracts: PriisData["contracts"],
  anomalies: PriisData["anomalies"],
): PriisData["watchlist"] {
  const fromAnomalies = anomalies
    .filter((a) => a.band === "hi")
    .map((a) => ({ kind: "anomaly" as const, id: a.id }));
  const fromContracts = contracts
    .filter((c) => c.status === "flagged")
    .map((c) => ({ kind: "contract" as const, id: c.id }));
  return [...fromAnomalies, ...fromContracts].slice(0, 8);
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
  /** Present once the job has exited (GET /pipeline/status/{job_id}). */
  returncode?: number;
}

export async function startPipeline(phase?: number): Promise<PipelineJob> {
  const res = await fetchWithTimeout(`${BASE}/pipeline/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phase: phase ?? null }),
  });
  // Without this check a 5xx body is cast straight to PipelineJob, yielding
  // `job_id: undefined` and an SSE subscription to `/pipeline/events/undefined`.
  if (!res.ok) throw new Error(`/pipeline/run → ${res.status}`);
  const job = (await res.json()) as Partial<PipelineJob>;
  if (!job.job_id) throw new Error("/pipeline/run returned no job_id");
  return job as PipelineJob;
}

export async function stopPipeline(jobId: string): Promise<void> {
  await fetchWithTimeout(`${BASE}/pipeline/${jobId}`, { method: "DELETE" });
}

/** Poll a job's terminal state. Used to resolve a run whose SSE stream dropped. */
export async function getPipelineStatus(jobId: string): Promise<PipelineJob> {
  const res = await fetchWithTimeout(`${BASE}/pipeline/status/${jobId}`);
  if (!res.ok) throw new Error(`/pipeline/status/${jobId} → ${res.status}`);
  return (await res.json()) as PipelineJob;
}

/** Handle for an open pipeline subscription. `close()` stops stream and polling. */
export interface PipelineStream {
  close: () => void;
}

/** How long to keep polling a job whose stream dropped but which is still alive. */
const STATUS_POLL_INTERVAL_MS = 2000;
const STATUS_POLL_MAX_FAILURES = 5;

/**
 * Subscribe to a running pipeline job.
 * Calls onLine for each stdout line, onDone when the job exits, and onError only
 * once the job can no longer be tracked at all.
 *
 * EventSource reconnects silently on transport failure, so without an `onerror`
 * handler a backend that dies mid-run leaves the caller waiting on a `done` event
 * that will never arrive — the UI stays "running" with no way back.
 *
 * A dropped stream is not the same as a dead job, though: the subprocess in
 * `pipeline_run` keeps going. So on a stream error we fall back to polling
 * `GET /pipeline/status/{job_id}` and keep reporting "running" until the job
 * actually reaches a terminal state. Giving up here would strand a live
 * subprocess the operator can no longer stop or monitor.
 */
export function streamPipeline(
  jobId: string,
  onLine: (line: string) => void,
  onDone: (returncode: number) => void,
  onError?: (message: string) => void,
  onDegraded?: (message: string) => void,
): PipelineStream {
  let closed = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let consecutiveFailures = 0;

  const es = new EventSource(`${BASE}/pipeline/events/${jobId}`);

  function close() {
    closed = true;
    if (timer !== undefined) clearTimeout(timer);
    es.close();
  }

  function finish(returncode: number) {
    if (closed) return;
    close();
    onDone(returncode);
  }

  function fail(message: string) {
    if (closed) return;
    close();
    onError?.(message);
  }

  function pollStatus() {
    if (closed) return;
    void getPipelineStatus(jobId)
      .then((job) => {
        if (closed) return;
        consecutiveFailures = 0;
        if (job.status === "running") {
          timer = setTimeout(pollStatus, STATUS_POLL_INTERVAL_MS);
          return;
        }
        finish(job.returncode ?? (job.status === "done" ? 0 : 1));
      })
      .catch(() => {
        if (closed) return;
        consecutiveFailures += 1;
        if (consecutiveFailures >= STATUS_POLL_MAX_FAILURES) {
          fail("Pipeline stream lost and the backend is unreachable");
          return;
        }
        timer = setTimeout(pollStatus, STATUS_POLL_INTERVAL_MS);
      });
  }

  es.onmessage = (ev) => { if (!closed) onLine(ev.data as string); };
  es.addEventListener("done", (ev) => {
    const msgEv = ev as MessageEvent<string>;
    const payload = JSON.parse(msgEv.data) as { returncode: number };
    finish(payload.returncode);
  });
  es.onerror = () => {
    if (closed) return;
    // Stop the browser's own silent reconnect loop and take over with polling,
    // keeping the job tracked rather than abandoning it.
    es.close();
    onDegraded?.("Pipeline log stream dropped — still tracking the job by status.");
    pollStatus();
  };

  return { close };
}

// ─── RAG ───────────────────────────────────────────────────────────────────────

/**
 * Stream a RAG query to the backend.
 * Calls onToken for each output line, onDone when the response ends, and onError
 * (if provided) when the request fails or returns no readable stream.
 */
export function streamRagQuery(
  query: string,
  onToken: (token: string) => void,
  onDone: () => void,
  onError?: (message: string) => void,
): () => void {
  let cancelled = false;

  void (async () => {
    try {
      const res = await fetchWithTimeout(`${BASE}/rag/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, top_k: 5 }),
      });
      if (!res.ok) {
        onError?.(`RAG backend returned ${res.status}`);
        onDone();
        return;
      }
      if (!res.body) {
        onError?.("RAG backend returned no response stream");
        onDone();
        return;
      }
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
      onDone();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "RAG request failed");
      onDone();
    }
  })();

  return () => { cancelled = true; };
}

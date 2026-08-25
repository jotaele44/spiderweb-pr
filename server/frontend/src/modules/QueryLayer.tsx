import { useEffect, useRef, useState } from "react";
import { streamRagQuery } from "../api/client";
import { runPriisQuery } from "../adapters/queryAdapter";
import type { PriisData, QueryResponse, Selection } from "../types/priis";
import { ConfidenceMeter, ContradictionFlag, TierBadge } from "../components/Badges";

export function QueryLayer({
  data,
  setSelection,
  pipelineLog = [],
  incomingQuery,
  runSignal = 0,
}: {
  data: PriisData;
  setSelection: (selection: Selection) => void;
  pipelineLog?: string[];
  /** Query text submitted from the global command bar. */
  incomingQuery?: string;
  /** Increments each time the command bar submits, triggering a run. */
  runSignal?: number;
}) {
  const [query, setQuery] = useState("vendors with concentration near restricted sites");
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [pending, setPending] = useState(false);
  const [streamLines, setStreamLines] = useState<string[]>([]);
  const [useRag, setUseRag] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const cancelRef = useRef<(() => void) | null>(null);
  const lastSignal = useRef(0);
  // Monotonic run id. The stub path returns a promise that cannot be aborted, so
  // a cancelled or superseded run is ignored by comparing against this instead —
  // otherwise a stale resolve overwrites the state the user just cleared.
  const runId = useRef(0);

  function runQuery(text: string) {
    const thisRun = ++runId.current;
    setStreamLines([]);
    setError(null);
    setResult(null);
    setPending(true);

    if (useRag) {
      // Stream from the real backend. Terminal return code is part of the
      // user-facing contract: an empty/nonzero response is an error, not a
      // successful answer with no text.
      const cancel = streamRagQuery(
        text,
        (token) => { if (runId.current === thisRun) setStreamLines((prev) => [...prev, token]); },
        (returncode) => {
          if (runId.current !== thisRun) return;
          cancelRef.current = null;
          setPending(false);
          if (returncode !== 0) setError(`RAG backend exited with code ${returncode}`);
        },
        (message) => {
          if (runId.current !== thisRun) return;
          cancelRef.current = null;
          setError(message);
          setPending(false);
        },
      );
      cancelRef.current = cancel;
    } else {
      // Use the typed adapter stub (local, fast)
      void runPriisQuery(text, data)
        .then((r) => {
          if (runId.current !== thisRun) return;
          setResult(r);
          setPending(false);
        })
        .catch((err: unknown) => {
          if (runId.current !== thisRun) return;
          setError(err instanceof Error ? err.message : "Query failed");
          setPending(false);
        });
    }
  }

  function submit() {
    if (pending) {
      // Bumping the run id retires any in-flight result, including the stub's.
      runId.current += 1;
      cancelRef.current?.();
      cancelRef.current = null;
      setPending(false);
      return;
    }
    runQuery(query);
  }

  // Tear down an in-flight RAG stream when the module unmounts (tab switch).
  useEffect(() => () => {
    runId.current += 1;
    cancelRef.current?.();
  }, []);

  // Run a query handed over from the global command bar.
  useEffect(() => {
    if (runSignal && runSignal !== lastSignal.current && incomingQuery !== undefined) {
      lastSignal.current = runSignal;
      setQuery(incomingQuery);
      runQuery(incomingQuery);
    }
    // runQuery closes over current state; we intentionally trigger only on a new signal.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runSignal, incomingQuery]);

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h1>Query Layer</h1>
          <span className="subtle">LLM orchestration surface · evidence-grounded responses</span>
        </div>
        <div className="row" style={{ gap: "0.5rem" }}>
          <button
            className="act"
            data-active={useRag}
            aria-pressed={useRag}
            onClick={() => setUseRag((v) => !v)}
            title="Toggle between local stub and live RAG backend"
          >
            {useRag ? "RAG LIVE" : "STUB"}
          </button>
          <button className="act primary" onClick={submit}>
            {pending ? "STOP" : "RUN QUERY"}
          </button>
        </div>
      </div>

      <div className="panel-grid">
        <div className="query-box">
          <label htmlFor="query-input" className="subtle mono">PROMPT</label>
          <textarea id="query-input" value={query} onChange={(event) => setQuery(event.target.value)} aria-label="Query prompt" />
        </div>

        {error && (
          <div className="card" style={{ borderColor: "var(--alert)" }} role="alert">
            <h2 style={{ color: "var(--alert)" }}>Query failed</h2>
            <p className="desc">{error}</p>
            {useRag && <p className="subtle">The RAG backend may be offline — switch to STUB for the local adapter.</p>}
          </div>
        )}

        {/* RAG streaming output */}
        {useRag && streamLines.length > 0 && (
          <div className="card">
            <h2>Response</h2>
            <pre className="mono" style={{ whiteSpace: "pre-wrap", fontSize: "0.85rem" }}>
              {streamLines.join("\n")}
              {pending && <span style={{ animation: "pulse 1s infinite" }}> ▋</span>}
            </pre>
          </div>
        )}

        {/* Structured stub result */}
        {!useRag && result && (
          <div className="card">
            <h2>Finding</h2>
            <p className="desc">{result.finding}</p>
            <div className="cards" style={{ gridTemplateColumns: "1fr 1fr" }}>
              <div className="card"><h2>Confidence</h2><ConfidenceMeter value={result.confidence} /></div>
              <div className="card"><h2>Source-tier breakdown</h2>
                <div className="row">
                  <TierBadge tier="T1" /> {result.sourceTierBreakdown.T1}
                  <TierBadge tier="T2" /> {result.sourceTierBreakdown.T2}
                  <TierBadge tier="T3" /> {result.sourceTierBreakdown.T3}
                  <TierBadge tier="T4" /> {result.sourceTierBreakdown.T4}
                </div>
              </div>
            </div>
            <div className="card"><h2>Evidence</h2>
              {result.evidence.map((ev) => (
                <button key={`${ev.label}-${ev.detail}`} className="navbtn" onClick={() => ev.entity && setSelection(ev.entity)}>
                  <span><TierBadge tier={ev.tier} /> {ev.label}</span>
                  <span>{ev.entity?.id}</span>
                </button>
              ))}
            </div>
            <ContradictionFlag items={result.contradictions} />
            <div className="card"><h2>Missing data</h2><ul>{result.missingData.map((item) => <li key={item}>{item}</li>)}</ul></div>
            <div className="card"><h2>Recommended action</h2><p>{result.recommendedAction}</p></div>
          </div>
        )}

        {/* Nothing run yet — say so rather than leaving the panel blank. */}
        {!pending && !error && !result && streamLines.length === 0 && (
          <div className="card">
            <h2>No query run yet</h2>
            <p className="desc">
              Edit the prompt and press RUN QUERY, or submit from the command bar.
              {useRag
                ? " RAG LIVE streams from the backend."
                : " STUB answers locally from the loaded dataset."}
            </p>
          </div>
        )}

        {/* Pipeline log passthrough */}
        {pipelineLog.length > 0 && (
          <div className="card">
            <h2>Pipeline log</h2>
            <pre className="mono" style={{ whiteSpace: "pre-wrap", fontSize: "0.75rem", maxHeight: "200px", overflowY: "auto" }}>
              {pipelineLog.join("\n")}
            </pre>
          </div>
        )}
      </div>
    </section>
  );
}

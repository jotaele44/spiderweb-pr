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

  function runQuery(text: string) {
    setStreamLines([]);
    setError(null);
    setResult(null);
    setPending(true);

    if (useRag) {
      // Stream from the real backend
      const cancel = streamRagQuery(
        text,
        (token) => setStreamLines((prev) => [...prev, token]),
        () => setPending(false),
        (message) => setError(message),
      );
      cancelRef.current = cancel;
    } else {
      // Use the typed adapter stub (local, fast)
      void runPriisQuery(text, data)
        .then((r) => {
          setResult(r);
          setPending(false);
        })
        .catch((err: unknown) => {
          setError(err instanceof Error ? err.message : "Query failed");
          setPending(false);
        });
    }
  }

  function submit() {
    if (pending) {
      cancelRef.current?.();
      setPending(false);
      return;
    }
    runQuery(query);
  }

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
            <h3 style={{ color: "var(--alert)" }}>Query failed</h3>
            <p className="desc">{error}</p>
            {useRag && <p className="subtle">The RAG backend may be offline — switch to STUB for the local adapter.</p>}
          </div>
        )}

        {/* RAG streaming output */}
        {useRag && streamLines.length > 0 && (
          <div className="card">
            <h3>Response</h3>
            <pre className="mono" style={{ whiteSpace: "pre-wrap", fontSize: "0.85rem" }}>
              {streamLines.join("\n")}
              {pending && <span style={{ animation: "pulse 1s infinite" }}> ▋</span>}
            </pre>
          </div>
        )}

        {/* Structured stub result */}
        {!useRag && result && (
          <div className="card">
            <h3>Finding</h3>
            <p className="desc">{result.finding}</p>
            <div className="cards" style={{ gridTemplateColumns: "1fr 1fr" }}>
              <div className="card"><h3>Confidence</h3><ConfidenceMeter value={result.confidence} /></div>
              <div className="card"><h3>Source-tier breakdown</h3>
                <div className="row">
                  <TierBadge tier="T1" /> {result.sourceTierBreakdown.T1}
                  <TierBadge tier="T2" /> {result.sourceTierBreakdown.T2}
                  <TierBadge tier="T3" /> {result.sourceTierBreakdown.T3}
                  <TierBadge tier="T4" /> {result.sourceTierBreakdown.T4}
                </div>
              </div>
            </div>
            <div className="card"><h3>Evidence</h3>
              {result.evidence.map((ev) => (
                <button key={`${ev.label}-${ev.detail}`} className="navbtn" onClick={() => ev.entity && setSelection(ev.entity)}>
                  <span><TierBadge tier={ev.tier} /> {ev.label}</span>
                  <span>{ev.entity?.id}</span>
                </button>
              ))}
            </div>
            <ContradictionFlag items={result.contradictions} />
            <div className="card"><h3>Missing data</h3><ul>{result.missingData.map((item) => <li key={item}>{item}</li>)}</ul></div>
            <div className="card"><h3>Recommended action</h3><p>{result.recommendedAction}</p></div>
          </div>
        )}

        {/* Pipeline log passthrough */}
        {pipelineLog.length > 0 && (
          <div className="card">
            <h3>Pipeline log</h3>
            <pre className="mono" style={{ whiteSpace: "pre-wrap", fontSize: "0.75rem", maxHeight: "200px", overflowY: "auto" }}>
              {pipelineLog.join("\n")}
            </pre>
          </div>
        )}
      </div>
    </section>
  );
}

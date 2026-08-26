import { Suspense, lazy, useEffect, useRef, useState } from "react";
import type { ModuleId, PriisData, Selection } from "./types/priis";
import { priisData as mockData } from "./data/mockData";
import type { PipelineStream } from "./api/client";
import { fetchPriisDataWithFallback, startPipeline, stopPipeline, streamPipeline } from "./api/client";
import { THEME_STORAGE_KEY, resolveInitialTheme, type Theme } from "./theme";
import { CommandBar } from "./components/CommandBar";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { LeftRail } from "./components/LeftRail";
import { Inspector } from "./components/Inspector";
import { Timeline } from "./components/Timeline";

// Route-split the modules so heavy dependencies (MapLibre for Spatial, TanStack
// Table for Finance) load only when their tab is first opened.
const CommandCenter = lazy(() => import("./modules/CommandCenter").then((m) => ({ default: m.CommandCenter })));
const FinanceIntelligence = lazy(() => import("./modules/FinanceIntelligence").then((m) => ({ default: m.FinanceIntelligence })));
const SpatialIntelligence = lazy(() => import("./modules/SpatialIntelligence").then((m) => ({ default: m.SpatialIntelligence })));
const AnomalyWorkbench = lazy(() => import("./modules/AnomalyWorkbench").then((m) => ({ default: m.AnomalyWorkbench })));
const InvestigationGraph = lazy(() => import("./modules/InvestigationGraph").then((m) => ({ default: m.InvestigationGraph })));
const QueryLayer = lazy(() => import("./modules/QueryLayer").then((m) => ({ default: m.QueryLayer })));

const tabs: { id: ModuleId; label: string }[] = [
  { id: "command", label: "Command" },
  { id: "finance", label: "Finance" },
  { id: "spatial", label: "Spatial" },
  { id: "anomaly", label: "Anomaly" },
  { id: "graph", label: "Graph" },
  { id: "query", label: "Query" },
];

type RunState = "idle" | "running" | "done" | "error";

const errorText = (err: unknown): string => (err instanceof Error ? err.message : String(err));

/** Newest event date in the dataset, as YYYY-MM-DD; today's date if there are none. */
function latestEventDate(data: PriisData): string {
  const times = data.events
    .map((event) => new Date(event.at).getTime())
    .filter((ms) => !Number.isNaN(ms));
  const ms = times.length ? Math.max(...times) : Date.now();
  return new Date(ms).toISOString().slice(0, 10);
}

export default function App() {
  const [data, setData] = useState<PriisData>(mockData);
  const [live, setLive] = useState(false);
  const [loading, setLoading] = useState(true);

  const [moduleId, setModule] = useState<ModuleId>("command");
  // Seeded defaults used to be fixture ids (anomaly A-014, INV-007, cursor
  // 2024-08-14). Against live data none of them resolve, so the app opened on
  // "Missing record", blanked the Anomaly detail pane, and parked the temporal
  // cursor outside the dataset. Start empty and derive from whatever loads.
  const [selection, setSelection] = useState<Selection | null>(null);
  const [activeInvestigation, setActiveInvestigation] = useState("");
  const [query, setQuery] = useState("vendors with concentration near restricted sites");
  const [cursor, setCursor] = useState("");

  // Pipeline state
  const [runState, setRunState] = useState<RunState>("idle");
  const [jobId, setJobId] = useState<string | null>(null);
  const [pipelineLog, setPipelineLog] = useState<string[]>([]);
  // Held so a stop (or unmount) can tear down the stream and its status polling.
  const streamRef = useRef<PipelineStream | null>(null);

  useEffect(() => () => streamRef.current?.close(), []);

  // Bumped each time the command bar submits, so the Query module runs the
  // global query instead of just switching tabs.
  const [querySubmitCount, setQuerySubmitCount] = useState(0);

  // Collapsible chrome — left rail and right inspector slide out of frame.
  const [leftCollapsed, setLeftCollapsed] = useState(
    () => localStorage.getItem("priis_left_collapsed") === "true",
  );
  const [rightCollapsed, setRightCollapsed] = useState(
    () => localStorage.getItem("priis_right_collapsed") === "true",
  );

  // Theme — initialized in main.tsx from storage/prefers-color-scheme; mirror it
  // here so the toggle and persistence live in React.
  const [theme, setTheme] = useState<Theme>(
    () => resolveInitialTheme(localStorage.getItem(THEME_STORAGE_KEY)),
  );

  // Load real data on mount; fall back to mock if API is down
  useEffect(() => {
    void fetchPriisDataWithFallback().then(({ data: d, live: l }) => {
      setData(d);
      setLive(l);
      setLoading(false);
      // Anchor the temporal cursor in the data that actually loaded, rather than
      // a literal that drifts from every dataset but the original fixture.
      setCursor((current) => current || latestEventDate(d));
      setActiveInvestigation((current) => current || (d.investigations[0]?.id ?? ""));
    });
  }, []);

  // Versioned localStorage — bump STORAGE_VERSION to wipe stale state on schema change
  const STORAGE_VERSION = "1";

  useEffect(() => {
    if (localStorage.getItem("priis_storage_version") !== STORAGE_VERSION) {
      localStorage.removeItem("priis_investigation");
      localStorage.removeItem("priis_cursor");
      localStorage.setItem("priis_storage_version", STORAGE_VERSION);
      return;
    }
    const stored = localStorage.getItem("priis_investigation");
    if (stored) setActiveInvestigation(stored);
    const storedCursor = localStorage.getItem("priis_cursor");
    if (storedCursor) setCursor(storedCursor);
  }, []);

  useEffect(() => {
    localStorage.setItem("priis_investigation", activeInvestigation);
  }, [activeInvestigation]);

  useEffect(() => {
    localStorage.setItem("priis_cursor", cursor);
  }, [cursor]);

  useEffect(() => {
    localStorage.setItem("priis_left_collapsed", String(leftCollapsed));
  }, [leftCollapsed]);

  useEffect(() => {
    localStorage.setItem("priis_right_collapsed", String(rightCollapsed));
  }, [rightCollapsed]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [theme]);

  // Keyboard chrome toggles: "[" left rail, "]" inspector. Ignore while typing.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)) {
        return;
      }
      if (event.key === "[") {
        event.preventDefault();
        setLeftCollapsed((value) => !value);
      } else if (event.key === "]") {
        event.preventDefault();
        setRightCollapsed((value) => !value);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  async function handlePipelineRun() {
    if (runState === "running" && jobId) {
      try {
        await stopPipeline(jobId);
      } catch (err) {
        // The job is probably still alive, so keep the handle and stay in
        // "running" — clearing it here would strand a live subprocess while the
        // UI offered to start a second one.
        setPipelineLog((prev) => [...prev, `stop failed, job still running: ${errorText(err)}`]);
        return;
      }
      streamRef.current?.close();
      streamRef.current = null;
      setRunState("idle");
      setJobId(null);
      return;
    }
    setPipelineLog([]);
    setRunState("running");
    let job;
    try {
      job = await startPipeline();
    } catch (err) {
      // Without this the rejection was unhandled and runState stayed "running",
      // leaving the button stuck on STOP with no job to stop.
      setPipelineLog([`pipeline failed to start: ${errorText(err)}`]);
      setRunState("error");
      return;
    }
    setJobId(job.job_id);
    streamRef.current = streamPipeline(
      job.job_id,
      (line) => setPipelineLog((prev) => [...prev, line]),
      (rc) => {
        streamRef.current = null;
        setRunState(rc === 0 ? "done" : "error");
        setJobId(null);
      },
      (message) => {
        streamRef.current = null;
        setPipelineLog((prev) => [...prev, message]);
        setRunState("error");
        setJobId(null);
      },
      // Degraded, not failed: the log stream dropped but the job is still
      // tracked by status polling, so stay in "running" and keep the handle.
      (message) => setPipelineLog((prev) => [...prev, message]),
    );
  }

  function renderModule() {
    if (loading) {
      return <div className="panel" style={{ display: "flex", alignItems: "center", justifyContent: "center", color: "var(--muted)" }}>Loading PRIIS data…</div>;
    }
    switch (moduleId) {
      case "command":  return <CommandCenter data={data} setSelection={setSelection} setModule={setModule} />;
      case "finance":  return <FinanceIntelligence data={data} selection={selection} setSelection={setSelection} />;
      case "spatial":  return <SpatialIntelligence data={data} selection={selection} setSelection={setSelection} leftCollapsed={leftCollapsed} rightCollapsed={rightCollapsed} />;
      case "anomaly":  return <AnomalyWorkbench data={data} selection={selection} setSelection={setSelection} />;
      case "graph":    return <InvestigationGraph data={data} setSelection={setSelection} />;
      case "query":    return <QueryLayer data={data} setSelection={setSelection} pipelineLog={pipelineLog} incomingQuery={query} runSignal={querySubmitCount} />;
      default: return null;
    }
  }

  return (
    <>
      <div className="classif">UNCLASSIFIED · DEMO · NOT FOR DISTRIBUTION · PR INTEGRATED INTELLIGENCE SYSTEM V1</div>
      <div className="workbench" data-left-collapsed={leftCollapsed} data-right-collapsed={rightCollapsed}>
        <CommandBar
          query={query}
          setQuery={setQuery}
          onSubmit={() => { setModule("query"); setQuerySubmitCount((count) => count + 1); }}
          runState={runState}
          onRunPipeline={() => { void handlePipelineRun(); }}
          live={live}
          theme={theme}
          onToggleTheme={() => setTheme((value) => (value === "dark" ? "light" : "dark"))}
        />
        <LeftRail
          data={data}
          moduleId={moduleId}
          setModule={setModule}
          activeInvestigation={activeInvestigation}
          setActiveInvestigation={setActiveInvestigation}
          setSelection={setSelection}
        />
        <main className="center">
          <div className="tabstrip">
            <button
              className="tab chrome-toggle"
              data-active={leftCollapsed}
              onClick={() => setLeftCollapsed((value) => !value)}
              title="Toggle left rail ([)"
              aria-label="Toggle left rail"
              aria-pressed={leftCollapsed}
            >
              {leftCollapsed ? "»" : "«"}
            </button>
            <div className="tabs" role="tablist" aria-label="Workbench modules">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  className="tab"
                  role="tab"
                  id={`tab-${tab.id}`}
                  aria-selected={moduleId === tab.id}
                  aria-controls="module-panel"
                  data-active={moduleId === tab.id}
                  onClick={() => setModule(tab.id)}
                >
                  {tab.label}
                </button>
              ))}
            </div>
            <div className="tab-meta">
              CURSOR <b>{cursor || "—"}</b> · SEL <b>{selection ? `${selection.kind}/${selection.id}` : "—"}</b>
            </div>
            <button
              className="tab chrome-toggle"
              data-active={rightCollapsed}
              onClick={() => setRightCollapsed((value) => !value)}
              title="Toggle inspector (])"
              aria-label="Toggle inspector"
              aria-pressed={rightCollapsed}
            >
              {rightCollapsed ? "«" : "»"}
            </button>
          </div>
          <div className="workspace" id="module-panel" role="tabpanel" aria-labelledby={`tab-${moduleId}`}>
            {/* Keyed on the module so switching tabs clears a caught error and
                one broken module never takes the rest of the workbench down. */}
            <ErrorBoundary key={moduleId}>
              <Suspense fallback={<div className="empty-state">Loading module…</div>}>
                {renderModule()}
              </Suspense>
            </ErrorBoundary>
          </div>
        </main>
        <Inspector data={data} selection={selection} setSelection={setSelection} />
        <Timeline events={data.events} cursor={cursor} setCursor={setCursor} setSelection={setSelection} />
      </div>
    </>
  );
}

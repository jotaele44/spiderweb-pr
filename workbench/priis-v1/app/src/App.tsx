import { useEffect, useState } from "react";
import type { ModuleId, PriisData, Selection, SpatialFilter, TrackPoint } from "./types/priis";
import { priisData as mockData } from "./data/mockData";
import { fetchFlightTrack, fetchPriisDataWithFallback, startPipeline, stopPipeline, streamPipeline } from "./api/client";
import { CommandBar } from "./components/CommandBar";
import { LeftRail } from "./components/LeftRail";
import { Inspector } from "./components/Inspector";
import { Timeline } from "./components/Timeline";
import { ToastStack, type ToastMessage, type ToastKind } from "./components/Toast";
import { CommandCenter } from "./modules/CommandCenter";
import { FinanceIntelligence } from "./modules/FinanceIntelligence";
import { SpatialIntelligence } from "./modules/SpatialIntelligence";
import { AnomalyWorkbench } from "./modules/AnomalyWorkbench";
import { InvestigationGraph } from "./modules/InvestigationGraph";
import { QueryLayer } from "./modules/QueryLayer";
import { clearStaleStorage, usePersistedState } from "./hooks/usePersistedState";

// Bump when ANY persisted-state shape changes incompatibly.
const STORAGE_VERSION = "1";
const PERSISTED_KEYS = ["priis_investigation", "priis_cursor", "priis_watchlist"];
// Run once at module load (before any hook renders) so the lazy useState
// initialisers inside usePersistedState see a clean slate on a version bump.
clearStaleStorage(STORAGE_VERSION, PERSISTED_KEYS);

const tabs: { id: ModuleId; label: string }[] = [
  { id: "command", label: "Command" },
  { id: "finance", label: "Finance" },
  { id: "spatial", label: "Spatial" },
  { id: "anomaly", label: "Anomaly" },
  { id: "graph", label: "Graph" },
  { id: "query", label: "Query" },
];

type RunState = "idle" | "running" | "done" | "error";

export default function App() {
  const [data, setData] = useState<PriisData>(mockData);
  const [live, setLive] = useState(false);
  const [loading, setLoading] = useState(true);

  const [moduleId, setModule] = useState<ModuleId>("command");
  const [selection, setSelection] = useState<Selection | null>({ kind: "anomaly", id: "A-014" });
  // Cross-module geographic filter set from a Spatial polygon click.
  const [spatialFilter, setSpatialFilter] = useState<SpatialFilter | null>(null);
  // ADS-B track for the currently selected flight event. null = not loading,
  // [] = loaded but empty (no track in DB yet).
  const [flightTrack, setFlightTrack] = useState<TrackPoint[] | null>(null);
  // Persisted state — load + save are unified by the hook. The bug-prone
  // load-effect / save-effect split is structurally impossible here.
  // The watchlist is client-side only; the backend doesn't currently have a
  // /watchlist endpoint (would require a user model first).
  const [watchlist, setWatchlist] = usePersistedState<Selection[]>("priis_watchlist", []);
  const [activeInvestigation, setActiveInvestigation] = usePersistedState("priis_investigation", "INV-007");
  const [query, setQuery] = useState("vendors with concentration near restricted sites");
  const [cursor, setCursor] = usePersistedState("priis_cursor", "2024-08-14");
  const [filters, setFilters] = useState([
    { key: "inv", label: "INV-007", color: "var(--t1)" },
    { key: "time", label: "12m window", color: "var(--t2)" },
    { key: "tier", label: "T1+T2 priority" },
  ]);

  // Pipeline state
  const [runState, setRunState] = useState<RunState>("idle");
  const [jobId, setJobId] = useState<string | null>(null);
  const [pipelineLog, setPipelineLog] = useState<string[]>([]);

  // Toast stack — small, useState-managed; no need for context yet.
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  function pushToast(text: string, kind: ToastKind = "info", ttl?: number) {
    const id = `t-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
    setToasts((prev) => [...prev, { id, text, kind, ttl }]);
  }
  function dismissToast(id: string) {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }

  // Load real data on mount; fall back to mock if API is down
  useEffect(() => {
    void fetchPriisDataWithFallback().then(({ data: d, live: l }) => {
      setData(d);
      setLive(l);
      setLoading(false);
      if (!l) {
        pushToast(
          "API unreachable — workbench running on mock fixture data",
          "warn",
          0, // sticky until dismissed
        );
      }
    });
  }, []);

  function pinToWatchlist(item: Selection) {
    setWatchlist((cur) =>
      cur.some((w) => w.kind === item.kind && w.id === item.id)
        ? cur
        : [...cur, item],
    );
  }
  function unpinFromWatchlist(item: Selection) {
    setWatchlist((cur) => cur.filter((w) => !(w.kind === item.kind && w.id === item.id)));
  }

  // Fetch the ADS-B track whenever the selection lands on a flight event.
  // Other selections clear the track (so the temp Spatial layer goes away).
  useEffect(() => {
    if (selection?.kind !== "event") {
      setFlightTrack(null);
      return;
    }
    const event = data.events.find((e) => e.id === selection.id);
    if (!event || event.kind !== "flight") {
      setFlightTrack(null);
      return;
    }
    let cancelled = false;
    void fetchFlightTrack(event.id).then((track) => {
      if (!cancelled) setFlightTrack(track);
    });
    return () => { cancelled = true; };
  }, [selection, data.events]);

  async function handlePipelineRun() {
    if (runState === "running" && jobId) {
      await stopPipeline(jobId);
      setRunState("idle");
      setJobId(null);
      return;
    }
    setPipelineLog([]);
    setRunState("running");
    try {
      const job = await startPipeline();
      setJobId(job.job_id);
      streamPipeline(
        job.job_id,
        (line) => setPipelineLog((prev) => [...prev, line]),
        (rc) => {
          setRunState(rc === 0 ? "done" : "error");
          setJobId(null);
          if (rc !== 0) {
            pushToast(
              `Pipeline exited with code ${rc} — see Query module log for details`,
              "error",
            );
          }
        },
      );
    } catch (err) {
      setRunState("error");
      pushToast(
        `Failed to start pipeline: ${err instanceof Error ? err.message : String(err)}`,
        "error",
      );
    }
  }

  // App-owned watchlist overrides whatever the API returned for `data.watchlist`
  // (the seed-time field is informational). This lets every module read a
  // single, persistent watchlist driven by user actions.
  const liveData: PriisData = { ...data, watchlist };

  function renderModule() {
    if (loading) {
      // Skeleton mirrors the panel-head + cards layout most modules use, so
      // the workbench geometry doesn't visibly reflow once data hydrates.
      return (
        <div className="panel skeleton-panel" aria-busy="true" aria-label="Loading PRIIS data">
          <div className="skeleton-row" data-w="40" />
          <div className="skeleton-row" data-w="80" />
          <div className="skeleton-row" data-w="60" />
          <div className="skeleton-row" data-w="100" />
          <div className="skeleton-row" data-w="80" />
          <div className="skeleton-row" data-w="60" />
        </div>
      );
    }
    switch (moduleId) {
      case "command":  return <CommandCenter data={liveData} setSelection={setSelection} setModule={setModule} />;
      case "finance":  return <FinanceIntelligence data={liveData} selection={selection} setSelection={setSelection} spatialFilter={spatialFilter} clearSpatialFilter={() => setSpatialFilter(null)} />;
      case "spatial":  return <SpatialIntelligence data={liveData} selection={selection} setSelection={setSelection} spatialFilter={spatialFilter} setSpatialFilter={setSpatialFilter} flightTrack={flightTrack} />;
      case "anomaly":  return <AnomalyWorkbench data={liveData} selection={selection} setSelection={setSelection} />;
      case "graph":    return <InvestigationGraph data={liveData} selection={selection} setSelection={setSelection} />;
      case "query":    return <QueryLayer data={liveData} setSelection={setSelection} pipelineLog={pipelineLog} pushToast={pushToast} />;
      default: return null;
    }
  }

  return (
    <>
      <div className="classif" data-mode={live ? "live" : "mock"}>
        UNCLASSIFIED · {live ? "LIVE" : "MOCK DATA · API OFFLINE"} · NOT FOR DISTRIBUTION · PR INTEGRATED INTELLIGENCE SYSTEM V1
      </div>
      <div className="workbench">
        <CommandBar
          query={query}
          setQuery={setQuery}
          filters={filters}
          removeFilter={(key) => setFilters((current) => current.filter((item) => item.key !== key))}
          onSubmit={() => setModule("query")}
          runState={runState}
          onRunPipeline={() => { void handlePipelineRun(); }}
          live={live}
        />
        <LeftRail
          data={liveData}
          moduleId={moduleId}
          setModule={setModule}
          activeInvestigation={activeInvestigation}
          setActiveInvestigation={setActiveInvestigation}
          setSelection={setSelection}
        />
        <main className="center">
          <div className="tabstrip">
            {tabs.map((tab) => (
              <button key={tab.id} className="tab" data-active={moduleId === tab.id} onClick={() => setModule(tab.id)}>
                {tab.label}
              </button>
            ))}
            <div className="tab-meta">
              CURSOR <b>{cursor}</b> · SEL <b>{selection ? `${selection.kind}/${selection.id}` : "—"}</b>
            </div>
          </div>
          <div className="workspace">{renderModule()}</div>
        </main>
        <Inspector data={liveData} selection={selection} setSelection={setSelection} spatialFilter={spatialFilter} clearSpatialFilter={() => setSpatialFilter(null)} flightTrack={flightTrack} watchlist={watchlist} pinToWatchlist={pinToWatchlist} unpinFromWatchlist={unpinFromWatchlist} />
        <Timeline events={data.events} cursor={cursor} setCursor={setCursor} setSelection={setSelection} />
      </div>
      <ToastStack messages={toasts} dismiss={dismissToast} />
    </>
  );
}

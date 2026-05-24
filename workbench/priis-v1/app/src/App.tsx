import { useEffect, useState } from "react";
import type { ModuleId, PriisData, Selection } from "./types/priis";
import { priisData as mockData } from "./data/mockData";
import { fetchPriisDataWithFallback, startPipeline, stopPipeline, streamPipeline } from "./api/client";
import { CommandBar } from "./components/CommandBar";
import { LeftRail } from "./components/LeftRail";
import { Inspector } from "./components/Inspector";
import { Timeline } from "./components/Timeline";
import { CommandCenter } from "./modules/CommandCenter";
import { FinanceIntelligence } from "./modules/FinanceIntelligence";
import { SpatialIntelligence } from "./modules/SpatialIntelligence";
import { AnomalyWorkbench } from "./modules/AnomalyWorkbench";
import { InvestigationGraph } from "./modules/InvestigationGraph";
import { QueryLayer } from "./modules/QueryLayer";

const tabs: Array<{ id: ModuleId; label: string }> = [
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
  const [activeInvestigation, setActiveInvestigation] = useState("INV-007");
  const [query, setQuery] = useState("vendors with concentration near restricted sites");
  const [cursor, setCursor] = useState("2024-08-14");
  const [filters, setFilters] = useState([
    { key: "inv", label: "INV-007", color: "var(--t1)" },
    { key: "time", label: "12m window", color: "var(--t2)" },
    { key: "tier", label: "T1+T2 priority" },
  ]);

  // Pipeline state
  const [runState, setRunState] = useState<RunState>("idle");
  const [jobId, setJobId] = useState<string | null>(null);
  const [pipelineLog, setPipelineLog] = useState<string[]>([]);

  // Load real data on mount; fall back to mock if API is down
  useEffect(() => {
    fetchPriisDataWithFallback().then(({ data: d, live: l }) => {
      setData(d);
      setLive(l);
      setLoading(false);
    });
  }, []);

  // Persist active investigation and cursor across sessions
  useEffect(() => {
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

  async function handlePipelineRun() {
    if (runState === "running" && jobId) {
      await stopPipeline(jobId);
      setRunState("idle");
      setJobId(null);
      return;
    }
    setPipelineLog([]);
    setRunState("running");
    const job = await startPipeline();
    setJobId(job.job_id);
    streamPipeline(
      job.job_id,
      (line) => setPipelineLog((prev) => [...prev, line]),
      (rc) => {
        setRunState(rc === 0 ? "done" : "error");
        setJobId(null);
      },
    );
  }

  function renderModule() {
    if (loading) {
      return <div className="panel" style={{ display: "flex", alignItems: "center", justifyContent: "center", color: "var(--muted)" }}>Loading PRIIS data…</div>;
    }
    switch (moduleId) {
      case "command":  return <CommandCenter data={data} setSelection={setSelection} setModule={setModule} />;
      case "finance":  return <FinanceIntelligence data={data} selection={selection} setSelection={setSelection} />;
      case "spatial":  return <SpatialIntelligence data={data} selection={selection} setSelection={setSelection} />;
      case "anomaly":  return <AnomalyWorkbench data={data} selection={selection} setSelection={setSelection} />;
      case "graph":    return <InvestigationGraph data={data} setSelection={setSelection} />;
      case "query":    return <QueryLayer data={data} setSelection={setSelection} pipelineLog={pipelineLog} />;
      default: return null;
    }
  }

  return (
    <>
      <div className="classif">UNCLASSIFIED · DEMO · NOT FOR DISTRIBUTION · PR INTEGRATED INTELLIGENCE SYSTEM V1</div>
      <div className="workbench">
        <CommandBar
          query={query}
          setQuery={setQuery}
          filters={filters}
          removeFilter={(key) => setFilters((current) => current.filter((item) => item.key !== key))}
          onSubmit={() => setModule("query")}
          runState={runState}
          onRunPipeline={handlePipelineRun}
          live={live}
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
        <Inspector data={data} selection={selection} setSelection={setSelection} />
        <Timeline events={data.events} cursor={cursor} setCursor={setCursor} setSelection={setSelection} />
      </div>
    </>
  );
}

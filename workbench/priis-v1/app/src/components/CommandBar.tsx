interface FilterChip { key: string; label: string; color?: string }

type RunState = "idle" | "running" | "done" | "error";

const RUN_LABEL: Record<RunState, string> = {
  idle: "RUN PIPELINE",
  running: "STOP",
  done: "RUN AGAIN",
  error: "RETRY",
};

const RUN_COLOR: Record<RunState, string> = {
  idle: "var(--ok)",
  running: "var(--warn)",
  done: "var(--t1)",
  error: "var(--alert)",
};

export function CommandBar({
  query,
  setQuery,
  filters,
  removeFilter,
  onSubmit,
  runState = "idle",
  onRunPipeline,
  live = false,
}: {
  query: string;
  setQuery: (value: string) => void;
  filters: FilterChip[];
  removeFilter: (key: string) => void;
  onSubmit: (query: string) => void;
  runState?: RunState;
  onRunPipeline?: () => void;
  live?: boolean;
}) {
  return (
    <header className="cmdbar">
      <div className="brand">
        <div className="seal">PR</div>
        <div>
          <div className="brand-name">PRIIS V1</div>
          <div className="brand-sub">INTEGRATED INTEL</div>
        </div>
      </div>
      <form className="query" onSubmit={(event) => { event.preventDefault(); onSubmit(query); }}>
        <span className="subtle mono">QUERY</span>
        <input value={query} onChange={(event) => setQuery(event.target.value)} aria-label="Global PRIIS query" />
        <span className="kbd">ENTER</span>
      </form>
      <div className="chips">
        {filters.map((filter) => (
          <span key={filter.key} className="chip" style={{ borderColor: filter.color ?? undefined }}>
            {filter.label}
            <button aria-label={`Remove ${filter.label}`} onClick={() => removeFilter(filter.key)} style={{ border: 0, background: "transparent", color: "inherit" }}>×</button>
          </span>
        ))}
      </div>
      <div className="runstate">
        {onRunPipeline && (
          <button
            className="act"
            style={{ color: RUN_COLOR[runState], borderColor: RUN_COLOR[runState], marginRight: "0.5rem" }}
            onClick={onRunPipeline}
          >
            {RUN_LABEL[runState]}
          </button>
        )}
        <span>
          {live ? "LIVE" : "DEMO"} · {runState === "running" ? "PIPELINE ACTIVE" : "STANDBY"}
        </span>
        <span style={{ marginLeft: "0.75rem" }}>
          sources · sync <b style={{ color: live ? "var(--ok)" : "var(--warn)" }}>●</b>
        </span>
      </div>
    </header>
  );
}

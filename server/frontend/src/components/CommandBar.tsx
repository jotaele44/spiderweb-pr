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
  onSubmit,
  runState = "idle",
  onRunPipeline,
  live = false,
  theme = "dark",
  onToggleTheme,
  datasetStatus,
  savingDataset,
  onSaveDataset,
  dataLabel,
}: {
  query: string;
  setQuery: (value: string) => void;
  onSubmit: (query: string) => void;
  runState?: RunState;
  onRunPipeline?: () => void;
  live?: boolean;
  theme?: "light" | "dark";
  onToggleTheme?: () => void;
  datasetStatus?: string;
  savingDataset?: boolean;
  onSaveDataset?: () => void;
  dataLabel?: string;
}) {
  return (
    <header className="cmdbar">
      <div className="brand">
        <div className="seal">PR</div>
        <div>
          <div className="brand-name">Spiderweb</div>
          <div className="brand-sub">SPATIAL / OPERATIONAL</div>
        </div>
      </div>
      <form className="query" onSubmit={(event) => { event.preventDefault(); onSubmit(query); }}>
        <span className="subtle mono">QUERY</span>
        <input value={query} onChange={(event) => setQuery(event.target.value)} aria-label="Global Spiderweb query" />
        <span className="kbd">ENTER</span>
      </form>
      <div className="runstate">
        <div className="runstate-actions" style={{ flexWrap: "wrap" }}>
          {onSaveDataset && <button className="act" disabled={savingDataset} onClick={onSaveDataset} title={datasetStatus ?? 'Save this dataset on this device; demo data stays labeled demo'}>SAVE LOCAL COPY</button>}
          {onToggleTheme && (
            <button
              className="act theme-toggle"
              onClick={onToggleTheme}
              aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
              title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
            >
              {theme === "dark" ? "◐ LIGHT" : "◑ DARK"}
            </button>
          )}
          {onRunPipeline && (
            <button
              className="act"
              style={{ color: RUN_COLOR[runState], borderColor: RUN_COLOR[runState] }}
              onClick={onRunPipeline}
            >
              {RUN_LABEL[runState]}
            </button>
          )}
        </div>
        <span>
          {dataLabel ?? (live ? "LIVE" : "DEMO")} · {runState === "running" ? "PIPELINE ACTIVE" : "STANDBY"}
        </span>
        <div data-offline-status-host style={{ order: -1, flex: 1, minWidth: 0 }} />
        {datasetStatus && <div role="status" style={{ fontSize: 10, overflowWrap: 'anywhere' }}>{datasetStatus}</div>}
      </div>
    </header>
  );
}

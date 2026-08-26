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
}: {
  query: string;
  setQuery: (value: string) => void;
  onSubmit: (query: string) => void;
  runState?: RunState;
  onRunPipeline?: () => void;
  live?: boolean;
  theme?: "light" | "dark";
  onToggleTheme?: () => void;
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
        <div className="runstate-actions">
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
          {live ? "LIVE" : "DEMO"} · {runState === "running" ? "PIPELINE ACTIVE" : "STANDBY"}
        </span>
      </div>
    </header>
  );
}

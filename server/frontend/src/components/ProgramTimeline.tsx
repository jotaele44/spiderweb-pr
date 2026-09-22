import { useMemo, useState } from "react";

export type ProgramTimelineItem = {
  id: string;
  phase: "NOW" | "NEXT" | "QUEUED" | "BLOCKED";
  title: string;
  detail: string;
  category: string;
};

const rank: Record<ProgramTimelineItem["phase"], number> = { NOW: 0, NEXT: 1, QUEUED: 2, BLOCKED: 3 };

export function ProgramTimeline({ items }: { items: readonly ProgramTimelineItem[] }) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"ALL" | ProgramTimelineItem["phase"]>("ALL");
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return [...items]
      .filter((item) => (filter === "ALL" || item.phase === filter) && (!q || [item.title, item.detail, item.category, item.phase].some((value) => value.toLowerCase().includes(q))))
      .sort((a, b) => rank[a.phase] - rank[b.phase] || a.title.localeCompare(b.title));
  }, [items, query, filter]);
  const upcoming = items.filter((item) => item.phase !== "NOW").slice(0, 5);

  const badge = (phase: ProgramTimelineItem["phase"]) => (
    <span className="mono" style={{ minWidth: 58, textAlign: "center", border: "1px solid var(--border)", borderRadius: 999, padding: "4px 7px", fontSize: 9, fontWeight: 700 }}>
      {phase}
    </span>
  );

  const itemRow = (item: ProgramTimelineItem) => (
    <div key={item.id} style={{ display: "grid", gridTemplateColumns: "64px minmax(0,1fr)", gap: 10, padding: "11px 0", borderBottom: "1px solid var(--border)" }}>
      {badge(item.phase)}
      <div><b style={{ fontSize: 12 }}>{item.title}</b><div className="subtle" style={{ marginTop: 4, fontSize: 11, lineHeight: 1.45 }}>{item.detail}</div><div className="mono subtle" style={{ marginTop: 5, fontSize: 9 }}>{item.category.toUpperCase()}</div></div>
    </div>
  );

  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1.6fr) minmax(260px,.8fr)", gap: 14, marginBottom: 14 }}>
      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
          <div><div className="mono subtle" style={{ fontSize: 9 }}>PROGRAM ACTIVITY</div><h2 style={{ marginTop: 4 }}>Timeline</h2></div>
          <span className="mono subtle">SPATIAL WORKFLOW</span>
        </div>
        <div style={{ display: "flex", gap: 6, overflowX: "auto", marginTop: 10 }}>
          {(["ALL","NOW","NEXT","QUEUED","BLOCKED"] as const).map((value) => <button key={value} className={`act ${filter === value ? "primary" : ""}`} onClick={() => setFilter(value)}>{value}</button>)}
        </div>
        <input aria-label="Search program activity" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search activity, function, or state" style={{ width: "100%", marginTop: 9, minHeight: 34, border: "1px solid var(--border)", borderRadius: 6, background: "var(--bg)", color: "var(--text)", padding: "0 10px" }} />
        <div>{visible.length ? visible.map(itemRow) : <div className="subtle" style={{ padding: 12 }}>No timeline items match this filter.</div>}</div>
      </div>
      <div className="card">
        <div><div className="mono subtle" style={{ fontSize: 9 }}>NEXT QUEUE</div><h2 style={{ marginTop: 4 }}>Upcoming work</h2></div>
        <div style={{ marginTop: 6 }}>{upcoming.map(itemRow)}</div>
      </div>
    </div>
  );
}

import type { EventRecord, Selection } from "../types/priis";
import { TierBadge } from "./Badges";

const start = new Date("2024-03-01").getTime();
const end = new Date("2025-04-01").getTime();

function pct(date: string): number {
  const t = new Date(date).getTime();
  return Math.max(0, Math.min(100, ((t - start) / (end - start)) * 100));
}

export function Timeline({
  events,
  cursor,
  setCursor,
  setSelection
}: {
  events: EventRecord[];
  cursor: string;
  setCursor: (value: string) => void;
  setSelection: (selection: Selection) => void;
}) {
  const cursorPct = pct(cursor);
  return (
    <footer className="timeline" onClick={(event) => {
      const rect = event.currentTarget.getBoundingClientRect();
      const clickPct = (event.clientX - rect.left) / rect.width;
      const date = new Date(start + (end - start) * clickPct);
      setCursor(date.toISOString().slice(0, 10));
    }}>
      <div className="timeline-head"><span>TIMELINE · finance / imagery / flight / reports</span><span>cursor <b>{cursor}</b></span></div>
      <div className="timeline-lanes">
        <div className="cursor-line" style={{ left: `${cursorPct}%` }} />
        {events.map((item) => (
          <div key={item.id} className="timeline-event" style={{ left: `${pct(item.at)}%` }}>
            <button onClick={(event) => { event.stopPropagation(); setSelection({ kind: "event", id: item.id }); }}>
              {item.tier ? <TierBadge tier={item.tier} /> : null} {item.id}
            </button>
          </div>
        ))}
      </div>
    </footer>
  );
}

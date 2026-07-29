import type { EventRecord, Selection } from "../types/priis";
import { TierBadge } from "./Badges";

const DAY = 86_400_000;

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function toISODate(ms: number): string {
  return new Date(ms).toISOString().slice(0, 10);
}

export function Timeline({
  events,
  cursor,
  setCursor,
  setSelection,
}: {
  events: EventRecord[];
  cursor: string;
  setCursor: (value: string) => void;
  setSelection: (selection: Selection) => void;
}) {
  // Derive the visible window from the event data (padded), instead of a
  // hardcoded date range that drifts from the dataset. Fall back to a window
  // around the cursor when there are no events.
  const times = events
    .map((e) => new Date(e.at).getTime())
    .filter((n) => !Number.isNaN(n));
  const cursorMs = new Date(cursor).getTime();
  const rawMin = times.length ? Math.min(...times) : cursorMs - 180 * DAY;
  const rawMax = times.length ? Math.max(...times) : cursorMs + 180 * DAY;
  const span = Math.max(rawMax - rawMin, DAY);
  const start = rawMin - span * 0.05;
  const end = rawMax + span * 0.05;

  const pct = (ms: number): number => clamp(((ms - start) / (end - start)) * 100, 0, 100);
  const cursorPct = pct(cursorMs);

  function setCursorFromClientX(clientX: number, rect: DOMRect) {
    const p = clamp((clientX - rect.left) / rect.width, 0, 1);
    setCursor(toISODate(start + (end - start) * p));
  }

  function moveCursor(days: number) {
    setCursor(toISODate(clamp(cursorMs + days * DAY, start, end)));
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    const step = event.shiftKey ? 7 : 1;
    if (event.key === "ArrowLeft") { event.preventDefault(); moveCursor(-step); }
    else if (event.key === "ArrowRight") { event.preventDefault(); moveCursor(step); }
    else if (event.key === "Home") { event.preventDefault(); setCursor(toISODate(start)); }
    else if (event.key === "End") { event.preventDefault(); setCursor(toISODate(end)); }
  }

  return (
    <footer className="timeline">
      <div className="timeline-head">
        <span>TIMELINE · finance / imagery / reports</span>
        <span>cursor <b>{cursor}</b></span>
      </div>
      <div
        className="timeline-track"
        role="slider"
        tabIndex={0}
        aria-label="Temporal cursor — arrow keys to move, shift for a week"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(cursorPct)}
        aria-valuetext={cursor}
        onKeyDown={onKeyDown}
        onClick={(event) => setCursorFromClientX(event.clientX, event.currentTarget.getBoundingClientRect())}
      >
        <div className="cursor-line" style={{ left: `${cursorPct}%` }} />
        {events.map((item) => (
          <div key={item.id} className="timeline-event" style={{ left: `${pct(new Date(item.at).getTime())}%` }}>
            <button
              onClick={(event) => { event.stopPropagation(); setSelection({ kind: "event", id: item.id }); }}
              title={`${item.id} · ${item.label} · ${item.at}`}
              aria-label={`Event ${item.id}: ${item.label} on ${item.at}`}
            >
              {item.tier ? <TierBadge tier={item.tier} /> : null} {item.id}
            </button>
          </div>
        ))}
      </div>
    </footer>
  );
}

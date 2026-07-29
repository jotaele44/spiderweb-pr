import type { EventRecord, Selection, TemporalWindow } from '../types/gis';

const DAY = 86_400_000;

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

export function Timeline({
  events,
  window,
  cursor,
  onCursor,
  onSelect,
}: {
  events: EventRecord[];
  window: TemporalWindow;
  cursor: string;
  onCursor: (value: string) => void;
  onSelect: (selection: Selection) => void;
}) {
  const start = Date.parse(window.start);
  const end = Math.max(Date.parse(window.end), start + DAY);
  const cursorMs = clamp(Date.parse(cursor), start, end);
  const percentage = (value: number) => clamp(((value - start) / (end - start)) * 100, 0, 100);

  function updateCursor(clientX: number, rect: DOMRect): void {
    const ratio = clamp((clientX - rect.left) / rect.width, 0, 1);
    onCursor(new Date(start + (end - start) * ratio).toISOString().slice(0, 10));
  }

  return (
    <footer className="timeline">
      <div className="timeline-heading">
        <span>Temporal analysis · {events.length} visible events</span>
        <span>Cursor <b>{cursor}</b></span>
      </div>
      <div
        className="timeline-track"
        role="slider"
        tabIndex={0}
        aria-label="Temporal cursor"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(percentage(cursorMs))}
        aria-valuetext={cursor}
        onClick={(event) => updateCursor(event.clientX, event.currentTarget.getBoundingClientRect())}
        onKeyDown={(event) => {
          if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
          event.preventDefault();
          const direction = event.key === 'ArrowLeft' ? -1 : 1;
          const step = event.shiftKey ? 7 : 1;
          const next = clamp(cursorMs + direction * step * DAY, start, end);
          onCursor(new Date(next).toISOString().slice(0, 10));
        }}
      >
        <div className="timeline-cursor" style={{ left: `${percentage(cursorMs)}%` }} />
        {events.map((eventRecord) => (
          <button
            key={eventRecord.id}
            className="timeline-event"
            style={{ left: `${percentage(Date.parse(eventRecord.at))}%` }}
            data-tier={eventRecord.tier ?? 'unassigned'}
            title={`${eventRecord.label} · ${eventRecord.at}`}
            onClick={(event) => {
              event.stopPropagation();
              onSelect({ kind: 'event', id: eventRecord.id });
            }}
          >
            {eventRecord.id}
          </button>
        ))}
      </div>
    </footer>
  );
}

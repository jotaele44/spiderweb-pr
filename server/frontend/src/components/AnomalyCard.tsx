import type { ReactNode } from "react";
import type { Anomaly } from "../types/priis";
import { AnomalyScore } from "./Badges";

/**
 * Clickable anomaly cluster card used by CommandCenter, SpatialIntelligence, and
 * AnomalyWorkbench. `heading` is the title line, `meta` an optional subtle line
 * (e.g. category), and `body` the descriptive line.
 */
export function AnomalyCard({
  anomaly,
  heading,
  meta,
  body,
  onClick,
}: {
  anomaly: Pick<Anomaly, "band" | "score">;
  heading: ReactNode;
  meta?: ReactNode;
  body?: ReactNode;
  onClick: () => void;
}) {
  return (
    <button className="anom-card" data-band={anomaly.band} onClick={onClick}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h4>{heading}</h4>
        <AnomalyScore score={anomaly.score} />
      </div>
      {meta && <div className="subtle mono anom-meta">{meta}</div>}
      {body && <p className="desc">{body}</p>}
    </button>
  );
}

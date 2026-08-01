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
    // A <button>'s content model is phrasing content only, so the heading and
    // body are spans styled to match rather than <h4>/<p>.
    <button className="anom-card" data-band={anomaly.band} onClick={onClick}>
      <span className="row" style={{ justifyContent: "space-between" }}>
        <span className="anom-heading">{heading}</span>
        <AnomalyScore score={anomaly.score} />
      </span>
      {meta && <span className="subtle mono anom-meta">{meta}</span>}
      {body && <span className="desc">{body}</span>}
    </button>
  );
}

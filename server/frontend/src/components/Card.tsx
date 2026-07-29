import type { ReactNode } from "react";

/** KPI stat card: uppercase title, large stat with optional unit, small delta. */
export function Card({
  title,
  stat,
  unit,
  delta,
}: {
  title: string;
  stat: ReactNode;
  unit?: string;
  delta?: ReactNode;
}) {
  return (
    <div className="card">
      <h3>{title}</h3>
      <div className="stat">{stat}{unit && <span className="unit">{unit}</span>}</div>
      {delta && <div className="delta">{delta}</div>}
    </div>
  );
}

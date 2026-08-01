import type { ReactNode } from "react";

export interface EntityLink {
  key: string;
  label: ReactNode;
  value?: ReactNode;
  mono?: boolean;
  /** Omit for reference-only rows; they render as static text, not buttons. */
  onClick?: () => void;
}

/**
 * A titled card of clickable entity links (`.card > h3 + navbtn` rows) with a
 * built-in empty state. Replaces the linked-contracts / linked-anomalies /
 * linked-awards / vendor-concentration blocks duplicated across Inspector,
 * AnomalyWorkbench, and FinanceIntelligence.
 */
export function EntityLinkList({
  title,
  items,
  empty = "None",
}: {
  title: string;
  items: EntityLink[];
  empty?: ReactNode;
}) {
  return (
    <div className="card">
      <h2>{title}</h2>
      {items.length === 0 ? (
        <div className="rail-empty">{empty}</div>
      ) : (
        items.map((item) =>
          item.onClick ? (
            <button key={item.key} className="navbtn" onClick={item.onClick}>
              <span>{item.label}</span>
              <span className={item.mono ? "mono" : undefined}>{item.value}</span>
            </button>
          ) : (
            <div key={item.key} className="navbtn navbtn-static">
              <span>{item.label}</span>
              <span className={item.mono ? "mono" : undefined}>{item.value}</span>
            </div>
          ),
        )
      )}
    </div>
  );
}

import type { ReactNode } from "react";
import type { Confidence, EvidenceTier } from "../types/priis";

export function TierBadge({ tier }: { tier: EvidenceTier }) {
  return <span className="badge" data-tier={tier}>{tier}</span>;
}

export function Pill({ tone = "info", children }: { tone?: "ok" | "warn" | "alert" | "info"; children: ReactNode }) {
  return <span className="pill" data-tone={tone}>{children}</span>;
}

export function ConfidenceMeter({ value }: { value: Confidence }) {
  const label = value === 3 ? "high" : value === 2 ? "medium" : "low";
  return (
    <div className="col" style={{ gap: 4 }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <span className="subtle mono">CONFIDENCE</span>
        <b className="mono">{label}</b>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 3 }}>
        {[1, 2, 3].map((i) => (
          <div key={i} style={{ height: 6, background: i <= value ? "var(--ink)" : "var(--line-soft)" }} />
        ))}
      </div>
    </div>
  );
}

export function AnomalyScore({ score }: { score: number }) {
  const tone = score >= 0.8 ? "alert" : score >= 0.6 ? "warn" : "info";
  return <Pill tone={tone}>{Math.round(score * 100)} score</Pill>;
}

export function ContradictionFlag({ items }: { items: string[] }) {
  if (!items.length) return <Pill tone="ok">no contradictions logged</Pill>;
  return (
    <div className="card" style={{ borderColor: "var(--warn)" }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <b>Contradiction control</b>
        <Pill tone="warn">{items.length} open</Pill>
      </div>
      <ul>
        {items.map((item) => <li key={item}>{item}</li>)}
      </ul>
    </div>
  );
}

import type { ReactNode } from "react";
import type { Anomaly, Confidence, Contract, EvidenceTier, Investigation, SourceRecord, Vendor } from "../types/priis";

export type Tone = "ok" | "warn" | "alert" | "info";

// ── Tone/threshold helpers ───────────────────────────────────────────────────
// Single source of truth for the status/score/risk → tone mapping that was
// previously re-implemented inline across CommandCenter, Finance, Inspector,
// AnomalyWorkbench, and LeftRail.

export function scoreTone(score: number): Tone {
  return score >= 0.8 ? "alert" : score >= 0.6 ? "warn" : "info";
}

export function contractStatusTone(status: Contract["status"]): Tone {
  return status === "flagged" ? "alert" : status === "amended" ? "warn" : "ok";
}

export function sourceStatusTone(status: SourceRecord["status"]): Tone {
  return status === "online" ? "ok" : status === "partial" ? "warn" : "alert";
}

export function riskTone(risk: Vendor["risk"]): Tone {
  return risk > 0.7 ? "alert" : risk > 0.55 ? "warn" : "ok";
}

export function bandTone(band: Anomaly["band"]): Tone {
  return band === "hi" ? "alert" : "warn";
}

export function investigationStatusTone(status: Investigation["status"]): Tone {
  if (status === "active") return "ok";
  if (status === "needs_review") return "alert";
  return status === "paused" ? "warn" : "info";
}

// ── Primitives ───────────────────────────────────────────────────────────────

export function TierBadge({ tier }: { tier: EvidenceTier }) {
  return <span className="badge" data-tier={tier}>{tier}</span>;
}

export function Pill({ tone = "info", children }: { tone?: Tone; children: ReactNode }) {
  return <span className="pill" data-tone={tone}>{children}</span>;
}

export function ConfidenceMeter({ value }: { value: Confidence }) {
  const label = value === 3 ? "high" : value === 2 ? "medium" : "low";
  return (
    <div className="confidence-meter">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <span className="subtle mono">CONFIDENCE</span>
        <b className="mono">{label}</b>
      </div>
      <div className="confidence-bars">
        {[1, 2, 3].map((i) => (
          <div key={i} className="confidence-bar" data-filled={i <= value} />
        ))}
      </div>
    </div>
  );
}

export function AnomalyScore({ score }: { score: number }) {
  return <Pill tone={scoreTone(score)}>{Math.round(score * 100)} score</Pill>;
}

export function ContradictionFlag({ items }: { items: string[] }) {
  if (!items.length) return <Pill tone="ok">no contradictions logged</Pill>;
  return (
    <div className="card contradiction-card">
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

import { useMemo } from "react";
import { byId } from "../data/mockData";
import type {
  EventRecord,
  EvidenceTier,
  PriisData,
  Selection,
} from "../types/priis";
import {
  AnomalyScore,
  ConfidenceMeter,
  ContradictionFlag,
  Pill,
  TierBadge,
} from "../components/Badges";
import {
  evidenceTierBreakdown,
  isT3T4OnlyAtHighConfidence,
} from "../lib/evidence";

function EvidenceTierPanel({
  byTier,
  untieredEvents,
  total,
  violation,
}: {
  byTier: Record<EvidenceTier, number>;
  untieredEvents: number;
  total: number;
  violation: boolean;
}) {
  const tiers: EvidenceTier[] = ["T1", "T2", "T3", "T4"];
  return (
    <div
      className="card"
      style={violation ? { borderColor: "var(--alert)", borderWidth: 2 } : undefined}
    >
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h3>Evidence tier breakdown</h3>
        {violation && (
          <Pill tone="alert">HIGH CONFIDENCE WITHOUT T1/T2 EVIDENCE</Pill>
        )}
      </div>
      <div className="row" style={{ gap: 12, flexWrap: "wrap" }}>
        {tiers.map((t) => (
          <span key={t} className="row" style={{ gap: 4 }}>
            <TierBadge tier={t} />
            <b className="mono">{byTier[t]}</b>
          </span>
        ))}
        {untieredEvents > 0 && (
          <span className="row" style={{ gap: 4 }}>
            <span className="badge" data-tier="unknown">UNK</span>
            <b className="mono">{untieredEvents}</b>
          </span>
        )}
      </div>
      <div className="subtle mono" style={{ fontSize: "0.7rem", marginTop: 4 }}>
        rolled up from {anomalyEvidenceSourceCount(total)} — contracts + events
      </div>
      {violation && (
        <p className="subtle" style={{ marginTop: 6 }}>
          Per HANDOFF: pattern convergence alone is a lead, not a conclusion.
          Promote this only after a T1 or T2 source confirms.
        </p>
      )}
    </div>
  );
}

function anomalyEvidenceSourceCount(total: number): string {
  return total === 1 ? "1 source" : `${total} sources`;
}

function RelatedEventsCard({
  events,
  setSelection,
}: {
  events: EventRecord[];
  setSelection: (selection: Selection) => void;
}) {
  if (events.length === 0) {
    return (
      <div className="card">
        <h3>Related events</h3>
        <p className="subtle">No events linked to this anomaly.</p>
      </div>
    );
  }
  return (
    <div className="card">
      <h3>Related events</h3>
      {events.map((e) => (
        <button
          key={e.id}
          className="navbtn"
          onClick={() => setSelection({ kind: "event", id: e.id })}
          title={e.label}
        >
          <span>
            {e.tier ? <TierBadge tier={e.tier} /> : <span className="badge" data-tier="unknown">UNK</span>}
            {" "}
            <Pill>{e.kind}</Pill>
            {" "}
            {e.label}
          </span>
          <span className="mono">{e.at}</span>
        </button>
      ))}
    </div>
  );
}

export function AnomalyWorkbench({
  data,
  selection,
  setSelection,
}: {
  data: PriisData;
  selection: Selection | null;
  setSelection: (selection: Selection) => void;
}) {
  const active =
    selection?.kind === "anomaly"
      ? byId(data.anomalies, selection.id)
      : data.anomalies[0];

  const breakdown = useMemo(
    () => (active ? evidenceTierBreakdown(active, data) : null),
    [active, data],
  );
  const violation = active && breakdown
    ? isT3T4OnlyAtHighConfidence(active, breakdown.byTier)
    : false;
  const relatedEvents = useMemo(
    () =>
      active
        ? active.events
            .map((eid) => byId(data.events, eid))
            .filter((e): e is EventRecord => e !== undefined)
            .sort((a, b) => a.at.localeCompare(b.at))
        : [],
    [active, data.events],
  );

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h1>Anomaly Workbench</h1>
          <span className="subtle">
            Pattern convergence only · no conclusion-first escalation
          </span>
        </div>
        <Pill tone="warn">T3/T4 are leads</Pill>
      </div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "320px 1fr",
          height: "100%",
          minHeight: 0,
        }}
      >
        <aside
          className="layer-panel"
          style={{ borderLeft: 0, borderRight: "1px solid var(--line)" }}
        >
          <h3>Cluster queue</h3>
          <div className="col">
            {data.anomalies.map((anomaly) => (
              <button
                key={anomaly.id}
                className="anom-card"
                data-band={anomaly.band}
                data-active={selection?.kind === "anomaly" && selection.id === anomaly.id}
                onClick={() => setSelection({ kind: "anomaly", id: anomaly.id })}
              >
                <h4>{anomaly.id}</h4>
                <div className="row">
                  <AnomalyScore score={anomaly.score} />
                  <span>{anomaly.category}</span>
                </div>
                <p className="desc">{anomaly.title}</p>
              </button>
            ))}
          </div>
        </aside>
        <div className="panel-grid">
          {active && breakdown && (
            <>
              <div className="card">
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <h3>
                    {active.id} · {active.title}
                  </h3>
                  <AnomalyScore score={active.score} />
                </div>
                <p className="desc">{active.summary}</p>
              </div>
              <div className="cards" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
                <div className="card">
                  <h3>Site</h3>
                  <button
                    className="act"
                    onClick={() => setSelection({ kind: "site", id: active.siteId })}
                  >
                    {byId(data.sites, active.siteId)?.name}
                  </button>
                </div>
                <div className="card">
                  <h3>Confidence</h3>
                  <ConfidenceMeter value={active.confidence} />
                </div>
                <div className="card">
                  <h3>Contract count</h3>
                  <div className="stat">{active.contracts.length}</div>
                </div>
              </div>
              <EvidenceTierPanel
                byTier={breakdown.byTier}
                untieredEvents={breakdown.untieredEvents}
                total={breakdown.total}
                violation={violation}
              />
              <div className="card">
                <h3>Factors</h3>
                <ul>
                  {active.factors.map((factor) => (
                    <li key={`${factor.tag}-${factor.note}`}>
                      <b>{factor.tag}</b> — {factor.note}
                    </li>
                  ))}
                </ul>
                <div className="subtle" style={{ fontSize: "0.7rem", marginTop: 4 }}>
                  Factors are pattern signals, not evidence.
                </div>
              </div>
              <RelatedEventsCard events={relatedEvents} setSelection={setSelection} />
              <ContradictionFlag items={active.contradictions} />
            </>
          )}
        </div>
      </div>
    </section>
  );
}


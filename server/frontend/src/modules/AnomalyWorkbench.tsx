import { byId } from "../data/mockData";
import type { PriisData, Selection } from "../types/priis";
import { AnomalyScore, ConfidenceMeter, ContradictionFlag, Pill } from "../components/Badges";
import { AnomalyCard } from "../components/AnomalyCard";

export function AnomalyWorkbench({ data, selection, setSelection }: { data: PriisData; selection: Selection | null; setSelection: (selection: Selection) => void }) {
  const active = selection?.kind === "anomaly" ? byId(data.anomalies, selection.id) : data.anomalies[0];
  if (!data.anomalies.length) {
    return (
      <section className="panel">
        <div className="panel-head"><div><h1>Anomaly Workbench</h1><span className="subtle">Pattern convergence only · no conclusion-first escalation</span></div><Pill tone="warn">T3/T4 are leads</Pill></div>
        <div className="empty-state">No anomaly clusters in the current dataset.</div>
      </section>
    );
  }
  return (
    <section className="panel">
      <div className="panel-head"><div><h1>Anomaly Workbench</h1><span className="subtle">Pattern convergence only · no conclusion-first escalation</span></div><Pill tone="warn">T3/T4 are leads</Pill></div>
      <div style={{ display: "grid", gridTemplateColumns: "320px 1fr", height: "100%", minHeight: 0 }}>
        <aside className="layer-panel" style={{ borderLeft: 0, borderRight: "1px solid var(--line)" }}>
          <h3>Cluster queue</h3>
          <div className="col">
            {data.anomalies.map((anomaly) => (
              <AnomalyCard
                key={anomaly.id}
                anomaly={anomaly}
                heading={anomaly.id}
                meta={anomaly.category}
                body={anomaly.title}
                onClick={() => setSelection({ kind: "anomaly", id: anomaly.id })}
              />
            ))}
          </div>
        </aside>
        <div className="panel-grid">
          {active && <>
            <div className="card"><div className="row" style={{ justifyContent: "space-between" }}><h3>{active.id} · {active.title}</h3><AnomalyScore score={active.score} /></div><p className="desc">{active.summary}</p></div>
            <div className="cards" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
              <div className="card"><h3>Site</h3><button className="act" onClick={() => setSelection({ kind: "site", id: active.siteId })}>{byId(data.sites, active.siteId)?.name}</button></div>
              <div className="card"><h3>Confidence</h3><ConfidenceMeter value={active.confidence} /></div>
              <div className="card"><h3>Contract count</h3><div className="stat">{active.contracts.length}</div></div>
            </div>
            <div className="card"><h3>Factors</h3><ul>{active.factors.map((factor) => <li key={`${factor.tag}-${factor.note}`}><b>{factor.tag}</b> — {factor.note}</li>)}</ul></div>
            <ContradictionFlag items={active.contradictions} />
          </>}
        </div>
      </div>
    </section>
  );
}

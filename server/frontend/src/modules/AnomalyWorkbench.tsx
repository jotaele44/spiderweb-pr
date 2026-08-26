import { byId } from "../lib/format";
import type { PriisData, Selection } from "../types/priis";
import { AnomalyScore, ConfidenceMeter, ContradictionFlag, Pill } from "../components/Badges";
import { AnomalyCard } from "../components/AnomalyCard";
import { exportAnomaliesCsv } from "../export/csvExport";
import { downloadBrief } from "../export/evidenceBrief";

export function AnomalyWorkbench({ data, selection, setSelection }: { data: PriisData; selection: Selection | null; setSelection: (selection: Selection) => void }) {
  // Falls back to the head of the queue when the selection names an anomaly this
  // dataset does not contain — a stale selection used to blank the whole detail
  // pane, which reads as a broken module rather than a bad id.
  const active =
    (selection?.kind === "anomaly" ? byId(data.anomalies, selection.id) : undefined) ??
    data.anomalies[0];
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
      <div className="panel-head">
        <div><h1>Anomaly Workbench</h1><span className="subtle">Pattern convergence only · no conclusion-first escalation</span></div>
        <div className="row" style={{ gap: "0.5rem" }}>
          <Pill tone="warn">T3/T4 are leads</Pill>
          <button className="act" onClick={() => exportAnomaliesCsv(data)}>EXPORT CSV</button>
          <button className="act" disabled={!active} onClick={() => active && downloadBrief(active.id, data)}>
            EXPORT BRIEF
          </button>
        </div>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "320px 1fr", height: "100%", minHeight: 0 }}>
        <aside className="layer-panel" style={{ borderLeft: 0, borderRight: "1px solid var(--line)" }}>
          <h2>Cluster queue</h2>
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
            <div className="card"><div className="row" style={{ justifyContent: "space-between" }}><h2>{active.id} · {active.title}</h2><AnomalyScore score={active.score} /></div><p className="desc">{active.summary}</p></div>
            <div className="cards" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
              <div className="card"><h2>Site</h2><button className="act" onClick={() => setSelection({ kind: "site", id: active.siteId })}>{byId(data.sites, active.siteId)?.name}</button></div>
              <div className="card"><h2>Confidence</h2><ConfidenceMeter value={active.confidence} /></div>
              <div className="card"><h2>Contract count</h2><div className="stat">{active.contracts.length}</div></div>
            </div>
            <div className="card"><h2>Factors</h2><ul>{active.factors.map((factor) => <li key={`${factor.tag}-${factor.note}`}><b>{factor.tag}</b> — {factor.note}</li>)}</ul></div>
            <ContradictionFlag items={active.contradictions} />
          </>}
        </div>
      </div>
    </section>
  );
}

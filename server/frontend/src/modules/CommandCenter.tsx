import { fmtMoney } from "../lib/format";
import type { ModuleId, PriisData, Selection } from "../types/priis";
import { Pill, TierBadge } from "../components/Badges";
import { Card } from "../components/Card";
import { AnomalyCard } from "../components/AnomalyCard";

export function CommandCenter({ data, setSelection, setModule }: { data: PriisData; setSelection: (selection: Selection) => void; setModule: (id: ModuleId) => void }) {
  const total = data.contracts.reduce((sum, contract) => sum + contract.amount, 0);
  const flagged = data.contracts.filter((contract) => contract.status === "flagged").length;
  const high = data.anomalies.filter((anomaly) => anomaly.band === "hi");
  return (
    <section className="panel">
      <div className="panel-head"><div><h1>Command Center</h1><span className="subtle">Spiderweb spatial / operational producer · PRII federation</span></div><button className="act primary" onClick={() => setModule("query")}>OPEN QUERY LAYER</button></div>
      <div className="panel-grid">
        <div className="cards">
          <Card title="Total awarded" stat={fmtMoney(total)} delta={`${data.contracts.length} contracts`} />
          <Card title="Contracts flagged" stat={flagged} unit={` of ${data.contracts.length}`} delta="requires evidence review" />
          <Card title="High-score clusters" stat={high.length} unit=" ≥0.80" delta="pattern-convergence only" />
          <Card title="Sources" stat={data.sources.length} unit=" fixtures" delta={`${data.sources.filter((s) => s.status !== "online").length} degraded`} />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1.3fr 1fr", gap: 14 }}>
          <div className="card">
            <h2>Alert feed</h2>
            <table className="dtable">
              <thead><tr><th>Time</th><th>Kind</th><th>Subject</th><th>Tier</th><th>Inv</th></tr></thead>
              <tbody>{data.alerts.length === 0
                ? <tr><td colSpan={5} className="subtle" style={{ padding: 16, textAlign: "center" }}>No active alerts.</td></tr>
                : data.alerts.map((alert) => <tr key={alert.id}><td className="mono">{alert.at}</td><td><Pill tone={alert.kind === "anomaly" ? "alert" : alert.kind === "source" ? "warn" : "info"}>{alert.kind}</Pill></td><td>{alert.title}</td><td><TierBadge tier={alert.tier} /></td><td className="mono">{alert.investigation}</td></tr>)}</tbody>
            </table>
          </div>
          <div className="col">
            {data.anomalies.map((anomaly) => (
              <AnomalyCard
                key={anomaly.id}
                anomaly={anomaly}
                heading={`${anomaly.id} · ${anomaly.title}`}
                meta={anomaly.category}
                body={anomaly.summary}
                onClick={() => { setSelection({ kind: "anomaly", id: anomaly.id }); setModule("anomaly"); }}
              />
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

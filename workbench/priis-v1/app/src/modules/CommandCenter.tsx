import { fmtMoney } from "../data/mockData";
import type { ModuleId, PriisData, Selection } from "../types/priis";
import { AnomalyScore, Pill, TierBadge } from "../components/Badges";

function Card({ title, stat, unit, delta }: { title: string; stat: string | number; unit?: string; delta: string }) {
  return <div className="card"><h3>{title}</h3><div className="stat">{stat}<span className="unit">{unit}</span></div><div className="delta">{delta}</div></div>;
}

export function CommandCenter({ data, setSelection, setModule }: { data: PriisData; setSelection: (selection: Selection) => void; setModule: (id: ModuleId) => void }) {
  const total = data.contracts.reduce((sum, contract) => sum + contract.amount, 0);
  const high = data.anomalies.filter((anomaly) => anomaly.band === "hi");
  return (
    <section className="panel">
      <div className="panel-head"><div><h1>Command Center</h1><span className="subtle">PRIIS operational view · Puerto Rico integrated intelligence</span></div><button className="act primary" onClick={() => setModule("query")}>OPEN QUERY LAYER</button></div>
      <div className="panel-grid">
        <div className="cards">
          <Card title="Total awarded" stat={fmtMoney(total)} delta={`${data.contracts.length} contracts`} />
          <Card title="Contracts flagged" stat={data.contracts.filter((contract) => contract.status === "flagged").length} unit=" of 8" delta="requires evidence review" />
          <Card title="High-score clusters" stat={high.length} unit=" ≥0.80" delta="pattern-convergence only" />
          <Card title="Sources" stat={data.sources.length} unit=" fixtures" delta="1 partial source" />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1.3fr 1fr", gap: 14 }}>
          <div className="card">
            <h3>Alert feed</h3>
            <table className="dtable">
              <thead><tr><th>Time</th><th>Kind</th><th>Subject</th><th>Tier</th><th>Inv</th></tr></thead>
              <tbody>{data.alerts.map((alert) => <tr key={alert.id}><td className="mono">{alert.at}</td><td><Pill tone={alert.kind === "anomaly" ? "alert" : alert.kind === "source" ? "warn" : "info"}>{alert.kind}</Pill></td><td>{alert.title}</td><td><TierBadge tier={alert.tier} /></td><td className="mono">{alert.investigation}</td></tr>)}</tbody>
            </table>
          </div>
          <div className="col">
            {data.anomalies.map((anomaly) => (
              <button key={anomaly.id} className="anom-card" data-band={anomaly.band} onClick={() => { setSelection({ kind: "anomaly", id: anomaly.id }); setModule("anomaly"); }}>
                <h4>{anomaly.id} · {anomaly.title}</h4>
                <div className="row"><AnomalyScore score={anomaly.score} /><span className="subtle">{anomaly.category}</span></div>
                <p className="desc">{anomaly.summary}</p>
              </button>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

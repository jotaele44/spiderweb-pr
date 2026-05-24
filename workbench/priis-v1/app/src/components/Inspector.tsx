import { byId, fmtMoney } from "../data/mockData";
import type { PriisData, Selection } from "../types/priis";
import { AnomalyScore, ConfidenceMeter, ContradictionFlag, Pill, TierBadge } from "./Badges";

export function Inspector({ data, selection, setSelection }: { data: PriisData; selection: Selection | null; setSelection: (selection: Selection) => void }) {
  if (!selection) {
    return (
      <aside className="inspector">
        <div className="inspector-head"><div className="subtle mono">INSPECTOR</div><h2>No selection</h2></div>
        <div className="inspector-body"><p>Select a contract, site, anomaly, vendor, or event.</p></div>
      </aside>
    );
  }

  if (selection.kind === "anomaly") {
    const anomaly = byId(data.anomalies, selection.id);
    if (!anomaly) return <Missing selection={selection} />;
    const site = byId(data.sites, anomaly.siteId);
    return (
      <aside className="inspector">
        <div className="inspector-head">
          <div className="subtle mono">ANOMALY · {anomaly.id}</div>
          <h2>{anomaly.title}</h2>
          <div className="row"><AnomalyScore score={anomaly.score} /><Pill tone={anomaly.band === "hi" ? "alert" : "warn"}>{anomaly.category}</Pill></div>
        </div>
        <div className="inspector-body">
          <p className="desc">{anomaly.summary}</p>
          <ConfidenceMeter value={anomaly.confidence} />
          <ContradictionFlag items={anomaly.contradictions} />
          {site && <button className="act" onClick={() => setSelection({ kind: "site", id: site.id })}>Open site · {site.name}</button>}
          <div className="card">
            <h3>Factors</h3>
            <ul>{anomaly.factors.map((factor) => <li key={`${factor.tag}-${factor.note}`}><b>{factor.tag}</b> — {factor.note}</li>)}</ul>
          </div>
          <div className="card">
            <h3>Linked contracts</h3>
            {anomaly.contracts.map((id) => {
              const contract = byId(data.contracts, id);
              return contract ? <button className="navbtn" key={id} onClick={() => setSelection({ kind: "contract", id })}><span>{id}</span><span>{fmtMoney(contract.amount)}</span></button> : null;
            })}
          </div>
        </div>
      </aside>
    );
  }

  if (selection.kind === "contract") {
    const contract = byId(data.contracts, selection.id);
    if (!contract) return <Missing selection={selection} />;
    const agency = byId(data.agencies, contract.agency);
    const vendor = byId(data.vendors, contract.vendor);
    const site = byId(data.sites, contract.site);
    return (
      <aside className="inspector">
        <div className="inspector-head">
          <div className="subtle mono">CONTRACT · {contract.id}</div>
          <h2>{fmtMoney(contract.amount)}</h2>
          <div className="row"><TierBadge tier={contract.tier} /><Pill tone={contract.status === "flagged" ? "alert" : contract.status === "amended" ? "warn" : "ok"}>{contract.status}</Pill></div>
        </div>
        <div className="inspector-body">
          <div className="card"><h3>Record</h3><p>{contract.note ?? "No note."}</p><p className="mono">signed {contract.signed}</p></div>
          {agency && <button className="act" onClick={() => setSelection({ kind: "agency", id: agency.id })}>Agency · {agency.code}</button>}
          {vendor && <button className="act" onClick={() => setSelection({ kind: "vendor", id: vendor.id })}>Vendor · {vendor.name}</button>}
          {site && <button className="act" onClick={() => setSelection({ kind: "site", id: site.id })}>Site · {site.name}</button>}
        </div>
      </aside>
    );
  }

  if (selection.kind === "site") {
    const site = byId(data.sites, selection.id);
    if (!site) return <Missing selection={selection} />;
    const contracts = data.contracts.filter((contract) => contract.site === site.id);
    const anomalies = data.anomalies.filter((anomaly) => anomaly.siteId === site.id);
    return (
      <aside className="inspector">
        <div className="inspector-head"><div className="subtle mono">SITE · {site.id}</div><h2>{site.name}</h2><div className="row"><Pill tone={site.sensitive ? "alert" : "info"}>{site.kind}</Pill></div></div>
        <div className="inspector-body">
          <div className="card"><h3>Coordinates</h3><p className="mono">{site.lat.toFixed(4)}, {site.lng.toFixed(4)}</p></div>
          <div className="card"><h3>Contracts</h3>{contracts.map((contract) => <button key={contract.id} className="navbtn" onClick={() => setSelection({ kind: "contract", id: contract.id })}><span>{contract.id}</span><span>{fmtMoney(contract.amount)}</span></button>)}</div>
          <div className="card"><h3>Anomalies</h3>{anomalies.map((anomaly) => <button key={anomaly.id} className="navbtn" onClick={() => setSelection({ kind: "anomaly", id: anomaly.id })}><span>{anomaly.id}</span><span>{Math.round(anomaly.score * 100)}</span></button>)}</div>
        </div>
      </aside>
    );
  }

  if (selection.kind === "vendor") {
    const vendor = byId(data.vendors, selection.id);
    if (!vendor) return <Missing selection={selection} />;
    const contracts = data.contracts.filter((contract) => contract.vendor === vendor.id);
    return (
      <aside className="inspector">
        <div className="inspector-head"><div className="subtle mono">VENDOR · {vendor.id}</div><h2>{vendor.name}</h2><div className="row"><TierBadge tier={vendor.tier} /><Pill tone={vendor.risk > 0.7 ? "alert" : vendor.risk > 0.55 ? "warn" : "ok"}>risk {vendor.risk.toFixed(2)}</Pill></div></div>
        <div className="inspector-body">
          <div className="card"><h3>Linked awards</h3>{contracts.map((contract) => <button key={contract.id} className="navbtn" onClick={() => setSelection({ kind: "contract", id: contract.id })}><span>{contract.id}</span><span>{fmtMoney(contract.amount)}</span></button>)}</div>
        </div>
      </aside>
    );
  }

  const event = selection.kind === "event" ? byId(data.events, selection.id) : undefined;
  if (event) {
    return (
      <aside className="inspector">
        <div className="inspector-head"><div className="subtle mono">EVENT · {event.id}</div><h2>{event.label}</h2><div className="row">{event.tier && <TierBadge tier={event.tier} />}<Pill>{event.kind}</Pill></div></div>
        <div className="inspector-body"><button className="act" onClick={() => setSelection({ kind: "site", id: event.siteId })}>Open linked site</button>{event.refId && <button className="act" onClick={() => setSelection({ kind: "contract", id: event.refId ?? "" })}>Open referenced record</button>}</div>
      </aside>
    );
  }

  return <Missing selection={selection} />;
}

function Missing({ selection }: { selection: Selection }) {
  return (
    <aside className="inspector">
      <div className="inspector-head"><div className="subtle mono">INSPECTOR</div><h2>Missing record</h2></div>
      <div className="inspector-body"><p>{selection.kind}/{selection.id} is not present in the fixture dataset.</p></div>
    </aside>
  );
}

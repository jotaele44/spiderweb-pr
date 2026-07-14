import { byId, fmtMoney } from "../data/mockData";
import type { PriisData, Selection } from "../types/priis";
import {
  AnomalyScore, ConfidenceMeter, ContradictionFlag, Pill, TierBadge,
  bandTone, contractStatusTone, riskTone,
} from "./Badges";
import { InspectorShell } from "./InspectorShell";
import { EntityLinkList, type EntityLink } from "./EntityLinkList";

export function Inspector({ data, selection, setSelection }: { data: PriisData; selection: Selection | null; setSelection: (selection: Selection) => void }) {
  if (!selection) {
    return (
      <InspectorShell eyebrow="INSPECTOR" title="No selection">
        <p>Select a contract, site, anomaly, vendor, or event.</p>
      </InspectorShell>
    );
  }

  if (selection.kind === "anomaly") {
    const anomaly = byId(data.anomalies, selection.id);
    if (!anomaly) return <Missing selection={selection} />;
    const site = byId(data.sites, anomaly.siteId);
    const contractLinks: EntityLink[] = anomaly.contracts.flatMap((id) => {
      const contract = byId(data.contracts, id);
      return contract ? [{ key: id, label: id, value: fmtMoney(contract.amount), onClick: () => setSelection({ kind: "contract", id }) }] : [];
    });
    return (
      <InspectorShell
        eyebrow={`ANOMALY · ${anomaly.id}`}
        title={anomaly.title}
        badges={<><AnomalyScore score={anomaly.score} /><Pill tone={bandTone(anomaly.band)}>{anomaly.category}</Pill></>}
      >
        <p className="desc">{anomaly.summary}</p>
        <ConfidenceMeter value={anomaly.confidence} />
        <ContradictionFlag items={anomaly.contradictions} />
        {site && <button className="act" onClick={() => setSelection({ kind: "site", id: site.id })}>Open site · {site.name}</button>}
        <div className="card">
          <h3>Factors</h3>
          <ul>{anomaly.factors.map((factor) => <li key={`${factor.tag}-${factor.note}`}><b>{factor.tag}</b> — {factor.note}</li>)}</ul>
        </div>
        <EntityLinkList title="Linked contracts" items={contractLinks} empty="No linked contracts" />
      </InspectorShell>
    );
  }

  if (selection.kind === "contract") {
    const contract = byId(data.contracts, selection.id);
    if (!contract) return <Missing selection={selection} />;
    const agency = byId(data.agencies, contract.agency);
    const vendor = byId(data.vendors, contract.vendor);
    const site = byId(data.sites, contract.site);
    return (
      <InspectorShell
        eyebrow={`CONTRACT · ${contract.id}`}
        title={fmtMoney(contract.amount)}
        badges={<><TierBadge tier={contract.tier} /><Pill tone={contractStatusTone(contract.status)}>{contract.status}</Pill></>}
      >
        <div className="card"><h3>Record</h3><p>{contract.note ?? "No note."}</p><p className="mono">signed {contract.signed}</p></div>
        {agency && <button className="act" onClick={() => setSelection({ kind: "agency", id: agency.id })}>Agency · {agency.code}</button>}
        {vendor && <button className="act" onClick={() => setSelection({ kind: "vendor", id: vendor.id })}>Vendor · {vendor.name}</button>}
        {site && <button className="act" onClick={() => setSelection({ kind: "site", id: site.id })}>Site · {site.name}</button>}
      </InspectorShell>
    );
  }

  if (selection.kind === "site") {
    const site = byId(data.sites, selection.id);
    if (!site) return <Missing selection={selection} />;
    const contractLinks: EntityLink[] = data.contracts
      .filter((contract) => contract.site === site.id)
      .map((contract) => ({ key: contract.id, label: contract.id, value: fmtMoney(contract.amount), onClick: () => setSelection({ kind: "contract", id: contract.id }) }));
    const anomalyLinks: EntityLink[] = data.anomalies
      .filter((anomaly) => anomaly.siteId === site.id)
      .map((anomaly) => ({ key: anomaly.id, label: anomaly.id, value: Math.round(anomaly.score * 100), onClick: () => setSelection({ kind: "anomaly", id: anomaly.id }) }));
    return (
      <InspectorShell
        eyebrow={`SITE · ${site.id}`}
        title={site.name}
        badges={<Pill tone={site.sensitive ? "alert" : "info"}>{site.kind}</Pill>}
      >
        <div className="card"><h3>Coordinates</h3><p className="mono">{site.lat.toFixed(4)}, {site.lng.toFixed(4)}</p></div>
        {(site.municipio_geoid ?? site.tract_geoid ?? site.zcta_geoid) && (
          <div className="card">
            <h3>TIGER GEOIDs</h3>
            {site.municipio_geoid && <p className="mono">municipio · <b>{site.municipio_geoid}</b></p>}
            {site.tract_geoid     && <p className="mono">tract · <b>{site.tract_geoid}</b></p>}
            {site.zcta_geoid      && <p className="mono">zcta · <b>{site.zcta_geoid}</b></p>}
          </div>
        )}
        <EntityLinkList title="Contracts" items={contractLinks} empty="No contracts at this site" />
        <EntityLinkList title="Anomalies" items={anomalyLinks} empty="No anomalies at this site" />
      </InspectorShell>
    );
  }

  if (selection.kind === "vendor") {
    const vendor = byId(data.vendors, selection.id);
    if (!vendor) return <Missing selection={selection} />;
    const awardLinks: EntityLink[] = data.contracts
      .filter((contract) => contract.vendor === vendor.id)
      .map((contract) => ({ key: contract.id, label: contract.id, value: fmtMoney(contract.amount), onClick: () => setSelection({ kind: "contract", id: contract.id }) }));
    return (
      <InspectorShell
        eyebrow={`VENDOR · ${vendor.id}`}
        title={vendor.name}
        badges={<><TierBadge tier={vendor.tier} /><Pill tone={riskTone(vendor.risk)}>risk {vendor.risk.toFixed(2)}</Pill></>}
      >
        <EntityLinkList title="Linked awards" items={awardLinks} empty="No linked awards" />
      </InspectorShell>
    );
  }

  const event = selection.kind === "event" ? byId(data.events, selection.id) : undefined;
  if (event) {
    return (
      <InspectorShell
        eyebrow={`EVENT · ${event.id}`}
        title={event.label}
        badges={<>{event.tier && <TierBadge tier={event.tier} />}<Pill>{event.kind}</Pill></>}
      >
        <button className="act" onClick={() => setSelection({ kind: "site", id: event.siteId })}>Open linked site</button>
        {event.refId && <button className="act" onClick={() => setSelection({ kind: "contract", id: event.refId ?? "" })}>Open referenced record</button>}
      </InspectorShell>
    );
  }

  return <Missing selection={selection} />;
}

function Missing({ selection }: { selection: Selection }) {
  return (
    <InspectorShell eyebrow="INSPECTOR" title="Missing record">
      <p>{selection.kind}/{selection.id} is not present in the fixture dataset.</p>
    </InspectorShell>
  );
}

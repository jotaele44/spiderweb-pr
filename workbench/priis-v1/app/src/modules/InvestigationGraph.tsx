import type { PriisData, Selection } from "../types/priis";
import { byId } from "../data/mockData";

interface GraphNode { id: string; label: string; kind: Selection["kind"]; x: number; y: number }

export function InvestigationGraph({ data, setSelection }: { data: PriisData; setSelection: (selection: Selection) => void }) {
  const anomaly = data.anomalies[0];
  if (!anomaly) {
    return (
      <section className="panel">
        <div className="panel-head"><div><h1>Investigation Graph</h1><span className="subtle">Entity graph scaffold · vendor / agency / site / anomaly</span></div></div>
        <div className="empty-state">No anomalies in the current dataset to graph.</div>
      </section>
    );
  }
  const site = byId(data.sites, anomaly.siteId);
  const contract = byId(data.contracts, anomaly.contracts[0]);
  const vendor = contract ? byId(data.vendors, contract.vendor) : undefined;
  const agency = contract ? byId(data.agencies, contract.agency) : undefined;
  const nodes: GraphNode[] = [
    { id: anomaly.id, label: anomaly.id, kind: "anomaly", x: 50, y: 45 },
    { id: site?.id ?? "S-000", label: site?.name ?? "site", kind: "site", x: 24, y: 28 },
    { id: contract?.id ?? "C-000", label: contract?.id ?? "contract", kind: "contract", x: 72, y: 28 },
    { id: vendor?.id ?? "V-000", label: vendor?.name ?? "vendor", kind: "vendor", x: 72, y: 68 },
    { id: agency?.id ?? "AG-000", label: agency?.code ?? "agency", kind: "agency", x: 28, y: 68 }
  ];
  return (
    <section className="panel">
      <div className="panel-head"><div><h1>Investigation Graph</h1><span className="subtle">Entity graph scaffold · vendor / agency / site / anomaly</span></div><button className="act">EXPORT GRAPH</button></div>
      <div className="graph-surface">
        <svg width="100%" height="100%" style={{ position: "absolute", inset: 0 }}>
          <line x1="50%" y1="45%" x2="24%" y2="28%" stroke="var(--line-hard)" />
          <line x1="50%" y1="45%" x2="72%" y2="28%" stroke="var(--line-hard)" />
          <line x1="72%" y1="28%" x2="72%" y2="68%" stroke="var(--line-hard)" />
          <line x1="72%" y1="28%" x2="28%" y2="68%" stroke="var(--line-hard)" />
        </svg>
        {nodes.map((node) => <button key={node.id} className="graph-node" style={{ left: `${node.x}%`, top: `${node.y}%` }} onClick={() => setSelection({ kind: node.kind, id: node.id })}><b>{node.kind}</b><br />{node.label}</button>)}
      </div>
    </section>
  );
}

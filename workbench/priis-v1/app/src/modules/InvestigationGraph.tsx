import type { PriisData, Selection } from "../types/priis";
import { byId } from "../data/mockData";

interface GraphNode { id: string; label: string; kind: Selection["kind"]; x: number; y: number }

function download(filename: string, content: string, mime = "application/json"): void {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

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

  // Node positions are defined once here; the SVG connectors below are derived
  // from these coordinates (no duplicated literals).
  const nodes: GraphNode[] = [
    { id: anomaly.id, label: anomaly.id, kind: "anomaly", x: 50, y: 45 },
    { id: site?.id ?? "S-000", label: site?.name ?? "site", kind: "site", x: 24, y: 28 },
    { id: contract?.id ?? "C-000", label: contract?.id ?? "contract", kind: "contract", x: 72, y: 28 },
    { id: vendor?.id ?? "V-000", label: vendor?.name ?? "vendor", kind: "vendor", x: 72, y: 68 },
    { id: agency?.id ?? "AG-000", label: agency?.code ?? "agency", kind: "agency", x: 28, y: 68 },
  ];
  const nodeById = (id: string) => nodes.find((n) => n.id === id);
  const edges: [string, string][] = [
    [nodes[0].id, nodes[1].id],
    [nodes[0].id, nodes[2].id],
    [nodes[2].id, nodes[3].id],
    [nodes[2].id, nodes[4].id],
  ];

  function exportGraph() {
    const payload = {
      generatedAt: new Date().toISOString(),
      anomaly: anomaly.id,
      nodes: nodes.map((n) => ({ id: n.id, kind: n.kind, label: n.label })),
      edges: edges.map(([from, to]) => ({ from, to })),
    };
    download(`priis-graph-${anomaly.id}.json`, JSON.stringify(payload, null, 2));
  }

  return (
    <section className="panel">
      <div className="panel-head"><div><h1>Investigation Graph</h1><span className="subtle">Entity graph scaffold · vendor / agency / site / anomaly</span></div><button className="act" onClick={exportGraph}>EXPORT GRAPH</button></div>
      <div className="graph-surface">
        <svg width="100%" height="100%" style={{ position: "absolute", inset: 0 }}>
          {edges.map(([from, to]) => {
            const a = nodeById(from);
            const b = nodeById(to);
            if (!a || !b) return null;
            return <line key={`${from}-${to}`} x1={`${a.x}%`} y1={`${a.y}%`} x2={`${b.x}%`} y2={`${b.y}%`} stroke="var(--line-hard)" />;
          })}
        </svg>
        {nodes.map((node) => <button key={node.id} className="graph-node" style={{ left: `${node.x}%`, top: `${node.y}%` }} onClick={() => setSelection({ kind: node.kind, id: node.id })}><b>{node.kind}</b><br />{node.label}</button>)}
      </div>
    </section>
  );
}

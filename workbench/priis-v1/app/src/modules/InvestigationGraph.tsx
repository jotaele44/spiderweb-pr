import { useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  type NodeMouseHandler,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { byId } from "../data/mockData";
import type { PriisData, Selection } from "../types/priis";

type EntityKind = Selection["kind"];

interface NodeData extends Record<string, unknown> {
  label: string;
  kind: EntityKind;
  entityId: string;
  sublabel?: string;
}

const NODE_STYLE: Record<EntityKind, { background: string; color: string; border: string }> = {
  anomaly:       { background: "var(--alert)",    color: "var(--ink)",     border: "1px solid var(--alert)" },
  contract:      { background: "var(--surface-2)", color: "var(--ink)",     border: "1px solid var(--t2)" },
  vendor:        { background: "var(--surface-2)", color: "var(--ink)",     border: "1px solid var(--t1)" },
  agency:        { background: "var(--surface-2)", color: "var(--ink)",     border: "1px solid var(--muted)" },
  site:          { background: "var(--surface-2)", color: "var(--ink)",     border: "1px solid var(--ok)" },
  event:         { background: "var(--surface-2)", color: "var(--ink)",     border: "1px solid var(--t3)" },
  source:        { background: "var(--surface-2)", color: "var(--ink)",     border: "1px solid var(--t4)" },
  investigation: { background: "var(--surface-2)", color: "var(--ink)",     border: "1px solid var(--muted)" },
  finding:       { background: "var(--surface-2)", color: "var(--ink)",     border: "1px solid var(--muted)" },
};

function nodeId(kind: EntityKind, id: string): string {
  return `${kind}:${id}`;
}

/** Place N items evenly around a circle of radius `r` centred at origin. */
function ringPositions(n: number, r: number, phase = 0): Array<{ x: number; y: number }> {
  if (n === 0) return [];
  return Array.from({ length: n }, (_, i) => {
    const angle = phase + (i * 2 * Math.PI) / n;
    return { x: r * Math.cos(angle), y: r * Math.sin(angle) };
  });
}

interface GraphModel { nodes: Node<NodeData>[]; edges: Edge[] }

/**
 * Build a 2-hop entity graph for the focal anomaly:
 *   anomaly → contracts → (vendors | agencies | sites)
 *               sites → other anomalies on the same site
 *
 * Layout: focal at origin, contracts on r=200, deduplicated
 * vendor/agency/site union on r=380, co-anomalies on r=560.
 */
function buildGraph(focal: PriisData["anomalies"][number], data: PriisData): GraphModel {
  const nodes: Node<NodeData>[] = [];
  const edges: Edge[] = [];

  // Focal anomaly
  nodes.push({
    id: nodeId("anomaly", focal.id),
    data: { label: focal.id, kind: "anomaly", entityId: focal.id, sublabel: focal.title },
    position: { x: 0, y: 0 },
    style: NODE_STYLE.anomaly,
  });

  // Contracts ring
  const contractIds = focal.contracts.filter((cid) => byId(data.contracts, cid));
  const contractPositions = ringPositions(contractIds.length, 200, -Math.PI / 2);
  const innerEntities = new Set<string>(); // dedupe of vendor/agency/site graph-node IDs

  const innerEntityHits: Array<{ kind: EntityKind; entityId: string; label: string }> = [];

  contractIds.forEach((cid, i) => {
    const contract = byId(data.contracts, cid);
    if (!contract) return;
    const nid = nodeId("contract", cid);
    nodes.push({
      id: nid,
      data: { label: cid, kind: "contract", entityId: cid, sublabel: `$${Math.round(contract.amount / 1e6)}M` },
      position: contractPositions[i],
      style: NODE_STYLE.contract,
    });
    edges.push({ id: `e-${nodeId("anomaly", focal.id)}-${nid}`, source: nodeId("anomaly", focal.id), target: nid });

    // Queue (vendor, agency, site) for the outer ring; dedupe by id.
    const vendor = byId(data.vendors, contract.vendor);
    const agency = byId(data.agencies, contract.agency);
    const site = contract.site ? byId(data.sites, contract.site) : undefined;
    [
      vendor && { kind: "vendor" as EntityKind, entityId: vendor.id, label: vendor.name },
      agency && { kind: "agency" as EntityKind, entityId: agency.id, label: agency.code },
      site   && { kind: "site"   as EntityKind, entityId: site.id,   label: site.name },
    ].forEach((hit) => {
      if (!hit) return;
      const hitId = nodeId(hit.kind, hit.entityId);
      // Always emit the contract→entity edge, even if the entity is shared.
      edges.push({ id: `e-${nid}-${hitId}`, source: nid, target: hitId });
      if (!innerEntities.has(hitId)) {
        innerEntities.add(hitId);
        innerEntityHits.push(hit);
      }
    });
  });

  // Outer ring of vendors/agencies/sites
  const outerPositions = ringPositions(innerEntityHits.length, 380, -Math.PI / 2 + Math.PI / 6);
  innerEntityHits.forEach((hit, i) => {
    nodes.push({
      id: nodeId(hit.kind, hit.entityId),
      data: { label: hit.label, kind: hit.kind, entityId: hit.entityId, sublabel: hit.kind },
      position: outerPositions[i],
      style: NODE_STYLE[hit.kind],
    });
  });

  // Co-anomalies — other anomalies sharing any site with the focal's contracts.
  const focalSiteIds = new Set<string>(
    contractIds
      .map((cid) => byId(data.contracts, cid)?.site)
      .filter((s): s is string => Boolean(s)),
  );
  // Focal anomaly's own site too.
  focalSiteIds.add(focal.siteId);
  const coAnomalies = data.anomalies.filter(
    (a) => a.id !== focal.id && focalSiteIds.has(a.siteId),
  );
  const coPositions = ringPositions(coAnomalies.length, 560, Math.PI / 2);
  coAnomalies.forEach((co, i) => {
    const nid = nodeId("anomaly", co.id);
    nodes.push({
      id: nid,
      data: { label: co.id, kind: "anomaly", entityId: co.id, sublabel: co.category },
      position: coPositions[i],
      style: NODE_STYLE.anomaly,
    });
    edges.push({
      id: `e-site-${co.siteId}-${nid}`,
      source: nodeId("site", co.siteId),
      target: nid,
    });
  });

  return { nodes, edges };
}

export function InvestigationGraph({
  data,
  selection,
  setSelection,
}: {
  data: PriisData;
  selection: Selection | null;
  setSelection: (selection: Selection) => void;
}) {
  // Focal anomaly: the selected anomaly, or first as fallback.
  const focal =
    (selection?.kind === "anomaly" ? byId(data.anomalies, selection.id) : undefined) ??
    data.anomalies[0];

  const { nodes, edges } = useMemo(
    () => (focal ? buildGraph(focal, data) : { nodes: [], edges: [] }),
    [focal, data],
  );

  const onNodeClick: NodeMouseHandler<Node<NodeData>> = (_event, node) => {
    setSelection({ kind: node.data.kind, id: node.data.entityId });
  };

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h1>Investigation Graph</h1>
          <span className="subtle">
            Entity traversal · focal anomaly{focal && (
              <>
                {" · "}
                <b>{focal.id}</b>
              </>
            )}
          </span>
        </div>
        <span className="subtle mono">{nodes.length} nodes · {edges.length} edges</span>
      </div>
      <div style={{ flex: 1, minHeight: 0, position: "relative", background: "var(--surface-2)" }}>
        {focal ? (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodeClick={onNodeClick}
            fitView
            fitViewOptions={{ padding: 0.15 }}
            minZoom={0.3}
            maxZoom={2}
            nodesDraggable
            nodesConnectable={false}
            elementsSelectable
            colorMode="dark"
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={32} />
            <Controls showInteractive={false} />
            <MiniMap pannable zoomable nodeStrokeWidth={3} />
          </ReactFlow>
        ) : (
          <div style={{ display: "grid", placeItems: "center", height: "100%", color: "var(--muted)" }}>
            No anomaly selected — pick one from the LeftRail or AnomalyWorkbench.
          </div>
        )}
      </div>
    </section>
  );
}

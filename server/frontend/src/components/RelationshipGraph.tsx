export type RelationshipRenderClass = "verified" | "context" | "hypothesized" | "contradicted" | "unresolved";

export interface RelationshipNode {
  id: string;
  label: string;
  group: string;
}

export interface RelationshipEdge {
  id: string;
  from: string;
  to: string;
  type: string;
  renderClass: RelationshipRenderClass;
  statement: string;
  distanceM?: number | null;
}

/**
 * Line style per class. A link that is not verified must never look verified,
 * so every class has its own dash pattern and its own text label; colour is
 * never the only difference.
 */
export const EDGE_STYLE: Record<RelationshipRenderClass, { dash: string; width: number; label: string; meaning: string }> = {
  verified: { dash: "none", width: 3, label: "verified", meaning: "direct evidence, independently reviewed" },
  context: { dash: "1 5", width: 1.5, label: "context", meaning: "near each other or in the same mapped unit; not a connection" },
  hypothesized: { dash: "8 6", width: 2, label: "hypothesized", meaning: "proposed, not supported yet" },
  contradicted: { dash: "2 4", width: 2, label: "contradicted", meaning: "evidence against this link is on record" },
  unresolved: { dash: "10 4 2 4", width: 2, label: "unresolved", meaning: "not adjudicated either way" },
};

export const RENDER_CLASS_ORDER: RelationshipRenderClass[] = [
  "verified",
  "context",
  "hypothesized",
  "contradicted",
  "unresolved",
];

const WIDTH = 640;
const HEIGHT = 360;

function layout(nodes: RelationshipNode[]): Map<string, { x: number; y: number }> {
  const groups = [...new Set(nodes.map((node) => node.group))];
  const positions = new Map<string, { x: number; y: number }>();
  groups.forEach((group, column) => {
    const members = nodes.filter((node) => node.group === group);
    const x = ((column + 1) * WIDTH) / (groups.length + 1);
    members.forEach((node, row) => {
      positions.set(node.id, { x, y: ((row + 1) * HEIGHT) / (members.length + 1) });
    });
  });
  return positions;
}

/** Typed relationship explorer. Draws each link in the style of its class. */
export function RelationshipGraph({
  nodes,
  edges,
  emptyMessage = "No relationships are recorded between these registries.",
}: {
  nodes: RelationshipNode[];
  edges: RelationshipEdge[];
  emptyMessage?: string;
}) {
  if (edges.length === 0) {
    return (
      <div className="empty-state" role="status">
        {emptyMessage}
      </div>
    );
  }
  const positions = layout(nodes);
  return (
    <figure className="relationship-graph">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label="Relationships between records">
        {edges.map((edge) => {
          const a = positions.get(edge.from);
          const b = positions.get(edge.to);
          if (!a || !b) return null;
          const style = EDGE_STYLE[edge.renderClass];
          const mx = (a.x + b.x) / 2;
          const my = (a.y + b.y) / 2;
          return (
            <g key={edge.id} data-render-class={edge.renderClass} data-edge-id={edge.id}>
              <title>{`${style.label}: ${edge.statement}`}</title>
              <line
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke="currentColor"
                strokeWidth={style.width}
                strokeDasharray={style.dash}
                data-render-class={edge.renderClass}
              />
              {edge.renderClass === "contradicted" && (
                <text x={mx} y={my + 5} textAnchor="middle" aria-hidden="true">
                  ✕
                </text>
              )}
              <text x={mx} y={my - 8} textAnchor="middle" className="relationship-edge-label">
                {style.label}
              </text>
            </g>
          );
        })}
        {nodes.map((node) => {
          const p = positions.get(node.id);
          if (!p) return null;
          return (
            <g key={node.id} data-node-id={node.id}>
              <circle cx={p.x} cy={p.y} r={6} fill="currentColor" />
              <text x={p.x} y={p.y + 20} textAnchor="middle" className="mono">
                {node.label}
              </text>
            </g>
          );
        })}
      </svg>
      <figcaption>
        <ul className="relationship-legend" aria-label="Line styles">
          {RENDER_CLASS_ORDER.map((renderClass) => {
            const style = EDGE_STYLE[renderClass];
            return (
              <li key={renderClass} data-render-class={renderClass}>
                <svg width="46" height="10" aria-hidden="true">
                  <line x1="2" y1="5" x2="44" y2="5" stroke="currentColor" strokeWidth={style.width} strokeDasharray={style.dash} />
                </svg>
                <strong>{style.label}</strong> — {style.meaning}
              </li>
            );
          })}
        </ul>
        <table className="ap-table">
          <caption className="subtle">Recorded relationships</caption>
          <thead>
            <tr>
              <th scope="col">From</th>
              <th scope="col">To</th>
              <th scope="col">Type</th>
              <th scope="col">Class</th>
              <th scope="col">Statement</th>
            </tr>
          </thead>
          <tbody>
            {edges.map((edge) => (
              <tr key={edge.id} data-render-class={edge.renderClass}>
                <td className="mono">{edge.from}</td>
                <td className="mono">{edge.to}</td>
                <td>{edge.type.toLowerCase().replace(/_/g, " ")}</td>
                <td>{EDGE_STYLE[edge.renderClass].label}</td>
                <td>{edge.statement}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </figcaption>
    </figure>
  );
}

import { useState } from "react";
import { RelationshipGraph, type RelationshipEdge, type RelationshipNode } from "../../components/RelationshipGraph";
import {
  errorMessage,
  fetchAccessPointRelationships,
  shortHash,
  type AccessPointRelationships as RelationshipsDocument,
} from "./accessPointsApi";

type State =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; document: RelationshipsDocument }
  | { status: "error"; message: string };

/** Nodes and edges for the graph, straight from the ledger rows. */
export function toGraph(document: RelationshipsDocument): { nodes: RelationshipNode[]; edges: RelationshipEdge[] } {
  const nodes = new Map<string, RelationshipNode>();
  const edges = document.relationships.map((relationship) => {
    for (const end of [relationship.source, relationship.target]) {
      nodes.set(end.identifier, { id: end.identifier, label: end.identifier, group: end.namespace });
    }
    return {
      id: relationship.relationship_id,
      from: relationship.source.identifier,
      to: relationship.target.identifier,
      type: relationship.relationship_type,
      renderClass: relationship.render_class,
      statement: relationship.statement,
      distanceM: relationship.distance_m,
    };
  });
  return { nodes: [...nodes.values()], edges };
}

/** Relationship explorer for the access-point registries. Loads on request. */
export function AccessPointRelationships() {
  const [state, setState] = useState<State>({ status: "idle" });
  const load = () => {
    setState({ status: "loading" });
    fetchAccessPointRelationships()
      .then((document) => setState({ status: "ready", document }))
      .catch((reason: unknown) => setState({ status: "error", message: errorMessage(reason) }));
  };
  return (
    <section className="card" aria-label="Access-point relationships">
      <h2>Access-point relationships</h2>
      <p className="subtle">
        Typed links between Inland and Off-Shore Access Point records. Being near each other is context, not a
        connection; a path is verified only if every link in it is.
      </p>
      {state.status === "idle" && (
        <button type="button" className="act" onClick={load}>
          Load relationships
        </button>
      )}
      {state.status === "loading" && <p role="status">Loading relationships…</p>}
      {state.status === "error" && (
        <p className="ap-alert" role="alert">
          Relationships could not be loaded: {state.message}
        </p>
      )}
      {state.status === "ready" && (
        <>
          <RelationshipGraph {...toGraph(state.document)} />
          <p className="subtle">
            {state.document.provenance.path} · sha256 {shortHash(state.document.provenance.sha256)}
          </p>
        </>
      )}
    </section>
  );
}

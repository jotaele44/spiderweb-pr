# Distributed ILAP Cluster System v1

## Active Vector

`DISTRIBUTED_ILAP_CLUSTER_SYSTEM`

## Objective

Refactor ILAP analysis so Spiderweb Pins are not treated as isolated suspicious points. Each Pin can instead operate as a subcomponent node inside a broader ILAP Area and ILAP Cluster.

This is an analytic grouping model. It does not assert that a site contains underground access, covert infrastructure, or non-public activity. It records spatial-functional coherence, contradictions, evidence tiers, and gaps.

## Ontology

| Level | Term | Meaning |
|---|---|---|
| L0 | Spiderweb Domain | Islandwide investigative domain. |
| L1 | ILAP Area | Broad geographic operating zone. |
| L2 | ILAP Cluster | Cohesive multi-node system inside an ILAP Area. |
| L3 | Subcomponent Node | Atomic Spiderweb Pin with a functional role. |
| L4 | Feature | Geometry, record, image feature, or observation supporting the node. |

## Pin Fields Added

The Pin schema now supports optional distributed ILAP assignment fields:

| Field | Purpose |
|---|---|
| `ilap_area_id` | Broad ILAP Area identifier. |
| `ilap_cluster_id` | Cluster identifier for grouped subcomponent nodes. |
| `node_role` | Functional role of the Pin inside the cluster. |
| `system_function` | Higher-level function inferred for the node. |
| `cluster_coherence_score` | 0-100 cluster coherence value. |
| `contradiction_flags` | Explicit source/model conflicts. |

## Node Role Logic

A Pin should remain low-confidence when it is anomalous alone. Cluster confidence rises only when multiple Pins form a coherent spatial-functional system across roles such as hydro, utility, access, logistics, terrain, airspace, institutional, or context-only functions.

## Evidence Rules

- T1 technical/primary evidence can support confirmation.
- T2 operational records can materially raise confidence.
- T3 observations can support but not prove.
- T4 secondary material can seed only.
- Residential-cover nodes cannot anchor a high-confidence cluster without T1/T2 support.
- Scores above 70 require at least two roles and two thematic domains.
- Scores above 85 require T1/T2 support and contradiction review.

## Execution

Build or refresh the registry:

```bash
python3 scripts/build_pin_registry.py
```

Rescore atomic Pins into clusters:

```bash
python3 scripts/rescore_ilap_clusters.py \
  --registry configs/master_pin_registry.yaml \
  --output outputs/RESCORED_ILAP_CLUSTER_LEDGER_v1.yaml
```

## Current Limitation

The current registry is labels-only until a pins-pass populates `pins[]`. Running the rescore script now produces a valid empty coverage ledger with the blocker marked as `registry is labels-only`.

## Output

Primary output:

`outputs/RESCORED_ILAP_CLUSTER_LEDGER_v1.yaml`

The output contains:

- expected universe
- assigned/unassigned pin counts
- coverage percentage
- cluster count
- unresolved pin list
- cluster records
- contradiction and gap flags

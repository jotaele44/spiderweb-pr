# Spiderweb Ontology

This directory contains the controlled vocabulary baseline for Spiderweb/UGCN records.

The ontology has three layers:

1. **Canonical vocabulary** — stable terms used by schemas, validators, exports, dashboard filters, scoring, and corridor construction.
2. **Alias bridge** — normal GIS/infrastructure/public-records language mapped to Spiderweb terms.
3. **Free-text evidence notes** — descriptive observations that should not become canonical terms unless they affect scoring or validation.

## Boundary rule

A term becomes canonical only if it is used in one or more of the following:

- scoring
- filtering
- validation
- deduplication
- export
- dashboard logic
- corridor construction
- source/provenance classification

Otherwise, it remains an alias or evidence note.

## Guardrail

Every exported POI, ILAP, corridor, anomaly, evidence item, or observation should carry:

- `entity_class`
- `analysis_mode`
- `world_layer`
- `claim_status`
- `taxonomy_version`

This prevents factual research, analytical hypothesis, and fictional worldbuilding records from collapsing into the same layer.

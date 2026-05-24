# PRIIS V1 Vector Lock

## Active vector

`LOCK_SPIDERWEB_DEMO_AS_PRIIS_V1_VISUAL_REFERENCE → EXTRACT_DESIGN_SYSTEM_AND_COMPONENT_INVENTORY → FREEZE_PRIIS_SCHEMAS → REBUILD_AS_REACT_TYPESCRIPT_MAPLIBRE_WORKBENCH`

## Source handoff audited

- Input bundle: `Spiderweb Demo-handoff.zip`
- Primary visual source: `spiderweb-demo/project/PRIIS Workbench.html`
- Primary React prototype source: `app.jsx`, `shell.jsx`, `inspector.jsx`, `timeline.jsx`, `mod-1.jsx`, `mod-2.jsx`, `mod-3.jsx`, `mod-4.jsx`, `styles.css`, `data.jsx`

## Authority hierarchy

| Rank | Authority | Scope |
|---:|---|---|
| 1 | `/contracts/*.schema.json` and `ontology.json` | Entity model, evidence model, source lineage, confidence structure |
| 2 | `/docs/DESIGN_SYSTEM_EXTRACTION.md` | UI behavior, component inventory, state rules |
| 3 | Spiderweb Demo visual handoff | Visual direction, layout proportions, interaction intent |
| 4 | `/app` implementation | Current starter workbench, not final production backend |
| 5 | Prototype mock data in `data.jsx` | Fixture reference only; not system truth |

## Locked decisions

| Decision | Status | Rationale |
|---|---|---|
| Preserve command bar / left rail / center workspace / right inspector / bottom timeline | Locked | Correct intelligence workbench geometry |
| Use evidence tiers T1/T2/T3/T4 everywhere | Locked | Prevents unsupported anomaly escalation |
| Treat anomaly analysis as pattern-convergence only | Locked | Avoids conclusion-first framing |
| Replace Leaflet with MapLibre GL JS | Locked | Supports vector-layer, source/layer, and GIS-grade evolution |
| Rebuild as React + TypeScript | Locked | Removes global Babel/CDN structure and enables strict contracts |
| Mock data becomes typed fixture data | Locked | Prevents mock object drift into backend contract |
| LLM/query layer remains an adapter stub | Locked | Real retrieval/tool routing comes after schema-bound UI is stable |

## Drift controls

| Drift risk | Control |
|---|---|
| Design tool invents backend entities | Contracts folder has higher authority than visual files |
| Leaflet assumptions survive into V1 | Map module names MapLibre explicitly and uses MapLibre GL JS |
| Query surface becomes a generic chatbot | `QueryLayer` uses evidence-first response contract |
| T3/T4 claims become conclusions | `source.schema.json`, `finding.schema.json`, and docs require tier-weighted confidence |
| Static prototype files become production code | App scaffold uses ES modules and TypeScript |

## Completion state

| Stage | State |
|---|---|
| Lock visual reference | Complete |
| Extract design system | Complete |
| Freeze initial schemas | Complete |
| Rebuild workbench starter | Complete as implementation scaffold |
| Verify production build | Not run; dependencies are not installed in this environment |

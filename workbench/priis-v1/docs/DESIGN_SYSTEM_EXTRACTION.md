# PRIIS V1 Design-System Extraction

## Baseline

The Spiderweb Demo is locked as the **PRIIS V1 visual and interaction reference**, not the production architecture. The extracted system below converts the prototype into implementation rules for a React/TypeScript + MapLibre workbench.

## Workbench geometry

| Region | Prototype source | V1 component | Behavior |
|---|---|---|---|
| Classification banner | `app.jsx` | `ClassificationBanner` | Optional operational banner above the workbench |
| Command bar | `shell.jsx` | `CommandBar` | Global query, active filters, run state, system brand |
| Left rail | `shell.jsx` | `LeftRail` | Module navigation, active investigation, source health, watchlist |
| Center workspace | `app.jsx` | `WorkspaceFrame` | Hosts active module; includes synchronized tabstrip |
| Right inspector | `inspector.jsx` | `Inspector` | Selected entity details, evidence, confidence, contradictions, linked objects |
| Bottom timeline | `timeline.jsx` | `Timeline` | Temporal cursor and linked event tracks |

## Primary modules

| Module | Prototype source | V1 route / component | Required state sync |
|---|---|---|---|
| Command Center | `mod-1.jsx` | `CommandCenter` | Select anomaly/site/contract; open module |
| Finance Intelligence | `mod-1.jsx` | `FinanceIntelligence` | Select contract/vendor/site; filter flagged contracts |
| Spatial Intelligence | `mod-2.jsx` | `SpatialIntelligence` | Select map site/anomaly; layer toggles; sync inspector |
| Anomaly Workbench | `mod-3.jsx` | `AnomalyWorkbench` | Select anomaly; filter categories; show evidence factors |
| Investigation Graph | `mod-4.jsx` | `InvestigationGraph` | Select graph node and linked entity |
| Query Layer | `mod-4.jsx` | `QueryLayer` | Submit prompt to typed adapter stub; return cited findings |

## Design tokens

The initial token values are extracted from `styles.css`.

| Token class | Examples | Notes |
|---|---|---|
| Typography | `--font-sans`, `--font-mono`, `--font-serif` | Public Sans / JetBrains Mono / Source Serif 4 visual direction preserved |
| Surfaces | `--bg`, `--surface`, `--surface-2`, `--surface-3` | Paper-grade government/GIS aesthetic |
| Lines | `--line`, `--line-soft`, `--line-hard` | Thin administrative boundaries and panels |
| Evidence | `--t1`, `--t2`, `--t3`, `--t4` | Tier badges and source rows |
| Status | `--alert`, `--warn`, `--ok`, `--info` | Findings, run health, contradiction markers |
| Layout | `--rail-w`, `--inspector-w`, `--cmd-h`, `--time-h` | Workbench grid dimensions |

## Evidence-tier visual rules

| Tier | Meaning | Visual rule | Analytical rule |
|---|---|---|---|
| T1 | Technical evidence | Teal badge / strongest source indicator | Highest weight; can support high confidence when corroborated |
| T2 | Operational record | Ochre badge | Strong institutional signal; contract/procurement/source-of-record class |
| T3 | Eyewitness / field report | Slate badge | Lead only unless T1/T2 corroborates |
| T4 | Secondary source | Gray badge | Lowest weight; cannot confirm findings alone |

## Confidence rules

| Confidence | UI value | Required interpretation |
|---|---:|---|
| Low | 1 | Lead or weak pattern; missing corroboration |
| Medium | 2 | Multiple signals or one strong T1/T2 signal, unresolved gaps remain |
| High | 3 | Multiple independent signals with at least one T1/T2 source and no blocking contradiction |

## Contradiction state matrix

| State | UI treatment | Required action |
|---|---|---|
| None | Quiet / no flag | No contradiction known; still show missing data |
| Minor | Warning line | Keep finding provisional |
| Blocking | Alert flag | Prevent high-confidence conclusion |
| Unresolved date/location conflict | Warning line with exact disputed field | Add to lead queue |

## Component inventory

| Component | Purpose | Required props |
|---|---|---|
| `TierBadge` | Evidence/source tier marker | `tier` |
| `ConfidenceMeter` | Low/medium/high evidence confidence | `value` |
| `AnomalyScore` | Numerical anomaly score and band | `score` |
| `ContradictionFlag` | Visible contradiction marker | `items` |
| `CommandBar` | Global command/query/filter/run state | `query`, `filters`, `runState`, `onSubmit` |
| `LeftRail` | Navigation and investigation control | `activeModule`, `activeInvestigation`, `sources`, `watchlist` |
| `Inspector` | Entity detail and source lineage | `selection`, `data`, `onSelect` |
| `Timeline` | Event tracks and date cursor | `events`, `cursor`, `onCursorChange`, `onSelect` |
| `FinanceIntelligence` | Contract/vendor/agency table | `data`, `selection`, `onSelect` |
| `SpatialIntelligence` | MapLibre map and layers | `sites`, `contracts`, `anomalies`, `layers`, `onSelect` |
| `AnomalyWorkbench` | Pattern-convergence review | `anomalies`, `selection`, `onSelect` |
| `InvestigationGraph` | Entity graph surface | `nodes`, `edges`, `onSelect` |
| `QueryLayer` | LLM orchestration UI | `queryAdapter`, `onSelect` |

## Module state requirements

| State | Command | Finance | Spatial | Anomaly | Graph | Query |
|---|---:|---:|---:|---:|---:|---:|
| Empty data | Required | Required | Required | Required | Required | Required |
| Loading | Required | Required | Required | Required | Required | Required |
| Partial source outage | Required | Required | Required | Required | Optional | Required |
| Selection active | Required | Required | Required | Required | Required | Required |
| Contradiction present | Required | Required | Required | Required | Optional | Required |
| Exportable evidence trail | Required | Required | Required | Required | Optional | Required |

## MapLibre specification

Leaflet behavior from `mod-2.jsx` is preserved conceptually but replaced by MapLibre.

| Map behavior | V1 MapLibre implementation |
|---|---|
| Site markers | GeoJSON source `sites` + circle/symbol layers or HTML markers |
| Contract concentration | Derived site totals shown as marker radius/opacity |
| Anomaly radius | GeoJSON source `anomalies` with score-dependent circle layer |
| Sensitive sites | GeoJSON source with explicit `sensitive: true` flag |
| Layer toggles | UI state controls MapLibre layer visibility |
| Selection sync | Map click calls global `setSelection({ kind, id })` |

## Query layer specification

The query layer is an orchestration surface, not a chatbot.

Every response must include:

1. Finding
2. Evidence references
3. Source-tier breakdown
4. Confidence
5. Contradictions
6. Missing data
7. Recommended next action

Real retrieval will later route to SQL, vector, geospatial, graph, and timeline tools. The starter app implements only a typed adapter stub.

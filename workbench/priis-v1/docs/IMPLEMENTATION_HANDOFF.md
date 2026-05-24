# PRIIS V1 Implementation Handoff

## What was produced

This package contains:

```text
priis-v1-execution/
  docs/
    VECTOR_LOCK.md
    DESIGN_SYSTEM_EXTRACTION.md
    IMPLEMENTATION_HANDOFF.md
  contracts/
    ontology.json
    evidence_tiers.json
    *.schema.json
    llm_answer_contract.md
  app/
    React + TypeScript + Vite + MapLibre scaffold
```

## Implementation state

| Item | State |
|---|---|
| React/TypeScript scaffold | Created |
| MapLibre module | Created |
| Typed mock fixtures | Created |
| Evidence-tier components | Created |
| Inspector | Created |
| Timeline | Created |
| Finance module | Created |
| Anomaly module | Created |
| Graph module | Created as non-library scaffold |
| Query layer | Created with typed adapter stub |
| Runtime build verification | Not run; dependency install is required first |

## Local run steps

From `priis-v1-execution/app`:

```bash
npm install
npm run dev
```

To check production compilation:

```bash
npm run build
npm run preview
```

## Hard requirements for the coding agent

1. Do not import the original Babel/CDN prototype files directly.
2. Do not use Leaflet.
3. Preserve the workbench geometry from the visual baseline.
4. Preserve evidence tiers T1/T2/T3/T4.
5. Keep anomaly analysis as pattern convergence only.
6. Treat `/contracts` as the source of truth.
7. Keep the Query Layer behind an adapter boundary until real retrieval is integrated.
8. Do not claim high confidence from T3/T4 evidence alone.

## First hardening patch after install

| Patch | Reason |
|---|---|
| Add ESLint + strict rules | Catch entity drift and unused state |
| Add schema validation with Zod | Runtime fixture validation |
| Add TanStack Table | Stronger finance table sorting/filtering |
| Add persisted state | Keep active investigation and timeline cursor |
| Add geospatial source/layer architecture | Replace marker-only MapLibre path with full GeoJSON layers |
| Add export stubs | Evidence brief, CSV, session log |

## Known limitations

- The app uses fixture data only.
- Map tiles depend on external raster tile availability.
- No real retrieval, vector DB, PostGIS, or LLM API is wired.
- The graph is a visual scaffold, not a graph database view.
- JSON schemas are initial V1 contracts and should be versioned.

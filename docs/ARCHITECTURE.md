# spiderweb-pr Architecture

`spiderweb-pr` is the spatial / operational producer in the PRII federation. It prepares retained GIS-linked records, operational review outputs, provenance, confidence metadata, and canonical export packages for validation and aggregation by [`thehub-pr`](https://github.com/jotaele44/thehub-pr).

> Boundary: FlightRadar24 screenshot ingestion, FR24 route extraction, and active airspace observation export belong to [`skywatcher-pr`](https://github.com/jotaele44/skywatcher-pr). Spiderweb retains legacy spatial bridge logic and spatial / operational export surfaces, but it is not the active FR24 owner.

## Status refresh

As of the latest boundary refresh, `spiderweb-pr` operates purely as the spatial / operational **Federation** producer: it validates retained records and materializes canonical export packages for `thehub-pr` to discover and aggregate. FlightRadar24 screenshot ingestion and the **RLSM** (resilient loader / state-machine) airspace pipeline have been migrated to `skywatcher-pr` and are no longer owned here. This document is refreshed whenever the federation role or the FR24 / RLSM boundary changes.

## Current module map

```text
spiderweb-pr/
│
├── pipeline/                    Retained operational/spatial analysis modules
│   ├── aircraft_intelligence.py  Operator/profile enrichment retained for review
│   ├── geo_anchors.py            Evidence-bounded homography helpers
│   ├── gis_intelligence.py       Puerto Rico infrastructure graph and GIS helpers
│   ├── mission_inference.py      Mission scoring and behavioral review helpers
│   └── operational_intelligence.py
│
├── integration/                  Validation and export adapters
│   ├── schema_validation.py      JSON Schema record validation
│   ├── pr_intel_adapter.py       Parquet / GeoJSON / integration_report export
│   ├── ilap_airspace_bridge.py   Retained ILAP bridge reference/export logic
│   └── aasb_airspace_bridge.py   Retained AASB edge-list bridge logic
│
├── federation/                   Producer-side Hub envelope writer
│   ├── envelope.py               Canonical envelope model
│   └── export_writer.py          Export writer for producer package materialization
│
├── scripts/                      Validation, export, and release commands
│   ├── validate_export.py        Producer export validation
│   └── federation_export.py      Hub-compatible canonical projection
│
├── schemas/                      JSON Schema files for retained export records
├── server/frontend/              The interface — Vite SPA, served by desktop/
├── dashboard/                    Generated branding derivatives only (no UI)
├── docs/                         Runbooks, data policy, boundary docs
├── gebco/                        Optional bathymetry / terrain package
├── earthgpt/                     Optional satellite anomaly-detection package
└── llm/                          Optional local RAG / PRUAP text-query package
```

## Data flow

```text
local records / retained spatial artifacts
        ↓
validation + review routing
        ↓
producer envelope / retained exports
        ↓
canonical projection: entities + sources + relationships
        ↓
thehub-pr validates, aggregates, and correlates across producers
```

Each canonical row carries an optional `evidence_state` declaration. It follows thehub-pr's candidate epistemic-state contract, vendored byte-identically at `schemas/federation_epistemic_state.v1.schema.json`. The local `federation_entity`, `federation_source` and `federation_relationship` schemas each accept it as one optional property.

Classification follows the record type, and only types with documented provenance are classified:

| Record type | Class | Location precision | Note |
|---|---|---|---|
| USGS metallic occurrence | CURATED | `OBSERVED_POINT` | Published occurrence points |
| Airport reference | CURATED | `REPRESENTATIVE_POINT` | |
| Structure sighting | CURATED | `INTERPRETED_POINT` | |
| PPP resolution | COMPUTED | `REPRESENTATIVE_POINT` | |

Location precision does not always come from the record type:

- A location taken from a LineString's first vertex is always declared `REPRESENTATIVE_POINT` / `FIRST_VERTEX`, whatever the record type.
- Undocumented types, such as screenshot-derived airspace records, are left undeclared, so thehub-pr fails closed for them.

Tests: `tests/test_federation_evidence_state.py`.

## Federation boundary

| Responsibility | Owner |
|---|---|
| Spatial / operational producer records | `spiderweb-pr` |
| FR24 ingestion and live airspace observations | `skywatcher-pr` |
| Producer discovery and manifest validation | `thehub-pr` |
| Cross-producer aggregation and correlation | `thehub-pr` |
| Downstream lead ranking / analytical consumption | consumer systems, not producers |

## Validation surfaces

| Surface | Command / path |
|---|---|
| Python tests | `python -m pytest tests/ -q --tb=short --ignore=tests/test_io.py --ignore=tests/test_terrain.py` |
| Schema validation | `make validate-schemas` |
| Export validation | `python scripts/validate_export.py --package exports/samples --mode test` |
| Canonical export | `python3 scripts/federation_export.py --mode test` |
| Federation manifest | `federation.json` |

## Optional resident subsystems

Spiderweb still contains optional packages that are not the active airspace producer role:

| Subsystem | Purpose |
|---|---|
| `gebco/` | Bathymetry / terrain derivatives |
| `earthgpt/` | Lightweight satellite anomaly-detection pipeline |
| `llm/` | Local RAG workflow over Puerto Rico UAP/social text data |

Keep these subsystems isolated behind their own extras and tests. Do not use them to reassign FR24 or active airspace ownership back to Spiderweb.

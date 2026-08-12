# Road to 100 — normalized federation score

**Audit date:** 2026-08-04  
**Scoring model:** code completeness 20%; main-branch availability 15%; CI enforcement 15%; data materialization 15%; operator verification 15%; GUI completeness 10%; federation readiness 10%.

## Current normalized score: 70.90 / 100

| Dimension | Weight | Score | Weighted |
|---|---:|---:|---:|
| Code completeness | 20 | 82 | 16.40 |
| Main-branch availability | 15 | 85 | 12.75 |
| CI enforcement | 15 | 68 | 10.20 |
| Data materialization | 15 | 55 | 8.25 |
| Operator verification | 15 | 60 | 9.00 |
| GUI completeness | 10 | 68 | 6.80 |
| Federation readiness | 10 | 75 | 7.50 |

The former ~85% figure did not consistently discount the explicit offline V2 backlog or the large GUI legacy baseline.

## State reconciliation

- Core analytical, GIS, ingestion, federation and tested frontend capabilities are on `main`.
- PR #243 is merged; standalone packaging still needs current-main certification.
- PR #237 is an older unmergeable GUI-parity candidate with a 1,016-signal legacy baseline; it requires current-main reconciliation or supersession.
- Content-bound checkpoint/resume and tracked-file data-policy lint are on `main`
  (`63b8c4b`); typed errors, map previews, GeoPackage, geo-anchors v2 and
  licensing/SPDX remain implementation gaps.
- Real infrastructure/hydrology cross-references and corpus growth remain data or operator constrained.
- Recent frontend auditing found inert filters, cursor, investigation selection, query adapter and graph surfaces that cannot be counted as complete controls.

## Priority exit sequence

1. Add typed error taxonomy before expanding live ingestion.
2. Add GeoPackage and map-preview outputs.
3. Implement geo-anchors v2 and then adjudicate dependent pixel-CV work.
4. Reconcile GUI parity against current main and reduce or explicitly classify legacy gaps.
5. Certify standalone packaging for the merged isolated-clone runtime.

## Machine-readable authority

See `docs/unfinished_implementation_ledger.v1.json`. Fixed proxy values and inert GUI controls remain open until replaced, removed or explicitly accepted as bounded diagnostics.

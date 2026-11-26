# D09, D10, D13 — Mosaic matrix, split-view workbench and API contract

Status: **SPECIFICATION**. None of this is built. Component and route names
below are proposals; file paths marked "new" do not exist.

The workbench is specified for this repository's frontend
(`server/frontend`), by the owner's decision of 2026-11-26. That needs the
existing "diagnostic-only" rule to be amended; see
[`ADR_WORKBENCH_SURFACE.md`](ADR_WORKBENCH_SURFACE.md).

## D10 — Split-view comparison workbench

### State model

Three kinds of state, held separately:

| State | Owner | Changes when |
|---|---|---|
| Analytical extent (geometry, segment, how it was selected) | `GeographicContext` | The user selects an area. Never when the map moves. |
| Viewport (centre, zoom, bearing, pitch, cursor) | `SynchronizationController` | The user pans or zooms either panel |
| Panel selection (family, source, dataset, version, date, asset, style, opacity, overlays) | Each `ComparisonPanel` | The user changes that panel only |

This separation is the main acceptance requirement: panning must not change
what is being compared.

### Components

| Component | New or reused |
|---|---|
| `GeographicResearchWorkbench` | New module, registered beside the existing six in `server/frontend/src/App.tsx` |
| `GeographicContext` | New. First shared context in the application. |
| `GeographicSelectionToolbar` | Reuses the polygon, buffer and identify tools of `SpatialToolsPanel.tsx` and the search box of `GisViewerControls.tsx` |
| `ComparisonPanel` | New. **One component, mounted twice** with a panel identifier. No panel-specific code. |
| Selectors inside the panel | New. Each list comes from the API for the current extent and the choices above it. |
| `GeographicViewport` | Reuses `SpatialRuntime` and the layer hooks of `SpatialIntelligence.tsx` |
| `SynchronizationController` | New. Replaces the one-way follow in `CompareOverlay.tsx`. |
| `EvidenceMetadata`, `AcquisitionStatus` | New. Pattern from `AccessPointDetail.tsx`. |
| `ComparisonResultsTable`, `LogicalMosaicMatrix` | New. TanStack Table, as in `FinanceIntelligence.tsx`. |
| `AnnotationLayer` | New. Blocked on the annotation contract (D14). |

### Selection methods

| Method | Feasible now |
|---|---|
| Coordinate, bounding box, drawn rectangle, drawn polygon | Yes |
| Segment identifier | Yes |
| Native tile footprint | Yes, from the ledger |
| Municipality, barrio | Only where the boundary data has been built locally (D02) |
| Watershed | No data |
| Registered feature, saved extent | Yes, from existing registries and local storage |

A point resolves to the L0 segment that contains it, shown explicitly.

### Selector cascade

Extent, then dataset family, source, dataset, version, observation date,
intersecting files, acquisition and integrity status. Every list is filtered
by exact intersection with the analytical extent. Registered files that are
not acquired are listed, not hidden.

For a file that is not acquired the panel shows, in place of a map: filename,
source, footprint outline, dates, version, share of the extent covered, files
required, files held, files missing, bytes to acquire, restrictions, blocking
dependencies, and an acquire control. **An empty map with no explanation is a
defect.**

### Synchronisation

Shared by default: extent, centre, zoom, bearing, cursor, scale. Independent
always: everything in the panel selection. Turning synchronisation off frees
the viewports and leaves the analytical extent as it was.

Prerequisite: the two conflicting writers of the map URL fragment (D11,
defect 1) are reduced to one before this is built.

### Display modes

Two panels side by side first. Swipe is available by adapting
`CompareOverlay.tsx`. Vertical split, four panels, full-screen single panel,
metadata only, temporal sequence and vector comparison come after the
two-panel workflow is accepted.

### Layout acceptance

| Width | Layout |
|---|---|
| 1280 px and wider | Two panels side by side; results below |
| 768 to 1279 px | Two panels side by side with metadata collapsed; results in a drawer |
| below 768 px | One panel at a time with an A/B switch; swipe mode offered; selection and results in drawers |

Checked with the existing browser matrix
(`server/frontend/tests/gui-runtime-matrix.mjs`): no horizontal overflow, no
console error, heading present, at six widths in three browsers.

### Acceptance list

1. Both panels are instances of one component.
2. Every option in every selector comes from an API response.
3. Panning does not change the analytical extent.
4. Changing one panel's selection changes nothing in the other.
5. With synchronisation on, both viewports show the same extent after any
   move, in both directions.
6. A file that is not acquired is explained, with its acquire control.
7. Closing the browser during an acquisition does not stop it; reopening
   shows its progress from the ledger.
8. A source-bound annotation shown in the other panel is drawn as a reference
   outline and is never stored as a second observation.

## D09 — Logical mosaic matrix

A table of segments against dataset families, with a review column.

- **It is derived.** Each cell is computed from ledger, gap and review
  records. There is no table to maintain.
- Cell states: `PASS`, `PARTIAL`, `OPEN`, `GAP`, `BLOCKED`, `N/A`. A cell is
  `PASS` only when every required asset is acquired and verified and every
  eligible comparison has a record. With today's data every pilot cell for
  elevation is `OPEN`.
- Expanding a cell shows: segment, family, dataset, version, period, each
  asset with its acquisition receipt, comparison records, review disposition,
  open gaps.
- Selecting a cell opens the workbench with that segment and family set.
- Rows are produced only for segments that have records.

## D13 — Frontend and backend API

New router beside `server/backend/gis_api.py`, prefix `/geo-sar`. Read routes
serve the registry files; write routes go through the job ledger.

| Route | Purpose |
|---|---|
| `GET /geo-sar/context?bbox=` or `?segment=` | Resolve a selection to an analytical extent and its segments |
| `GET /geo-sar/options?extent=&family=&source=&dataset=&version=` | The next selector list, filtered by intersection |
| `GET /geo-sar/assets?extent=&dataset_version=` | Asset records with footprints, acquisition and integrity status |
| `GET /geo-sar/requirements?segment=&dataset_version=` | Required, held and missing files with sizes |
| `POST /geo-sar/acquisitions` | Submit an acquisition job. Body carries an idempotency key. Returns the job identifier. |
| `GET /geo-sar/jobs/{id}` | Job and step states |
| `GET /geo-sar/jobs/{id}/events?after=` | Events after a cursor; also offered as server-sent events |
| `POST /geo-sar/eligibility` | Classify a pair of selections |
| `POST /geo-sar/comparisons` | Submit a comparison job for an eligible pair |
| `GET, POST /geo-sar/observations` | Observations bound to asset, panel and comparison |
| `GET /geo-sar/gaps`, `GET /geo-sar/mosaic` | Gap records and the derived matrix |

Constraints:

- The API process does not run jobs. It writes to the ledger and reads from
  it. A separate worker does the work.
- A write route without a grant returns a refusal; the server holds no
  standing grant.
- The existing API has no authentication because it binds to the local
  machine only. That assumption is recorded in D15 and must hold for these
  routes too, or authentication is added first.
- Events use the existing `sse-starlette` dependency. The cursor is the ledger
  event number, so a client that reconnects misses nothing.

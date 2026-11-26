# D07, D08 — Comparison method registry and gap registry contract

Status: **CANDIDATE**. No method is qualified for segment review. One
comparison of the two pilot versions already exists in the elevation lane; it
is site-based and is not bound to segments.

## D07 — Comparison method registry

File: `registry/geo_sar/comparison_methods.json`. Schema:
`schemas/geo_sar_comparison_methods.schema.json`.

A method is listed only if its implementation exists in this repository; a
test checks that each named file and symbol is there. Listing is not
qualification. Every entry is `UNVERIFIED`.

| Method | Implementation | Default |
|---|---|---|
| Elevation surfaces against lidar, and the 2024 lidar against the 2018 lidar | `scripts/run_dem_vs_3dep_lidar.py` | Automated |
| Changed-pixel fraction between two images | `imagery/compare.py` | Manual review only |
| Site timeline pixel difference | `spiderweb/site_timeline/metrics.py` | Manual review only |
| Identifier set comparison | `tools/gis_evidence/core.py` | Automated |
| Denominator comparison | `spiderweb/spatial/archipelago.py` | Automated |
| Snapshot replay comparison | `scripts/source_adapters/pr_hydrography/control_plane.py` | Automated |

No implementation exists for: adjacent tile continuity, vector geometry,
feature presence and absence, optical against terrain, imagery quality
artifacts, hydrological consistency, documentary reconciliation, cross-domain
relationships.

### What already exists for the pilot pair

The elevation lane ran the first method on 2026-11-24 at eight sites across
the island (`docs/sources/dem_lidar_comparison.md`, receipt in
`evidence/dem_sources/lidar_comparison_2026-11-24/`). One site is the pilot's
tile position x81y203. There, on a lattice of 1/9 arc-second, the 2024 survey
minus the 2018 survey has a median of -0.07 m over 8,458,491 cells; across all
eight sites the median is -0.14 m. That document gives two explanations it
could not separate. This is real, prior evidence and is the starting point
for the pilot comparison. It is one of four zone 19N tile positions in the
pilot, it is not computed per segment, and the method is not yet registered
as qualified.

An island-wide change screen of the same two surveys exists on the unmerged
branch `claude/ilap-lidar-change-screen`. It is not on main and is not
listed.

### Eligibility

A pair of evidence selections is classified as one of: eligible for automated
comparison, manual review only, analytically incompatible, blocked.

| Check | Existing code | State |
|---|---|---|
| Geographic overlap | Exact intersection (D04) | Available |
| Temporal compatibility | `classify_epoch` in `spiderweb/site_timeline/epoch.py` | Imagery only |
| Coordinate transformation | Reprojection used in the pilot | Available |
| Datum compatibility | Explicit datum chain in `scripts/run_dem_vs_3dep_lidar.py` | Elevation only |
| Native resolution | `compare_pair` in `spiderweb/site_timeline/timeline.py` | Imagery only |
| Positional uncertainty | — | Absent |
| Semantic compatibility | — | Absent |
| Source independence | — | Absent |
| Evidence integrity | Ledger receipts | Available once acquired |
| Licensing and authorisation | Ledger grant | Licence status is `UNVERIFIED` for every asset |
| Registered method version | Registry | Available |

Rule: a check that cannot be evaluated makes the pair **blocked**, not
eligible. Two datasets that are not comparable are recorded as incompatible;
no number is computed for them.

For the pilot pair (2018 against 2024, same provider, same resolution, same
tile scheme in zone 19N): overlap, transformation and temporal order pass.
Both are stated to be on the same vertical datum; the label itself is
contested (stated NAVD88, behaves as PRVD02; open registry conflict
`3dep_vertical_datum_label`), which does not prevent differencing the two.
Integrity cannot be evaluated because no file is held, and licence is
unverified. The pair is therefore **blocked** today, on acquisition and
licence only.

## D08 — Gap registry

Taxonomy: `registry/geo_sar/gap_taxonomy.json`. Instances:
`registry/geo_sar/pilot_001_gaps.json`. Schemas:
`schemas/geo_sar_gap_taxonomy.schema.json`,
`schemas/geo_sar_gap_registry.schema.json`.

The sixteen classes G01 to G16 are taken from the directive. **They are a
Spiderweb-local candidate.** No Federation gap taxonomy was found in thehub-pr
at the head read; the nearest are a blocker registry with a severity and a
free-text scope, and per-lane state lists in this repository
(`ResidualState` in `spiderweb/subsurface/residuals.py`, `CoverageState` in
`gebco/marine_evidence.py`). Adoption is thehub-pr's decision.

Every gap record has: a stable identifier, a class, a state, a geographic
scope, the denominator it counts against, the responsible repository, the
evidence files that support it, what would resolve it, what is still needed,
and a history that is only added to.

Rules:

- A gap describes missing or conflicting evidence. It is never evidence that
  something is absent on the ground.
- Evidence paths must exist; a test checks this.
- New evidence reopens only the segments and comparisons whose assets it
  touches. The ledger makes this computable: each segment lists its assets per
  version.

### Coverage denominators

Kept apart. They are never averaged into one percentage.

| Dimension | Pilot numerator / denominator | State |
|---|---|---|
| Discovery | 28 / 28 catalogue items for one dataset family | Closed for that family only; other families `UNVERIFIED` |
| Geographic coverage | Footprints cover 42 / 42 segments in both versions; valid-data coverage unknown | `UNVERIFIED` |
| Acquisition | 0 / 28 | Open |
| Integrity | 0 / 0 acquired | Not applicable yet |
| Comparison | 0 segment comparisons / unknown eligible. One site-level comparison exists and is unbound. | `UNVERIFIED` |
| Review | 0 / 42 | Open |
| Gap resolution | 0 / 6 | Open |
| Qualification | See the dossier | — |

### Pilot gaps

| Gap | Class | Statement |
|---|---|---|
| 001 | G04 | No pilot file is held (28 files, 6.6 GB). Three were fetched by an earlier run; only their hashes remain. |
| 002 | G05 | No provider checksum; 16 of 28 object tags are multipart tags, not content hashes |
| 003 | G03 | Valid-data extent is unknown; footprints are raster extents |
| 004 | G02 | The 2018 survey is one collection in several project lots; what each lot fills in a tile is unknown |
| 005 | G08 | The versions were compared at one pilot tile position, not per segment |
| 006 | G02 | Zone 20N files are not file-for-file alternates of zone 19N files |

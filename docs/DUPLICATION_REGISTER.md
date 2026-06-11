# Duplication Register

Tracks files that exist in more than one federation repo. Each entry declares a
canonical owner and either a removal condition (for genuine, temporary duplication) or a
resolution (when the apparent "duplicate" is in fact a per-repo adaptation that is kept by
decision). A genuine duplicate is tolerable **only** while listed here with `temporary`
status.

| File | Also in | Canonical owner | Status | Resolution / removal condition |
|------|---------|-----------------|--------|--------------------------------|
| `integration/ilap_airspace_bridge.py` | `../skywatcher-pr/ilap_airspace_bridge.py` | **split — each repo owns its own copy** | resolved (per-repo adaptation) | Kept by decision; see "ILAP/AASB airspace bridges" below. Not a shared-logic duplicate. |
| `integration/aasb_airspace_bridge.py` | `../skywatcher-pr/aasb_airspace_bridge.py` | **split — each repo owns its own copy** | resolved (per-repo adaptation) | Same as above. |

## ILAP/AASB airspace bridges — ownership split (resolved 2026-06-11)

These two files share a **common ancestor** (the pre-split FR24/airspace subsystem) but have
**diverged into two repo-specific adaptations** that are no longer interchangeable. A `diff`
confirms they are not byte-identical and, more importantly, depend on **different, non-shared**
modules in each repo — so there is no clean shared module and no safe cross-repo import.

**spiderweb-pr owns its copies** (`integration/ilap_airspace_bridge.py`,
`integration/aasb_airspace_bridge.py`). They are the **spatial/operational producer flavor**:

- Imports spiderweb-local modules that **do not exist in skywatcher-pr**:
  `integration.mbil` (MBIL urbanization banding), `integration.kml_export` (native KML sibling),
  and `provenance_utils` (`geojson_feature_meta`, `reproducibility_metadata`,
  `feature_collection_summary`).
- Emits spiderweb's federation-producer surface: per-feature `_meta` provenance blocks,
  explicit `crs`/`epsg` stamps, run-level `reproducibility` metadata, `bbox` summaries, MBIL
  class/corridor flags, and operator-facing corridor/POI banding labels.
- Are **live in spiderweb's own export path** — they are not vestigial:
  - `run_all.py` → `_run_export_spiderweb` (phase 2 / `--export-spiderweb`)
  - `release_check.py` → `export_spiderweb` (a **gating** release stage that writes
    `spiderweb_ingest_manifest.json`)

**skywatcher-pr owns its copies** (`../skywatcher-pr/{ilap,aasb}_airspace_bridge.py`). They are
the **airspace/EarthGPT flavor**: they import `gis_intelligence` (PR infrastructure proximity)
and GEBCO bathymetry for `_infra_align_score` / `_hydro_utility_score`, and expose
`poi_to_earthgpt_context` — none of which exist in spiderweb's producer copies.

### Why both exist (and why we did NOT de-duplicate)
- The airspace **ingestion** subsystem (the `fr24/` screenshot pipeline + RLSM suite) migrated
  to skywatcher-pr in 2026-06 (spiderweb PRs #110/#111). skywatcher-pr carries the bridges as
  the **airspace** producer; spiderweb-pr retains its own copies as part of its **spatial/ops
  producer export**, which is explicitly within spiderweb's owned surface (`integration/` +
  federation producer, per `docs/REPO_BOUNDARY.md`).
- The two copies have diverged onto **disjoint local dependency sets**. Extracting a shared
  module would require either duplicating those deps into a common location or introducing a
  **cross-repo import** — the latter is forbidden by `docs/REPO_BOUNDARY.md` ("any future
  federation/consumer code … must be a thin client … not a second copy"). Neither is a clean,
  low-risk win, so the bridges stay independent and each repo owns its own copy.
- Repointing spiderweb's phase-2 / `release_check` export at skywatcher's output would be
  **breaking** (it would remove a gating producer stage and its manifest) and is rejected.

### Maintenance rule
The files are **no longer a shared duplicate** — they are sibling adaptations. Make
spiderweb-specific producer changes in `integration/`; make airspace/EarthGPT changes in
skywatcher-pr. Do not attempt to keep the two byte-identical or to import one from the other.

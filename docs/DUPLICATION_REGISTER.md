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
| `imagery/` (package) | `../skywatcher-pr/imagery/` | **split — each repo owns its own copy** | temporary (registered 2026-11-07; previously unlisted) | Removal condition: the hub acquisition runtime ships (hub ADR 0006). See "Satellite imagery package and the site timeline" below. |
| `spiderweb/site_timeline/epoch.py`, `spiderweb/site_timeline/score.py` | `../skywatcher-pr/satim_temporal_change.py` | **skywatcher-pr owns the SATIM spec** | temporary (spec-derived re-implementation) | Re-implemented from the spec because cross-repo imports are forbidden. Removal condition: the hub or a shared contract carries the epoch and score logic. See below. |

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

### Update 2026-07-29 — the rest of the airspace surface is gone, the bridges stay
The FR24/ADS-B ingestion, the `/events/{flight_id}/track` endpoint, the aircraft
columns on `/events`, the RLSM ontology/schema set and the whole `dashboard/`
viewer (which still shipped an **FR24 Review Queue** tab) were retired to
`docs/legacy/` — see `docs/REPO_BOUNDARY.md`. That removed the last cross-repo
*duplication of function*; what remains below is the deliberate per-repo
*adaptation* of the two bridges.

The bridges are explicitly **not** part of that retirement: they are still live in
`run_all.py::_run_export_spiderweb` and the gating `release_check.py::export_spiderweb`
stage, so removing them would drop a release gate. The reasoning below stands
unchanged.

### Maintenance rule
The files are **no longer a shared duplicate** — they are sibling adaptations. Make
spiderweb-specific producer changes in `integration/`; make airspace/EarthGPT changes in
skywatcher-pr. Do not attempt to keep the two byte-identical or to import one from the other.

## Satellite imagery package and the site timeline (registered 2026-11-07)

**`imagery/`.** The package docstring says it stays identical across repositories. A
comparison with skywatcher-pr (read-only, at its commit 4def79d) shows that is not
exactly true. `__init__.py`, `cache.py`, `config.py`, `manifest.py` and the whole
`providers/` directory are byte-identical. `compare.py`, `geo.py`, `models.py` and
`server.py` differ only in typing and formatting style (`Optional[...]` versus
`... | None`, import placement, line wrapping), with the same behaviour. `sink.py`
differs by design: here it hands the manifest to `readiness/satellite_ingest.py`,
while skywatcher-pr has no satellite-ingest pipeline and carries a self-contained
validator and writer. The duplication is tolerated only while listed, and only until
the hub acquisition runtime ships: hub ADR 0006 moves satellite-provider access,
credentials and the imagery cache into `thehub-pr`. Nothing in `spiderweb/site_timeline/`
edits `imagery/`.

**SATIM epoch model and temporal score.** `spiderweb/site_timeline/epoch.py` and
`spiderweb/site_timeline/score.py` re-implement skywatcher-pr's mixed-epoch classes and
`score_temporal_change` from the SATIM mixed-epoch validation spec (a document in
skywatcher-pr's docs directory) and its `satim_temporal_change.py` module. This
repository forbids cross-repo imports, so a copy is unavoidable until the logic lives in
a shared contract. The copy
is kept honest by `tests/test_site_timeline_score.py`, which pins 16 cases generated by
running the original function read-only at skywatcher-pr commit 4def79d, including every
class and each threshold boundary. That proves the port matches the original; it does
not show either one is calibrated. Every threshold is an uncalibrated heuristic, and the
near-epoch window (`NEAR_EPOCH_DAYS`) and the 5 m resolution rule are this repository's
own additions, not part of the SATIM spec. The table holds each case's inputs, so when
skywatcher-pr changes the original, run the new original over those inputs and compare
the results with `expected`; any difference means the port needs the same change.

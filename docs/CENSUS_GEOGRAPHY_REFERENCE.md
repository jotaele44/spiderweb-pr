# Census Geography Reference for PRIIS

Source: U.S. Census Bureau, *Geography Collections* — a catalog of every nested
rollup their data APIs accept (e.g., "All Block Groups within Census Tract").
The full spreadsheet has 291 rows; this doc and its companion CSV capture only
the subset that's actually useful for Puerto Rico in the PRIIS workbench.

## The filtered catalog

[`data/census/geography_collections_pr.csv`](../data/census/geography_collections_pr.csv)
holds **65 rollups** across **13 summary levels** that apply to PR-relevant
work. Each row is one child→parent relationship the Census API will accept.

| Column | Meaning |
|---|---|
| `child_sl` | Census summary-level code (e.g. `050`, `140`) |
| `child_sl_label` | Human label, PR-flavoured where relevant |
| `child_geoid_template` | The GEOID prefix template Census uses (e.g. `0500000`) |
| `parent_sl` | Summary-level the child is requested *within* |
| `description` | Census's own one-line description of the rollup |
| `wired_in_repo` | `true` if PR data for this SL is already ingested |
| `notes` | Caveats — e.g. layers too large to ingest yet |

Regenerate from the source `.xlsx` with:

```bash
python3 server/ingestion/build_geography_catalog.py \
    --src ~/Downloads/list-of-available-collections-of-geographies.xlsx
```

The `.xlsx` itself is **not** committed.

## Summary-level legend (workbench-relevant subset)

| SL | What it is | PR meaning |
|---|---|---|
| 040 | State | Puerto Rico as a whole (STATEFP=72) |
| 050 | County | Municipio (78 of them) |
| 060 | County Subdivision | Barrio-pueblo / Barrio (~900) |
| 140 | Census Tract | ~945 tracts |
| 150 | Block Group | Finest level ACS publishes; ~2,400-3,200 |
| 160 | Place | Incorporated places + CDPs (~250) |
| 310 | CBSA | Metro/Micro Statistical Areas (e.g. San Juan-Bayamón-Caguas) |
| 330 | CSA | Combined Statistical Area |
| 795 | PUMA | Public Use Microdata Area (ACS PUMS) |
| 860 | ZCTA | ZIP Code Tabulation Area (PR ZIPs 006xx / 007xx / 009xx) |
| 950 | School District (Elementary) | DEPR-relevant |
| 960 | School District (Secondary) | DEPR-relevant |
| 970 | School District (Unified) | DEPR-relevant |

## What's wired today

`server/ingestion/ingest_tiger_pr.py` ingests these TIGER/Line layers and
writes one GeoJSON per layer to `data/`. Counts are from the 2025 vintage:

| SL | Layer name | 2025 features | Default-on in Spatial module? |
|---|---|---|---|
| 040 | `state` | 1 | yes (single-feature framing layer) |
| 050 | `municipios` | 78 | yes |
| 060 | `barrios` | 939 | no |
| 140 | `tracts` | 981 | no |
| 150 | `block_groups` | 2,555 | no |
| 160 | `places` | 292 | no |
| 860 | `zctas` | 132 (PR only; USVI 008xx excluded) | no |

Sites in the SQLite DB are spatially joined to:
- `municipio_geoid` (TIGER county GEOID, STATEFP=72)
- `tract_geoid` (TIGER tract GEOID)
- `zcta_geoid` (TIGER ZCTA5 GEOID — may be NULL for sites in uninhabited
  reserves or military land; see "ZCTA coverage gaps" below)

…via `_sjoin_with_fallback` in the ingester.

### ZCTA coverage gaps

Unlike municipios/tracts (which fully tessellate PR's land area), ZCTAs are
derived from USPS ZIP delivery patterns and have gaps over uninhabited
parcels — wildlife reserves, decommissioned military bases, large water
bodies. Sites landing in these gaps will have `zcta_geoid IS NULL` even
after the within→intersects fallback. Known examples in the seed data:
- *Vieques Western Reserve* (S-010)
- *Roosevelt Roads — Ceiba* (S-001, former naval base)

This is expected behavior, not a sjoin bug. The unmatched list is recorded
in `data/tiger/{year}/sites_unmatched.json` for audit.

## Gaps (in the CSV with `wired_in_repo=false`)

| SL | Layer | Why not yet |
|---|---|---|
| 310 | CBSA | No consumer yet — easy add when one materializes |
| 330 | CSA | Same as above |
| 795 | PUMA | Only useful once PUMS microdata is in scope |
| 950 / 960 / 970 | School districts | Useful when finance touches DEPR spend |

## Things that are NOT in the CSV (and why)

- **SL 100 Blocks** — ~1M features for PR; only worth ingesting when a real
  consumer needs block-level granularity.
- **SL 871 "ZCTA5 within State"** — a state-nested rollup query over the same
  data SL 860 covers nationally. Once 860 is wired and filtered to PR, 871
  adds nothing operationally.
- **PR Planning Regions** — *not* a Census-tabulated geography. The 8 PR
  planning regions are an admin layer maintained by Junta de Planificación
  and would be sourced separately (their own ingester, mirroring this one's
  `LAYER_SPECS` discipline). Tracked as a B2 follow-on.
- **SL 250 AIANNH, SL 230 Alaska Native, NECTA, water bodies, state-leg
  districts as a "within" parent** — non-applicable to PR.

## Adding a new SL

The mechanical pattern in [`server/ingestion/ingest_tiger_pr.py`](../server/ingestion/ingest_tiger_pr.py):

1. Add an entry to `LAYER_SPECS` with `archive_template`, expected count band,
   `simplify_tolerance_initial`, `max_bytes`, `on_oversize`.
2. If the TIGER archive is nationwide (no STATEFP filter), add a per-layer
   filter check in `_read_layer` (see the ZCTA prefix filter for the pattern).
3. If sites should be enriched with the new GEOID, add a column via
   `migrations.py::ensure_sites_geoid_columns` and a `_sjoin_with_fallback`
   call alongside the existing municipio / tract / zcta joins.
4. Extend the `/geo/{layer}.geojson` allowlist in `server/backend/main.py`.
5. Add the layer to `POLYGON_LAYERS` in
   `workbench/priis-v1/app/src/modules/SpatialIntelligence.tsx`.
6. Flip the `wired_in_repo` flag in the catalog generator's `WIRED_TODAY` set
   and regenerate the CSV.

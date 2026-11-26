# D17 — Pilot qualification suite

Pilot `GEOSAR-PILOT-001`. Tests: `tests/test_geo_sar_pilot.py` (30 cases) and
`tests/test_geo_sar_job_durability.py` (12 cases). All run offline.

## Pilot extent

| | |
|---|---|
| Bounding box | 66.05° W to 65.95° W, 18.30° N to 18.40° N |
| Area | 117.0 km² |
| Segments | 42 Grid V2 L0 cells (2 km) with area inside the extent |
| Dataset family | Elevation, 1 m, United States Geological Survey 3DEP |
| Versions | 2018 survey (20 files, 3.32 GB); 2024 survey (8 files, 3.28 GB) |
| Catalogue denominator | Closed: provider reported 28, returned 28 |
| Why this extent | It is the one area for which this repository already held registered files in two versions |

## The one live run

| | |
|---|---|
| Date | 2026-11-26 |
| Grant | Metadata discovery, at most 150 requests, given by the repository owner in session |
| Requests made | 29 (1 catalogue, 28 file headers of 64 KiB) |
| Hosts | `tnmaccess.nationalmap.gov`, `prd-tnm.s3.amazonaws.com` |
| Bytes received | 1,938,598 |
| Files downloaded | 0 |
| Receipt | `evidence/geo_sar/pilot_001/discovery/discovery_receipt.json` |
| Replay | `python scripts/geo_sar_pilot_discovery.py replay` reproduces the ledger byte for byte |

## What the run established (COMPUTED from kept bytes)

1. All 28 files are 10,012 by 10,012 pixels at 1 m. Sizes in the file store
   equal sizes in the catalogue for all 28.
2. Twenty footprints that the older registry held as unresolved are now read
   from the files. The eight it already held agree with what was read.
3. Catalogue bounding boxes agree with file footprints to within 0.00006° for
   the 2024 files and exactly for the 2018 files.
4. Every segment has footprint coverage of 1.0 in both versions. This is
   raster extent, not valid data.
5. **The 2018 survey is published in four lots (D, E, G, H).** One tile
   position holds two or three files with identical footprints and different
   contents; sizes range from 57 MB to 310 MB, which suggests each lot fills
   only part of its tile. Which part is unknown without the files. (Gap 004.)
6. **The zone 19N and zone 20N tilings of the 2024 survey are offset.** Each
   zone 19N footprint is split between zone 20N footprints; the largest single
   share is between 40 % and 59 %. The two listed sets share 70.6 % of their
   area. The older registry's per-file "alternate" class does not hold file to
   file. (Gap 006.)
7. A 2018 lot D file and the 2024 zone 19N file at the same tile position have
   the same footprint. Version-to-version comparison can therefore be done
   tile to tile in zone 19N without resampling the grid.
8. Adjacent tiles in one zone share a 12 m strip (0.12 % of a tile).

## What the repository already held (reconciled, not re-derived)

The elevation lane compared the two surveys at eight sites on 2026-11-24. One
site is this pilot's tile position x81y203.

9. Three pilot files were fetched then: the 2024 file and 2018 lots D and H at
   x81y203. Their SHA-256 values are recorded in
   `evidence/dem_sources/lidar_comparison_2026-11-24/tiles_provenance.json`.
   The bytes were not kept. The ledger carries each hash as
   `prior_acquisition`; its own integrity fields stay empty.
10. For all three, the size then equals the size now, and the object tag then
    equals the object tag read today. The files have not changed in between.
11. Sixteen of the 28 object tags are multipart tags. Those are not a hash of
    the content, so the tag can signal a change but cannot verify a file.
12. The 2024 survey minus the 2018 survey at this tile position, on a lattice
    of 1/9 arc-second: median -0.07 m, 2.0 % of cells beyond 1 m
    (`docs/sources/dem_lidar_comparison.md`).
13. Survey windows are 2018-04-17 to 2019-04-19 and 2023-12-27 to 2025-03-20.
    Both are stated to be on NAVD88; the same document shows the heights
    behave as PRVD02. The conflict is open in the elevation catalogue and is
    carried on every asset.
14. The elevation catalogue counts 477 files of this dataset family over
    Puerto Rico. The pilot's 28 are 5.9 % of that.

## Fixtures

| Fixture the directive asks for | Case | Test |
|---|---|---|
| Two dataset versions | 2018 and 2024 over all 42 segments | `test_two_dataset_versions_cover_every_pilot_segment` |
| Exact original filenames, native footprints | 28 assets, footprints from file headers | `test_catalogue_denominator_is_closed_and_every_footprint_is_from_the_file` |
| Existing local evidence reconciled | Older registry compared file by file; three earlier acquisition receipts matched by address, size and object tag | `test_prior_acquisition_receipts_are_reconciled_not_adopted`, `test_dataset_identity_and_survey_window_match_the_elevation_catalogue` |
| Missing acquisition requirements | All 28 not acquired; nothing claimed | `test_no_acquisition_or_integrity_result_is_claimed` |
| Comparison eligibility | Same tile position across versions | `test_the_same_tile_position_matches_across_versions` |
| Known discrepancy | Zone 19N against zone 20N | `test_no_zone_20_file_substitutes_for_a_zone_19_file` |
| Known missing data | Valid-data extent unknown; gaps 001 to 005 | `test_pilot_gaps_use_the_taxonomy_and_cite_existing_evidence` |
| False-positive rejection | Near-identical names, different ground; unrelated names, same ground; one position, several files | Three `test_*filenames*` and `test_one_tile_position_*` cases |
| Duplicate acquisition | 42 segments need 28 files; one effect per content hash | `test_shared_assets_are_counted_once_across_segments`, durability test 05 |
| Interrupted retrieval | Worker killed mid-copy | Durability tests 03, 04, 08 |
| Recovery and authorisation | Grant enforced before and after a kill | Durability test 06 |
| Discovery controls | No default grant; hosts, scheme, port, credentials refused; budget enforced; changed bytes refused; a finished run not overwritten | Seven cases |

Synthetic data is used only in the durability tests, for the file being
copied. Every pilot fixture is real provider metadata.

## Acceptance for the pilot (frozen)

The pilot is accepted when, for these 42 segments and these two versions:

1. Every required file is acquired once, with a computed SHA-256 and a
   receipt, under a product grant that bounds files and bytes. The three
   files with an earlier hash must reproduce it.
2. Valid-data extent is computed per file and segment coverage is restated
   from it.
3. The lot question (gap 004) and the alternate question (gap 006) are
   resolved in the ledger.
4. The vertical datum conflict is either resolved or carried explicitly on
   every comparison record.
5. The existing elevation comparison is qualified and registered for
   version-to-version use per segment.
6. Each segment has an eligibility result and either a comparison record or a
   manual-review record.
7. Discrepancies that remain are gap records; each segment has a review
   disposition.
8. Steps 1 to 7 are run through the job ledger, and the directive's
   end-to-end scenario (§23) is demonstrated in the workbench against these
   records, not against mock data.

None of the eight is met today. Items 1 and 2 need a product download grant
for about 6.6 GB, or 3.3 GB if only the zone 19N files of both surveys are
taken (14 files; they cover all 42 segments on their own).

# D03–D06 — Asset ledger, segmentation, discovery and acquisition contracts

Status: **CANDIDATE**. D03 and D04 are exercised by the pilot. D05 is
exercised for one provider. D06 is exercised only against local files.

## D03 — Native asset ledger

Schema: `schemas/geo_sar_asset_ledger.schema.json`. Instance:
`registry/geo_sar/pilot_001_asset_ledger.json`.

One record per provider file. The record keeps three things apart:

| Block | Holds | Who says so |
|---|---|---|
| `native_identity` | Original filename, provider identifiers, source address, hash of the catalogue response that listed it | Provider |
| `source_provided` | Bounding box, size and dates as the catalogue states them | Provider |
| `verified` | Coordinate system, footprint, pixel size and object size read from the file's own first bytes, with the hash of those bytes | This repository |

A value moves from `source_provided` to `verified` only when it has been read
from bytes this repository holds. Where the two disagree the record carries a
`discrepancies` entry; neither value is overwritten.

**Identity.** An asset is identified by provider, provider tile identifier and
catalogue snapshot, never by filename alone. Once acquired, the content hash
joins the identity. This matters in practice: the pilot contains files whose
names differ by one character and cover different ground, and files with
unrelated names that cover the same ground.

Cases the record shape must carry, and where each stands:

| Case | State |
|---|---|
| Source address changes | Carried: address is an attribute, not the identity |
| File revised under the same name | Carried once acquired (content hash); not exercised |
| Several files at one tile position | Exercised: the 2018 survey has lots D, E, G, H; pilot gap 004 |
| Archives and multi-part datasets | Not specified yet |
| Provider replicas | Not specified yet |
| Different tiling schemes for one collection | Exercised: zone 19N and zone 20N tilings; pilot gap 006 |

Two further blocks record what other lanes already established, without
adopting it as this ledger's own result:

| Block | Holds |
|---|---|
| `prior_registration` | Whether the older registry's row for the file agrees |
| `prior_acquisition` | A hash computed by an earlier run whose bytes are no longer held, with whether size and object tag still match |

Survey window and catalogue identity come from the elevation catalogue
(`data_sources/elevation/dem_platform_catalog.yml`). The vertical datum is
recorded as contested, with the catalogue's open conflict named.

Still empty for every pilot asset, by design: this ledger's own checksum,
horizontal datum, valid-data extent, licence. They are `UNVERIFIED`, not
assumed.

## D04 — Geographic segmentation

Three structures stay separate and are related many-to-many:

1. **Native footprints.** Whatever the provider tiled. Never altered.
2. **Review segments.** Cells of Grid V2 (`spiderweb/geographic_grid_v2.py`):
   squares in EPSG:6566 at 2 km (L0), 1 km (L1), 500 m (L2) and 250 m (L3),
   exactly nested. No new grid is introduced.
3. **Reporting boundaries.** Municipalities, barrios, watersheds. Not
   available in this repository today (D02).

Mapping of the directive's scales:

| Directive | Here |
|---|---|
| L00 complete extent | Grid V2 extent |
| L01 regional | Not defined; use reporting boundaries when available |
| L02 primary review segment | Grid V2 L0 (2 km), 11,457 cells |
| L03 detailed subsegment | Grid V2 L1 and L2 |
| L04 high-resolution window | Grid V2 L3 |
| L05 native geometry | Asset footprint |

Rules:

- A footprint is bound to segments by exact polygon intersection in the grid
  coordinate system (`bind_exact_polygon` in
  `spiderweb/grid_v2_geometry_bindings.py`), after reprojecting the footprint
  with its edges densified. Bounding boxes in latitude and longitude are not
  used for binding: for these tiles they overstate shared area.
- Segments are materialised only where work exists. The pilot materialises 42
  of 11,457.
- A segment identifier is a Grid V2 cell identifier. The directive's
  `PR-S0001` form is not adopted, to avoid a second identity for one cell.

**Open.** Grid V2 is a release candidate (`2.0.0-rc1`). If it changes before
release, segment identifiers change with it. Whether the grid covers the
maritime research extent was not checked.

## D05 — Source discovery

Conforms to thehub-pr's acquisition rules (five identities: raw, query
receipt, snapshot, normalised, canonical; a remote feature is a candidate, not
an identity; a count that does not close is not a pass).

Required of every discovery run:

1. Nothing is requested without an explicit, bounded grant naming who gave it.
2. Only named hosts, only https, redirects refused, a byte ceiling per
   response.
3. Every response is kept byte for byte with its hash before anything is
   derived from it.
4. Everything derived is rebuilt from the kept bytes; an offline replay must
   reproduce it exactly and must refuse if a byte changed.
5. The provider's own total is compared with what was returned. Unequal means
   the denominator is `OPEN`.
6. A finished run is never overwritten.

Implemented for USGS 1 m elevation in `scripts/geo_sar_pilot_discovery.py`.
The pattern comes from `spiderweb/access_points/discovery.py`. Other
mechanisms the directive lists (STAC, ArcGIS REST, OGC services, object
storage listings) have adapters in other lanes (D01, B09) that do not yet meet
rules 3 and 4 uniformly.

## D06 — Acquisition requirement

A requirement is: for one segment, one dataset version, the set of assets
whose footprints have area in the segment. The pilot ledger holds this for
every segment and both versions.

Sequence, with what exists:

| Step | State |
|---|---|
| Discover, snapshot, register asset, filename, footprint | Done for the pilot |
| Compute segment intersections | Done for the pilot |
| Evaluate applicability | Not built |
| Reconcile verified local artifacts | Done against earlier receipts for 3 of 28 files (hashes only; bytes not held). The job ledger reuses a held artifact by content hash. |
| Identify missing evidence | Done for the pilot: all 28 |
| Evaluate authorisation | Ledger enforces level, file count and byte ceiling before a step runs |
| Evaluate resources | Not built |
| Queue unique acquisition | Ledger: one job per idempotency key, one effect per content hash |
| Retrieve original bytes | Local files only; no provider retrieval handler |
| Verify integrity | Size and SHA-256 against expected, failure is final and the partial file is removed |
| Validate geographic content | Not built |
| Persist artifact, bind segments, receipt | Atomic rename and effect receipt; segment binding not wired |

Rules for the retrieval handler when it is built:

- Reuse the controls of `DownloadSession` in
  `spiderweb/access_points/products.py`: host allow-list, https only, no
  redirects, a declared length, a byte ceiling, hash while writing.
- A partial artifact is never presented as a complete one. A range read is
  recorded as a range read.
- Priority goes to the asset that unlocks the most segments. In the pilot one
  file serves up to 25 segments.
- Nothing is downloaded because it is listed.

**Sizes.** The pilot needs 6,601,968,792 bytes in total: 3,322,776,699 for the
2018 survey (20 files) and 3,279,192,093 for the 2024 survey (8 files). Each
survey is published in two zones; the zone 19N files alone (10 and 4 files,
3,310,696,836 bytes together) cover every pilot segment in both versions.

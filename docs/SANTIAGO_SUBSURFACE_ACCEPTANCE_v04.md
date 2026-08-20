# Santiago Triangle — Subsurface Public-Source Acceptance v0.4

## Run identity

- Workflow: `Subsurface Santiago Acceptance`
- Workflow run: `32407248171`
- Branch head: `1d71289ca7261294d63a4c35f1eab97636091b90`
- Artifact: `santiago-subsurface-v04-32407248171`
- Artifact digest: `sha256:0e9f37f34e100fa6e3021e7e1e83062178685d9be0e591b0cd690f9a67259f63`
- Frozen AOI canonical SHA256: `4b4109c31681f8d510b8dba9ca0a9018d165ab88ecc05a0625c8a98ce3aca3c8`
- AOI source-byte SHA256: `c8bf698be741bcd439228901cfd3f9304b86a73c8a968c5f7c9f2343d36de34f`
- Source denominator SHA256: `d347986c50f0d70feeff006a043d2ce889a0fdf933620a22ae41bbba78bb62d9`

## Public-source gate

The v0.4 live execution produced:

- required source manifestations: **58**
- terminal manifestations: **47**
- `PASS`: **45**
- `ZERO`: **2**
- explicit `OPEN` denominator rows: **4 required + 1 non-required active-military exclusion**
- source execution `FAIL`: **7**, all USACE former-site reference manifestations returning HTTP 403 from the GitHub Actions runner
- `records_request_eligible`: **false**
- public-source exhaustion: **OPEN**

No HTTP failure or unindexed source is interpreted as a zero-result finding.

### Family certification

| Family | Terminal / required | State |
|---|---:|---|
| GEOLOGY_KARST_CAVES | 4 / 4 | PASS |
| AQUIFERS_WELLS_SPRINGS | 5 / 5 | PASS |
| FAULTS_STRUCTURES | 3 / 3 | PASS |
| MINES_QUARRIES_SHAFTS | 8 / 9 | OPEN |
| MILITARY_HARDENED_SUBSURFACE | 4 / 12 | OPEN |
| INDUSTRIAL_REMEDIATION | 5 / 5 | PASS |
| UTILITIES_UNDERGROUND | 9 / 10 | OPEN |
| HISTORICAL_CORROBORATION | 9 / 10 | OPEN |

## Remaining required residue

The records-request gate remains closed because the following required rows are nonterminal:

1. `HISTORIC_WORKINGS_NONMAPPED_RESIDUAL`
2. `FORMER_MILITARY_SUBSURFACE_REPORT_CORPUS_RESIDUAL`
3. `NON_AAA_PRIVATE_BURIED_NETWORK_RESIDUAL`
4. `HISTORICAL_AERIAL_COLLECTION_INDEX_RESIDUAL`
5. `USACE_FUDS_PR_INVENTORY` — HTTP 403
6. `USACE_CULEBRA_SUPPLEMENTAL_ASR_2005` — HTTP 403
7. `USACE_FUDS_CULEBRA_REPORT_INDEX` — HTTP 403
8. `USACE_FUDS_DESECHEO_REPORT_INDEX` — HTTP 403
9. `USACE_FUDS_FORT_BROOKE_REPORT_INDEX` — HTTP 403
10. `USACE_FUDS_MONITO_REPORT_INDEX` — HTTP 403
11. `USACE_FORT_BROOKE_ADMIN_RECORD_2025` — HTTP 403

`ACTIVE_MILITARY_HARDENED_ASSET_CLASS` remains deliberately non-required and is excluded from precise current-asset enumeration.

## AOI evidence ledger

The live AOI run emitted **15,932** evidence rows from bbox discovery followed by exact AOI spatial adjudication:

- `FULLY_WITHIN`: 7,713
- `PARTIAL`: 298
- `OUTSIDE`: 7,909
- `UNRESOLVED`: 12

`OUTSIDE` records are retained because the adapter first retrieves the AOI envelope candidate set and the evidence layer then applies exact polygon predicates. This is intentional candidate-set preservation, not a false positive.

### Historic mine/opening branch

- consolidated USGS mine-symbol points: 21 bbox candidates; **9 fully within**
- the 9 fully-within point symbols are classified by USGS as **Quarry**, not shaft/adit openings
- explicit opening filter `ftr_type IN ('Adit','Air Shaft','Mine Shaft')`: **ZERO**, with successful count-query closure
- consolidated mine polygons: 9 bbox candidates; **1 fully within + 2 partial**, classified as quarry context
- hosted MRDS: 62 bbox candidates; **33 fully within**

The explicit-opening `ZERO` applies only to mapped USGS historical-topographic opening symbols in the query envelope. It does not establish that no undocumented or unmapped historic working exists; `HISTORIC_WORKINGS_NONMAPPED_RESIDUAL` therefore remains OPEN.

### Geology / karst / cave branch

- PRPB cave layer: 6 bbox candidates; **1 fully within** (`Cueva Naranjo`)
- PRPB sinkhole layer: one broad polygon intersects the AOI partially; it is not interpreted as a count of discrete sinkholes
- geology and aquifer polygons retain `PARTIAL`, `FULLY_WITHIN`, `OUTSIDE`, and `UNRESOLVED` states independently rather than forcing a nearest/majority assignment

### Wells / springs / groundwater

The AOI contains substantial groundwater-source evidence across overlapping authoritative manifestations:

- PRPB JCA potable-well features fully within: **22**
- PRPB AAA well features fully within: **25**
- USGS monitoring-location features fully within: **393**
- PRPB spring features fully within: **13 rows**

These counts are source-row counts, not a deduplicated unique-well/spring denominator. Cross-source identity resolution remains separate.

### Utilities

Feature-segment counts intersecting or fully contained by the AOI include:

- AAA water-main segments: **4,014** relevant (`FULLY_WITHIN|PARTIAL`)
- AAA gravity-sewer segments: **3,125** relevant
- AAA force-main/pumped-sewer segments: **30** relevant
- PRPB broadband-service-by-road features: **154** relevant

These are segment/feature counts, not unique systems, and broadband service-by-road geometry is candidate context rather than proof of buried conduit.

### Historical map coverage

- topoView returned 152 AOI-envelope map-footprint candidates
- **108** intersect the exact Santiago Triangle (`107 PARTIAL`, `1 FULLY_WITHIN`)

This closes machine-queryable map-edition discovery for the registered topoView manifestation, but not the complete historical aerial/frame/scene payload denominator. The historical collection/index residual therefore remains OPEN.

### Military context boundary

Former-site/FUDS and land-tenure manifestations are retained only as discovery/support context. This acceptance report intentionally does not enumerate precise current hardened/underground military asset locations, and former-site evidence cannot promote to current protected-asset identity.

## Artifact hashes

| Artifact | SHA256 |
|---|---|
| `source_control.json` | `aa33c39f54ac7bf7fe080791b26ad37d8a7e4f017ebdf47efe5d2c0acf7f62a9` |
| `public_exhaustion.json` | `c9c6152b5183fa9863d5a4f434bd1afe6b43a47b41e66e8eec4d45d86ecd1fd2` |
| `evidence.csv` | `2b8cf3e41a994555191638da89e0173c0ced7fd1c075319a48ee8815f69645b9` |
| `evidence.geojson` | `fe5f7e89cebd51d6deffde9e83facde6525a1d7fd6e87113d5d98bc259adac66` |
| `evidence.kmz` | `5e15b00146bf624a37ca3b5701df4be6d6e39784dbfa2ec39b387ddce3fe5473` |

The table hashes above correspond to the successful acceptance artifact used for substantive AOI analysis. A later utility-status-only correction increased source terminality from 46 to 47 without changing the four hard public-source residual classes.

## Certification

`PUBLIC_SOURCE_EXHAUSTION = OPEN`

`RECORDS_REQUEST_ELIGIBLE = FALSE`

`FOIA = FORBIDDEN`

The next permissible work is continued public-source closure or adjudication of genuinely blocked public manifestations. A records-request vector must not activate until the bounded exhaustion certificate is `PASS`.

# Santiago Triangle — Subsurface Public-Source Acceptance v0.5

## Run identity

- Workflow: `Subsurface Santiago Acceptance`
- Workflow run: `32417060798`
- Executed branch head: `ee84b9f6b76bc7f80742c9cef81d69866df473c5`
- Artifact: `santiago-subsurface-v05-32417060798`
- Artifact ID: `9424369174`
- Artifact size: `85,465,165` bytes
- Artifact digest: `sha256:9e81a613feb943d799a000df4abfc95302b7e0781e1718ffd0439a65b8536aec`
- Frozen AOI canonical SHA256: `4b4109c31681f8d510b8dba9ca0a9018d165ab88ecc05a0625c8a98ce3aca3c8`
- Source denominator SHA256: `aeba833c8719f7b2860070f4a160336f0c4d728f89332ef9c678a16abc904934`

## Public-source execution gate

The live v0.5 denominator produced:

- required source manifestations: **67**
- terminal required manifestations: **51**
- source states across all rows: **48 PASS | 3 ZERO | 12 FAIL | 5 OPEN**
- `PUBLIC_SOURCE_EXHAUSTION = OPEN`
- `RECORDS_REQUEST_ELIGIBLE = FALSE`
- `FOIA = FORBIDDEN`

A failed transport, authentication/index limitation, or documented public-data gap is never interpreted as a zero real-world result.

### Family certification

| Family | Terminal / required | State |
|---|---:|---|
| GEOLOGY_KARST_CAVES | 4 / 4 | PASS |
| AQUIFERS_WELLS_SPRINGS | 5 / 5 | PASS |
| FAULTS_STRUCTURES | 3 / 3 | PASS |
| MINES_QUARRIES_SHAFTS | 10 / 11 | OPEN |
| MILITARY_HARDENED_SUBSURFACE | 4 / 15 | OPEN |
| INDUSTRIAL_REMEDIATION | 5 / 5 | PASS |
| UTILITIES_UNDERGROUND | 10 / 11 | OPEN |
| HISTORICAL_CORROBORATION | 10 / 13 | OPEN |

## Bounded residual adjudication

Residual state is separate from source-execution state. `FINAL_PUBLIC_GAP` means that the bounded authoritative public search has established that a complete public denominator is not available; it is **not** negative evidence and it does not count as `PASS|ZERO` for records-request eligibility.

| Required residue | v0.5 residual state | Effect |
|---|---|---|
| `HISTORIC_WORKINGS_NONMAPPED_RESIDUAL` | `FINAL_PUBLIC_GAP` | USGS explicitly states that no comprehensive national abandoned-mine-feature inventory currently exists; mapped USMIN/HTMC features cannot cover every destroyed, covered, undocumented, or never-mapped working. |
| `FORMER_MILITARY_SUBSURFACE_REPORT_CORPUS_RESIDUAL` | `OPEN` | Additional official FUDS project/document surfaces remain publicly discoverable; precise current protected-asset enumeration remains excluded. |
| `NON_AAA_PRIVATE_BURIED_NETWORK_RESIDUAL` | `FINAL_PUBLIC_GAP` | Public products expose selected infrastructure/service/technology while no authoritative island-wide public line dataset was found that distinguishes all buried non-AAA/private electric, telecom, and sanitary geometry. |
| `HISTORICAL_AERIAL_COLLECTION_INDEX_RESIDUAL` | `OPEN` | EarthExplorer/M2M remains an executable public inventory surface; the Santiago frame/scene metadata denominator has not yet been materialized. |

All four residual assessments have `negative_evidence_permitted = false`.

## v0.5 public manifestations

New authoritative source manifestations added over v0.4 include:

- USGS abandoned-mine-inventory status page — `PASS`, byte-frozen
- USGS consolidated mine-features release page — `PASS`, byte-frozen
- PRPB `Cable Take off` layer 23 — `ZERO`, complete count-query closure; zero applies only to the registered AOI manifestation and does not prove absence of buried telecom
- USGS Aerial Photo Single Frames data dictionary — `PASS`, byte-frozen
- EarthExplorer inventory/search surface — `PASS`, byte-frozen
- topoView inventory/download surface — `PASS`, byte-frozen
- USACE FUDS portal home/resources and Ramey project index — transport-blocked from the Actions runner and preserved as `FAIL`, not zero

### Remaining transport-blocked official references

Twelve public references failed live retrieval from the Actions runner:

- nine USACE/Jacksonville/FUDS manifestations returned HTTP 403, including the Puerto Rico inventory, Culebra/Desecheo/Fort Brooke/Monito/Ramey report indexes, Culebra supplemental ASR, and Fort Brooke administrative-record index
- two FUDS Portal surfaces failed TLS handshake from the runner
- two NARA historical-aerial pages returned HTTP 503

The official webpages are independently discoverable on the public web, so these states are `transport/runtime blocked`, not `source absent`.

## Canonical asset denominator

Deduplication is restricted to the requested physical target classes. Non-well USGS monitoring sites, utility segments, map footprints, and other unrelated evidence rows are excluded from the canonical-asset denominator.

### Input target rows

**441** exact-AOI target source rows:

- USGS monitoring locations typed `Well | Spring | Multiple wells`: **336**
- hosted MRDS: **33**
- PRPB AAA wells: **25**
- PRPB JCA potable wells: **22**
- PRPB springs: **13**
- USGS consolidated mine/quarry point symbols: **9**
- PRPB quarries: **3**

### Canonical output

**423 canonical assets**:

- `GROUNDWATER_POINT`: **378**
- `MINE_QUARRY_FEATURE`: **45**

Relationship/component structure:

- `1:1`: **422 canonical components**
- `N:1`: **1 canonical component**
- singleton/source-only components: **406**
- two-member canonical components: **16**
- three-member canonical components: **1**

Confidence:

- `SOURCE_ONLY`: **406**
- `SUPPORTING`: **10**
- `DIRECT`: **7**

Identity-edge ledger: **23 edges**

- `AUTHORITATIVE_ID`: **8**
- `DUPLICATE_SOURCE_ROW`: **1**
- `GEOMETRY_NAME`: **10**
- `PROXIMITY_CANDIDATE`: **4**
- binding edges: **19**
- non-binding candidate edges: **4**

Hard identity examples use PRPB spring `SITE_ID == USGS monitoring_location_number`. JCA↔AAA well merging requires tight geometry plus strong normalized-name agreement; shared water-system IDs or nearest-neighbor proximity alone do not bind identity. Quarry/mineral proximity is candidate-only unless strong independent name binding is also present.

The 441→423 reduction is **18 source rows (4.08%)**. No candidate-only edge is used to collapse assets.

## Public-evidence relevance model v1

The model partitions the AOI into coarse 0.02-degree cells clipped to the Santiago polygon and uses exact geometry intersection only. It is a **public-evidence relevance model**, not a subsurface-connectivity model.

### Hard prohibitions

- military-family records are excluded from scoring
- nearest/buffer/proximity evidence cannot establish connectivity
- score cannot establish identity, hidden use, access, intent, or current protected infrastructure
- dense utility segmentation is logarithmically capped so infrastructure line density cannot dominate geological/hydrogeological evidence

### Live zone distribution

**146 zones**:

- `VERY_LOW`: **75**
- `LOW`: **63**
- `MODERATE`: **8**
- `HIGH`: **0**

Evidence-tier distribution:

- `CANDIDATE`: **138**
- `SUPPORTING`: **7**
- `DIRECT`: **1**

Score range: **0.124–6.697**; mean approximately **1.639**.

The single `DIRECT` zone is direct only because a mapped cave feature intersects that cell. It does not establish connectivity to any other feature. No explicit USGS historical `Adit | Air Shaft | Mine Shaft` symbol was returned in the Santiago AOI, so no relevance zone receives direct-opening evidence from that manifestation.

## v0.4 findings preserved

The v0.5 execution preserves the principal v0.4 Santiago findings:

- total evidence rows: **15,932**
- `FULLY_WITHIN`: **7,713**
- `PARTIAL`: **298**
- `OUTSIDE` bbox candidates after exact polygon adjudication: **7,909**
- `UNRESOLVED`: **12**
- one PRPB cave feature is fully within (`Cueva Naranjo`)
- explicit USGS mapped-opening filter remains a complete `ZERO`
- mine/quarry manifestations are quarry context rather than mapped adit/shaft evidence
- substantial well/spring and public water/sewer evidence is present, with cross-source identity kept separate from raw source-row counts
- topoView provides machine-queryable historical map-edition coverage but does not close aerial frame/scene enumeration

## Artifact SHA256

| Artifact | SHA256 |
|---|---|
| `source_control.json` | `b699d5d295a3a1c0583c88a546fe6d6a8271dd79d6d946695079965d000771cc` |
| `public_exhaustion.json` | `95841d914b7292ffcef3ff630a5f3e0586390346acb79ec091a974390249a0c2` |
| `public_residual_assessment.json` | `e9c888b7f8e3221b1a4f77a3d23284fffd19af9731c21464058e683fc177ec65` |
| `evidence.csv` | `79a25294c42c1818355d571798296d726394ee08261d655a7c0ac2ac2b583b7e` |
| `evidence.geojson` | `249ce548ec97a6d04c5e443796160975a7c3e78732a09ccf33c7ba2981aa6fca` |
| `evidence.kml` | `301a1eb973d505eedbfa7507879fc166cf5c0599efe33bc6f60f57fd40940b87` |
| `evidence.kmz` | `f99eb5471cf3cdc85712ad27f8533944a8499df9279850b50e9b2efd30e3beff` |
| `derived/canonical_assets.json` | `2a645313717bcb6bacd047fae75b10b7c24943e5c9c150e149be73e3d756c4bb` |
| `derived/identity_edges.json` | `1eae208590e11c1911577e3ea7a62c8446dc8bc06a12d32be11a94f4c559239d` |
| `derived/relevance_zones.geojson` | `6f70e7e86c58b299d5671cdc6ee37eb0d38d5c4431370ad64488f7e22cef51e2` |

## CI / certification

For executed code head `ee84b9f6b76bc7f80742c9cef81d69866df473c5`, the following completed successfully:

- full Python tests on 3.11 and 3.12
- lint/type allowlist
- data-policy gate
- frontend tests/build
- GEBCO tests
- install matrix
- release check
- Secret scan
- Semgrep
- CodeQL
- pip-audit
- PRII smoke gate
- federation template drift
- live Santiago v0.5 acceptance

## Binding final state

`PUBLIC_SOURCE_EXECUTION = PROVISIONAL_PASS_WITH_BLOCKED_REFERENCES`

`BOUNDED_PUBLIC_SOURCE_EXHAUSTION = OPEN`

`PUBLIC_RESIDUALS = 2 FINAL_PUBLIC_GAP | 2 OPEN`

`RECORDS_REQUEST_ELIGIBLE = FALSE`

`FOIA = FORBIDDEN`

Next public work is limited to (1) completing former-site property/report enumeration through official FUDS public systems without precise current protected-asset mapping, and (2) materializing the Santiago EarthExplorer/M2M aerial frame/scene denominator plus the two transport-blocked NARA series. The two `FINAL_PUBLIC_GAP` rows remain non-negative evidence and do not need to be repeatedly rediscovered unless authoritative public-source conditions change.

# TIGER/Line 2026 Puerto Rico — acquisition and federation routing

Status: SOURCE DISCOVERY PASS; SOURCE BYTES/CONTENT UNVERIFIED; PROMOTION WITHHELD.

Source: https://www2.census.gov/geo/tiger/TIGER2026/

The two tracked CSVs were enumerated from all 49 TIGER2026 thematic directories on 2026-11-12 (Puerto Rico local time). They record 796 Puerto Rico-specific ZIP URLs (780 municipality archives across 10 families, 16 statewide archives) and 17 national candidate ZIP URLs. They do not attest to archive contents, feature counts, geometry quality, or national-layer membership. Preserve the existing TIGER2025 manifest and its frozen hashes.

## Source ownership and downstream consumers

- Spiderweb-PR is the sole owner of original TIGER ZIP acquisition, SHA-256 evidence, canonical GEOIDs/geometry/CRS, normalizations, and certified geospatial exports.
- AguaYLuz-PR consumes Spiderweb-certified AREAWATER and LINEARWATER hydrography, roads for utility access, and administrative joins, with exact-version Spiderweb receipts. No duplicate TIGER source downloads.
- Skywatcher-PR consumes certified administrative boundaries, road and point-landmark reference layers via Spiderweb. TIGER does not provide elevation/horizon itself.
- OVNIS-PR consumes certified municipio, barrio, subbarrio and spatial join geometries, not unverified geocodes.
- Centinelas-PR consumes certified geographies as contextual reference, preserving source lineage.
- MoneySweep-PR consumes certified GEOID crosswalks and polygon references for award place-of-performance normalization; financial evidence stays in MoneySweep.
- Mucaro-AI consumes approved geometry test fixtures and exact-version evaluation metadata, not mutable source URLs.
- TheHub-PR owns cross-repository receipts, source version pins, integration checks and LOCKSTEP. Do not duplicate Spiderweb acquisition controls.

## Acquisition sequence and gates

1. Freeze directory manifests and verify 796 URLs with HEAD or GET.
2. Download into immutable cache; record source byte lengths, SHA-256, HTTP status and UTC timestamp.
3. Inspect 17 national ZIP candidates and explicitly accept/reject Puerto Rico features by actual geometry or STATEFP=72; candidates are not currently verified as relevant.
4. Validate internal shapefile schemas, geometries, coordinate systems and 78 municipality FIPS membership. Never overwrite vintage 2025 outputs.
5. Run existing server/ingestion/ingest_tiger_pr.py --year 2026 for its five supported layers only after confirming nationwide COUNTY coverage. Other source families require separately tested adapters.
6. Bind source hashes to derived output hashes and metadata; validate feature counts, GEOID keys, coverage and downstream consumer contracts.
7. Exact-head CI, required security/reviews, merge-head replay, then TheHub pin reconciliation and LOCKSTEP.

No automatic ingestion or certification is asserted by adding a source directory manifest.

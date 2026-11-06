# Postal Contract Route Intelligence — V1 (non-publishing tranche)

## Status and authority
- Implementation state: local/branch candidate, not island-wide dataset certification.
- Source bytes acquired: **none by this tranche**.
- Authoritative USPS route IDs: **none validated**.
- Live USPS licensing, coverage denominator, and contract identity: **OPEN**.
- Spatial route geometry: **none produced**.
- Publication, Martin registry mutation, and federation promotion: **BLOCKED**.
- Postal designation parsing is a discovery tool; it is not USPS validation.
- Airspace/screenshot ingestion stays in Skywatcher; cross-producer correlation stays in TheHub.

## Pipeline
1. Inventory authoritative USPS RR/HC documentation, AIS/ZIP+4/Carrier Route
   product availability for Puerto Rico, post-office IDs, and contract records.
2. For each permitted acquisition, retain original bytes, URL, UTC timestamp,
   license/access class, length, SHA256, schema, and pagination denominator.
3. Keep RAW, NORMALIZED, CANONICAL and REJECTED/QUARANTINED distinct.
4. Parse discovery observations with `postal_routes.parse_designation`.
5. Bind only with stable USPS IDs and independent authorized evidence.
6. Preserve ambiguous candidates and contradictions; do not infer route lines
   from ZIP/ZCTA geometry, screenshot markers or nearest post offices.
7. On geodata, preserve CRS/Z/M and classify null, outside, touch, partial,
   fully-within, unresolved; compare topology and attribute deltas.
8. Publish only approved aggregate public layers after privacy, licensing,
   exact-head regression, independent review, and Martin authorization.

## Initial adversarial fixture
`Rural Route HC 1 5191` from a third-party map is deliberately classified
`UNRESOLVED`; `HC 1 BOX 5191` is only a normalization candidate, not proof
that the box exists or has a particular location.

## Scope and next gates
- P0: exact-head dependency and baseline snapshot; previous code unchanged.
- P1: lawful source acquisition and Puerto Rico product-coverage verification.
- P2: schema, typed source manifest, and independent denominator tests.
- P3: postal identity and temporal reconciliation with contradiction ledger.
- P4: spatial geometry only when independently evidenced.
- P5: privacy-reviewed API, UI and controlled tile publication.
- P6: source and merged-head replay, independent approval, federation contract.

## Failure policy
A failed gate quarantines candidate outputs and preserves the last valid version.
Never assign CERTIFIED on the basis of local parser tests or synthetic fixtures.

# Spiderweb Public Residual Closure v0.4

## Scope

v0.4 advances the bounded public-source denominator without declaring Puerto Rico-wide completeness. Records-request consideration remains forbidden unless `public_exhaustion.py` returns `PASS` for the selected scope.

## Mine / shaft / adit class

The current USGS consolidated mine-feature service is represented by separate point (17) and polygon (18) manifestations. The unfiltered point/polygon layers are supporting evidence only. A second point manifestation applies the authoritative `ftr_type` filter `Adit`, `Air Shaft`, and `Mine Shaft`; only this filtered manifestation is eligible for DIRECT historical-opening evidence. Direct evidence here means the historical map explicitly depicts that opening class, not that the opening is presently accessible, extant, safe, or publicly accessible.

The current hosted MRDS layer is also bound as a queryable supporting manifestation. MRDS status and development fields are preserved and are not treated as current-operation truth.

## Former military class

Only former/decommissioned property and report-corpus sources are enumerated. Culebra, Desecheo, Fort Brooke, and Monito project/report indexes plus the Fort Brooke administrative-record index are bound as public reference manifestations. Current protected hardened/underground military assets are not precisely enumerated and remain excluded from precise-asset completeness claims.

## Utilities

PRPB broadband service-by-road geometry is bound as discovery-only because route/service geometry is not buried-conduit geometry. The Puerto Rico Broadband Program Smart Island download portal is separately preserved as a public reference manifestation. AAA water/sewer layers and LUMA underground-distribution standards remain separate earlier manifestations. The non-AAA/private buried-network residual remains OPEN.

## Historical maps/aerials

USGS topoView's AOI-queryable map-footprint overlay is now a machine manifestation. It closes map-edition discovery only after count/paging arithmetic; actual map payload files remain separate. EROS aerial frames, NARA series, DRNA/UPR imagery, USDA/NRCS and NOAA/NAIP remain collection/payload manifestations that must be byte-frozen or scene-enumerated when executable.

## Reference byte freezing

`reference_adapter.py` provides a terminal execution path for exact HTTPS reference pages/downloads. A successful reference receipt freezes raw bytes, retrieval UTC, byte count, and SHA-256. This terminal state certifies only the registered manifestation, not the completeness of a larger collection or real-world asset universe.

## Gate

The following required residues still block records-request eligibility:

- `HISTORIC_WORKINGS_NONMAPPED_RESIDUAL`
- `FORMER_MILITARY_SUBSURFACE_REPORT_CORPUS_RESIDUAL`
- `NON_AAA_PRIVATE_BURIED_NETWORK_RESIDUAL`
- `HISTORICAL_AERIAL_COLLECTION_INDEX_RESIDUAL`

Any other required source that remains NOT_RUN, OPEN, failed, or otherwise non-terminal also blocks the gate.

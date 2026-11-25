# Choppers.zip spatial reference pilot — 2026-10-12

Status: **AUDIT_ONLY / NONCANONICAL**. Reuse the existing Spiderweb source of truth; this is a frozen **subset** for deterministic tests, not a replacement aviation-airport registry.

## Published review fixture
`exports/reference/choppers_airport_points_audit_v1.geojson` contains nine Point geometry records copied without coordinate correction from `exports/real/observations.jsonl` (Git blob `5dfb03703331bd76eca68eb175eb97bc88aefc08` on the inspected `main` snapshot). Data lineage retains source observation IDs, ICAO codes, source registry ID and the recorded observation timestamp.

Validation scope:
- Exactly 9 features with unique source observation identifiers and unique ICAO strings.
- EPSG:4326, GeoJSON coordinate ordering longitude then latitude.
- All coordinates finite and within legal latitude/longitude ranges; source geometries are **points** only.
- No fabricated polygon, runway, vertical extent, buffer geometry, geospatial validity period, or mission semantics.

## Bounded use
The Skywatcher `Choppers.zip` audit reconstructed 816 indexed flight legs and tested 1,632 start/endpoints. A 3.0-km great-circle radius around all nine points generated 1,009 **unreviewed, computed, candidate** associations. Keep all candidates; do not force one closest airport, infer takeoff/landing, or classify operation.

The crosswalk to `skywatcher-pr/data/reference/pr_airports.jsonl` found 7 shared non-null ICAO codes among the nine Spiderweb points. Spiderweb-only by exact ICAO: TJVQ and TJCP; the Skywatcher registry includes 19 records, including records with null ICAO, so nulls must not be treated as an identity code. Shared ICAO does not prove two geographic manifestations are geometrically equivalent. At TJRV the two point placements differ by approximately 1.7 km, requiring authoritative adjudication.

## Integration contract
No bespoke direct Spiderweb–Skywatcher connector and no aviation ingestion in Spiderweb. This fixture is an audit input to an eventual versioned geography export through the already accepted federation-spatial schema and Hub admission rules. Follow `docs/ADR_SKYWATCHER_SPIDERWEB_INTEGRATION.md`.

## Required before certification
Resolve coordinate disagreements, test exact/source topologies, validate the full layer's source scope/manifest, freeze source bytes and any transformations, pass Spiderweb's spatial-contract gates, and run an actual Hub consumer validation. A passing local proximity calculation alone cannot certify a release.

# Federation Spatial Architecture v1

Status: PROVISIONAL / NON-CERTIFYING

## Purpose
Define the bounded GIS responsibility model for aguayluz-pr, moneysweep-pr, skywatcher-pr, spiderweb-pr, and TheHub without allowing repository-authored governance text to self-elevate into trusted policy.

## Invariants
1. Source manifestation is not canonical identity.
2. Name equality, normalized-name equality, count equality, proximity, same category, or source absence never prove identity.
3. Geometry overlap is not identity.
4. Preserve RAW, NORMALIZED, and CANONICAL values separately.
5. Preserve source CRS, geometry type, Z/M dimensions, and record any lossy transformation.
6. Discovery operations (search, bbox, fuzzy matching, nearest-neighbor, regex, buffer) remain candidate generation unless independently exhaustive/authoritative.
7. Spatial outcomes are FULLY_WITHIN | PARTIAL | TOUCH_ONLY | OUTSIDE | NULL_EMPTY | UNRESOLVED.
8. Identity cardinalities allowed: 1:1 | 1:N | N:1 | N:N | 0:1 | UNRESOLVED.
9. Tied top evidence remains REVIEW/UNRESOLVED.
10. Hard evidence overrides heuristics.
11. Every cross-repo join must assert source count, retained count, excluded count, join cardinality, no unintended multiplication, and arithmetic closure.
12. Certification requires frozen inputs, explicit inclusion/exclusion, passed positive/negative regression gates, zero material unresolved residue inside the claim, and frozen hashes.

## Repository roles
### spiderweb-pr — spatial substrate owner
Owns domain-neutral geometry services: geometry validation/canonicalization, CRS transforms, topology, spatial predicates, canonical boundary/coastline services, tile publication, and federation spatial-service interfaces. Spiderweb does not become authoritative for AguaYLuz hydrology, Skywatcher aviation/trajectory semantics, or MoneySweep financial semantics.

### aguayluz-pr — hydrology/environment/infrastructure producer
Owns hydrologic networks, water/power/environmental infrastructure semantics, exposure logic, hazards, gauges, drought/storm monitoring, and domain-specific spatial analysis. It consumes canonical geometry services where appropriate but preserves existing domain logic.

### skywatcher-pr — airspace/trajectory/imagery producer
Owns 4D trajectories, airspace/corridor semantics, imagery-forensic algorithms, terrain/bathymetric analytics, and aviation-specific spatial reasoning. It may remain internally GDAL-light while consuming federation spatial services for heterogeneous authoritative geometry.

### moneysweep-pr — spatial-binding consumer
Owns contracts, awards, entities, projects, payments, beneficiaries, and financial provenance. It MUST NOT invent geometry to satisfy GIS completeness. Spatial enrichment is represented as authoritative/candidate bindings to canonical spatial entities and geometry manifestations.

### thehub-pr — orchestration/discovery/control plane
Owns federation discovery, capability registry, provenance presentation, cross-repo query orchestration, and trusted governance interpretation. It is not an independent geometry authority and MUST NOT silently rewrite producer geometry or identity decisions.

## Canonical spatial identity model
Every canonical spatial entity MUST separate:
- canonical_id
- entity_type
- canonical_name
- aliases[]
- source_manifestations[]
- geometry_bindings[]
- temporal_validity
- jurisdiction
- identity_status
- geometry_status
- provenance_status

A source manifestation may bind to zero, one, or many canonical entities; canonical entities may bind to multiple source manifestations.

## Evidence priority for identity
stable ID -> authoritative binding -> certified geometry -> point-in-polygon + independent alias/ID -> point-in-polygon -> authoritative alias + spatial/temporal support -> historical continuity + corroboration -> proximity -> UNRESOLVED.

## Federation service boundary
Spiderweb spatial services MAY provide:
- validate_geometry
- transform_crs
- point_in_polygon
- intersects/contains/within/touches/crosses/overlaps
- exact/topological equality tests
- Hausdorff distance and symmetric difference when material
- canonical boundary lookup
- vector-tile publication
- geometry manifestation retrieval

They MUST NOT decide domain semantics such as causation, contract ownership, outage attribution, flight intent, or hydrologic interpretation.

## Cross-repo contract gates
PASS requires all of:
- schema compatibility
- stable-ID uniqueness within declared scope
- required-field validation
- geometry/null/type validity
- CRS declaration and transform audit
- source/retained/excluded arithmetic closure
- join cardinality checks
- duplicate/collision adjudication
- identity state bounded with no silent promotion
- positive and negative regression tests
- provenance snapshot + retrieval time + source locator + hash
- no unresolved material residue inside certification scope

## Current certification state
OPEN/BLOCKED. Existing repo manifests that declare OPEN gates or federation BLOCKED are treated as declarations, not certifications. This document itself does not certify runtime behavior.

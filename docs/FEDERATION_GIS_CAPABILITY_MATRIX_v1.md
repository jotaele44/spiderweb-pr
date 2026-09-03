# Federation GIS Capability / Duplication Matrix v1

## Frozen baseline

| Repo | Frozen main SHA | Spatial authority |
|---|---|---|
| spiderweb-pr | `02169e73bf7ae110eeccb8cfaf47a4f7dfa2989f` | cross-domain investigation/fusion GIS |
| moneysweep-pr | `b5661dd29b5905015016041057136b6c945ddf5a` | capital/contracts/ownership/project geography |
| aguayluz-pr | `d46758886a40a290c15a3b138e131910163b0d1e` | water/power/environmental infrastructure GIS |
| skywatcher-pr | `6d7831c1cc665ad3080c9cab92a673cc5eb8e2e9` | aviation/airspace/terrain/4D trajectory GIS |

## Capability matrix

| Capability | Spiderweb | MoneySweep | AguaYLuz | Skywatcher | Canonical owner after v1 |
|---|---|---|---|---|---|
| MapLibre interactive map | mature | limited/consumer | mature | consumer/optional | shared runtime contract |
| GeoJSON interchange | mature | partial | mature | mature | spatial contract |
| KML/track interchange | mature | n/a | optional | mature | spatial contract + Skywatcher domain |
| geometry hashing/provenance | mature local semantics | partial | partial | partial | spatial contract |
| geodesic distance | mixed legacy | new v1 core | new v1 core | v1 SATIM production metric | spatial core |
| bbox joins | yes | limited | yes | yes, legacy degree path retained for reproducibility | spatial core |
| 4D trajectory | consumer | n/a | n/a | authoritative | Skywatcher |
| hydro upstream/downstream | consumer | n/a | v1 primitive | n/a | AguaYLuz |
| raster/DEM contract | consumer | optional | v1 raster contract | GEBCO terrain owner | domain + shared raster contract |
| capital-flow geometry | consumer | v1 safe materializer | n/a | n/a | MoneySweep |
| cross-domain spatial relations | v1 typed relations | publishes candidates | publishes candidates | publishes candidates | Spiderweb consumption; hub correlation boundary preserved |
| PostGIS durable plane | v1 migration | v1 migration | v1 migration | v1 migration | repo-local ownership |
| vector tiles | planned v1 extension | producer | producer | producer | shared serving contract |
| offline package | `fedgeopack/1.0` | `fedgeopack/1.0` | `fedgeopack/1.0` | `fedgeopack/1.0` | shared contract |

## Duplication rules

1. No repo may invent a second CRS, coordinate-confidence, provenance-hash, or identity-semantics vocabulary.
2. `logical_sha256` and `source_manifestation_sha256` are distinct invariants.
3. Spatial proximity defaults to `CANDIDATE_NOT_IDENTITY`; only an explicit identity adjudication path may emit `IDENTITY_BINDING`.
4. WGS84/CRS84 is canonical interchange. Projected CRSs are allowed for computation but must be declared.
5. Producers own domain data; no federation database grants implicit cross-repo write ownership.
6. Rendering behavior is described through `federation-map-runtime/1.0`; a producer need not depend on MapLibre to publish a renderable layer.
7. Every spatial schema/API/geometry-semantic change requires a `federation-spatial-impact/1.0` report naming all four consumers.

## Known baseline deficits being closed

- MoneySweep: project points, infrastructure assets and contract-flow geometries are data-blocked when no real coordinates exist. v1 adds a no-fabrication materialization path; it does not centroid-geocode missing records.
- Skywatcher: SATIM's historical nearest-layer value in planar degrees is retained only for reproducibility; v1 adds WGS84 geodesic meters as the production metric.
- AguaYLuz: v1 adds deterministic hydro-network tracing and a formal raster interface without forcing heavy raster dependencies into the base install.
- Spiderweb: v1 adds typed, auditable cross-domain spatial relations while preserving the producer/hub boundary and `CANDIDATE_NOT_IDENTITY`.

## Certification rule

`FOUR-REPO GIS CERTIFIED` requires schema + geometry + tests + security + performance + federation + desktop + iOS gates to close. A branch or PR may be `TESTED` without being `CERTIFIED`.

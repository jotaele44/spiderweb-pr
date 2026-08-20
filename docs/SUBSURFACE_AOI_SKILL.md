# Spiderweb AOI Subsurface Relevance Skill v0.1

## Scope

`spiderweb.subsurface` turns a polygonal KML, KMZ, or GeoJSON file into a frozen AOI and a restartable subsurface-analysis dispatch receipt. It is a reusable control plane, not a claim that every subsurface source is already connected.

The skill deliberately separates:

- source byte identity from canonical geometry identity;
- discovery from identity/functional binding;
- spatial relationship from evidence tier;
- missing capability from negative evidence;
- score/ranking from certification.

## Intake

Accepted AOI formats:

- `.kml`
- `.kmz`
- `.geojson`
- `.json` containing GeoJSON

Only polygonal AOIs are accepted. Invalid or empty geometry fails closed. KML/KMZ and GeoJSON are treated as WGS84 coordinate sources; analysis is planar 2D. If Z is present, the receipt records the dimensional loss when freezing the 2D analysis geometry.

The frozen receipt records source SHA-256, source size, format, feature count, source geometry type, canonical GeoJSON, canonical geometry SHA-256, and (for KMZ) the selected KML member plus member SHA-256.

## Dispatch families

The dispatcher has an explicit denominator of eight layer families:

1. `GEOLOGY_KARST_CAVES`
2. `AQUIFERS_WELLS_SPRINGS`
3. `FAULTS_STRUCTURES`
4. `MINES_QUARRIES_SHAFTS`
5. `MILITARY_HARDENED_SUBSURFACE`
6. `INDUSTRIAL_REMEDIATION`
7. `UTILITIES_UNDERGROUND`
8. `HISTORICAL_CORROBORATION`

Adapters register against those stable family identifiers. An unregistered family is `OPEN`; it is never interpreted as evidence that no relevant feature exists.

## Evidence tiers

- `DIRECT`: authoritative/direct evidence of the asserted subsurface fact.
- `SUPPORTING`: independent evidence materially supporting relevance without independently proving the asserted fact.
- `CANDIDATE`: discovery evidence requiring adjudication.
- `CONTRADICTED`: evidence actively conflicting with the asserted interpretation.
- `UNRESOLVED`: evidence cannot be classified safely.

The following bases can never promote above `CANDIDATE` by themselves:

- `proximity_only`
- `nearest_only`
- `name_only`
- `normalized_name_only`
- `same_category`
- `source_absence`

Scores never prove identity, intent, connectivity, or underground function. Equal top scores are preserved as review ties.

## Spatial states

Every evidence geometry terminates in one of:

- `FULLY_WITHIN`
- `PARTIAL`
- `TOUCH_ONLY`
- `OUTSIDE`
- `NULL_EMPTY`
- `UNRESOLVED`

## Provenance manifest

`manifest.json` stores the frozen AOI, source-manifest entries supplied by adapters, dispatch plan, invariant counts, and non-promotion rules. Source adapters should freeze at minimum source URI/service/layer/query, retrieval UTC, source bytes or logical snapshot hash, schema, and row/feature count.

Different hashes establish byte difference only. They do not establish logical, schema, geometric, or source-manifestation difference without a corresponding comparison.

## Outputs

The artifact helpers emit:

- `evidence.csv`
- `evidence.geojson`
- `evidence.kml`
- `evidence.kmz`
- `manifest.json`

The command-line entrypoint additionally emits `aoi_frozen.geojson`.

## Operator entrypoint

```bash
spiderweb-subsurface AOI.kml --out subsurface_run
```

Restrict the dispatch denominator when needed:

```bash
spiderweb-subsurface AOI.geojson --out run \
  --family GEOLOGY_KARST_CAVES \
  --family AQUIFERS_WELLS_SPRINGS
```

A plan containing `OPEN` families is a valid preflight result but is **not** a completed subsurface relevance analysis. Register/source adapters, rerun, adjudicate all candidates, and close arithmetic before certification.

## Regression gates

The test suite covers:

- equivalent KML/GeoJSON geometry -> same canonical geometry hash;
- different manifestations -> different source byte hashes;
- KMZ container hash separated from member hash;
- invalid polygon -> fail closed;
- proximity-only attempted promotion -> capped at candidate;
- null geometry -> unresolved, not negative;
- touch-only -> distinct final spatial state;
- duplicate record IDs -> fail closed;
- tied top scores -> review flags, no arbitrary tie-break;
- missing handler -> `OPEN`, not negative evidence.

## Certification boundary

The subsystem can certify AOI intake and evidence-ledger invariants. A full subsurface claim is certifiable only after the requested layer-family denominator is defined, every family is terminal (`PASS`, justified `BLOCKED`, or otherwise explicitly adjudicated), every candidate is classified, duplicate/edge cases are resolved, provenance is frozen, and zero unresolved residue remains inside the claim scope.

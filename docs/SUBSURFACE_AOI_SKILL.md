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

`manifest.json` stores the frozen AOI, source-manifest entries supplied by adapters, dispatch plan, invariant counts, and non-promotion rules. Source adapters freeze source URI/service/layer/query, retrieval UTC, source bytes or logical snapshot hash, schema, and row/feature count where applicable.

Different hashes establish byte difference only. They do not establish logical, schema, geometric, or source-manifestation difference without a corresponding comparison.

## Public-source execution

Queryable ArcGIS and OGC manifestations use count/paging arithmetic with raw-byte and logical hashes. Exact authoritative reference pages/downloads are executable through `reference_adapter.py`, which freezes the retrieved bytes, retrieval UTC, byte count, and SHA-256. A reference receipt certifies only that registered manifestation; it does not certify the completeness of a broader collection or real-world asset universe.

The current public-source denominator is versioned additively through v0.4. `public_exhaustion.py` controls records-request eligibility. Every required source manifestation in scope must be terminal `PASS|ZERO`; any required OPEN, NOT_RUN, failed, discovery-only, unindexed, or otherwise non-terminal row keeps records-request consideration forbidden.

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

The test suite covers equivalent KML/GeoJSON geometry identity, manifestation hashes, KMZ member identity, invalid polygons, non-promotion rules, null/touch/duplicate/tie safeguards, ArcGIS/OGC paging, exact reference-byte freezing, versioned public-source denominators, and the records-request eligibility gate.

## Certification boundary

A full subsurface/public-source claim is certifiable only after the selected layer-family denominator is defined, every required source manifestation is terminal, every candidate is classified, duplicate/edge cases are resolved, provenance is frozen, and zero unresolved residue remains inside the claim scope. Precise current protected hardened/underground military assets are not enumerated by this subsystem.

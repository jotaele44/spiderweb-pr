# Santiago Triangle — Cantera Naranjo / Juana Díaz Manganese Lineage v0.1

## Controlling rule

This lineage is fail-closed. A shared name, commodity, road, nearby coordinate, quarry morphology, or common geologic setting does **not** establish real-world identity or subsurface connectivity. Historical Site 78, modern quarry manifestations, the USGS Juana Díaz Mine record, Cueva Naranjo, and user-supplied imagery remain separate entities until an authoritative identity/geometry edge binds them.

## Primary historical source

The frozen uploaded manifestation of *La Carretera Central: un viaje escénico a la historia de Puerto Rico* is attributed to the Oficina Estatal de Preservación Histórica de Puerto Rico and the Centro de Investigación y Desarrollo, Recinto Universitario de Mayagüez, Universidad de Puerto Rico.

Site 78 is `Cantera Naranjo`. The printed location is **`Al oeste del pueblo de Juana Díaz, PR-551, Km. 4.`**. There is no decimal after 4 in the source. The earlier working assumption `Km 4.4` is therefore superseded and preserved as a corrected contradiction.

The Site 78 text describes a marble quarry that exposed tunnels from a manganese mine worked in the early 1900s by a United States company. It states that the extracted vein mineral was ground into a black powder for export, that the tunnels followed the mineral vein through marble, that most tunnels were later destroyed by quarry exploitation, and that a small stone mine-office building survived when the guide was prepared.

Frozen local manifestation:

- PDF SHA256: `6a0516d70ad79dacfa152a212324c2f1a8150a22f51b8bfef85385e8e089973a`
- PDF bytes: `9,738,689`
- Site 78 PDF page: `41` / book page `34`
- rendered Site 78 page SHA256 (PNG, 150 dpi): `0272f52ac8b68b6ebd81cdd8c68c74084b1bd1d036cf118c72b7d137bef47b08`
- source map places Site 78 west of Juana Díaz, but the map is an illustrative route map rather than survey geometry.

## Independent mineral corroboration

USGS Open-File Report 98-038 independently documents manganese exploitation in Juana Díaz. Its manuscript states that Atlantic Ore Company initiated manganese-oxide production in the barrios of Tijeras and Guayabal in 1915 and identifies the Juana Díaz Mine as active from 1915 through 1939. The report's mineral-occurrence appendix identifies `W701145 JUANA DIAZ MINE` at `18-04-15N / 066-27-55W`, commodity Mn, described as fissure fillings in limestone in the Río Descalabrado quadrangle.

This independently corroborates a United States mining company, Juana Díaz manganese exploitation, limestone-hosted mineralization and the early-twentieth-century time window. It does **not** explicitly state that `W701145` and OECH Site 78 are the same mine/property.

A 1930s *Revista de Obras Públicas de Puerto Rico* manifestation additionally discusses Atlantic Ore Company operations at Juana Díaz, subsurface exploration, a mine and mill, a ridge extending toward the Guayabal reservoir and Río Descalabrado, and nearby marble deposits. It states that the mine was on the south-central side of an elongate limestone-capped ridge extending westward toward the Guayabal reservoir and eastward toward Río Descalabrado, and discusses exploratory underground operations. This is corroborating district-scale evidence, not exact Site-78 tunnel geometry.

### Historical-operator state

`ATLANTIC ORE COMPANY → JUANA DÍAZ MANGANESE DISTRICT` is `CORROBORATED` by independent USGS/historical-public-works evidence.

`ATLANTIC ORE COMPANY → OECH SITE 78` remains `UNRESOLVED`, because no recovered source yet explicitly names Site 78/Cantera Naranjo as the Atlantic Ore Company property.

## Point-manifestation geometry

Exact predicates against the frozen Santiago Triangle and SZ-0015 are used. Distances below are approximate projected distances to the nearest exact polygon boundary and are discovery context only.

| Manifestation | Coordinate | Santiago AOI | SZ-0015 | Interpretation |
|---|---|---|---|---|
| PRPB `CANTERA NARANJO` OBJECTID 38 | `18.0653387594,-66.4702715943` | WITHIN | WITHIN | existing quarry manifestation already counted by v1/v1.1; source address `CARR 551 KM 2.1 BO NARANJO`; not historical-tunnel identity |
| USGS MRDS `Cantero Naranjo` 200733 | `18.0684699997,-66.4702700001` | OUTSIDE | OUTSIDE | historical mineral-record manifestation; identity to PRPB/Site78 unresolved |
| USGS `W701145 JUANA DIAZ MINE` | `18.0708333333,-66.4652777778` | OUTSIDE (~133 m) | OUTSIDE (~141 m) | independent historical Mn mine record point; not tunnel entrance geometry |
| Procan embedded-map center | `18.0710037639,-66.4758622292` | OUTSIDE (~703 m) | OUTSIDE (~711 m) | modern business/map anchor near PR-551 Km 4.4/4.5; not quarry centroid |
| EPA `Productos de Agregados - Cantera Naranjo` | `18.054444,-66.500278` | OUTSIDE (~386 m) | OUTSIDE | modern regulatory facility point associated with PR-551 Km 2.7; not historical Site 78 |

The key geometry result is therefore asymmetric: **a modern PRPB manifestation named Cantera Naranjo is inside SZ-0015, but the independent USGS Juana Díaz historical-mine record point is outside the frozen Santiago AOI**. That difference is preserved instead of being reconciled by name or proximity.

The inside PRPB quarry point is approximately 806 m from the USGS W701145 mine record point. Cueva Naranjo's published point is approximately 144 m from the PRPB quarry point. Those distances are discovery measurements only and create no identity or connectivity edge.

## Frozen topographic quarry lineage inside SZ-0015

The already-certified v1.1 evidence ledger contains independent USGS historical-topographic quarry manifestations inside/intersecting SZ-0015:

| manifestation | source map | scan id | state |
|---|---|---:|---|
| USMin quarry point `487420` | Río Descalabrado 1945 | `362556` | FULLY_WITHIN |
| USMin quarry point `487419` | Río Descalabrado 1972 | `362238` | FULLY_WITHIN |
| USMin quarry polygon `115004` | Río Descalabrado 1982 | `362239` | FULLY_WITHIN |
| USMin quarry polygon `115000` | Río Descalabrado 1982 | `362239` | PARTIAL |

The 1982 polygons represent approximately 9,013 m² fully within and 26,454 m² for the larger partial polygon before clipping to the zone. These are historical **surface-quarry** manifestations. No registered historical `Adit|Air Shaft|Mine Shaft` symbol was returned for the AOI.

Relevant topoView footprints over SZ-0015 additionally include Río Descalabrado editions from 1945, 1952, 1960 and 1972 plus later US Topo editions. This supplies a bounded temporal map stack for future quarry-face reconstruction but does not by itself locate Site-78 tunnels.

## Additional cave/property corroboration

A separate Cueva Naranjo conservation manifestation places the cave in Cerro Cuevas, Guayabal, and describes it as being on the premises of Cantera Naranjo. That is relevant to cave/quarry **property context**. It is not evidence that the natural cave connects to the historical manganese workings or that the named quarry manifestation in that source equals OECH Site 78.

## Current identity graph

All Site-78 identity edges remain `UNRESOLVED`:

- Site78 ↔ PRPB `CANTERA NARANJO` OBJECTID 38 — `UNRESOLVED`
- Site78 ↔ MRDS `Cantero Naranjo` — `UNRESOLVED`
- Site78 ↔ USGS W701145 Juana Díaz Mine — `UNRESOLVED`
- Site78 ↔ Productos de Cantera / Procan — `UNRESOLVED`
- Site78 ↔ EPA Productos de Agregados / Cantera Naranjo — `UNRESOLVED`
- Site78 ↔ Cueva Naranjo — `UNRESOLVED`
- Site78 ↔ IMG_4020 / IMG_4021 / IMG_4022 — `UNRESOLVED`

No nearest-neighbor or name-only edge may collapse these entities.

## Contradiction register

### CN-CONTR-001 — chainage correction

Earlier working text used `PR-551 Km 4.4`; the frozen OECH page prints `PR-551 Km. 4.`. The `4.4/4.5` value belongs to separate modern Productos de Cantera/Procan manifestations and cannot be imported into the historical source.

### CN-CONTR-002 — multiple Cantera Naranjo chainages

The corpus contains modern manifestations around `Km 2.1`, `Km 2.7`, and modern Productos de Cantera/Procan around `Km 4.4–4.5`, while historical Site 78 prints `Km 4.`. These are not forced into one quarry. Current business directories likewise list Procan around Km 4.5 and Cantera Naranjo around Km 2.7 as separate entries.

### CN-CONTR-003 — split spatial states

PRPB Cantera Naranjo lies inside SZ-0015, while MRDS Cantero Naranjo, USGS W701145, Procan's map center and the EPA facility manifestation lie outside the exact Santiago Triangle. Bbox membership is not substituted for exact polygon membership.

### CN-CONTR-004 — mapped-opening ZERO versus documentary tunnels

The Santiago live query against the explicit USGS `Adit|Air Shaft|Mine Shaft` historical map-symbol manifestation returned ZERO. OECH Site 78 nevertheless documents historical tunnels in the Juana Díaz quarry/mining context. These findings are not logically inconsistent: they concern different source universes and the independently geocoded W701145 record point is outside the exact AOI.

### CN-CONTR-005 — natural cave versus artificial historical workings

Cueva Naranjo is direct mapped natural-subsurface evidence inside SZ-0015. The historical manganese tunnels are documentary artificial-subsurface evidence whose exact geometry has not been bound inside SZ-0015. Connectivity remains `UNRESOLVED`.

### CN-CONTR-006 — modern quarry status fields

The PRPB quarry row's status and GPS timestamp are historical source attributes. They are not promoted to a claim about current operating status.

## Residual-state correction

`HISTORIC_WORKINGS_NONMAPPED_RESIDUAL` was `FINAL_PUBLIC_GAP` in frozen v0.5. It is **reopened to `OPEN` in v0.6** because Site 78 supplies a specific authoritative documentary manifestation that creates new bounded public-source work:

1. Site78 ↔ W701145 identity adjudication;
2. PR-551 historical/current chainage reconstruction;
3. original OECH/UPR field-note and photograph search;
4. Atlantic Ore Company property/operator lineage;
5. historic topo/aerial quarry-footprint reconstruction;
6. mine-office building identification;
7. destroyed-versus-surviving workings adjudication.

Reopening the residual does not imply that a comprehensive national mine-working inventory exists.

## Relevance-model consequence

**No v1.1 score change is currently permitted.**

SZ-0015 remains `6.558`, `MODERATE`, `ROBUST`, and `DIRECT` solely because of the mapped natural cave evidence already present in the certified model. Its quarry contribution already includes the PRPB and USGS quarry manifestations above. The recovered historical artificial-subsurface evidence cannot add a new score contribution until exact spatial identity/containment places the historical working inside the zone without double-counting an existing manifestation.

Therefore:

- `HISTORICAL_ARTIFICIAL_SUBSURFACE` = `OPEN / NOT_SCORED`
- `CAVE↔MINE_CONNECTIVITY` = `UNRESOLVED`
- `SITE78↔SZ0015` = `UNRESOLVED`
- `HIGH_PROMOTION` = `NOT_SUPPORTED`
- `IMG_4020` = `UNRESOLVED`
- `IMG_4021` = `UNRESOLVED`
- `IMG_4022` = `CANDIDATE visual quarry binding only`

## Remaining bounded public vectors

Priority order:

1. recover original OECH/UPR Site-78 survey card, notes and photograph(s), if publicly manifested;
2. recover Atlantic Ore Company Juana Díaz property descriptions, maps and mine/mill plans from USGS/USBM/PR historical publications;
3. reconstruct PR-551 Km 4 historical chainage and compare with current Km 4.4/4.5 Procan manifestations;
4. acquire actual HTMC map payloads and historical aerial epochs to reconstruct quarry-face migration and likely destruction zones;
5. search for the stone mine-office structure as a historical georegistration anchor;
6. preserve every competing quarry/facility manifestation rather than normalizing by name.

Records requests remain forbidden while public-source exhaustion is OPEN.

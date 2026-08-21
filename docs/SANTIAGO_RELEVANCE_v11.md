# Santiago Triangle — Subsurface Relevance Model v1.1

## Purpose

v1.1 preserves the v1 zone ledger and hardens interpretation by replacing duplicate-prone groundwater and mine/quarry source-row counts with canonical physical-asset counts where binding exists, then running auxiliary-family perturbations and rank-stability tests. It does not infer subsurface connectivity, access, intent, hidden use, or current protected infrastructure.

## v1 → v1.1 transition

Frozen v1: 146 zones = 75 VERY_LOW | 63 LOW | 8 MODERATE | 0 HIGH.

Canonical-asset v1.1 recomputation:

- 146 total zones
- 77 VERY_LOW
- 62 LOW
- 7 MODERATE
- 0 HIGH
- `SZ-0083` is the only original MODERATE zone that drops class, from 4.046 to 3.931 LOW
- no LOW/VERY_LOW zone promotes to MODERATE or HIGH

Original elevated-zone sensitivity state:

- `SZ-0015` — ROBUST, v1 6.697 → v1.1 6.558; rank 1 under all tested auxiliary-family perturbations
- `SZ-0006` — SEMI_ROBUST, 4.985 → 4.869; rank 2 under all tested perturbations
- `SZ-0041` — THRESHOLD
- `SZ-0040` — THRESHOLD
- `SZ-0014` — THRESHOLD
- `SZ-0074` — THRESHOLD
- `SZ-0018` — THRESHOLD
- `SZ-0083` — PROVISIONAL; canonical dedup crosses below the MODERATE threshold

The perturbation set removes utilities, historical corroboration, industrial/remediation, utility+history, and utility+history+industrial. Rank ranges are persisted per zone.

## SZ-0015 adjudication

`SZ-0015` remains the only DIRECT elevated cell because the PRPB cave layer contains `Cueva Naranjo` inside the cell. DIRECT means only that a mapped cave feature intersects the cell.

The frozen local corpus also contains:

- PRPB `Cantera Naranjo` quarry manifestation (`CERRADO` in the frozen quarry attributes)
- USGS historical quarry-symbol manifestations tied to Río Descalabrado topographic editions, including 1945 and 1972 source dates
- USGS quarry polygon manifestations tied to 1982 mapping
- USGS `TCAS WELL, JUANA DIAZ, PR`
- a PRPB UST manifestation for `CANTERA NARANJO`, frozen as `CERRADA`
- 16 topoView map-edition footprints spanning 1945, 1947, 1952, 1960, 1972, 2013, 2018, and 2024 manifestations

The exact PRPB geology polygons intersecting the 0.02-degree cell include Coamo Formation, Fault breccia, Guaracanal Formation, and Rio Descalabrado Formation. Exact feature-to-geology intersection in the frozen geometry binds the quarry/well/UST manifestations primarily to the Rio Descalabrado Formation polygon, while the cave geometry does not intersect that PRPB geology polygon set. Therefore the cell is not treated as one homogeneous lithologic body and cave↔quarry co-location is not promoted to a shared system.

External public geology corroboration identifies Cueva Naranjo with the Cerro Cuevas south-coast karst setting; USGS nomenclature assigns Cuevas Limestone to the Jacaguas Group and distinguishes it stratigraphically from the younger Juana Díaz Formation. This supports a natural karst interpretation while reinforcing the need to keep the cave and quarry geometries independently bound.

### SZ-0015 v1.1 score decomposition

- cave: 3.000
- groundwater: 0.520
- mine/quarry: 1.613
- industrial: 0.173
- utility: 0.111
- historical map: 0.142
- independent-source diversity: 1.000
- total: 6.558 MODERATE

Sensitivity:

- no utility: 6.347
- no history: 6.317
- no industrial: 6.285
- no utility/history: 6.056
- no utility/history/industrial: 5.732
- leave out aquifers/wells/springs: 5.938
- leave out mine/quarry family: 4.546
- leave out geology/karst/caves: 3.308

The last result demonstrates that the cave/geology family is the controlling direct-evidence component. Removing it drops the cell below MODERATE; this is expected and is not treated as instability because that perturbation removes the primary phenomenon being measured.

## Historical and aerial coverage boundary

topoView closes a substantial topographic-map chronology for SZ-0015, including 1945/1947/1952/1960/1972 HTMC and 2013/2018/2024 US Topo manifestations. The historical aerial frame/scene denominator remains OPEN under the v0.5 public-source certificate; v1.1 therefore does not claim a complete aerial temporal stack.

## Interpretation boundary

A relevance zone is a cell-level evidence concentration. It is not an inferred cave passage, quarry connection, tunnel, underground facility, access route, or shared subsurface network. `HIGH` remains empty and no zone may be promoted to HIGH solely from proximity, utility density, historical-map density, or duplicated source manifestations.

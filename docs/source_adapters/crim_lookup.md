# CRIM/SIGE parcel lookup adapter

`integration.crim_lookup` provides fail-closed parcel discovery against the CRIM/SIGE `Parcelario` ArcGIS Feature Layer.

## Scope

The adapter may establish what the CRIM parcel service returns: parcel identifiers, source classifications, geometry, and spatial relationships. It **does not** establish current ownership, title, deed history, tax balance, valuation, beneficial ownership, or occupancy.

## Source contract

- Layer: `crim/crim_parcelas/MapServer/0`
- Expected layer id: `0`
- Expected geometry: `esriGeometryPolygon`
- Expected native CRS: EPSG:32161
- Required fields: `OBJECTID`, `GLOBALID`, `NUM_CATASTRO`, `OLDPID`, `TIPO`, `CATEGORIA`
- `TIPO`: `P=PARCELA`, `V=VIAL`, `A=AGUA`

The live metadata currently declares the `GLOBALID` and `NUM_CATASTRO` indexes non-unique. Exact identifier lookups therefore retain every returned candidate. Cardinality is always explicit, and even a single identifier result remains `PROVISIONAL` until an independent authoritative binding establishes canonical identity.

## Failure semantics

Transport failure, invalid JSON, an ArcGIS `error` object, missing or malformed `features`/`objectIds`, schema drift, transfer-limit truncation, and pagination arithmetic failure are errors. None is converted into `VALID_ZERO_RESULT`.

## Completeness

Broad retrieval uses `returnCountOnly` plus `returnIdsOnly`, then OBJECTID chunks. Certification requires `count == object-id denominator == unique retrieved OBJECTIDs`. Duplicate or missing records fail closed.

## Commands

```bash
python scripts/crim_freeze_source_contract.py
python scripts/crim_lookup.py id NUM_CATASTRO <value>
python scripts/crim_lookup.py point -66.05 18.35
python scripts/crim_lookup.py bbox -66.1 18.3 -66.0 18.4
python scripts/crim_live_canary.py
```

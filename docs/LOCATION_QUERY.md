# Spiderweb LOCATION_QUERY v1

`LOCATION_QUERY` is the canonical planning entry point for asking Spiderweb what spatial data can serve a location or AOI.

It does **not** replace provider-specific adapters. It routes a validated query to the existing authoritative acquisition/resolver lane and emits an acquisition plan before bytes are fetched.

## Contract

Supported geometry types:

- `point`
- `radius`
- `bbox`
- `polygon`
- `geojson`

Modes:

- `plan` — routing/readiness only; no downloads.
- `cache_only` — downstream adapters may use certified local cache only.
- `fetch` — downstream provider adapters may acquire missing authoritative bytes subject to their own guards.

The JSON schema is `schemas/location_query.schema.json`.

Example:

```json
{
  "query_id": "hucar-2km",
  "geometry": {
    "type": "radius",
    "lat": 18.0119,
    "lon": -66.2396,
    "radius_m": 2000
  },
  "mode": "plan",
  "allow_partial": false
}
```

Run:

```bash
python scripts/location_query.py query.json --out outputs/location_query/hucar/acquisition_plan.json
```

## Routing states

The unified registry `configs/location_query_providers.json` preserves deliberate capability asymmetry:

- `READY` — routable without additional credentials.
- `READY_WITH_CREDENTIALS` — routable when required credentials are present.
- `READY_SPECIALIZED` — implemented through a specialized authoritative lane rather than the generic AOI fetcher.
- `RESOLVER_ONLY` — source discovery/resolution exists, but a complete generic byte-acquisition contract is not yet unified.
- `PROVIDER_BINDING_OPEN` — acquisition machinery exists but authoritative catalog/URL binding is incomplete.
- `SCHEMA_ONLY` — contract/schema exists without an executable resolver.
- `NOT_IMPLEMENTED` — provider family is intentionally represented in the denominator but has no integrated adapter yet.
- `BLOCKED` — implementation exists but a certification dependency prevents promotion.

These states are routing facts, not source-availability claims.

## Initial provider denominator

The v1 registry includes:

- USGS 3DEP 1 m DEM — `READY`
- legacy PRVI 2018 1 m DEM provider contract — `PROVIDER_BINDING_OPEN`
- NCEI Coastal DEM — `READY`
- NASA GIBS — `READY`
- Sentinel Hub — `READY_WITH_CREDENTIALS`
- Copernicus Data Space — `READY_WITH_CREDENTIALS`
- PRPB geology/karst/caves — `RESOLVER_ONLY`
- PR aquifers/wells/springs — `RESOLVER_ONLY`
- PR marine lidar/topobathy — `READY_SPECIALIZED`
- SSURGO — `NOT_IMPLEMENTED` in-repo (external certified workflow exists)
- USGS 3DHP/NHD — `NOT_IMPLEMENTED`
- USFWS NWI — `NOT_IMPLEMENTED`
- FEMA NFHL — `NOT_IMPLEMENTED`
- general USACE GIS — `RESOLVER_ONLY`

## Existing authoritative lanes

The router references rather than replaces:

- `tools/source_manifestation_seed.py` + `tools/spatial_aoi_fetcher.py` for USGS DEM source discovery/acquisition.
- `source_adapters/ncei_coastal_dem` for NCEI Coastal DEM.
- `imagery/providers/*` for GIBS, Sentinel Hub and Copernicus imagery.
- `spiderweb/subsurface/sources.py` for geology/karst/hydrogeology source resolution.
- `pipeline/pr_marine_datasets.py` and `docs/MARINE_LIDAR_BINDING.md` for marine/topobathy sources.

## Non-promotion rules

- `NO_COVERAGE` is not `SOURCE_ABSENCE`.
- `MISSING_PROVIDER_BINDING` is not `MISSING_DATASET`.
- Place-name geocoding is discovery until converted to a bounded geometry.
- Provider family identity is not source-manifestation identity.
- Count equality is not identity evidence.
- Raw authoritative bytes precede clipping/derivation.
- Plan precedes download.
- Geographic `Cell_ID` binding remains blocked until the canonical grid transform is certified.

## Next integration denominator

The next missing-provider implementation sequence is:

1. integrate the certified SSURGO AOI resolver;
2. add USGS 3DHP/NHD hydrography;
3. add USFWS NWI wetlands;
4. add FEMA NFHL flood hazard;
5. unify the general USACE ArcGIS/service catalog;
6. add place-name geocoding as discovery-only AOI construction;
7. run a frozen Puerto Rico reference-AOI regression corpus and certify bounded coverage.

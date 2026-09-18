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

Run planning:

```bash
python scripts/location_query.py query.json --out outputs/location_query/hucar/acquisition_plan.json
```

Execute only the bounded request specs emitted by the plan:

```bash
python scripts/location_query_fetch.py outputs/location_query/hucar/acquisition_plan.json \\
  --output-dir data/cache/location_query/hucar
```

The executor preserves raw response bytes and SHA-256 receipts before any downstream interpretation. Production fetch remains fail-closed for incomplete providers. `--discovery-only` is a separate bounded scope that may execute only discovery metadata or explicit `RESOLVER_STAGE` requests; it cannot execute ordinary production source requests. `RESOLVER_ONLY` evidence is never promoted automatically.

After acquisition, `scripts/location_query_package.py` re-hashes every raw denominator/batch artifact and freezes a package-level provenance manifest. Canonical provider-health auditing is `scripts/audit_location_query_provider_health.py`; endpoint health is explicitly not AOI coverage. `scripts/location_query_provider_health.py` is retained only as NONCANONICAL compatibility.

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

## Provider denominator

The v1 registry currently contains 16 provider entries. Provider readiness and unified-executor readiness are separate dimensions: a specialized adapter may be operational while the generic LOCATION_QUERY executor still reports an execution gap.

The registry includes:

- USGS 3DEP 1 m DEM — `READY`
- legacy PRVI 2018 1 m DEM provider contract — `PROVIDER_BINDING_OPEN`
- NCEI Coastal DEM — `READY`
- NASA GIBS — `READY`
- Sentinel Hub — `READY_WITH_CREDENTIALS`
- Copernicus Data Space — `READY_WITH_CREDENTIALS`
- PRPB geology/karst/caves — `READY_SPECIALIZED` via the existing frozen subsurface source denominator
- PR aquifers/wells/springs — `READY_SPECIALIZED` via PRPB + USGS Water Data queryable manifestations
- PR marine lidar/topobathy — `READY_SPECIALIZED`
- SSURGO — `RESOLVER_ONLY`: AOI SurveyAreaPoly/MapunitPoly requests are bound; MUKEY→COKEY→child production certification remains open in-repo
- USGS 3DHP/NHD — `RESOLVER_ONLY`: the authoritative `3DHP_all` FeatureServer is bound and six observed layer-ID candidates are preserved, but production routing remains metadata-first until raw service metadata + receipt are frozen and stable-ID set adjudication closes
- USFWS NWI — `READY_SPECIALIZED`: Wetlands FeatureServer layer bound
- FEMA NFHL — `RESOLVER_ONLY`: official public WMS/MSC surface bound; vector denominator remains open
- FEMA Puerto Rico ABFE 1% — `RESOLVER_ONLY`: Puerto Rico-specific map service bound; layer denominator remains open and is separate from effective NFHL identity
- USACE ports/navigation — `READY_SPECIALIZED`: ports, principal ports, navigation facilities and waterway-network nodes bound
- general USACE GIS — `RESOLVER_ONLY`: enterprise service denominator remains open

## Execution coverage gate

Every plan reports:

- `generic_executor_provider_ids` — providers with bounded request specifications executable by `location_query_fetch.py`;
- `specialized_adapter_provider_ids` — operational providers still requiring their authoritative specialized lane;
- `incomplete_provider_ids` — resolver/binding/blocker states;
- `execution_gap_provider_ids` — provider-ready lanes not yet delegated by the generic executor;
- `fetch_blocker_provider_ids`;
- `fetch_gate`.

For `mode=fetch`, the generic executor refuses to run unless `fetch_gate=READY`. `allow_partial=true` produces `ALLOW_PARTIAL_WITH_EXPLICIT_GAPS`; it never silently converts an incomplete denominator into complete coverage.

ArcGIS FeatureServer acquisition is denominator-first: Spiderweb first requests `returnIdsOnly=true`, freezes the object-ID set, then fetches deterministic ID batches and requires returned-ID set equality. A single HTTP-200 feature response is never accepted as exhaustive AOI coverage.

## Stage authority and compatibility

The canonical control-plane authority is staged rather than monolithic:

- `spiderweb/location_query.py` + `spiderweb/location_query_sources.py` — canonical routing/request planning.
- `scripts/location_query_fetch.py` — canonical bounded byte-transfer/provenance executor.
- `spiderweb/ssurgo_chain.py` — generic SSURGO MapunitPoly -> MUKEY -> SDA mapunit/component dependent-stage planner.
- `scripts/location_query_ssurgo.py` — NONCANONICAL compatibility-only monolithic runner; it requires `--allow-noncanonical-compat` and cannot certify the canonical modular SSURGO chain.
- `spiderweb/place_resolver.py` + `scripts/place_resolve.py` — canonical staged place discovery/candidate binding.
- `scripts/location_query_geocode.py` — NONCANONICAL compatibility direct geocoder; explicit override required, and its output cannot bypass canonical candidate binding.
- `spiderweb/provider_denominators.py` + `spiderweb/denominator_chain.py` — canonical metadata-denominator freezing and dependent provider-stage planning.

Where two tools overlap, the staged contract above is authoritative. Compatibility/specialized runners may add analysis or certification but must not silently redefine routing identity or provider readiness.
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

## Remaining integration denominator

1. execute and certify the in-repo SSURGO staged chain, including the current component-child denominator, without flattening 1:N;
2. resolve FEMA NFHL vector-feature manifestation(s) without conflating WMS display with feature identity;
3. freeze the Puerto Rico ABFE service layer denominator separately from NFHL;
4. close the recursive USACE root + folder service denominator through `provider_denominators.py`, `denominator_chain.py`, and `merge_location_service_denominators.py`; the root-only `location_query_usace_inventory.py` compatibility lane fails closed when folders exist;
5. freeze 3DHP raw FeatureServer metadata and run stable layer-ID set adjudication before any readiness promotion;
6. delegate existing USGS 3DEP, NCEI and imagery specialized adapters into the unified fetch executor without duplicating their acquisition logic;
7. execute the frozen Puerto Rico reference-AOI regression corpus when runner infrastructure is available;
8. keep place-name geocoding discovery-only until a selected candidate is explicitly bound to bounded geometry.

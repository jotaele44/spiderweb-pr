# Martin delivery canary

This directory contains Spiderweb-PR's non-canonical Martin tile-delivery configuration.

## Invariant

Martin is a presentation/delivery service. It does not establish source authority, canonical identity, visibility, provenance, or analytical truth. Those remain owned by Spiderweb.

The canary intentionally publishes exactly one source: `municipios`.

`martin/config.yaml` uses `geojson.sources` and deliberately does **not** use `geojson.paths`. Directory discovery would allow an added file to become a published source without an explicit Spiderweb authorization change.

## Frozen canary binding

The delivery registry at `configs/martin_delivery.yaml` binds the canary to the 2025 TIGER municipios artifact recorded in `data/tiger/2025/manifest.json`:

- feature count: 78
- CRS: EPSG:4326
- artifact SHA-256: `adebd4e779e36ca4aecb69291af9e153e430a829cc4ca8a676f7d5f5197a5d76`
- identity field: `GEOID`

The existing `/geo/municipios.geojson` FastAPI route is retained as the rollback/parity path.

## Run locally

Mount the repository `data` directory read-only at `/spiderweb-data` and run a pinned Martin 1.13.0 build with this config. Example container topology:

```text
host data/municipios.geojson -> /spiderweb-data/municipios.geojson:ro
host martin/config.yaml      -> /config.yaml:ro
Martin                       -> --config /config.yaml
```

The exact container digest should be pinned before promotion. Do not use a floating `latest` tag for certification.

After Martin starts:

```bash
python scripts/check_martin_canary.py --base http://127.0.0.1:3000
pytest -q tests/test_martin_catalog_contract.py
```

## Promotion gate

The `municipios` source has progressed from `candidate` to
`publication_state: validated` (runtime canary, MapLibre rendering path,
feature-ID parity, negative publication tests, and rollback test all pass —
see `.github/workflows/martin-canary.yml` and
`.github/workflows/martin-publication-contract.yml`). A non-mutating
eligibility check (`scripts/check_martin_promotion.py --source municipios
--target published`) confirms it is `ELIGIBLE_FOR_EXPLICIT_TRANSITION`; a
receipt is on file at `evidence/martin/municipios_promotion_eligibility_receipt.json`.

`validated` is still not `published`: per `configs/martin_delivery.yaml`'s
`authorization_note`, production config generation excludes this source
"until an explicit future validated-to-published action." That final flip
is a deliberate operator decision — it is not performed automatically by
passing the eligibility check, and updates the guard tests in
`tests/test_martin_publication_contract.py` that currently assert the
non-published state (`test_canary_is_validated_but_not_published`,
`test_production_ingress_authorizes_no_sources_today`). Tile geometry is a
derived clipped/quantized manifestation and must not replace the canonical
source geometry.

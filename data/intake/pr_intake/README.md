# PR-intake dropzone (spiderweb-pr spatial/operational lane, #41)

> **⚠️ Deprecated (2026-06): receiver retired.** spiderweb-pr became a producer-only
> federation node. The receiver workflow `.github/workflows/intake-normalize.yml` was
> **deleted**, and the normalizer now lives at
> `docs/legacy/scripts/build_spiderweb_spatial_lane.py` (via
> `docs/legacy/readiness/spiderweb_spatial_lane.py`). Delivered derivatives are **no
> longer auto-normalized**. Contract-Sweeper also retired its cross-repo delivery
> (its `intake-delivery.yml` no longer pushes here). Kept as historical reference;
> see `docs/REPO_BOUNDARY.md`.

The Contract-Sweeper PR-intake router delivers this repo's lane export here:

```
data/intake/pr_intake/spiderweb_pr_derivatives.csv
```

`scripts/build_spiderweb_spatial_lane.py --input data/intake/pr_intake` (via
`readiness/spiderweb_spatial_lane.py`) normalizes it into the spatial/operational
tables under `data/normalized/`, candidate geojsons under `data/exports/`, and
review queues under `data/review/` — zero-loss.

Delivery into this directory is handled by the Contract-Sweeper
`intake-delivery.yml` workflow (cross-repo PR, gated on a `FEDERATION_DELIVERY_TOKEN`
PAT); `.github/workflows/intake-normalize.yml` here normalizes a delivered file.
See `Contract-Sweeper/docs/INTAKE_DELIVERY.md` for the full chain.

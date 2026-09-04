# Spatial Registry

Expected file:

```text
pr_grid_full_cell_index_saturated.csv
```

Expected SHA-256:

```text
17733f3f18c8a644e31c1eb25fb27b73b4bf353c6de57d5203c4311e05d64483
```

The full CSV is 6,807,952 bytes and contains 98,304 grid cells.

Validation command:

```bash
python scripts/validate_pr_grid.py --require-sha
```

## Geographic geometry layer

The CSV above is a *logical* index: 4x4-pixel cells over a 1536x1024 rendered
canvas, with pixel bounds and no Earth coordinates. The geometry layer projects
it into WGS84.

```bash
python -m pipeline.grid_georeference --emit-transform   # transform + certification
python -m pipeline.build_cell_geometry                  # 98,304 cell polygons
python scripts/validate_spatial_registry.py             # gates
```

`registry/spatial/geometry/pr_grid_cell_geometry.geojsonl` is a build product
(~62 MiB) and is not tracked. It is a deterministic function of the transform
record and the frozen grid, so CI rebuilds it and compares `sha256` against
`pr_grid_geometry_manifest.json`.

### Certification state: PROVISIONAL

The source image was authored to scale on WGS84, which fixes the *model* —
uniform degrees-per-pixel, no rotation — and an independent fit agrees
(anisotropy ~1.02). The *parameters* are not recovered. The derivation to CSV
discarded the georeference, and candidate scales from 512 to 683 px/degree all
score within noise of one another against the coastline cells.

The authored bounds `W -67.30, E -65.20, S 17.92, N 18.65` are recorded in the
transform record as provenance with status `DOCUMENTED_UNVERIFIED`. They do not
reproduce this canvas: their aspect is 2.877 against the canvas's 1.500, and
under every framing tried (fill, centred letterbox, best-offset letterbox, and
bounds-as-island-extent) the archipelago comes out near half its true
north-south extent. Geometry is therefore not derived from them.

While `PROVISIONAL`, `TRANSFORM_CERTIFICATION_GATE` caps every cell-to-source
binding and `configs/spatial_dataset_providers.json` keeps its
`blocked_pending_certified_georeference` status. Promotion to `VERIFIED` needs
independently supplied parameters that pass both assertions — a fitted transform
scored against the cells it was fitted to is circular and can never certify
itself.

**Fastest route to `VERIFIED`:** recover the original 1536x1024 image, its world
file, or the script that rasterised it. The CSV is a lossy derivative; the
georeference lives in the artifact that produced it.

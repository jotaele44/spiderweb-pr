# API reference (T12-99)

The public Python modules are PEP 561-typed (each shipped package carries a
`py.typed` marker), so editors and `mypy` resolve their types directly. For a
browsable HTML reference, generate it on demand with [`pdoc`](https://pdoc.dev)
— no committed build artifact, no extra CI job.

## Generate locally

```bash
pip install pdoc
pdoc -o site/api \
  pipeline integration federation readiness provenance_utils run_modes release_check
open site/api/index.html   # macOS; use xdg-open on Linux
```

## HTTP API

The FastAPI backend (`server/backend/main.py`) documents its own routes: run it
and open `/docs` (Swagger UI) or `/openapi.json`. The NOAA aerial imagery routes
are the ones the Spatial map's "Aerial imagery" controls call:

| Route | Returns |
|---|---|
| `GET /imagery/eri/datasets` | The flights registered in `configs/eri_imagery_sources.yaml` (id, label, event, date, extent, zoom range, link to the flight in the NOAA bucket). `503` if the registry is unavailable. |
| `GET /imagery/eri/{dataset_id}/footprints.geojson` | One polygon per source image, decoded from the bucket's key listing, with the image name, size and source URL. Listed once, then cached under `cache/eri_imagery/`. `502` if the bucket cannot be listed. |
| `GET /imagery/eri/{dataset_id}/tiles/{z}/{x}/{y}.png` | A 256 px Web-Mercator RGBA tile composited from the images under it; transparent where the flight has no coverage. `404` outside the flight's zoom range or for an unknown flight, `502` if no image under the tile could be read, `503` without `rasterio`. |

The bucket publishes GeoTIFFs in EPSG:4326 and no tile pyramid, which is why the
tiles are rendered here. Only flights in the registry can be requested; no
request parameter names a host or an object key. Rendering needs `rasterio` and
`PyYAML`, both in the `server` extra.

## Key public entry points

| Module | Purpose |
|---|---|
| `run_all` | Unified pipeline CLI (`spiderweb-run`). |
| `release_check` | Release gate (`spiderweb-release-check`). |
| `integration.ilap_airspace_bridge` / `integration.aasb_airspace_bridge` | Spiderweb GeoJSON/CSV producers. |
| `integration.mbil` | MBIL municipal-proximity scoring. |
| `integration.kml_export` | Native GeoJSON→KML serializer. |
| `federation.envelope` | Cross-repo evidence envelope + `CONTRACT_VERSION`. |
| `federation.hub.query` | Cross-producer correlation query. |
| `pipeline.logging_config` / `pipeline.config_loader` / `pipeline.seeding` / `pipeline.path_safety` | Observability + robustness helpers. |
| `provenance_utils` | Reproducibility metadata + GeoJSON `_meta`. |

The curated lint/type allowlist in `.github/workflows/ci.yml` tracks which
modules are fully ruff/black/mypy-clean today; it grows over time.

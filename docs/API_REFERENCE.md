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

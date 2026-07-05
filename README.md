# spiderweb-pr — Spatial / Operational Producer (PRII federation)

[![CI](https://github.com/jotaele44/spiderweb-pr/actions/workflows/ci.yml/badge.svg)](https://github.com/jotaele44/spiderweb-pr/actions/workflows/ci.yml)
[![coverage](https://img.shields.io/badge/coverage-%E2%89%A564%25-brightgreen)](https://github.com/jotaele44/spiderweb-pr/actions/workflows/ci.yml)
[![python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)](pyproject.toml)

`spiderweb-pr` is the spatial / operational producer node for the Puerto Rico Integrated Intelligence (PRII) federation. It prepares GIS-linked records, operational context, provenance, confidence metadata, and review outputs for federation aggregation in [`thehub-pr`](https://github.com/jotaele44/thehub-pr).

> **Boundary update:** FlightRadar24 screenshot ingestion, FR24 route extraction, and the active airspace observation export now belong to [`skywatcher-pr`](https://github.com/jotaele44/skywatcher-pr). Spiderweb keeps legacy spatial bridge logic and retained integration exports, but it is not the active FR24 owner.

> **Status:** diagnostic / integration-ready only after validation gates pass. Run `--validate` and review `integration_report.json` before promoting outputs.

## Federation role

| Field | Value |
|---|---|
| Program id | `spiderweb-pr` |
| Parent hub | [`thehub-pr`](https://github.com/jotaele44/thehub-pr) |
| Primary function | Spatial / operational export package producer |
| Airspace producer | [`skywatcher-pr`](https://github.com/jotaele44/skywatcher-pr) |

Cross-producer correlation is owned by the Hub and downstream consumers. Spiderweb should emit clean, reviewable records; it should not duplicate Hub-level correlation authority.

## Scope boundaries

| Domain | Owner |
|---|---|
| Spatial bridge records and GIS-linked review exports | `spiderweb-pr` |
| FR24 ingestion and airspace observations | `skywatcher-pr` |
| Public-money and procurement records | `moneysweep-pr` / `moneysweep-pr` |
| Water, wastewater, power, outage, and recovery records | `aguayluz-pr` |
| Puerto Rico historical case corpus | `OVNIS` / `ovnis-pr` |
| Producer discovery, validation, aggregation, and cross-producer correlation | `thehub-pr` |

## Quick start

```bash
pip install -e ".[airspace]"
python run_all.py --status
python run_all.py --images 10
python run_all.py --db flight_database.db --validate
python run_all.py --db flight_database.db --export-pr-intel ./outputs/pr_intel
python run_all.py --db flight_database.db --export-spiderweb ./outputs/spiderweb
```

## Main outputs

| Output | Purpose |
|---|---|
| `integration_report.json` | Validation gate report |
| `source_manifest.json` | File inventory and row counts |
| `review_queue.csv` | Low-confidence rows requiring review |
| `*.parquet` | Structured retained records |
| `*.geojson` | GIS-linked features and bridge candidates |
| `aasb_airspace_edges.csv` | Airport-node edge list retained for bridge review |

## Development gates

```bash
python -m pytest -q
python run_all.py --db flight_database.db --validate
```

## Documentation

[Docs index](docs/README.md) · [Architecture](docs/ARCHITECTURE.md) · [Execution Guide](docs/EXECUTION_GUIDE.md) · [Testing](docs/TESTING.md) · [Data Policy](docs/DATA_POLICY.md) · [Repo boundary](docs/REPO_BOUNDARY.md) · [Roadmap (V2)](docs/NEXT_100_TASKS_V2.md) · [Task Ledger](docs/ROI_TASK_LEDGER.md) · [Changelog](CHANGELOG.md)

## USGS OFR 98-038 Puerto Rico geology / mineral layers

Spiderweb tracks the USGS Open-File Report 98-038 Puerto Rico geology/mineral package as a structural-geodata baseline. The source package covers geologic maps, faults, gravity, magnetic, mineral occurrence, terrane, placer drainage, Vieques, Mona, and Puerto Rico outline layers.

Tracked registry files:

- `data/usgs_ofr_98_038/registry/usgs_ofr_98_038_manifest.json`
- `data/usgs_ofr_98_038/registry/usgs_ofr_98_038_layers.csv`
- `data/usgs_ofr_98_038/docs/README_USGS_OFR_98_038_BUILD.md`

Normalized lightweight derivative:

- `data/usgs_ofr_98_038/derived/usgs_ofr_98_038_metallic_occurrences_wgs84.geojson`

Raw ARC/INFO `.e00`, GeoPackage, ZIP, and shapefile binaries remain local/ignored unless explicitly force-added for release packaging.

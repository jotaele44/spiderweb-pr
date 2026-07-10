# Data Policy

Defines what is and is not committed to the repository, and how runtime artifacts should be managed.

---

## Directory conventions

| Directory | Committed | Purpose | Owner |
|-----------|-----------|---------|-------|
| `outputs/` | `.gitkeep` only | All runtime outputs (parquet, GeoJSON, JSON, JSONL, CSV reports) | All modules |
| `data/` | `.gitkeep` only | Input datasets (screenshots, GEBCO .nc, social CSV) | All modules |
| `cache/` | Never | Spiderweb intermediate results, model caches | Spiderweb |
| `tile_cache/` | `.gitkeep` only | EarthGPT XYZ tile PNGs | EarthGPT iOS |

**Never commit** files in `outputs/`, `data/`, `cache/`, or `tile_cache/`. The `.gitignore` enforces this for `outputs/*.jsonl`, `outputs/*.geojson`, and `tile_cache/*.png`. The `.gitkeep` files preserve directory structure in git.

---

## What IS committed

- All Python source files and packages
- `schemas/` — JSON Schema definitions
- `configs/georef_anchors.csv` — 5 static PR airport anchor coordinates
- `constraints.txt` — exact pip reproducibility pins for GEBCO
- `pyproject.toml` — GEBCO package metadata
- `requirements*.txt` — dependency declarations
- `tests/` — all test files and fixtures
- `docs/` — this documentation
- `.github/workflows/ci.yml` — CI pipeline definition
- `dashboard/dashboard.html` / `dashboard/dashboard.jsx` — browser dashboard
- Source-adapter manifests and coverage ledgers when they are small, non-sensitive, and needed for reproducibility

---

## What is NEVER committed

| Type | Examples | Reason |
|------|----------|--------|
| Screenshot images | `*.jpg`, `*.png` flight screenshots | Binary, large, potentially sensitive |
| GEBCO bathymetry grid | `GEBCO_2023.nc` (~7 GB) | Binary, too large, freely downloadable |
| Social media CSV | `PRUAP_MASTER_SOCIAL.csv` | May contain personal data |
| SQLite databases | `*.db`, `flight_database.db` | Runtime state, potentially large |
| Parquet files | `*.parquet` | Binary runtime output |
| Vector index | `outputs/pruap_index/` (ChromaDB) | Runtime artifact |
| API keys / tokens | `.env`, `HF_TOKEN` | Credentials |
| Tile PNG cache | `tile_cache/*.png` | Binary, regenerable |
| JSONL outputs | `outputs/*.jsonl` | Runtime artifact |
| GeoJSON outputs | `outputs/*.geojson` | Runtime artifact |
| Raw source downloads | Census ZIPs, extracted shapefiles, temporary batch folders | Regenerable input payloads |

---

## Source adapter policy

Source adapters should prefer on-demand acquisition plus small provenance records over committed raw data dumps.

For the Census Partnership Puerto Rico adapter, commit only documentation, source manifests, SHA256 manifests, coverage ledgers, and promoted normalized GIS outputs. Do not commit raw Census ZIP files, extracted shapefile trees, partial downloads, or temporary batch folders. See `docs/source_adapters/census_partnership_pr.md` for the adapter-specific rule set.

---

## Sensitive data handling

**Social media data** (`PRUAP_MASTER_SOCIAL.csv`): Contains Reddit posts about UAP/UFO sightings. Do not commit. Store in `data/` locally. De-identify before sharing outputs.

**Flight track data**: Derived from public FlightRadar24 screenshots. The raw screenshots and the SQLite DB that stores extracted coordinates should not be shared without verifying they do not expose non-public operational flight details.

**EarthGPT outputs** (`outputs/ranked_targets.geojson`): Satellite anomaly coordinates. Do not share publicly without review.

**HF tokens**: If using gated Hugging Face models (e.g., Llama), set `HF_TOKEN` as an environment variable. Never hardcode or commit tokens.

```bash
# Correct
export HF_TOKEN=hf_...
python llm/query_llm.py "..."

# Wrong — never do this
# python llm/query_llm.py "..." --token hf_...  (if you add such a flag)
```

---

## Clearing runtime artifacts

```bash
# Clear all outputs (keeps .gitkeep)
find outputs/ -not -name '.gitkeep' -delete

# Clear tile cache
find tile_cache/ -name '*.png' -delete
```

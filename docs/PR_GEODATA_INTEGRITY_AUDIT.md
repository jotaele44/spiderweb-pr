# PR Geodata Integrity Audit

This is a local file-integrity check for the reorganized `PR_Geodata/` folder.

It should be run before any Puerto Rico DEM, vector, or scoring workflow uses the local datasets.

## Checks included

| Check group | Purpose |
|---|---|
| DEM inventory | Confirms expected tile count, total size, and zero-byte status |
| DEM CRS and resolution | Confirms sampled tiles are readable when raster tools are installed |
| Shapefile sidecars | Confirms every `.shp` has `.shx`, `.dbf`, and `.prj` siblings |
| GPKG / GDB containers | Confirms vector container presence and optional layer readability |
| Road-like layer names | Confirms readable vector containers include road or edge layer names |
| Repo path scan | Finds stale pre-reorganization path references |

## Output files

Default output folder:

```bash
outputs/pr_geodata_audit/
```

Generated reports:

| File | Purpose |
|---|---|
| `PR_GEODATA_INTEGRITY_GO_NO_GO.md` | Human-readable status report |
| `pr_geodata_integrity_audit.json` | Machine-readable full audit |
| `pr_geodata_integrity_findings.csv` | CSV findings table |

## Status meanings

| Status | Meaning |
|---|---|
| `GO` | No FAIL or WARN findings |
| `CONDITIONAL_GO` | No FAIL findings, but WARN findings need review |
| `NO_GO` | At least one FAIL finding exists |

## Optional GIS packages

The script runs with standard Python. For stronger CRS and vector checks, install:

```bash
pip install rasterio fiona pyogrio
```

If these are not installed, the audit still checks folder structure, counts, file sizes, shapefile sidecars, and stale path references.

## Normal run

From the repository root:

```bash
python tools/pr_geodata_integrity_audit.py \
  --geodata-root "~/Documents/Data/PR_Geodata" \
  --repo-root "."
```

## Structural-only run

Use this when you want to avoid opening large raster or vector files:

```bash
python tools/pr_geodata_integrity_audit.py \
  --geodata-root "~/Documents/Data/PR_Geodata" \
  --repo-root "." \
  --no-raster-read \
  --no-vector-read
```

## Full DEM CRS inventory

The default samples DEM tiles. To check every tile:

```bash
python tools/pr_geodata_integrity_audit.py \
  --geodata-root "~/Documents/Data/PR_Geodata" \
  --repo-root "." \
  --all-dem-crs
```

## Strict mode

Strict mode treats WARN findings as `NO_GO`:

```bash
python tools/pr_geodata_integrity_audit.py \
  --geodata-root "~/Documents/Data/PR_Geodata" \
  --repo-root "." \
  --strict
```

## Expected folder layout

```text
PR_Geodata/
  01_DEM_1m_LiDAR/
  03_Geodatabases/
  05_Vector_Shapefiles/
```

Default expected DEM tile count: `191`.

Expected sampled DEM CRS values:

```text
EPSG:26919
EPSG:26920
```

## Next step after a clean audit

Run a one-tile pilot first, verify that real output files were created, then expand in batches.

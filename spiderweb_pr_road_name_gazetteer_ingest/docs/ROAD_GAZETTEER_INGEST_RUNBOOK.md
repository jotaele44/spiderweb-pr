# Road gazetteer ingest runbook

## 0. Confirm source acquisition

Expected raw files:

```text
data/reference/roads/raw/tiger2025/tl_2025_72001_roads.zip
...
data/reference/roads/raw/tiger2025/tl_2025_72153_roads.zip
data/reference/roads/raw/osm/puerto-rico-latest-free.gpkg.zip or extracted GPKG
data/reference/roads/raw/dtop/<authoritative route dataset>
```

## 1. Download TIGER + OSM

```bash
python3 pipeline/download_road_sources.py --all
```

## 2. Unzip OSM GPKG if needed

```bash
mkdir -p data/reference/roads/raw/osm/extracted
unzip data/reference/roads/raw/osm/puerto-rico-latest-free.gpkg.zip -d data/reference/roads/raw/osm/extracted
```

## 3. Add DTOP/ACT authoritative file

Place any DTOP/ACT route source under `data/reference/roads/raw/dtop/`.

Optional `dtop_column_map.json` example:

```json
{
  "source_record_id": "OBJECTID",
  "road_name": "NOMBRE",
  "route_number": "RUTA",
  "road_class": "CLASE",
  "municipio": "MUNICIPIO"
}
```

## 4. Run ingest

```bash
python3 pipeline/execute_road_gazetteer_ingest.py
```

## 5. QA gates

Check:

```text
data/reference/roads/processed/road_ingest_report.json
data/reference/roads/processed/road_ingest_source_manifest.csv
data/reference/roads/processed/road_source_conflicts.csv
```

Promote only after:

- TIGER count equals 78 PR municipio files.
- DTOP source is present or explicitly waived.
- OSM source has been used only as T3 alias/context.
- `road:*` outputs do not include `gnis:*` features.

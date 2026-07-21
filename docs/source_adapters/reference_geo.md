# Reference / environmental geography adapters

`server/ingestion/ingest_reference_geo.py` provides reproducible, live-source
adapters for three catalogued Puerto Rico reference layers. These layers already
had operator-local GPKG producers in `scripts/populate_dataset_layers.py`
(`NID_v1_*.gpkg`, `Spiderweb_Master_Warehouse`, `Gazetteer_PR_GPKG.gpkg`); this
adapter adds an authoritative, dated, provenance-tracked path that does **not**
depend on those undated operator snapshots, and turns `wetlands_nwi_prvi` (which
was `reference_only`) into an actually-served layer.

## Sources

| Layer | Source | Endpoint | Geometry |
| --- | --- | --- | --- |
| `nid_dams` | National Inventory of Dams (USACE) | `https://nid.sec.usace.army.mil/api/nation/csv` (national CSV, filter `State == PR`) | point |
| `gazetteer_pr_domestic_names` | USGS GNIS Domestic Names | National Map S3 `StagedProducts/GeographicNames/DomesticNames/DomesticNames_PR_Text.zip` (pipe-delimited, filter `state_numeric == 72`) | point |
| `wetlands_nwi_prvi` | USFWS National Wetlands Inventory | ArcGIS `Wetlands/MapServer/0` tiled + paginated queries over the PR bbox, deduped by `OBJECTID` | polygon |

The GNIS/NWI download systems moved from their older direct-download URLs (the
old `geonames.usgs.gov` state zip and `fws.gov/wetlands/Data/State-Downloads`
paths are now 503/404); the endpoints above are the current live locations.

**NWI serving size:** the raw NWI layer is ~16.5k polygons and huge (~110 MB),
dominated by very large offshore *Estuarine and Marine Deepwater* polygons. The
adapter therefore, by default, **drops the deepwater class** and **topologically
simplifies** each kept polygon (`shapely`, ~0.0001° ≈ 11 m) on top of 5-dp
coordinate rounding — an ~89% size reduction on coastal samples, bringing the
served layer well under ~20 MB while keeping the true wetland footprints. Opt out
with `--nwi-include-deepwater` and tune with `--nwi-simplify-tol` (0 disables).
The `wetlands_nwi_prvi` manifest records `dropped_deepwater`, `simplify_tol`, and
`include_deepwater`.

## Scope note

These are static reference geographies — a dam inventory, a place-name
gazetteer, and wetland footprints — distinct from the operational
water/wastewater/power/outage **records** owned by `aguayluz-pr` per the
`README.md` scope table. They are in scope for spiderweb's spatial/reference
role.

## Repository policy

Per `docs/DATA_POLICY.md`, only the small per-layer provenance manifests are
tracked (`data/reference_geo/<layer>_manifest.json`); raw source caches
(`data/reference_geo/cache/`) and the regenerable `data/<layer>.geojson` outputs
are git-ignored runtime artifacts.

## Commands

```bash
# all three (NWI is a multi-minute tiled fetch)
python server/ingestion/ingest_reference_geo.py --source all

# a single source, or a dry run (fetch + build, write nothing)
python server/ingestion/ingest_reference_geo.py --source nid
python server/ingestion/ingest_reference_geo.py --source gnis --dry-run
```

## Serving

The three layer ids are registered in `configs/layer_catalog.yaml`
(`pipeline_wired: true`) and in the `/geo/{layer}.geojson` allowlist
(`server/backend/main.py::_FALLBACK_LAYERS`), and are served from
`data/<layer>.geojson` by `_find_geojson`.

## Tests

`tests/test_reference_geo_adapter.py` covers the pure helpers and the source
contract offline; the live fetchers run under `pytest -m integration`.

# PR DEM One-Tile Pilot

This guide runs the local file audit, processes one DEM GeoTIFF, verifies that output files exist, and checks that `ILAP_SCORE` equals the sum of component score columns.

## 1. Install local dependencies

```bash
pip install rasterio numpy scipy fiona pyogrio
```

`scipy`, `fiona`, and `pyogrio` improve speed and vector checks. The one-tile DEM pilot requires `rasterio` and `numpy`.

## 2. Run the PR_Geodata integrity audit

```bash
python tools/pr_geodata_integrity_audit.py \
  --geodata-root "~/Documents/Data/PR_Geodata" \
  --repo-root "."
```

Open this report:

```bash
cat outputs/pr_geodata_audit/PR_GEODATA_INTEGRITY_GO_NO_GO.md
```

Proceed only after all `FAIL` findings are resolved. A `CONDITIONAL_GO` is acceptable only when the remaining warnings are understood.

## 3. Select one DEM tile

This command selects the first GeoTIFF in the DEM folder and stores its path in `DEM_TILE`:

```bash
DEM_TILE=$(find ~/Documents/Data/PR_Geodata/01_DEM_1m_LiDAR -type f \( -iname "*.tif" -o -iname "*.tiff" \) | head -n 1)
echo "$DEM_TILE"
```

## 4. Run the one-tile pilot

```bash
python tools/pr_dem_one_tile_pilot.py \
  --dem-tile "$DEM_TILE" \
  --output-dir outputs/pr_dem_one_tile_pilot \
  --target-resolution-m 5
```

Expected files:

```text
outputs/pr_dem_one_tile_pilot/pr_dem_one_tile_candidates.csv
outputs/pr_dem_one_tile_pilot/pr_dem_one_tile_candidates.geojson
outputs/pr_dem_one_tile_pilot/pr_dem_one_tile_manifest.json
```

## 5. Verify output files exist and are non-empty

```bash
test -s outputs/pr_dem_one_tile_pilot/pr_dem_one_tile_candidates.csv && echo "CSV exists"
test -s outputs/pr_dem_one_tile_pilot/pr_dem_one_tile_candidates.geojson && echo "GeoJSON exists"
test -s outputs/pr_dem_one_tile_pilot/pr_dem_one_tile_manifest.json && echo "Manifest exists"
```

## 6. Run the score-sum sanity check

```bash
python tools/verify_ilap_score_sum.py \
  --csv outputs/pr_dem_one_tile_pilot/pr_dem_one_tile_candidates.csv \
  --output-json outputs/pr_dem_one_tile_pilot/score_sum_check.json
```

The check passes only when every row satisfies:

```text
ILAP_SCORE = score_flat_patch + score_edge_contrast + score_high_local_position
```

## 7. Inspect top rows

```bash
python - <<'PY'
import csv
p = 'outputs/pr_dem_one_tile_pilot/pr_dem_one_tile_candidates.csv'
with open(p, newline='', encoding='utf-8') as f:
    rows = list(csv.DictReader(f))
print('rows:', len(rows))
for r in rows[:10]:
    print(r['candidate_id'], r['ILAP_SCORE'], r['review_class'], r['lon'], r['lat'], r['area_m2'])
PY
```

## Expansion rule

Do not expand beyond one tile until:

1. The integrity audit has no unresolved `FAIL` findings.
2. The CSV, GeoJSON, and manifest exist and are non-empty.
3. The score-sum check returns `PASS`.
4. The top candidate rows make visual/geographic sense in QGIS.

After that, expand to a small named batch, then to larger batches.

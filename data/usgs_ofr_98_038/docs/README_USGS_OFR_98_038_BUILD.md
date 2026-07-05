# USGS OFR 98-038 build package

This package was built from the uploaded `all_export_files.zip` and `Metadata__metallic_points_WGS84.zip`.

## Build outputs

- Raw ARC/INFO export coverages: `38` files under `raw/export/`.
- Metallic occurrence derivative: `364` WGS84 point features under `derived/`.
- Dataset manifest: `registry/usgs_ofr_98_038_manifest.json`.
- Layer registry: `registry/usgs_ofr_98_038_layers.csv`.

## Conversion status

Full E00 coverage conversion remains queued because this execution environment does not include the GDAL/AVCE00 conversion stack. The build does not invent full converted coverages. It preserves the raw E00 package and creates a verified derivative from `metallic.e00` LAB coordinates.

GPKG status: `created`.

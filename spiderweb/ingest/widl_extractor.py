from __future__ import annotations

from pathlib import Path
import yaml
import geopandas as gpd

from spiderweb.ingest.gpkg_loader import GPKGLoader


DEFAULT_MAPPING_PATH = "configs/layers/pri_layer_mapping.yml"


def load_layer_mapping(mapping_path: str = DEFAULT_MAPPING_PATH) -> dict:
    with open(mapping_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def extract_widl_nodes(
    gpkg_path: str,
    mapping_path: str = DEFAULT_MAPPING_PATH,
    target_crs: str = "EPSG:4326",
) -> gpd.GeoDataFrame:
    """Extract configured WIDL and utility nodes from a GeoPackage.

    Large input files are intentionally read layer-by-layer. Missing configured
    layers are skipped so the extractor can run across partial datasets.
    """
    loader = GPKGLoader(gpkg_path)
    available_layers = set(loader.list_layers())
    mapping = load_layer_mapping(mapping_path)

    node_layers = {}
    node_layers.update(mapping.get("widl_nodes", {}))
    node_layers.update(mapping.get("utility_nodes", {}))

    frames = []
    for layer_name, node_type in node_layers.items():
        if layer_name not in available_layers:
            continue

        gdf = loader.load_layer(layer_name)
        if gdf.empty:
            continue

        if gdf.crs is None:
            gdf = gdf.set_crs(target_crs)
        elif str(gdf.crs) != target_crs:
            gdf = gdf.to_crs(target_crs)

        gdf = gdf.copy()
        gdf["source_layer"] = layer_name
        gdf["node_type"] = node_type
        gdf["node_id"] = [f"{node_type}_{layer_name}_{i}" for i in range(len(gdf))]
        frames.append(gdf[["node_id", "node_type", "source_layer", "geometry"]])

    if not frames:
        return gpd.GeoDataFrame(
            columns=["node_id", "node_type", "source_layer", "geometry"],
            geometry="geometry",
            crs=target_crs,
        )

    return gpd.GeoDataFrame(
        gpd.pd.concat(frames, ignore_index=True),
        geometry="geometry",
        crs=target_crs,
    )


def extract_icg_edges(
    gpkg_path: str,
    mapping_path: str = DEFAULT_MAPPING_PATH,
    target_crs: str = "EPSG:4326",
) -> gpd.GeoDataFrame:
    loader = GPKGLoader(gpkg_path)
    available_layers = set(loader.list_layers())
    mapping = load_layer_mapping(mapping_path)

    frames = []
    for layer_name, edge_type in mapping.get("icg_edges", {}).items():
        if layer_name not in available_layers:
            continue

        gdf = loader.load_layer(layer_name)
        if gdf.empty:
            continue

        if gdf.crs is None:
            gdf = gdf.set_crs(target_crs)
        elif str(gdf.crs) != target_crs:
            gdf = gdf.to_crs(target_crs)

        gdf = gdf.copy()
        gdf["source_layer"] = layer_name
        gdf["edge_type"] = edge_type
        gdf["edge_id"] = [f"{edge_type}_{layer_name}_{i}" for i in range(len(gdf))]
        frames.append(gdf[["edge_id", "edge_type", "source_layer", "geometry"]])

    if not frames:
        return gpd.GeoDataFrame(
            columns=["edge_id", "edge_type", "source_layer", "geometry"],
            geometry="geometry",
            crs=target_crs,
        )

    return gpd.GeoDataFrame(
        gpd.pd.concat(frames, ignore_index=True),
        geometry="geometry",
        crs=target_crs,
    )

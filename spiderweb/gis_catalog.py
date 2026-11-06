"""Build the gis-layer-catalog/1.0 document served at GET /gis/catalog.

Joins three existing registries without replacing any of them:

* ``configs/layer_catalog.yaml`` -- folder tree, labels, visibility gate
  (``visibility_classes`` V1/V2/V3 -> ``access_default``) and registry status;
* ``configs/spatial_layer_bindings.yaml`` -- rendering binding (format);
* ``configs/gis_layer_interaction.yaml`` -- identify/search/query metadata.

Pure: the caller loads the YAML and supplies a ``data_available`` probe.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

CONTRACT_CATALOG = "gis-layer-catalog/1.0"
PRODUCER_REPO = "spiderweb-pr"
GENERATED_FROM = (
    "configs/layer_catalog.yaml",
    "configs/spatial_layer_bindings.yaml",
    "configs/gis_layer_interaction.yaml",
)
_STATUS_MAP = {
    "active": "active",
    "wired": "active",
    "deferred": "deferred",
    "blocked": "blocked",
}
_BINDING_KIND = {
    "geojson": "geojson",
    "pmtiles": "vector_tiles",
    "terrain": "raster_dem",
}


class GisCatalogError(ValueError):
    """The interaction registry names a layer the layer catalog does not."""


def _catalog_layers(
    layer_catalog: Mapping[str, Any],
) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    out = []
    for family in layer_catalog.get("families") or []:
        for layer in family.get("layers") or []:
            out.append((family, layer))
    return out


def validate_interaction_registry(
    layer_catalog: Mapping[str, Any], interaction: Mapping[str, Any]
) -> None:
    known = {layer["layer_id"] for _family, layer in _catalog_layers(layer_catalog)}
    unknown = sorted(set((interaction.get("layers") or {}).keys()) - known)
    if unknown:
        raise GisCatalogError(
            f"gis_layer_interaction.yaml names layers missing from layer_catalog.yaml: {unknown}"
        )


def build_gis_catalog(
    layer_catalog: Mapping[str, Any],
    bindings: Mapping[str, Any],
    interaction: Mapping[str, Any],
    *,
    data_available: Callable[[str], bool] | None = None,
    geojson_url: Callable[[str], str] = lambda layer_id: f"/geo/{layer_id}.geojson",
) -> dict[str, Any]:
    validate_interaction_registry(layer_catalog, interaction)
    visibility = layer_catalog.get("visibility_classes") or {}
    binding_by_id = {
        b["layer_id"]: b for b in bindings.get("bindings") or [] if "layer_id" in b
    }
    interaction_layers = interaction.get("layers") or {}
    default_modes = list((interaction.get("defaults") or {}).get("query_modes") or [])

    layers: list[dict[str, Any]] = []
    for family, layer in _catalog_layers(layer_catalog):
        layer_id = layer["layer_id"]
        meta = interaction_layers.get(layer_id) or {}
        vclass = family.get("visibility")
        access = (
            (visibility.get(vclass) or {}).get("access_default") if vclass else None
        )
        binding = binding_by_id.get(layer_id)
        kind = _BINDING_KIND.get((binding or {}).get("format", "geojson"), "none")
        status = _STATUS_MAP.get(
            str(layer.get("status", "deferred")).lower(), "deferred"
        )
        entry: dict[str, Any] = {
            "layer_id": layer_id,
            "title": layer.get("label") or layer_id,
            "category": family.get("label") or family.get("id") or "uncategorised",
            "group": family.get("id"),
            "visibility_class": vclass,
            "access_default": access,
            "status": status,
            "blocked_reason": meta.get("blocked_reason"),
            "source": {
                "kind": kind,
                "url": geojson_url(layer_id) if kind == "geojson" else None,
                "source_layer": None,
            },
            "geometry_types": list(meta.get("geometry_types") or []),
            "min_zoom": meta.get("min_zoom"),
            "max_zoom": meta.get("max_zoom"),
            "default_visible": bool(meta.get("default_visible", False)),
            "identify_fields": list(meta.get("identify_fields") or []),
            "search_fields": list(meta.get("search_fields") or []),
            "query_modes": list(meta.get("query_modes") or default_modes),
            "temporal_field": meta.get("temporal_field"),
            "classification": meta.get("classification"),
            "classification_blocked_reason": meta.get("classification_blocked_reason"),
            "precision_field": meta.get("precision_field"),
            "precision_max_zoom": meta.get("precision_max_zoom"),
            "documents_ref": meta.get("documents_ref"),
            "network_ref": meta.get("network_ref"),
            "exportable": access == "PUBLIC",
            "federation_layer_id": meta.get("federation_layer_id"),
        }
        if data_available is not None:
            entry["data_available"] = bool(data_available(layer_id))
        layers.append(entry)

    return {
        "contract_version": CONTRACT_CATALOG,
        "producer_repo": PRODUCER_REPO,
        "generated_from": list(GENERATED_FROM),
        "layers": layers,
    }

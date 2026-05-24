from dataclasses import dataclass


@dataclass
class WIDLNode:
    node_id: str
    node_type: str
    source_layer: str
    geometry_wkt: str
    hydro_region: str | None = None

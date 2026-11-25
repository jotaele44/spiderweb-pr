"""Location context for GET /gis/identify in spiderweb-pr.

Two lookups for a clicked WGS84 point:

* which administrative boundary feature contains it (municipio, barrio, ...);
* which PR_GRID_GEOGRAPHIC_V2 cell(s) the point falls in.

The grid lookup is a *cursor lookup*: the clicked point is not a
VERIFIED_SOURCE_COORDINATE, so the result is reported as COMPUTED context and
explicitly marked as not being a record-cell binding (record bindings go
through spiderweb/grid_v2_source_coordinates.py and its evidence gates).
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from spiderweb import geographic_grid_v2 as grid
from spiderweb import gis_query as gq


def containing_feature(
    features: Sequence[Mapping[str, Any]],
    lon: float,
    lat: float,
    *,
    name_fields: Sequence[str] = ("NAME", "name"),
    id_fields: Sequence[str] = ("GEOID", "geoid"),
) -> dict[str, Any] | None:
    """First polygon feature containing the point (boundary inclusive)."""
    point = (float(lon), float(lat))
    for feature in features:
        parts = gq.feature_parts(feature)
        if parts is None or not parts.polygons:
            continue
        if any(gq.point_in_polygon(point, rings) for rings in parts.polygons):
            props = feature.get("properties") or {}
            name = next(
                (props[k] for k in name_fields if props.get(k) not in (None, "")), None
            )
            ident = next(
                (props[k] for k in id_fields if props.get(k) not in (None, "")), None
            )
            return {"name": name, "id": None if ident is None else str(ident)}
    return None


def grid_v2_cursor_lookup(
    lon: float, lat: float, *, level: str = "L3"
) -> dict[str, Any]:
    """PR Grid V2 cell(s) under a clicked point, or an UNAVAILABLE/OUTSIDE status."""
    base = {
        "grid_id": grid.GRID_ID,
        "grid_version": grid.GRID_VERSION,
        "crs": grid.CRS,
        "level": level,
        "binding": "CURSOR_LOOKUP_NOT_RECORD_BINDING",
        "evidence_state": "COMPUTED",
    }
    try:
        from pyproj import Transformer
        from pyproj.exceptions import ProjError
    except ImportError:
        return {
            **base,
            "status": "UNAVAILABLE",
            "reason": "pyproj is not installed",
            "cell_ids": [],
        }
    try:
        transformer = Transformer.from_crs(
            "EPSG:4326", grid.CRS, always_xy=True, allow_ballpark=False, only_best=True
        )
        x, y = transformer.transform(float(lon), float(lat), errcheck=True)
    except (ProjError, ValueError, TypeError) as exc:
        return {
            **base,
            "status": "UNAVAILABLE",
            "reason": f"transform failed: {exc}",
            "cell_ids": [],
        }
    binding = grid.bind_point(x, y, level=level, crs=grid.CRS)
    return {
        **base,
        "status": "OUTSIDE" if binding.state == grid.BoundaryState.OUTSIDE else "OK",
        "boundary_state": binding.state.value,
        "cell_ids": list(binding.cell_ids),
        "projected": {"x": round(x, 3), "y": round(y, 3)},
    }

"""Top-down (planimetric) map view."""

from __future__ import annotations

import math
from typing import Any

from . import dem as demlib
from .frame import LINK_STYLE
from .snapshot import Snapshot
from .svg import Svg
from .validate import check_extent_coverage, evidence_of

DEFAULT_LAYERS = ["terrain", "waterbody", "hydro_network", "wells", "connections"]
UNKNOWN_STYLE = ("#ffffff", "#888888")


def visible(feature: dict[str, Any], date: str | None) -> bool:
    obs = (feature.get("properties") or {}).get("observation_date")
    return date is None or obs is None or obs == date


def render_xy(
    snap: Snapshot, config: dict[str, Any], render_id: str, issues: list[dict[str, Any]]
):
    w, s, e, n = config.get("extent") or snap.manifest["extent"]
    layers = config.get("layers", DEFAULT_LAYERS)
    date = config.get("date")
    width = int(config.get("width", 800))
    lat0 = (s + n) / 2
    map_h = round(width * (n - s) / ((e - w) * math.cos(math.radians(lat0))))
    top, left, bottom = 30, 10, 130
    svg = Svg(width + 2 * left, map_h + top + bottom)
    steps = [
        "load snapshot (layer hashes verified)",
        "validate reference frames, identities, network, connections",
        f"project to equirectangular plane scaled by cos(lat0={lat0:.3f}); display only",
    ]

    def px(lon: float, lat: float) -> tuple[float, float]:
        return left + (lon - w) / (e - w) * width, top + (n - lat) / (n - s) * map_h

    extra: list[dict[str, Any]] = []
    dem = snap.layer("raster_dem")
    if "terrain" in layers:
        grid = [
            (w + (e - w) * i / 8, s + (n - s) * j / 8)
            for i in range(9)
            for j in range(9)
        ]
        extra += check_extent_coverage(snap, grid, "map extent")
    if "terrain" in layers and dem is not None:
        shade = demlib.hillshade(dem)
        nr, nc = dem["nrows"], dem["ncols"]
        dw, ds, de, dn = dem["bbox"]
        for r in range(nr - 1):
            for c in range(nc - 1):
                rr, cc = min(max(r, 1), nr - 2), min(max(c, 1), nc - 2)
                v = shade[rr][cc]
                if v is None:
                    continue
                x0, y0 = px(
                    dw + (de - dw) * c / (nc - 1), dn - (dn - ds) * r / (nr - 1)
                )
                x1, y1 = px(
                    dw + (de - dw) * (c + 1) / (nc - 1),
                    dn - (dn - ds) * (r + 1) / (nr - 1),
                )
                svg.rect(x0, y0, x1 - x0 + 0.5, y1 - y0 + 0.5, f"rgb({v},{v},{v})")
        steps.append("hillshade: Horn method, azimuth 315, altitude 45")
    drawn: list[dict[str, Any]] = []

    def note(f: dict[str, Any], layer: dict[str, Any], style: str) -> None:
        drawn.append(
            {
                "id": f["id"],
                "layer_id": layer["layer_id"],
                "evidence": evidence_of(f),
                "style": style,
                "observation_date": (f.get("properties") or {}).get("observation_date"),
            }
        )

    for layer in snap.feature_layers():
        kind = layer["kind"]
        if kind not in layers:
            continue
        for f in layer["features"]:
            if not visible(f, date):
                continue
            ev, geom = evidence_of(f), f["geometry"]
            if kind == "waterbody":
                ring = [px(*c) for c in geom["coordinates"][0]]
                fill, stroke = (
                    UNKNOWN_STYLE if ev == "unknown" else ("#9ecae1", "#08519c")
                )
                svg.polygon(ring, fill, stroke, 'fill-opacity="0.8"')
                note(f, layer, "polygon")
            elif kind == "hydro_network":
                colour = "#888888" if ev == "unknown" else "#1f78b4"
                svg.polyline([px(*c) for c in geom["coordinates"]], colour, 2)
                note(f, layer, "line")
            elif kind == "wells":
                x, y = px(*geom["coordinates"])
                fill, stroke = (
                    UNKNOWN_STYLE if ev == "unknown" else ("#fdae6b", "#7f2704")
                )
                svg.circle(x, y, 4, fill, stroke)
                svg.text(x + 6, y + 3, f["id"], 9)
                note(f, layer, "point")
            elif kind == "connections":
                colour, dash, shown = LINK_STYLE[ev]
                if shown:
                    svg.polyline([px(*c) for c in geom["coordinates"]], colour, 2, dash)
                note(f, layer, "link" if shown else "not_drawn")
    svg.footer_y = top + map_h + 20
    svg.title = config.get("title", "Top-down map")
    return svg, drawn, steps, extra

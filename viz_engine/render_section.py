"""Vertical cross-section along a user-defined transect."""

from __future__ import annotations

from typing import Any

from federation.spatial_core import geodesic_distance_m

from . import dem as demlib
from .frame import LINK_STYLE
from .render_xy import visible
from .snapshot import Snapshot
from .svg import Svg
from .validate import check_extent_coverage, evidence_of

FT_TO_M = 0.3048
MAX_HEIGHT_PX = 1600


def stations(points: list[list[float]], count: int) -> list[tuple[float, float, float]]:
    """(distance_m, lon, lat) at evenly spaced distances along the polyline."""
    cum, total = [0.0], 0.0
    for a, b in zip(points, points[1:]):
        total += geodesic_distance_m(a[0], a[1], b[0], b[1])
        cum.append(total)
    out = []
    for k in range(count):
        d = total * k / (count - 1)
        i = (
            max(j for j in range(len(cum) - 1) if cum[j] <= d)
            if d < total
            else len(cum) - 2
        )
        span = cum[i + 1] - cum[i]
        t = (d - cum[i]) / span if span else 0.0
        a, b = points[i], points[i + 1]
        out.append((d, a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return out


def render_section(
    snap: Snapshot, config: dict[str, Any], render_id: str, issues: list[dict[str, Any]]
):
    pts = config["transect"]
    ve = float(config.get("vertical_exaggeration", 1.0))
    buffer_m = float(config.get("buffer_m", 1500.0))
    st = stations(pts, int(config.get("samples", 120)))
    extra = check_extent_coverage(snap, [(lon, lat) for _, lon, lat in st], "transect")
    dem = snap.layer("raster_dem")
    ground = [demlib.sample(dem, lon, lat) if dem else None for _, lon, lat in st]
    steps = [
        "load snapshot (layer hashes verified)",
        f"transect of {len(pts)} vertices sampled at {len(st)} stations (linear lon/lat interpolation between vertices)",
        "ground profile: bilinear DEM sample at each station",
        "well depths converted ft->m (x0.3048), reference below_land_surface, positive down",
    ]
    total = st[-1][0]
    width, left, right, top = 800, 60, 20, 30
    xscale = (width - left - right) / total
    wells = []
    for f in (snap.layer("wells") or {}).get("features", []):
        if "wells" not in config.get("layers", ["wells", "connections"]) or not visible(
            f, config.get("date")
        ):
            continue
        lon, lat = f["geometry"]["coordinates"]
        k = min(
            range(len(st)),
            key=lambda i: geodesic_distance_m(lon, lat, st[i][1], st[i][2]),
        )
        if (
            geodesic_distance_m(lon, lat, st[k][1], st[k][2]) <= buffer_m
            and ground[k] is not None
        ):
            wells.append((f, k))
    valid = [g for g in ground if g is not None]
    zmax = (max(valid) if valid else 0.0) + 20.0
    floor = min(valid) if valid else 0.0
    for f, k in wells:
        floor = min(
            floor, (ground[k] or 0.0) - f["properties"].get("depth_ft", 0.0) * FT_TO_M
        )
    zmin = floor - 20.0
    yscale = xscale * ve
    plot_h = (zmax - zmin) * yscale
    if plot_h > MAX_HEIGHT_PX:
        raise ValueError(
            f"section would be {plot_h:.0f}px tall at vertical exaggeration {ve}; lower it or shorten the relief"
        )
    plot_h = max(plot_h, 160.0)
    svg = Svg(width, int(top + plot_h + 150))

    def px(d: float, z: float) -> tuple[float, float]:
        return left + d * xscale, top + (zmax - z) * yscale

    svg.polyline(
        [(left, top), (left, top + plot_h), (width - right, top + plot_h)], "#333", 1
    )
    for z in range(int(zmin // 100) * 100, int(zmax) + 1, 100):
        if zmin <= z <= zmax:
            x, y = px(0, z)
            svg.text(2, y + 3, f"{z} m", 9)
    run: list[tuple[float, float]] = []
    for (d, _, _), g in zip(st, ground):
        if g is None:
            if len(run) > 1:
                svg.polyline(run, "#5b3a1a", 2)
            run = []
        else:
            run.append(px(d, g))
    if len(run) > 1:
        svg.polyline(run, "#5b3a1a", 2)
    drawn: list[dict[str, Any]] = []
    anchor: dict[str, tuple[float, float]] = {}
    for f, k in wells:
        p, d = f["properties"], st[k][0]
        gk = ground[k]
        assert gk is not None  # wells are only kept where the DEM covers them
        x, ytop = px(d, gk)
        depth_m = p["depth_ft"] * FT_TO_M
        _, ybot = px(d, gk - depth_m)
        svg.polyline([(x, ytop), (x, ybot)], "#7f2704", 3)
        svg.text(x + 4, ytop - 4, f["id"], 9)
        if p.get("depth_to_water_ft") is not None:
            _, yw = px(d, ground[k] - p["depth_to_water_ft"] * FT_TO_M)
            svg.polygon(
                [(x - 5, yw - 6), (x + 5, yw - 6), (x, yw)], "#1f78b4", "#08306b"
            )
        anchor[f["id"]] = (x, (ytop + ybot) / 2)
        drawn.append(
            {
                "id": f["id"],
                "layer_id": "wells",
                "evidence": evidence_of(f),
                "style": "well_bar",
                "observation_date": p.get("observation_date"),
            }
        )
    for f in (snap.layer("connections") or {}).get("features", []):
        p, ev = f["properties"], evidence_of(f)
        colour, dash, shown = LINK_STYLE[ev]
        in_section = p.get("from_id") in anchor and p.get("to_id") in anchor
        if shown and in_section:
            svg.polyline([anchor[p["from_id"]], anchor[p["to_id"]]], colour, 2, dash)
        style = (
            "link"
            if shown and in_section
            else ("not_drawn" if not shown else "outside_section")
        )
        drawn.append(
            {
                "id": f["id"],
                "layer_id": "connections",
                "evidence": ev,
                "style": style,
                "observation_date": p.get("observation_date"),
            }
        )
    steps.append(
        f"vertical exaggeration {ve:g}x (horizontal {xscale:.4f} px/m, vertical {yscale:.4f} px/m)"
    )
    svg.footer_y = top + plot_h + 20
    svg.title = config.get("title", "Vertical section")
    svg.text(
        left,
        top - 10,
        f"A  {total / 1000:.1f} km  A'   VE {ve:g}x   datum {snap.manifest['vertical_datum']}",
        10,
    )
    return svg, drawn, steps, extra

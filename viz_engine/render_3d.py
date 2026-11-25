"""Bounded 3D terrain + wells + connections, written as glTF 2.0 (self-contained JSON)."""

from __future__ import annotations

import base64
import json
import struct
from typing import Any

from federation.spatial_core import geodesic_distance_m

from . import dem as demlib
from .frame import LINK_STYLE
from .render_section import FT_TO_M
from .render_xy import visible
from .snapshot import Snapshot
from .validate import evidence_of

MAX_CELLS = 250_000


def _rgb(hex_colour: str) -> list[float]:
    return [int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5)] + [1.0]


def render_3d(
    snap: Snapshot, config: dict[str, Any], render_id: str, issues: list[dict[str, Any]]
):
    dem = snap.layer("raster_dem")
    extra: list[dict[str, Any]] = []
    if dem is None:
        return (
            None,
            [],
            ["no raster_dem layer"],
            [
                {
                    "code": "NO_RASTER",
                    "severity": "error",
                    "message": "3D view needs a raster_dem layer",
                    "feature_ids": [],
                }
            ],
        )
    nr, nc = dem["nrows"], dem["ncols"]
    if nr * nc > MAX_CELLS:
        raise ValueError(
            f"3D pilot is bounded to {MAX_CELLS} cells; raster has {nr * nc}"
        )
    ve = float(config.get("vertical_exaggeration", 1.0))
    w, s, e, n = dem["bbox"]
    clat = (s + n) / 2
    mx = geodesic_distance_m(w, clat, e, clat) / (e - w)  # metres per degree lon
    my = geodesic_distance_m(w, s, w, n) / (n - s)  # metres per degree lat

    def local(lon: float, lat: float, z: float) -> tuple[float, float, float]:
        return ((lon - w) * mx, z * ve, -((lat - s) * my))  # glTF: +y up, north = -z

    verts: list[tuple[float, float, float]] = []
    index: list[int] = []
    ids: dict[tuple[int, int], int] = {}
    dlon, dlat = (e - w) / (nc - 1), (n - s) / (nr - 1)
    for r in range(nr):
        for c in range(nc):
            z = dem["values"][r][c]
            if demlib._valid(dem, z):
                ids[(r, c)] = len(verts)
                verts.append(local(w + dlon * c, n - dlat * r, z))
    for r in range(nr - 1):
        for c in range(nc - 1):
            tl, tr = ids.get((r, c)), ids.get((r, c + 1))
            bl, br = ids.get((r + 1, c)), ids.get((r + 1, c + 1))
            if tl is None or tr is None or bl is None or br is None:
                continue
            index += [tl, bl, tr, tr, bl, br]
    steps = [
        "load snapshot (layer hashes verified)",
        f"terrain mesh from {nr}x{nc} DEM, vertical exaggeration {ve:g}x, local metres (x east, y up, -z north)",
    ]
    prims: list[
        tuple[str, list[tuple[float, float, float]], list[int], int, str, str | None]
    ] = [("terrain", verts, index, 4, "#b8a98f", None)]
    drawn: list[dict[str, Any]] = []
    anchors: dict[str, tuple[float, float, float]] = {}
    for f in (snap.layer("wells") or {}).get("features", []):
        if not visible(f, config.get("date")):
            continue
        lon, lat = f["geometry"]["coordinates"]
        g = demlib.sample(dem, lon, lat)
        p = f["properties"]
        if g is None:
            extra.append(
                {
                    "code": "MISSING_RASTER_COVERAGE",
                    "severity": "error",
                    "message": f"well {f['id']} outside raster coverage",
                    "feature_ids": [f["id"]],
                }
            )
            continue
        top, bot = local(lon, lat, g), local(lon, lat, g - p["depth_ft"] * FT_TO_M)
        prims.append((f["id"], [top, bot], [0, 1], 1, "#7f2704", evidence_of(f)))
        anchors[f["id"]] = ((top[0] + bot[0]) / 2, (top[1] + bot[1]) / 2, top[2])
        drawn.append(
            {
                "id": f["id"],
                "layer_id": "wells",
                "evidence": evidence_of(f),
                "style": "well_line",
                "observation_date": p.get("observation_date"),
            }
        )
    for f in (snap.layer("connections") or {}).get("features", []):
        p, ev = f["properties"], evidence_of(f)
        colour, _, shown = LINK_STYLE[ev]
        ok = shown and p.get("from_id") in anchors and p.get("to_id") in anchors
        if ok:
            prims.append(
                (
                    f["id"],
                    [anchors[p["from_id"]], anchors[p["to_id"]]],
                    [0, 1],
                    1,
                    colour,
                    ev,
                )
            )
        drawn.append(
            {
                "id": f["id"],
                "layer_id": "connections",
                "evidence": ev,
                "style": (
                    "link" if ok else ("not_drawn" if not shown else "outside_scene")
                ),
                "observation_date": p.get("observation_date"),
            }
        )
    blob = bytearray()
    views, accessors, meshes, nodes, materials = [], [], [], [], []
    for k, (name, vs, ix, mode, colour, prim_ev) in enumerate(prims):
        off = len(blob)
        blob += b"".join(struct.pack("<3f", *v) for v in vs)
        views.append(
            {
                "buffer": 0,
                "byteOffset": off,
                "byteLength": len(vs) * 12,
                "target": 34962,
            }
        )
        lo = [min(v[i] for v in vs) for i in range(3)]
        hi = [max(v[i] for v in vs) for i in range(3)]
        accessors.append(
            {
                "bufferView": len(views) - 1,
                "componentType": 5126,
                "count": len(vs),
                "type": "VEC3",
                "min": lo,
                "max": hi,
            }
        )
        pos_acc = len(accessors) - 1
        off = len(blob)
        blob += b"".join(struct.pack("<I", i) for i in ix)
        views.append(
            {"buffer": 0, "byteOffset": off, "byteLength": len(ix) * 4, "target": 34963}
        )
        accessors.append(
            {
                "bufferView": len(views) - 1,
                "componentType": 5125,
                "count": len(ix),
                "type": "SCALAR",
            }
        )
        materials.append(
            {
                "pbrMetallicRoughness": {
                    "baseColorFactor": _rgb(colour),
                    "metallicFactor": 0.0,
                }
            }
        )
        meshes.append(
            {
                "name": name,
                "primitives": [
                    {
                        "attributes": {"POSITION": pos_acc},
                        "indices": len(accessors) - 1,
                        "mode": mode,
                        "material": k,
                    }
                ],
            }
        )
        nodes.append({"name": name, "mesh": k, "extras": {"evidence": prim_ev}})
    gltf = {
        "asset": {
            "version": "2.0",
            "generator": f"spiderweb-viz-engine/{render_id[:16]}",
            "extras": {
                "render_id": render_id,
                "crs": snap.manifest["crs"],
                "vertical_datum": snap.manifest["vertical_datum"],
                "vertical_exaggeration": ve,
                "note": "visual only; a drawn line is not evidence of a connection",
            },
        },
        "scene": 0,
        "scenes": [{"nodes": list(range(len(nodes)))}],
        "nodes": nodes,
        "meshes": meshes,
        "materials": materials,
        "accessors": accessors,
        "bufferViews": views,
        "buffers": [
            {
                "byteLength": len(blob),
                "uri": "data:application/octet-stream;base64,"
                + base64.b64encode(bytes(blob)).decode("ascii"),
            }
        ],
    }
    steps.append(
        f"{len(prims) - 1} well/connection line primitive(s) added; unknown-evidence links omitted"
    )
    return (
        json.dumps(gltf, sort_keys=True, separators=(",", ":")) + "\n",
        drawn,
        steps,
        extra,
    )

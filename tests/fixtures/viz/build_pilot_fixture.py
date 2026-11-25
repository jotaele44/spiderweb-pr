"""Regenerate the synthetic pilot snapshot (fixture only; not real data).

    python tests/fixtures/viz/build_pilot_fixture.py

Everything here is invented for engine certification.  It says nothing about
real Puerto Rico hydrology.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from viz_engine.snapshot import freeze_snapshot

ROOT = Path(__file__).parent / "pilot_snapshot"
BBOX = [-66.20, 18.00, -66.00, 18.20]
N = 13


def lonlat(u: float, v: float) -> list[float]:
    return [
        round(BBOX[0] + (BBOX[2] - BBOX[0]) * u, 5),
        round(BBOX[1] + (BBOX[3] - BBOX[1]) * v, 5),
    ]


def elevation(u: float, v: float) -> float:
    return round(
        900 * math.exp(-((u - 0.5) ** 2 / 0.12 + (v - 0.75) ** 2 / 0.05)) + 60 * v + 10,
        1,
    )


def feature(fid: str, geometry: dict, **props) -> dict:
    return {"id": fid, "geometry": geometry, "properties": props}


def line(*uv):
    return {"type": "LineString", "coordinates": [lonlat(*p) for p in uv]}


def point(u, v):
    return {"type": "Point", "coordinates": lonlat(u, v)}


def write(name: str, data: dict) -> None:
    (ROOT / "layers").mkdir(parents=True, exist_ok=True)
    (ROOT / "layers" / name).write_text(
        json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )


def main() -> None:
    hdr = {
        "crs": "EPSG:4326",
        "source": {"authority": "synthetic fixture", "license": "CC0-1.0"},
    }
    values = [
        [elevation(c / (N - 1), 1 - r / (N - 1)) for c in range(N)] for r in range(N)
    ]
    write(
        "dem.json",
        {
            **hdr,
            "layer_id": "dem_fixture",
            "kind": "raster_dem",
            "vertical_datum": "NAVD88",
            "unit": "m",
            "bbox": BBOX,
            "nrows": N,
            "ncols": N,
            "nodata": -9999,
            "values": values,
        },
    )
    flow = {
        "evidence": "observed",
        "flow_direction": "digitized_downstream",
        "observation_date": "2025-03-01",
    }
    write(
        "hydro.json",
        {
            **hdr,
            "layer_id": "hydro_fixture",
            "kind": "hydro_network",
            "vertical_datum": None,
            "features": [
                feature(
                    "SEG_1",
                    line((0.5, 0.88), (0.52, 0.62)),
                    from_node="N1",
                    to_node="N2",
                    **flow,
                ),
                feature(
                    "SEG_2",
                    line((0.52, 0.62), (0.5, 0.42)),
                    from_node="N2",
                    to_node="N3",
                    **flow,
                ),
                feature(
                    "SEG_3",
                    line((0.5, 0.42), (0.5, 0.26)),
                    from_node="N3",
                    to_node="RES_1",
                    **flow,
                ),
                feature(
                    "SEG_T",
                    line((0.32, 0.78), (0.52, 0.62)),
                    from_node="N0",
                    to_node="N2",
                    **flow,
                ),
            ],
        },
    )
    write(
        "waterbody.json",
        {
            **hdr,
            "layer_id": "waterbody_fixture",
            "kind": "waterbody",
            "vertical_datum": None,
            "features": [
                feature(
                    "RES_1",
                    {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                lonlat(*p)
                                for p in (
                                    (0.44, 0.24),
                                    (0.56, 0.24),
                                    (0.56, 0.12),
                                    (0.44, 0.12),
                                    (0.44, 0.24),
                                )
                            ]
                        ],
                    },
                    evidence="observed",
                    observation_date="2025-03-01",
                )
            ],
        },
    )
    well = {"depth_reference": "below_land_surface", "evidence": "observed"}
    write(
        "wells.json",
        {
            **hdr,
            "layer_id": "wells_fixture",
            "kind": "wells",
            "vertical_datum": None,
            "features": [
                feature(
                    "W1",
                    point(0.52, 0.34),
                    depth_ft=150.0,
                    depth_to_water_ft=20.0,
                    observation_date="2025-03-01",
                    **well,
                ),
                feature(
                    "W2",
                    point(0.48, 0.48),
                    depth_ft=300.0,
                    depth_to_water_ft=60.0,
                    observation_date="2025-03-01",
                    **well,
                ),
                feature(
                    "W3",
                    point(0.92, 0.5),
                    depth_ft=100.0,
                    observation_date="2025-03-01",
                    **well,
                ),
            ],
        },
    )
    write(
        "connections.json",
        {
            **hdr,
            "layer_id": "connections_fixture",
            "kind": "connections",
            "vertical_datum": None,
            "features": [
                feature(
                    "C_OBS",
                    line((0.52, 0.34), (0.48, 0.48)),
                    kind="subsurface_conduit",
                    from_id="W1",
                    to_id="W2",
                    evidence="observed",
                    observation_ref="fixture-dye-trace-001",
                ),
                feature(
                    "C_INF",
                    line((0.48, 0.48), (0.5, 0.2)),
                    kind="subsurface_conduit",
                    from_id="W2",
                    to_id="RES_1",
                    evidence="inferred",
                ),
                feature(
                    "C_UNK",
                    line((0.52, 0.34), (0.92, 0.5)),
                    kind="subsurface_conduit",
                    from_id="W1",
                    to_id="W3",
                    evidence="unknown",
                ),
            ],
        },
    )
    freeze_snapshot(
        ROOT,
        snapshot_id="pilot_fixture",
        version="1.0.0",
        crs="EPSG:4326",
        vertical_datum="NAVD88",
        extent=BBOX,
    )
    cfg = ROOT.parent / "configs"
    cfg.mkdir(exist_ok=True)
    (cfg / "xy.json").write_text(
        json.dumps(
            {"title": "Synthetic pilot: top-down", "extent": BBOX, "width": 720},
            indent=1,
        )
        + "\n"
    )
    (cfg / "section.json").write_text(
        json.dumps(
            {
                "title": "Synthetic pilot: section A-A'",
                "transect": [lonlat(0.5, 0.95), lonlat(0.5, 0.08)],
                "vertical_exaggeration": 12,
                "buffer_m": 2500,
                "samples": 90,
            },
            indent=1,
        )
        + "\n"
    )
    (cfg / "3d.json").write_text(
        json.dumps(
            {"title": "Synthetic pilot: 3D", "vertical_exaggeration": 3}, indent=1
        )
        + "\n"
    )


if __name__ == "__main__":
    main()

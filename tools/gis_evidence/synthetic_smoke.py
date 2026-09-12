"""Generate and run a real-engine smoke fixture using supplied local runtimes.

The polygons and lineage are synthetic. Nothing is fetched, promoted or
represented as Puerto Rico evidence. Missing runtimes emit a BLOCKED receipt.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path

from spiderweb.spatial.archipelago import (
    GeometryDerivationState, GeometryManifestation, GeometryOrigin,
    GeometryRepresentation,
)
from .core import canonical_json, digest, write_new
from .delivery_benchmark import run


def prepare_fixture(out: Path, martin: dict, maplibre: dict) -> dict:
    out.mkdir(parents=True, exist_ok=False)
    features = []
    for key, lon in (("A", -66.4), ("B", -66.39), ("C", -66.15)):
        lat = 18.22
        ring = [[lon-.002,lat-.002], [lon+.002,lat-.002],
                [lon+.002,lat+.002], [lon-.002,lat+.002],
                [lon-.002,lat-.002]]
        features.append({"type":"Feature", "properties":{"GEOID":"SYNTHETIC:"+key},
                         "geometry":{"type":"Polygon","coordinates":[ring]}})
    source = out / "synthetic.geojson"
    source.write_bytes(canonical_json({"type":"FeatureCollection", "features":features}))
    source_hash = digest(source.read_bytes())
    snapshot = "SYNTHETIC_TEST_ONLY:v1"
    mid = "SYNTHETIC_ONLY:source:"+source_hash
    node = GeometryManifestation(
        mid, "SYNTHETIC_TEST_ONLY", GeometryRepresentation.POLYGON,
        GeometryOrigin.SOURCE_NATIVE, "FeatureCollection<Polygon>",
        derivation_state=GeometryDerivationState.SOURCE_NATIVE,
    )
    lock_path = out / "lineage.json"
    write_new(lock_path, {"schema":"spiderweb.geometry-lineage-lock.v1",
        "nodes":[asdict(node)], "artifact_bindings":[{
            "geometry_manifestation_id":mid, "artifact_sha256":source_hash,
            "source_snapshot_id":snapshot}]})
    views = [{"id":f"synthetic_z{zoom}", "center":[-66.4,18.22], "zoom":zoom,
        "pan_path":[[-66.15,18.22],[-66.4,18.22]], "expect_nonempty":True,
        "expected_visible_ids":{"initial":["SYNTHETIC:A","SYNTHETIC:B"],
            "pan:0":["SYNTHETIC:C"], "pan:1":["SYNTHETIC:A","SYNTHETIC:B"]}}
        for zoom in (13,14)]
    spec = {"layer_id":"synthetic_gis_smoke", "source_layer":"synthetic_gis_smoke",
        "source_path":str(source.resolve()), "source_sha256":source_hash,
        "expected_feature_count":3, "stable_id_field":"GEOID",
        "data_kind":"SYNTHETIC_TEST_ONLY", "source_snapshot_id":snapshot,
        "manifestation_id":mid, "source_crs":"OGC:CRS84",
        "coordinate_order":"longitude_latitude", "identity_zoom":10,
        "lineage_lock":{"path":str(lock_path.resolve()),"sha256":digest(lock_path.read_bytes())},
        "repetitions":5, "viewports":views, "viewport_pixels":{"width":1280,"height":800},
        "martin_binary":martin, "maplibre_js":maplibre}
    write_new(out/"spec.json", spec)
    return spec


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    for kind in ("martin", "maplibre"):
        parser.add_argument(f"--{kind}-path", default="__UNBOUND_LOCAL_RUNTIME__")
        parser.add_argument(f"--{kind}-sha256")
        parser.add_argument(f"--{kind}-version")
    args = parser.parse_args()
    def runtime(kind: str) -> dict:
        return {"path":getattr(args,kind+"_path"),
                "sha256":getattr(args,kind+"_sha256"),
                "version":getattr(args,kind+"_version")}
    spec = prepare_fixture(args.out,runtime("martin"),runtime("maplibre"))
    measured = args.out/"measurement"
    measured.mkdir()
    try:
        result = run(spec, measured)
    except Exception as exc:
        result = {"state":"FAIL", "error_type":type(exc).__name__, "error":str(exc),
                  "data_kind":"SYNTHETIC_TEST_ONLY", "mvt_canonical":False}
    write_new(measured/"receipt.json",result)
    print(result["state"])
    return 0 if result["state"] == "MEASURED_NOT_PUBLISHED" else 2


if __name__ == "__main__":
    raise SystemExit(main())

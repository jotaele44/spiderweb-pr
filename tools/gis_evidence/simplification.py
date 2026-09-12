"""Measure frozen FULL/SIMPLIFIED polygon pairs; never authorize simplification.

All geometric values are measured in a caller-declared projected metre CRS.
Discrete Hausdorff is labelled as such and does not claim a continuous bound.
Point probes preserve all containing and boundary-touching candidates.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import json
import math
import numpy as np
import pyproj
from pyproj import CRS, Transformer
import shapely
from shapely.geometry import shape, Point
from shapely.ops import transform
from .core import load_geojson, set_receipt, write_new, positive_finite


def metric_crs(value: str) -> CRS:
    crs = CRS.from_user_input(value)
    if not crs.is_projected or len(crs.axis_info) < 2:
        raise ValueError("PROJECTED_METRE_CRS_REQUIRED")
    if any(abs(axis.unit_conversion_factor - 1.0) > 1e-12 for axis in crs.axis_info[:2]):
        raise ValueError("PROJECTED_METRE_CRS_REQUIRED")
    return crs


def prepare_geometry(feature: dict, transformer: Transformer):
    raw = feature.get("geometry")
    if raw is None:
        raise ValueError("NULL_GEOMETRY")
    geom = shape(raw)
    if geom.is_empty:
        raise ValueError("EMPTY_GEOMETRY")
    if geom.geom_type not in {"Polygon","MultiPolygon"}:
        raise ValueError("POLYGON_METRICS_REQUIRED")
    if geom.has_z or (hasattr(shapely,"has_m") and shapely.has_m(geom)):
        raise ValueError("Z_M_MEASUREMENT_REQUIRES_EXPLICIT_PROJECTION_POLICY")
    if not geom.is_valid:
        raise ValueError("INVALID_SOURCE_GEOMETRY:"+shapely.is_valid_reason(geom))
    projected = transform(transformer.transform, geom)
    if projected.is_empty or not projected.is_valid or not all(math.isfinite(x) for x in projected.bounds):
        raise ValueError("INVALID_TRANSFORMED_GEOMETRY")
    return projected


def polygon_metrics(a, b, densify: float = 0.25) -> dict:
    positive_finite(densify,"densify")
    if densify > 1:
        raise ValueError("DENSIFY_OUT_OF_RANGE")
    if not a.is_valid or not b.is_valid or a.is_empty or b.is_empty:
        raise ValueError("INVALID_OR_EMPTY_GEOMETRY")
    if a.area <= 0:
        raise ValueError("NONPOSITIVE_POLYGON_AREA")
    sym = a.symmetric_difference(b).area
    return {
        "topological_equals":bool(a.equals(b)),
        "exact_coordinate_equals":bool(a.equals_exact(b,0)),
        "geometry_type_equal":a.geom_type == b.geom_type,
        "hausdorff_discrete_m":float(shapely.hausdorff_distance(a,b,densify=densify)),
        "hausdorff_densify":densify,
        "symmetric_difference_m2":float(sym),
        "symmetric_difference_pct_of_full":float(100*sym/a.area),
        "full_area_m2":float(a.area),"simplified_area_m2":float(b.area),
        "area_delta_m2":float(b.area-a.area),
        "area_delta_pct_of_full":float(100*(b.area-a.area)/a.area),
        "vertices_full":int(shapely.get_num_coordinates(a)),
        "vertices_simplified":int(shapely.get_num_coordinates(b)),
        "validity_preserved":True,
        "topology_preserved":None,  # validity alone does not prove topology.
    }


def classify_point(geometries: dict, point: Point) -> dict:
    return {"within_ids":sorted(k for k,g in geometries.items() if g.contains(point)),
            "touching_ids":sorted(k for k,g in geometries.items() if g.touches(point))}


def boundary_probes(geometries: dict, offset_m: float, samples_per_feature: int = 8) -> list[dict]:
    """Deterministic samples, not universal boundary attribution proof."""
    positive_finite(offset_m,"offset_m")
    if type(samples_per_feature) is not int or not 1 <= samples_per_feature <= 100:
        raise ValueError("INVALID_PROBE_SAMPLE_COUNT")
    probes=[]
    for key,g in sorted(geometries.items()):
        boundary = g.boundary
        for i in range(samples_per_feature):
            p=boundary.interpolate((i+0.5)/samples_per_feature,normalized=True)
            for label,dx,dy in [("on",0,0),("east",offset_m,0),("west",-offset_m,0),("north",0,offset_m),("south",0,-offset_m)]:
                probes.append({"probe_id":f"{key}:{i}:{label}","x":p.x+dx,"y":p.y+dy})
    return probes


def pip_stability(a: dict, b: dict, probes: list[dict]) -> dict:
    ids=set();out=[]
    for p in probes:
        if p["probe_id"] in ids:
            raise ValueError("DUPLICATE_PROBE_ID")
        ids.add(p["probe_id"])
        if not all(isinstance(p[k],(int,float)) and not isinstance(p[k],bool) and math.isfinite(p[k]) for k in ("x","y")):
            raise ValueError("INVALID_PROBE_COORDINATE")
        point=Point(p["x"],p["y"])
        before=classify_point(a,point);after=classify_point(b,point)
        out.append({**p,"before":before,"after":after,"equal":before==after})
    return {"scope":"supplied probes only; not exhaustive PIP equivalence","probe_count":len(out),"mismatch_count":sum(not r["equal"] for r in out),"rows":out}


def compare_layers(full: dict, simplified: dict, source_crs: str, operation_crs: str, densify: float = 0.25, probes: list[dict] | None = None) -> dict:
    if not full or not simplified:
        raise ValueError("EMPTY_COMPARISON_SCOPE")
    op=metric_crs(operation_crs)
    transformer=Transformer.from_crs(CRS.from_user_input(source_crs),op,always_xy=True,allow_ballpark=False)
    diff=set_receipt(set(full),set(simplified))
    good_a={};good_b={};records=[]
    for key in sorted(set(full)|set(simplified)):
        if key not in full or key not in simplified:
            records.append({"stable_id":key,"state":"UNRESOLVED","reason":"MISSING_FEATURE_ON_ONE_SIDE"});continue
        try:
            a=prepare_geometry(full[key],transformer);b=prepare_geometry(simplified[key],transformer)
            good_a[key]=a;good_b[key]=b
            records.append({"stable_id":key,"state":"MEASURED",**polygon_metrics(a,b,densify)})
        except (ValueError,TypeError,shapely.GEOSException) as exc:
            records.append({"stable_id":key,"state":"UNRESOLVED","reason":str(exc)})
    numeric=[r for r in records if r["state"]=="MEASURED"]
    aggregate={}
    for k in ("hausdorff_discrete_m","symmetric_difference_m2","symmetric_difference_pct_of_full"):
        values=[r[k] for r in numeric]
        aggregate[k]={"max":max(values),"p99":float(np.percentile(values,99)),"p95":float(np.percentile(values,95)),"median":float(np.median(values))} if values else None
    residue=sum(r["state"]!="MEASURED" for r in records)
    probe_result=pip_stability(good_a,good_b,probes) if probes is not None and residue==0 else None
    return {"state":"MEASURED" if residue==0 else "OPEN","certification":"AUDIT_ONLY","threshold_selected":None,"source_crs":source_crs,"operation_crs":operation_crs,"operation_wkt":op.to_wkt(),"transformation":transformer.definition,"shapely_version":shapely.__version__,"geos_version":shapely.geos_version_string,"pyproj_version":pyproj.__version__,"coordinate_order":"always_xy","z_m_policy":"reject, not strip","sets":diff,"feature_count":len(records),"measured_count":len(numeric),"unresolved_count":residue,"metrics":records,"aggregate":aggregate,"pip_stability":probe_result,"scope_limits":["Metric CRS suitability remains an explicit caller responsibility.","Point probes are bounded samples, not universal classification equivalence.","Geometric error alone cannot establish acceptable operational risk."]}


def main() -> int:
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ("full","simplified","out"):
        ap.add_argument("--"+name,type=Path,required=True)
    for name in ("full-sha256","simplified-sha256","stable-id","source-crs","operation-crs"):
        ap.add_argument("--"+name,required=True)
    ap.add_argument("--densify",type=float,default=0.25)
    ap.add_argument("--probe-offset-m",type=float)
    args=ap.parse_args()
    try:
        _,a=load_geojson(args.full,args.full_sha256,args.stable_id)
        _,b=load_geojson(args.simplified,args.simplified_sha256,args.stable_id)
        probes=None
        if args.probe_offset_m is not None:
            tr=Transformer.from_crs(args.source_crs,metric_crs(args.operation_crs),always_xy=True,allow_ballpark=False)
            ga={k:prepare_geometry(v,tr) for k,v in a.items()}
            probes=boundary_probes(ga,args.probe_offset_m)
        result=compare_layers(a,b,args.source_crs,args.operation_crs,args.densify,probes)
        result["inputs"]={"full_sha256":args.full_sha256,"simplified_sha256":args.simplified_sha256,"stable_id":args.stable_id}
        write_new(args.out,result)
        return 0 if result["state"]=="MEASURED" else 1
    except (OSError,ValueError,pyproj.exceptions.ProjError) as exc:
        write_new(args.out,{"state":"BLOCKED" if isinstance(exc,FileNotFoundError) else "FAIL","error":str(exc),"threshold_selected":None})
        return 2


if __name__=="__main__":
    raise SystemExit(main())

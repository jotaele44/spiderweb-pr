"""Typed cross-domain spatial relations for Spiderweb investigations.

Spatial relations are evidence, never silent identity.  Every computed edge
records its method/version/threshold and defaults to CANDIDATE_NOT_IDENTITY.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any, Mapping
from .spatial_core import CONTRACT_VERSION, IDENTITY_DEFAULT, geodesic_distance_m

RELATION_TYPES={"WITHIN","INTERSECTS","OVERLAPS","NEAREST_TO","WITHIN_DISTANCE","CROSSES","UPSTREAM_OF","DOWNSTREAM_OF","CONNECTED_TO","SERVES","ROUTE_NEAR","ROUTE_INTERSECTS","LOCATED_AT","APPROX_LOCATED_IN","FUNDED_PROJECT_AT","CONTRACT_FOR_ASSET"}
ALGORITHM_VERSION="federation-spatial-relations/1.0"

@dataclass(frozen=True)
class SpatialRelation:
    relation_type:str
    source_feature_id:str
    target_feature_id:str
    method:str
    algorithm_version:str=ALGORITHM_VERSION
    distance_m:float|None=None
    threshold_m:float|None=None
    confidence:str="HIGH"
    identity_semantics:str=IDENTITY_DEFAULT
    evidence_state:str="COMPUTED"
    contract_version:str=CONTRACT_VERSION
    def as_dict(self)->dict[str,Any]: return asdict(self)

def _point(feature:Mapping[str,Any])->tuple[float,float]:
    geom=feature.get("geometry") or {}
    if geom.get("type")!="Point": raise ValueError("relation helper currently requires Point geometry")
    c=geom.get("coordinates") or []
    if len(c)<2: raise ValueError("point has no coordinate pair")
    return float(c[0]),float(c[1])

def within_distance(source:Mapping[str,Any], target:Mapping[str,Any], threshold_m:float)->SpatialRelation|None:
    if threshold_m<0: raise ValueError("threshold_m must be non-negative")
    slon,slat=_point(source); tlon,tlat=_point(target)
    d=geodesic_distance_m(slon,slat,tlon,tlat)
    if d>threshold_m:return None
    return SpatialRelation("WITHIN_DISTANCE",str(source["feature_id"]),str(target["feature_id"]),"WGS84_VINCENTY_POINT_DISTANCE",distance_m=d,threshold_m=float(threshold_m))

def nearest(source:Mapping[str,Any], candidates:list[Mapping[str,Any]])->SpatialRelation|None:
    if not candidates:return None
    slon,slat=_point(source)
    scored=[]
    for target in candidates:
        tlon,tlat=_point(target); scored.append((geodesic_distance_m(slon,slat,tlon,tlat),target))
    d,target=min(scored,key=lambda item:item[0])
    return SpatialRelation("NEAREST_TO",str(source["feature_id"]),str(target["feature_id"]),"WGS84_VINCENTY_POINT_DISTANCE",distance_m=d)

"""Materialize Spiderweb results for the frozen real C6062 observation fixture."""
from __future__ import annotations
import hashlib, json
from pathlib import Path

from federation.surface_analysis import IdentityState, MeasurementClass, ResolutionSummary, SpatialAnalysisResult
from federation.surface_engine import SurfaceManifestation
from federation.xarray_surface_source import XarraySurfaceSource

ROOT=Path(__file__).resolve().parents[1]
RASTER=ROOT/"data/frozen/noaa_cudem_9525/san_juan_19_prvd02_2015.nc"
OBS=ROOT.parent/"skywatcher-pr/exports/fr24_bbox_icon_scaled_package/observations.geojson"
OUT=ROOT/"reports/certification/c6062_real_surface_results.ndjson"
MANIFEST_ID="noaa-ncei-san-juan-19-prvd02-2015-frozen-20260908"

def main():
    raw=json.loads(OBS.read_text()); features=[f for f in raw["features"] if (f.get("properties") or {}).get("synthetic") is False]
    m=SurfaceManifestation(MANIFEST_ID,"san_juan_19_prvd02_2015","NOAA_NCEI_COASTAL_DEM","EPSG:4326","Puerto Rico Vertical Datum of 2002","positive_up",3.43,MeasurementClass.MODELED,"23aa9ae1b3df76265851fd423db963c261b1e26050f6bef9350f4e6544f31109","source-native-no-transform")
    rows=[]
    with XarraySurfaceSource(RASTER,m) as surface:
        for f in features:
            p=f["properties"]; lon,lat=f["geometry"]["coordinates"]; sample=surface.sample_surface(lon,lat)
            geometry_hash=hashlib.sha256(json.dumps(f["geometry"],sort_keys=True,separators=(",",":")).encode()).hexdigest()
            r=SpatialAnalysisResult(analysis_id=f"c6062-surface-{p['observation_id']}",query_id="c6062-real-fixture-20260908",subject_type="aircraft_observation",subject_id=p["observation_id"],subject_manifestation_id=p["lineage_id"],geometry_role="TRACK_POSITION_UNCERTAINTY",input_geometry_hash=geometry_hash,input_time_start=p["event_datetime"],input_time_end=p["event_datetime"],target_domain=sample.surface_class.value if sample.surface_class else "SURFACE_MODEL",spatial_state=sample.spatial_state,identity_state=IdentityState.UNRESOLVED,source_manifestation_ids=(MANIFEST_ID,),measurement_classes=(MeasurementClass.MODELED,),resolution_summary=ResolutionSummary(3.43,3.43,3.43,0,1,0 if sample.value_m is not None else 1),analysis_engine_version="surface/1.0",crs_operation="EPSG:4326 identity point sample",horizontal_source_crs="EPSG:4326",horizontal_computation_crs="EPSG:4326",vertical_datum=m.vertical_datum,depth_sign_convention=m.depth_sign_convention,surface_depth_min_m=sample.value_m,surface_depth_max_m=sample.value_m,surface_depth_mean_m=sample.value_m,confidence_state="MEDIUM")
            rows.append(r.as_artifact())
    OUT.write_text("".join(json.dumps(r,sort_keys=True)+"\n" for r in rows),encoding="utf-8")
    print(json.dumps({"source_features":len(features),"result_rows":len(rows),"output":str(OUT),"result_hashes":[r["result_hash"] for r in rows],"depths_m":[r["surface_depth_mean_m"] for r in rows]},indent=2))

if __name__=="__main__": main()

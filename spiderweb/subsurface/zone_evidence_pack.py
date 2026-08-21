"""Build evidence dossiers and ranked GeoJSON/KML/KMZ overlays for elevated zones."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import zipfile
from xml.sax.saxutils import escape

from shapely.geometry import shape
from shapely.strtree import STRtree


def _p(f): return f.get("properties") or {}
def _a(f): return _p(f).get("attributes") or {}
def _source(f): return _p(f).get("source_id")
def _family(f): return _p(f).get("layer_family")
def _rid(f): return str(_p(f).get("record_id"))


def _display_name(f):
    attrs = _a(f)
    for key in ("Cueva", "Nombre", "Name", "STATION_NA", "monitoring_location_name", "Comment", "ftr_name", "site_name", "Nombre_Fac"):
        if attrs.get(key): return str(attrs[key]).strip()
    return ""


def _polygon_kml(geom):
    polygons = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
    chunks = []
    for poly in polygons:
        coords = " ".join(f"{x},{y},0" for x, y in poly.exterior.coords)
        chunks.append(f"<Polygon><outerBoundaryIs><LinearRing><coordinates>{coords}</coordinates></LinearRing></outerBoundaryIs></Polygon>")
    return chunks[0] if len(chunks) == 1 else "<MultiGeometry>" + "".join(chunks) + "</MultiGeometry>"


def build_top8_pack(v11_geojson: dict, evidence_geojson: dict, canonical_assets: dict) -> tuple[dict, dict]:
    member_to_asset = {str(member): asset["canonical_id"] for asset in canonical_assets.get("assets", []) for member in asset.get("member_record_ids", [])}
    evidence = [f for f in evidence_geojson.get("features", []) if f.get("geometry") and _p(f).get("spatial_state") in {"FULLY_WITHIN", "PARTIAL"}]
    geoms = [shape(f["geometry"]) for f in evidence]
    tree = STRtree(geoms)
    elevated = [f for f in v11_geojson.get("features", []) if _p(f).get("relevance") == "MODERATE"]
    elevated.sort(key=lambda f: float(_p(f).get("score") or 0), reverse=True)
    dossiers = []
    overlay = []
    for rank, zone in enumerate(elevated, 1):
        zg = shape(zone["geometry"])
        hits = [evidence[int(i)] for i in tree.query(zg, predicate="intersects")]
        source_counts = Counter(_source(f) for f in hits)
        target = []
        for f in hits:
            if _family(f) in {"GEOLOGY_KARST_CAVES", "AQUIFERS_WELLS_SPRINGS", "MINES_QUARRIES_SHAFTS", "INDUSTRIAL_REMEDIATION"}:
                target.append({
                    "record_id": _rid(f), "source_id": _source(f), "family": _family(f),
                    "display_name": _display_name(f), "canonical_asset_id": member_to_asset.get(_rid(f)),
                    "evidence_tier": _p(f).get("evidence_tier"), "spatial_state": _p(f).get("spatial_state"),
                    "attributes": _a(f),
                })
        props = dict(_p(zone)); props["rank_v1"] = rank
        overlay.append({"type": "Feature", "geometry": zone["geometry"], "properties": props})
        dossiers.append({
            "rank_v1": rank, "zone_id": props["zone_id"], "baseline_score": props.get("score"),
            "v11_score": props.get("v11_score"), "v11_relevance": props.get("v11_relevance"),
            "sensitivity_state": props.get("sensitivity_state"), "rank_min": props.get("rank_min"),
            "rank_max": props.get("rank_max"), "rank_span": props.get("rank_span"),
            "bounds": list(zg.bounds), "score_components": props.get("v11_components"),
            "perturbations": props.get("perturbations"), "source_counts": dict(sorted(source_counts.items())),
            "target_evidence": target,
            "interpretive_boundary": "Evidence co-occurrence within a cell does not establish subsurface connectivity, identity, access, intent, or hidden use.",
        })
    return {"schema": "spiderweb.subsurface.top8_zone_evidence_pack.v1", "zones": dossiers}, {"type": "FeatureCollection", "features": overlay}


def write_pack(v11_path: str | Path, evidence_path: str | Path, assets_path: str | Path, out_dir: str | Path):
    v11 = json.loads(Path(v11_path).read_text(encoding="utf-8"))
    evidence = json.loads(Path(evidence_path).read_text(encoding="utf-8"))
    assets = json.loads(Path(assets_path).read_text(encoding="utf-8"))
    pack, overlay = build_top8_pack(v11, evidence, assets)
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    (out / "top8_evidence_pack.json").write_text(json.dumps(pack, indent=2, sort_keys=True), encoding="utf-8")
    (out / "top8_ranked.geojson").write_text(json.dumps(overlay, indent=2, sort_keys=True), encoding="utf-8")
    placemarks = []
    for feature in overlay["features"]:
        props = feature["properties"]
        summary = {k: props.get(k) for k in ("score", "v11_score", "v11_relevance", "sensitivity_state", "rank_min", "rank_max")}
        placemarks.append(f'<Placemark><name>{escape(props["zone_id"])}</name><description>{escape(json.dumps(summary, sort_keys=True))}</description>{_polygon_kml(shape(feature["geometry"]))}</Placemark>')
    kml = '<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>' + "".join(placemarks) + "</Document></kml>"
    kml_path = out / "top8_ranked.kml"; kml_path.write_text(kml, encoding="utf-8")
    kmz_path = out / "top8_ranked.kmz"
    with zipfile.ZipFile(kmz_path, "w", zipfile.ZIP_DEFLATED) as zf: zf.writestr("doc.kml", kml)
    zones = out / "zones"; zones.mkdir(exist_ok=True)
    for dossier in pack["zones"]:
        (zones / f'{dossier["zone_id"]}.json').write_text(json.dumps(dossier, indent=2, sort_keys=True), encoding="utf-8")
    return out / "top8_evidence_pack.json", out / "top8_ranked.geojson", kml_path, kmz_path

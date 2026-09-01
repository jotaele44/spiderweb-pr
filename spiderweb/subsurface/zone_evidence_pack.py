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


def _visual_by_zone(visual_morphology: dict | None) -> dict[str, list[dict]]:
    by_zone: dict[str, list[dict]] = {}
    if not visual_morphology:
        return by_zone
    for row in visual_morphology.get("assessments", []):
        zone_id = row.get("zone_id")
        if not zone_id:
            continue
        safe = dict(row)
        # Visual morphology is context/falsification only; it cannot affect score.
        safe["promotion_permitted"] = False
        by_zone.setdefault(str(zone_id), []).append(safe)
    return by_zone


def build_top8_pack(
    v11_geojson: dict,
    evidence_geojson: dict,
    canonical_assets: dict,
    visual_morphology: dict | None = None,
) -> tuple[dict, dict]:
    member_to_asset = {str(member): asset["canonical_id"] for asset in canonical_assets.get("assets", []) for member in asset.get("member_record_ids", [])}
    evidence = [f for f in evidence_geojson.get("features", []) if f.get("geometry") and _p(f).get("spatial_state") in {"FULLY_WITHIN", "PARTIAL"}]
    geoms = [shape(f["geometry"]) for f in evidence]
    tree = STRtree(geoms)
    elevated = [f for f in v11_geojson.get("features", []) if _p(f).get("relevance") == "MODERATE"]
    elevated.sort(key=lambda f: float(_p(f).get("score") or 0), reverse=True)
    visual_by_zone = _visual_by_zone(visual_morphology)
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
        zone_visual = visual_by_zone.get(str(_p(zone).get("zone_id")), [])
        props = dict(_p(zone)); props["rank_v1"] = rank
        props["visual_morphology_image_count"] = len(zone_visual)
        props["visual_morphology_score_effect"] = 0.0
        overlay.append({"type": "Feature", "geometry": zone["geometry"], "properties": props})
        dossiers.append({
            "rank_v1": rank, "zone_id": props["zone_id"], "baseline_score": props.get("score"),
            "v11_score": props.get("v11_score"), "v11_relevance": props.get("v11_relevance"),
            "sensitivity_state": props.get("sensitivity_state"), "rank_min": props.get("rank_min"),
            "rank_max": props.get("rank_max"), "rank_span": props.get("rank_span"),
            "bounds": list(zg.bounds), "score_components": props.get("v11_components"),
            "perturbations": props.get("perturbations"), "source_counts": dict(sorted(source_counts.items())),
            "target_evidence": target,
            "visual_morphology": zone_visual,
            "visual_morphology_summary": {
                "image_count": len(zone_visual),
                "classes": sorted({str(r.get("morphology_class")) for r in zone_visual if r.get("morphology_class")}),
                "visible_subsurface_indicator": (
                    "NONE_VISIBLE"
                    if zone_visual and all(r.get("visible_subsurface_indicator") in {"NONE_VISIBLE", "SURFACE_EXTRACTION_ONLY"} for r in zone_visual)
                    else "UNRESOLVED"
                ),
                "score_effect": 0.0,
            },
            "interpretive_boundary": "Evidence co-occurrence and satellite morphology within a cell do not establish subsurface connectivity, identity, access, intent, hidden use, or an underground facility.",
        })
    return {
        "schema": "spiderweb.subsurface.top8_zone_evidence_pack.v1.1",
        "visual_morphology_policy": "FALSIFICATION_CONTEXT_ONLY_NO_SCORE_PROMOTION",
        "zones": dossiers,
    }, {"type": "FeatureCollection", "features": overlay}


def write_pack(
    v11_path: str | Path,
    evidence_path: str | Path,
    assets_path: str | Path,
    out_dir: str | Path,
    visual_manifest_path: str | Path | None = None,
):
    v11 = json.loads(Path(v11_path).read_text(encoding="utf-8"))
    evidence = json.loads(Path(evidence_path).read_text(encoding="utf-8"))
    assets = json.loads(Path(assets_path).read_text(encoding="utf-8"))
    visual = json.loads(Path(visual_manifest_path).read_text(encoding="utf-8")) if visual_manifest_path else None
    pack, overlay = build_top8_pack(v11, evidence, assets, visual)
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    (out / "top8_evidence_pack.json").write_text(json.dumps(pack, indent=2, sort_keys=True), encoding="utf-8")
    (out / "top8_ranked.geojson").write_text(json.dumps(overlay, indent=2, sort_keys=True), encoding="utf-8")
    if visual is not None:
        (out / "visual_morphology_assessment.json").write_text(json.dumps(visual, indent=2, sort_keys=True), encoding="utf-8")
    placemarks = []
    for feature in overlay["features"]:
        props = feature["properties"]
        summary = {k: props.get(k) for k in ("score", "v11_score", "v11_relevance", "sensitivity_state", "rank_min", "rank_max", "visual_morphology_image_count")}
        placemarks.append(f'<Placemark><name>{escape(props["zone_id"])}</name><description>{escape(json.dumps(summary, sort_keys=True))}</description>{_polygon_kml(shape(feature["geometry"]))}</Placemark>')
    kml = '<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>' + "".join(placemarks) + "</Document></kml>"
    kml_path = out / "top8_ranked.kml"; kml_path.write_text(kml, encoding="utf-8")
    kmz_path = out / "top8_ranked.kmz"
    with zipfile.ZipFile(kmz_path, "w", zipfile.ZIP_DEFLATED) as zf: zf.writestr("doc.kml", kml)
    zones = out / "zones"; zones.mkdir(exist_ok=True)
    for dossier in pack["zones"]:
        (zones / f'{dossier["zone_id"]}.json').write_text(json.dumps(dossier, indent=2, sort_keys=True), encoding="utf-8")
    return out / "top8_evidence_pack.json", out / "top8_ranked.geojson", kml_path, kmz_path

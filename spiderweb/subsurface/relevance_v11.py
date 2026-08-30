"""Canonical-asset and sensitivity hardening for Santiago relevance model v1.1.

v1.1 preserves v1 scores and recomputes target groundwater/mine terms from the
canonical asset ledger. It also emits auxiliary-family perturbations and rank
stability. No proximity or current protected-military evidence is used.
"""
from __future__ import annotations

from collections import defaultdict
import csv
import json
import math
from pathlib import Path
from typing import Iterable

from shapely.geometry import shape
from shapely.strtree import STRtree

SCORING_FAMILIES = frozenset({
    "GEOLOGY_KARST_CAVES", "AQUIFERS_WELLS_SPRINGS", "MINES_QUARRIES_SHAFTS",
    "INDUSTRIAL_REMEDIATION", "UTILITIES_UNDERGROUND", "HISTORICAL_CORROBORATION",
})
GROUND_SOURCES = frozenset({"PRPB_WELLS_JCA_20", "PRPB_WELLS_AAA_21", "PRPB_SPRINGS_19", "USGS_MONITORING_LOCATIONS_PR"})
MINE_SOURCES = frozenset({"PRPB_QUARRIES_10", "USGS_USMIN_CONSOLIDATED_POINTS_17", "USGS_USMIN_EXPLICIT_OPENINGS_17", "USGS_USMIN_CONSOLIDATED_POLYGONS_18", "USGS_MRDS_HOSTED_0_PR_AOI"})
PERTURBATIONS = {
    "NO_UTILITY": frozenset({"UTILITIES_UNDERGROUND"}),
    "NO_HISTORY": frozenset({"HISTORICAL_CORROBORATION"}),
    "NO_INDUSTRIAL": frozenset({"INDUSTRIAL_REMEDIATION"}),
    "NO_UTILITY_HISTORY": frozenset({"UTILITIES_UNDERGROUND", "HISTORICAL_CORROBORATION"}),
    "NO_UTILITY_HISTORY_INDUSTRIAL": frozenset({"UTILITIES_UNDERGROUND", "HISTORICAL_CORROBORATION", "INDUSTRIAL_REMEDIATION"}),
}


def _p(f): return f.get("properties") or {}
def _a(f): return _p(f).get("attributes") or {}
def _source(f): return _p(f).get("source_id")
def _family(f): return _p(f).get("layer_family")
def _rid(f): return str(_p(f).get("record_id"))

def _ground(f):
    s = _source(f)
    if s in {"PRPB_WELLS_JCA_20", "PRPB_WELLS_AAA_21", "PRPB_SPRINGS_19"}: return True
    return s == "USGS_MONITORING_LOCATIONS_PR" and str(_a(f).get("site_type") or "").lower() in {"well", "spring", "multiple wells"}

def _mine(f): return _source(f) in MINE_SOURCES
def _cave(f): return _source(f) == "PRPB_CAVES_31"
def _history(f): return _source(f) == "USGS_TOPOVIEW_OVERLAY_0"
def _classify(score): return "HIGH" if score >= 7 else "MODERATE" if score >= 4 else "LOW" if score >= 1.5 else "VERY_LOW"


def _canonical_maps(assets: Iterable[dict]):
    member_to_asset, classes = {}, {}
    for asset in assets:
        classes[asset["canonical_id"]] = asset["asset_class"]
        for member in asset["member_record_ids"]:
            member_to_asset[str(member)] = asset["canonical_id"]
    return member_to_asset, classes


def _score(hits, member_to_asset, asset_classes, excluded=frozenset()):
    hits = [f for f in hits if _family(f) not in excluded]
    groundwater_assets, mine_assets = set(), set()
    groundwater_unbound = mine_unbound = 0
    for f in hits:
        if _ground(f):
            aid = member_to_asset.get(_rid(f))
            if aid and asset_classes.get(aid) == "GROUNDWATER_POINT": groundwater_assets.add(aid)
            else: groundwater_unbound += 1
        if _mine(f):
            aid = member_to_asset.get(_rid(f))
            if aid and asset_classes.get(aid) == "MINE_QUARRY_FEATURE": mine_assets.add(aid)
            else: mine_unbound += 1
    caves = sum(_cave(f) for f in hits)
    groundwater = len(groundwater_assets) + groundwater_unbound
    mines = len(mine_assets) + mine_unbound
    industrial = sum(_family(f) == "INDUSTRIAL_REMEDIATION" for f in hits)
    utilities = sum(_family(f) == "UTILITIES_UNDERGROUND" for f in hits)
    history = sum(_history(f) for f in hits)
    sources = {_source(f) for f in hits if _source(f)}
    parts = {
        "cave": min(3.0, caves * 3.0),
        "groundwater": min(2.5, math.log1p(groundwater) * 0.75),
        "mine_quarry": min(2.0, math.log1p(mines) * 0.9),
        "industrial": min(0.75, math.log1p(industrial) * 0.25),
        "utility": min(0.50, math.log1p(utilities) * 0.08),
        "history": min(0.25, math.log1p(history) * 0.05),
        "diversity": min(1.0, (len(sources) - 2) * 0.15) if len(sources) >= 3 else 0.0,
    }
    return {
        "score": round(min(10.0, sum(parts.values())), 3),
        "groundwater_assets": groundwater,
        "mine_quarry_assets": mines,
        "parts": {k: round(v, 3) for k, v in parts.items()},
    }


def harden_relevance(v1_geojson: dict, evidence_geojson: dict, canonical_assets: dict) -> dict:
    member_to_asset, asset_classes = _canonical_maps(canonical_assets.get("assets", []))
    evidence = [f for f in evidence_geojson.get("features", []) if f.get("geometry") and _family(f) in SCORING_FAMILIES and _p(f).get("spatial_state") in {"FULLY_WITHIN", "PARTIAL"}]
    geoms = [shape(f["geometry"]) for f in evidence]
    tree = STRtree(geoms)
    out = []
    for zone in v1_geojson.get("features", []):
        zg = shape(zone["geometry"])
        hits = [evidence[int(i)] for i in tree.query(zg, predicate="intersects")]
        base = _score(hits, member_to_asset, asset_classes)
        perturb = {name: _score(hits, member_to_asset, asset_classes, excluded)["score"] for name, excluded in PERTURBATIONS.items()}
        props = dict(zone.get("properties") or {})
        old_class = props.get("relevance")
        new_class = _classify(base["score"])
        if old_class == "MODERATE":
            core = (base["score"], perturb["NO_UTILITY_HISTORY"], perturb["NO_UTILITY_HISTORY_INDUSTRIAL"])
            if new_class not in {"MODERATE", "HIGH"}: sensitivity = "PROVISIONAL"
            elif all(v >= 4 for v in core): sensitivity = "ROBUST" if props.get("evidence_tier") == "DIRECT" else "SEMI_ROBUST"
            else: sensitivity = "THRESHOLD"
        else: sensitivity = "BASELINE"
        props.update({
            "v11_score": base["score"], "v11_relevance": new_class,
            "score_delta": round(base["score"] - float(props.get("score") or 0), 3),
            "sensitivity_state": sensitivity,
            "canonical_groundwater_assets": base["groundwater_assets"],
            "canonical_mine_quarry_assets": base["mine_quarry_assets"],
            "v11_components": base["parts"], "perturbations": perturb,
        })
        out.append({"type": "Feature", "geometry": zone["geometry"], "properties": props})

    scenarios = ["v11_score", *PERTURBATIONS]
    ranks = defaultdict(dict)
    for scenario in scenarios:
        scored = []
        for feature in out:
            props = feature["properties"]
            value = props["v11_score"] if scenario == "v11_score" else props["perturbations"][scenario]
            scored.append((value, props["zone_id"]))
        for rank, (_, zone_id) in enumerate(sorted(scored, reverse=True), 1): ranks[zone_id][scenario] = rank
    for feature in out:
        props = feature["properties"]
        rr = ranks[props["zone_id"]]
        props.update({"ranks": rr, "rank_min": min(rr.values()), "rank_max": max(rr.values()), "rank_span": max(rr.values()) - min(rr.values())})
    return {"type": "FeatureCollection", "features": out, "metadata": {"model": "SANTIAGO_SUBSURFACE_RELEVANCE_MODEL_v1_1", "parent": "v1", "canonical_asset_scoring": True, "military_family_excluded": True, "connectivity_inference": "PROHIBITED"}}


def write_transition_csv(path: str | Path, hardened: dict) -> Path:
    out = Path(path); out.parent.mkdir(parents=True, exist_ok=True)
    fields = ["zone_id", "score", "relevance", "v11_score", "v11_relevance", "score_delta", "sensitivity_state", "rank_min", "rank_max", "rank_span"]
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields); writer.writeheader()
        for feature in hardened.get("features", []):
            p = feature["properties"]; writer.writerow({k: p.get(k) for k in fields})
    return out


def run(v1_path: str | Path, evidence_path: str | Path, assets_path: str | Path, out_dir: str | Path) -> tuple[Path, Path]:
    v1 = json.loads(Path(v1_path).read_text(encoding="utf-8"))
    evidence = json.loads(Path(evidence_path).read_text(encoding="utf-8"))
    assets = json.loads(Path(assets_path).read_text(encoding="utf-8"))
    hardened = harden_relevance(v1, evidence, assets)
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    geo = out / "relevance_zones_v11.geojson"
    geo.write_text(json.dumps(hardened, indent=2, sort_keys=True), encoding="utf-8")
    csv_path = write_transition_csv(out / "zone_transition_matrix.csv", hardened)
    return geo, csv_path

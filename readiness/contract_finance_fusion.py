"""Fuse Contract-Finance scores with SpiderWeb airspace/ILAP overlays.

The fusion is conservative: it preserves the original airspace candidate fields
and adds contract-finance context only when spatial proximity or municipality
keys support it.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any

FUSED_OVERLAY = "spiderweb_fused_contract_finance_overlay.geojson"
FUSION_REPORT = "contract_finance_fusion_report.json"
DEFAULT_DISTANCE_DEG = 0.045  # approx. 5 km at Puerto Rico latitudes


class ContractFinanceFusionError(ValueError):
    """Raised when fusion inputs cannot be loaded safely."""


def _load_fc(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContractFinanceFusionError(f"missing required file: {path.name}") from exc
    except json.JSONDecodeError as exc:
        raise ContractFinanceFusionError(f"invalid JSON in {path.name}: {exc}") from exc
    if payload.get("type") != "FeatureCollection":
        raise ContractFinanceFusionError(f"{path.name} must be a GeoJSON FeatureCollection")
    return [f for f in payload.get("features", []) if isinstance(f, dict)]


def _coords(feature: dict[str, Any]) -> tuple[float, float] | None:
    geom = feature.get("geometry") or {}
    if geom.get("type") != "Point":
        return None
    coords = geom.get("coordinates")
    if not isinstance(coords, list) or len(coords) < 2:
        return None
    try:
        lon = float(coords[0])
        lat = float(coords[1])
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(lat) and math.isfinite(lon)):
        return None
    return lat, lon


def _distance_deg(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _safe_score(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, result)) if math.isfinite(result) else 0.0


def _base_candidate_score(props: dict[str, Any]) -> float:
    for key in ("spiderweb_score", "confidence", "overall_confidence", "corridor_alignment_score"):
        if key in props:
            return _safe_score(props.get(key))
    tier = str(props.get("evidence_tier") or "").upper()
    return {"T1": 0.85, "T2": 0.65, "T3": 0.45, "T4": 0.20}.get(tier, 0.0)


def _tier(score: float) -> str:
    if score >= 0.75:
        return "T1"
    if score >= 0.55:
        return "T2"
    if score >= 0.35:
        return "T3"
    return "T4"


def _index_contract_features(contract_features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed = []
    for feature in contract_features:
        props = feature.get("properties") or {}
        xy = _coords(feature)
        indexed.append({
            "feature": feature,
            "props": props,
            "coords": xy,
            "score": _safe_score(props.get("spiderweb_score")),
            "municipality_code": props.get("municipality_code"),
            "municipality_name": props.get("municipality_name"),
            "record_id": props.get("record_id"),
        })
    return indexed


def _best_contract_match(candidate: dict[str, Any], contracts: list[dict[str, Any]], max_distance_deg: float) -> dict[str, Any] | None:
    props = candidate.get("properties") or {}
    cand_xy = _coords(candidate)
    cand_code = props.get("municipality_code")
    cand_muni = props.get("municipality_name")
    best = None
    best_strength = -1.0
    for item in contracts:
        proximity = 0.0
        relation = None
        if cand_xy and item["coords"]:
            d = _distance_deg(cand_xy, item["coords"])
            if d <= max_distance_deg:
                proximity = max(0.0, 1.0 - (d / max_distance_deg))
                relation = "point_proximity"
        if proximity == 0.0 and cand_code and cand_code == item.get("municipality_code"):
            proximity = 0.65
            relation = "municipality_code"
        if proximity == 0.0 and cand_muni and cand_muni == item.get("municipality_name"):
            proximity = 0.50
            relation = "municipality_name"
        if proximity == 0.0:
            continue
        strength = proximity * item["score"]
        if strength > best_strength:
            best_strength = strength
            best = {
                "contract_record_id": item.get("record_id"),
                "contract_score": item["score"],
                "match_relation": relation,
                "match_strength": round(strength, 4),
                "contract_municipality_code": item.get("municipality_code"),
                "contract_municipality_name": item.get("municipality_name"),
            }
    return best


def fuse_contract_finance_scores(
    airspace_overlay: str | Path,
    contract_finance_overlay: str | Path,
    output_dir: str | Path,
    *,
    max_distance_deg: float = DEFAULT_DISTANCE_DEG,
) -> dict[str, Any]:
    """Fuse contract-finance scored features into an airspace/ILAP overlay."""

    airspace_path = Path(airspace_overlay)
    contract_path = Path(contract_finance_overlay)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    candidates = _load_fc(airspace_path)
    contracts = _index_contract_features(_load_fc(contract_path))
    fused: list[dict[str, Any]] = []
    matched = 0

    for candidate in candidates:
        props = dict(candidate.get("properties") or {})
        base_score = _base_candidate_score(props)
        match = _best_contract_match(candidate, contracts, max_distance_deg)
        contract_boost = 0.0
        if match:
            matched += 1
            contract_boost = 0.25 * match["match_strength"]
            props["contract_finance_match"] = match
        else:
            props["contract_finance_match"] = None
        fused_score = round(min(1.0, base_score + contract_boost), 4)
        props.update({
            "base_spiderweb_score": base_score,
            "contract_finance_boost": round(contract_boost, 4),
            "fused_spiderweb_score": fused_score,
            "fused_evidence_tier": _tier(fused_score),
        })
        fused.append({"type": "Feature", "geometry": candidate.get("geometry"), "properties": props})

    fused.sort(key=lambda f: (-_safe_score((f.get("properties") or {}).get("fused_spiderweb_score")), str((f.get("properties") or {}).get("candidate_type"))))
    overlay = {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4326"}},
        "features": fused,
    }
    (out / FUSED_OVERLAY).write_text(json.dumps(overlay, indent=2, sort_keys=True), encoding="utf-8")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "airspace_overlay": str(airspace_path),
        "contract_finance_overlay": str(contract_path),
        "candidate_count": len(candidates),
        "contract_feature_count": len(contracts),
        "matched_candidates": matched,
        "match_rate": round(matched / len(candidates), 4) if candidates else 0.0,
        "by_fused_tier": dict(sorted(Counter((f.get("properties") or {}).get("fused_evidence_tier", "UNKNOWN") for f in fused).items())),
        "outputs": {"fused_overlay": FUSED_OVERLAY, "fusion_report": FUSION_REPORT},
    }
    (out / FUSION_REPORT).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report

"""Calibration utilities for the SpiderWeb contract/finance layer.

The calibration report is intentionally data-profile based: it can run on real
Contract-Sweeper adapter outputs without changing score formulas at runtime.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import csv
import json
import math
from pathlib import Path
from typing import Any

from readiness.contract_finance_layer import ContractFinanceLayerError


CALIBRATION_REPORT = "contract_finance_calibration_report.json"


def _load_geojson_features(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContractFinanceLayerError(f"missing required file: {path.name}") from exc
    if payload.get("type") != "FeatureCollection":
        raise ContractFinanceLayerError(f"{path.name} is not a FeatureCollection")
    return [f for f in payload.get("features", []) if isinstance(f, dict)]


def _safe_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    pos = (len(values) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return round(values[lo], 4)
    return round(values[lo] * (hi - pos) + values[hi] * (pos - lo), 4)


def _amount_profile(features: list[dict[str, Any]]) -> dict[str, Any]:
    values: list[float] = []
    for feature in features:
        amount = _safe_float((feature.get("properties") or {}).get("amount"))
        if amount is not None:
            values.append(amount)
    nonzero = [v for v in values if v > 0]
    return {
        "count": len(values),
        "nonzero_count": len(nonzero),
        "sum": round(sum(values), 4),
        "p50_nonzero": _quantile(nonzero, 0.50),
        "p90_nonzero": _quantile(nonzero, 0.90),
        "p95_nonzero": _quantile(nonzero, 0.95),
        "p99_nonzero": _quantile(nonzero, 0.99),
        "max": round(max(values), 4) if values else None,
    }


def _coverage(features: list[dict[str, Any]], predicate) -> float:
    return round(sum(1 for feature in features if predicate(feature)) / len(features), 4) if features else 0.0


def calibrate_contract_finance_layer(input_dir: str | Path, output_path: str | Path | None = None) -> dict[str, Any]:
    """Profile adapter/layer outputs and produce calibration recommendations."""

    root = Path(input_dir)
    awards = _load_geojson_features(root / "contract_awards.geojson")
    flows = _load_geojson_features(root / "financial_flows.geojson")
    features = [*awards, *flows]

    scored_path = root / "contract_finance_scored_overlay.geojson"
    scored_features = _load_geojson_features(scored_path) if scored_path.exists() else []

    entity_counts: Counter[str] = Counter()
    municipality_amounts: dict[str, float] = defaultdict(float)
    feature_type_counts: Counter[str] = Counter()
    score_values: list[float] = []
    tier_counts: Counter[str] = Counter()

    for feature in features:
        props = feature.get("properties") or {}
        entity_id = props.get("entity_id")
        if entity_id:
            entity_counts[str(entity_id)] += 1
        code = str(props.get("municipality_code") or "UNKNOWN")
        municipality_amounts[code] += _safe_float(props.get("amount")) or 0.0
        feature_type_counts[str(props.get("feature_type") or "unknown")] += 1

    for feature in scored_features:
        props = feature.get("properties") or {}
        score = _safe_float(props.get("spiderweb_score"))
        if score is not None:
            score_values.append(score)
        tier_counts[str(props.get("evidence_tier") or "UNKNOWN")] += 1

    point_cov = _coverage(
        features,
        lambda f: isinstance(f.get("geometry"), dict)
        and f["geometry"].get("type") == "Point"
        and isinstance(f["geometry"].get("coordinates"), list),
    )
    muni_cov = _coverage(features, lambda f: bool((f.get("properties") or {}).get("municipality_code") or (f.get("properties") or {}).get("municipality_name")))
    entity_cov = _coverage(features, lambda f: bool((f.get("properties") or {}).get("entity_id")))
    lineage_cov = _coverage(features, lambda f: bool((f.get("properties") or {}).get("lineage")))

    recommendations: list[dict[str, Any]] = []
    if point_cov < 0.05:
        recommendations.append({
            "code": "LOW_POINT_GEOMETRY",
            "action": "Use municipality/entity-density calibration until geocoded contract points are available.",
            "value": point_cov,
        })
    if muni_cov < 0.25:
        recommendations.append({
            "code": "LOW_MUNICIPALITY_COVERAGE",
            "action": "Block production fusion unless municipality_code or municipality_name coverage improves.",
            "value": muni_cov,
        })
    if lineage_cov < 0.25:
        recommendations.append({
            "code": "LOW_LINEAGE_COVERAGE",
            "action": "Treat outputs as analysis-grade only; preserve source_hash/source_id in upstream package.",
            "value": lineage_cov,
        })

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_dir": str(root),
        "records": {
            "contract_awards": len(awards),
            "financial_flows": len(flows),
            "combined_money_features": len(features),
            "scored_features": len(scored_features),
        },
        "coverage": {
            "point_geometry": point_cov,
            "municipality": muni_cov,
            "entity_id": entity_cov,
            "lineage": lineage_cov,
        },
        "amount_profile": _amount_profile(features),
        "score_profile": {
            "count": len(score_values),
            "p50": _quantile(score_values, 0.50),
            "p90": _quantile(score_values, 0.90),
            "p95": _quantile(score_values, 0.95),
            "max": round(max(score_values), 4) if score_values else None,
        },
        "counts": {
            "by_feature_type": dict(sorted(feature_type_counts.items())),
            "by_evidence_tier": dict(sorted(tier_counts.items())),
            "top_entities_by_record_count": entity_counts.most_common(20),
            "top_municipalities_by_amount": sorted(municipality_amounts.items(), key=lambda kv: kv[1], reverse=True)[:20],
        },
        "recommendations": recommendations,
    }
    target = Path(output_path) if output_path else root / CALIBRATION_REPORT
    target.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report

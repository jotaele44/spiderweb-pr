"""Production readiness gate for Contract-Sweeper packages.

This gate runs at the SpiderWeb consumer boundary. It validates that a
Contract-Sweeper export package is production-safe before adapter ingestion and
engine scoring. It does not import Contract-Sweeper.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from federation.hub.adapters.contract_sweeper import (
    ContractSweeperAdapterError,
    load_contract_sweeper_package,
    location_point,
)


@dataclass(frozen=True)
class PackageGateThresholds:
    min_entities: int = 1
    min_sources: int = 1
    min_money_rows: int = 1
    min_location_object_coverage: float = 0.50
    min_municipality_coverage: float = 0.25
    warn_point_geometry_coverage: float = 0.05
    min_lineage_coverage: float = 0.25


class ContractSweeperPackageGateError(ValueError):
    """Raised when the gate cannot read or write its report."""


def _coverage(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0.0


def _has_location(row: dict[str, Any]) -> bool:
    return isinstance(row.get("location"), dict) and bool(row["location"])


def _has_municipality(row: dict[str, Any]) -> bool:
    loc = row.get("location") if isinstance(row.get("location"), dict) else {}
    return bool(loc.get("municipality_code") or loc.get("municipality_name"))


def _has_point(row: dict[str, Any]) -> bool:
    return location_point(row.get("location")) is not None


def _has_lineage(row: dict[str, Any]) -> bool:
    lineage = row.get("lineage")
    return isinstance(lineage, dict) and bool(lineage)


def assess_contract_sweeper_package(
    package_dir: str | Path,
    output_path: str | Path | None = None,
    *,
    thresholds: PackageGateThresholds | None = None,
) -> dict[str, Any]:
    """Assess a Contract-Sweeper package and optionally write a gate report."""

    thresholds = thresholds or PackageGateThresholds()
    package_dir = Path(package_dir)
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    try:
        package = load_contract_sweeper_package(package_dir, mode="production")
    except ContractSweeperAdapterError as exc:
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "package_dir": str(package_dir),
            "status": "NOT_READY",
            "blockers": [{"gate": "adapter_validation", "detail": str(exc)}],
            "warnings": [],
            "metrics": {},
        }
        if output_path:
            Path(output_path).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        return report

    streams = package.streams
    awards = streams.get("funding_awards", [])
    transactions = streams.get("transactions", [])
    money_rows = [*awards, *transactions]
    total_money = len(money_rows)

    metrics = {
        "entities": len(streams.get("entities", [])),
        "sources": len(streams.get("sources", [])),
        "funding_awards": len(awards),
        "transactions": len(transactions),
        "money_rows": total_money,
        "location_object_coverage": _coverage(sum(_has_location(r) for r in money_rows), total_money),
        "municipality_coverage": _coverage(sum(_has_municipality(r) for r in money_rows), total_money),
        "point_geometry_coverage": _coverage(sum(_has_point(r) for r in money_rows), total_money),
        "lineage_coverage": _coverage(sum(_has_lineage(r) for r in money_rows), total_money),
    }

    def block(gate: str, detail: str, value: Any, expected: Any) -> None:
        blockers.append({"gate": gate, "detail": detail, "value": value, "expected": expected})

    def warn(gate: str, detail: str, value: Any, expected: Any) -> None:
        warnings.append({"gate": gate, "detail": detail, "value": value, "expected": expected})

    if metrics["entities"] < thresholds.min_entities:
        block("min_entities", "Package has too few resolved entities", metrics["entities"], thresholds.min_entities)
    if metrics["sources"] < thresholds.min_sources:
        block("min_sources", "Package has too few sources", metrics["sources"], thresholds.min_sources)
    if metrics["money_rows"] < thresholds.min_money_rows:
        block("min_money_rows", "Package has too few award/transaction rows", metrics["money_rows"], thresholds.min_money_rows)
    if metrics["location_object_coverage"] < thresholds.min_location_object_coverage:
        block("location_object_coverage", "Too few money rows carry v1.1 location objects", metrics["location_object_coverage"], thresholds.min_location_object_coverage)
    if metrics["municipality_coverage"] < thresholds.min_municipality_coverage:
        block("municipality_coverage", "Too few money rows carry municipality location keys", metrics["municipality_coverage"], thresholds.min_municipality_coverage)
    if metrics["lineage_coverage"] < thresholds.min_lineage_coverage:
        block("lineage_coverage", "Too few money rows preserve source lineage", metrics["lineage_coverage"], thresholds.min_lineage_coverage)
    if metrics["point_geometry_coverage"] < thresholds.warn_point_geometry_coverage:
        warn("point_geometry_coverage", "Point geometry coverage is low; downstream scoring will rely on municipality/entity density", metrics["point_geometry_coverage"], thresholds.warn_point_geometry_coverage)

    status = "NOT_READY" if blockers else ("DEGRADED" if warnings else "READY")
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "package_dir": str(package_dir),
        "producer": package.producer,
        "export_contract_version": package.version,
        "status": status,
        "metrics": metrics,
        "blockers": blockers,
        "warnings": warnings,
    }
    if output_path:
        Path(output_path).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report

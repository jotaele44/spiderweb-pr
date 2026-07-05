"""Adapter hooks for Head Start contextual enrichment.

Spiderweb remains a spatial producer. Cross-producer correlation should be
performed by the Hub or by source-owning repos. These hooks preserve explicit
fields for later hydro, utility, corridor, heli, project, and ILAP joins without
turning the civic layer into a detector.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class HeadStartContext:
    hydro_region: str | None = None
    utility_overlap: str | None = None
    corridor_distance_m: float | None = None
    heli_proximity_m: float | None = None
    project_overlap: str | None = None
    ilap_context_distance_m: float | None = None
    enrichment_status: str = "pending_external_layers"

    def to_dict(self) -> dict:
        return asdict(self)


class HeadStartContextEnricher:
    """Null-safe enrichment adapter until external layers are mounted."""

    required_external_layers = (
        "hydro",
        "utility",
        "corridor",
        "heli",
        "project",
        "ilap_context",
    )

    def enrich_record(self, record: dict) -> dict:
        enriched = dict(record)
        enriched.update(HeadStartContext().to_dict())
        return enriched

    def readiness(self, available_layers: set[str] | None = None) -> dict:
        available_layers = available_layers or set()
        missing = [layer for layer in self.required_external_layers if layer not in available_layers]
        return {
            "status": "ready" if not missing else "degraded_pending_external_layers",
            "missing_layers": missing,
            "policy": "context_only_no_anomaly_scoring",
        }

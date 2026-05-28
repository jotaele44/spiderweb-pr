"""SpiderWeb federation layer registry.

The registry records downstream consumer layers that can be activated from
validated producer packages. Entries are deliberately declarative so external
producer repos remain decoupled from SpiderWeb internals.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class LayerRegistryEntry:
    """Declarative metadata for a SpiderWeb evidence/feature layer."""

    layer_id: str
    producer: str
    export_contract_version: str
    adapter_module: str
    engine_module: str
    input_artifacts: tuple[str, ...]
    output_artifacts: tuple[str, ...]
    score_features: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


CONTRACT_FINANCE_LAYER = LayerRegistryEntry(
    layer_id="contract_finance",
    producer="contract-sweeper",
    export_contract_version="1.1.0",
    adapter_module="federation.hub.adapters.contract_sweeper",
    engine_module="readiness.contract_finance_layer",
    input_artifacts=(
        "contract_awards.geojson",
        "financial_flows.geojson",
        "municipality_funding_density.csv",
        "entity_graph.graphml",
        "contract_finance_ingest_report.json",
    ),
    output_artifacts=(
        "contract_finance_scored_overlay.geojson",
        "contract_finance_layer_report.json",
    ),
    score_features=(
        "entity_convergence",
        "municipal_density",
        "temporal_funding_pulse",
    ),
)


LAYER_REGISTRY: dict[str, LayerRegistryEntry] = {
    CONTRACT_FINANCE_LAYER.layer_id: CONTRACT_FINANCE_LAYER,
}


def get_layer_entry(layer_id: str) -> LayerRegistryEntry:
    """Return a registered layer entry or raise KeyError."""

    return LAYER_REGISTRY[layer_id]
